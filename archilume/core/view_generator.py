# Archilume imports
from archilume.utils import (
    calc_centroid_of_points,
    calculate_dimensions_from_points,
    get_center_of_bounding_box,
    get_bounding_box_from_point_coordinates,
)
from archilume import config, utils

# Standard library imports
import logging
import multiprocessing
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

# Third-party imports
import pandas as pd

# CSV parsing constants
REQUIRED_COORDINATE_COLUMNS = ["x_coords", "y_coords", "z_coords"]
COORDINATE_PATTERN = r"X_(-?\d+\.?\d*)\s+Y_(-?\d+\.?\d*)\s+Z_(-?\d+\.?\d*)"

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)

@dataclass
class ViewGenerator:
    """
    Generates Radiance view files and AOI files from room boundary data for daylight analysis.
    
    This class processes CSV data containing room boundary coordinates to create:
    1. Area of Interest (AOI) files for each room containing boundary points and metadata
    2. Radiance view parameter files (.vp) for floor plan rendering at each building level
    
    The workflow involves parsing coordinate strings from CSV, calculating building geometry,
    and generating the necessary files for Radiance daylight simulations.
    
    Attributes:
        room_boundaries_csv_path: Path to input CSV file with room boundary coordinates
        ffl_offset: Height above finished floor level for camera positioning (meters)
        processed_room_boundaries_csv_path: Path to processed/cleaned CSV output
        view_file_dir: Directory for generated view files (outputs/views_grids/)
        aoi_dir: Directory for generated AOI files (outputs/aoi/)
        room_boundaries_df: Parsed DataFrame with coordinate data
        bounding_box_coordinates: 3D bounding box of all room boundaries
        x_coord_center, y_coord_center, z_coord_center: Building center coordinates
        view_horizontal, view_vertical: View dimensions for proper framing
        view_paths_per_level_df: DataFrame mapping floor levels to view file paths
    
    Example:
        >>> from pathlib import Path
        >>> csv_path = Path("inputs/room_boundaries.csv")
        >>> generator = ViewGenerator(
        ...     room_boundaries_csv_path=csv_path,
        ...     ffl_offset=1.2  # Camera height above floor level
        ... )
        >>> generator.create_aoi_files()  # Generate AOI files first
        >>> generator.create_view_files()  # Then generate view files
        
    Input CSV Format:
        The CSV should contain columns for apartment_no, room, and coordinate strings
        in the format "X_123.45 Y_678.90 Z_012.34" where coordinates are in millimeters.
        Multiple coordinate columns per row are supported and will be processed.
                                      
    Generated Files:
        - AOI files (.aoi): One per room in outputs/aoi/ directory
          Contains room metadata, centroid, associated view file, and boundary points
        - View files (.vp): One per floor level in outputs/views_grids/ directory  
          Contains Radiance camera parameters for top-down orthographic floor views
    
    Notes:
        - Coordinates are automatically converted from millimeters to meters
        - Files are automatically organized by floor level based on Z coordinates
        - Output directories are created automatically if they don't exist
        - Requires valid room boundary data for proper functioning
    """

    # required inputs
    ffl_offset: float

    # Required - directories where view and AOI files will be written
    view_file_dir: Path
    aoi_dir: Path

    # Room-boundary source - provide exactly one of these
    room_boundaries_csv_path: Path | None = None
    aoi_inputs_dir: Path | None = None

    # Fixed - not user configurable but accessible from instance.
    # All geometry fields are populated in __post_init__ via _compute_view_geometry().
    processed_room_boundaries_csv_path: Path        = field(init=False)
    room_boundaries_df: pd.DataFrame                = field(init=False)
    bounding_box_coordinates: Any                   = field(init=False)
    x_coord_center: float                           = field(init=False)
    y_coord_center: float                           = field(init=False)
    z_coord_center: float                           = field(init=False)
    view_horizontal: float                          = field(init=False)
    view_vertical: float                            = field(init=False)
    view_paths_per_level_df: pd.DataFrame | None    = field(init=False, default=None)

    def __post_init__(self):
        """
        Initialize the ViewGenerator after dataclass construction.
        
        Performs post-initialization setup by:
        1. Creating output directories for AOI and view files if they don't exist
        2. Automatically parsing and processing the input CSV file
        
        This method is called automatically after the dataclass is instantiated.
        All file processing and validation happens here to ensure the instance
        is ready for AOI and view file generation.
        
        Raises:
            Various exceptions may be logged if CSV parsing fails, but the method
            completes execution to allow the instance to be created.
        """

        # Exactly one of (CSV, aoi dir) must be provided
        if (self.room_boundaries_csv_path is None) == (self.aoi_inputs_dir is None):
            print("\nError: provide exactly one of room_boundaries_csv_path or aoi_inputs_dir")
            sys.exit(1)

        if self.room_boundaries_csv_path is not None and not self.room_boundaries_csv_path.exists():
            print(f"\nError: Room boundaries CSV not found at {self.room_boundaries_csv_path}")
            sys.exit(1)

        if self.aoi_inputs_dir is not None and not self.aoi_inputs_dir.exists():
            print(f"\nError: AOI inputs directory not found at {self.aoi_inputs_dir}")
            sys.exit(1)

        # Default ffl_offset to 0.01m if zero or negative
        if self.ffl_offset <= 0:
            self.ffl_offset = 0.01

        # Create the output directory if it doesn't exist
        os.makedirs(self.aoi_dir, exist_ok=True)
        os.makedirs(self.view_file_dir, exist_ok=True)

        # Build the processed long-format DataFrame from whichever source was given
        if self.aoi_inputs_dir is not None:
            self.__parse_aoi_inputs_dir()
        else:
            self.__parse_room_boundaries_csv()

        # Compute building geometry (bbox, centre, view dimensions) eagerly so
        # downstream consumers see non-Optional values.
        self._compute_view_geometry()

    def _compute_view_geometry(self) -> None:
        """Load processed CSV and derive bounding box, centre, and view dimensions.

        Raises:
            ValueError: if the processed CSV is empty, missing coordinate columns,
                contains no valid points, or geometry helpers return None.
        """
        df = pd.read_csv(self.processed_room_boundaries_csv_path)
        if df.empty:
            raise ValueError(
                f"Processed room boundaries CSV is empty: {self.processed_room_boundaries_csv_path}"
            )

        missing = [c for c in REQUIRED_COORDINATE_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"Processed CSV missing required coordinate columns {missing}: "
                f"{self.processed_room_boundaries_csv_path}"
            )

        points_df = df[REQUIRED_COORDINATE_COLUMNS].dropna()
        if points_df.empty:
            raise ValueError(
                f"No valid coordinate points in {self.processed_room_boundaries_csv_path}"
            )

        bbox = get_bounding_box_from_point_coordinates(points_df)
        center = get_center_of_bounding_box(bbox) if bbox is not None else None
        dimensions = calculate_dimensions_from_points(bbox) if bbox is not None else None
        if bbox is None or center is None or dimensions is None:
            raise ValueError(
                f"Failed to compute building geometry from {self.processed_room_boundaries_csv_path}"
            )

        self.room_boundaries_df = df
        self.bounding_box_coordinates = bbox
        self.x_coord_center, self.y_coord_center, self.z_coord_center = [round(c, 3) for c in center]
        self.view_horizontal, self.view_vertical = [round(d, 3) for d in dimensions]
        print(f"Centre coordinates: ({self.x_coord_center}, {self.y_coord_center}, {self.z_coord_center})")

    @property
    def view_files(self) -> list[Path]:
        """Return sorted list of generated .vp view files."""
        return sorted(self.view_file_dir.glob("*.vp"))

    def create_plan_view_files(self) -> bool:
        """
        Generate Radiance view parameter files for each floor level.

        Creates .vp view files containing camera parameters for top-down orthographic
        rendering of building floor plans. Each file represents a different floor level
        with camera positioning optimized for architectural visualization.

        Processing Workflow:
            1. Maps floor levels to view file paths using floor level information
            2. Generates individual view parameter files for each floor level
            3. Populates each file with complete Radiance view parameters

        Geometric inputs (bbox, centre, view dimensions) are computed eagerly
        in __post_init__ via _compute_view_geometry().

        Camera heights: Floor level + ffl_offset for each level.

        Generated View Files:
            - Location: outputs/views_grids/ directory
            - Naming: plan_ffl_{millimeters}.vp (e.g., plan_ffl_90000.vp for 90.0m, plan_ffl_103180.vp for 103.18m)
            - Content: Complete Radiance view parameter string for each floor
            - Camera setup: Top-down orthographic view from building center

        View Parameters Generated:
            - Camera position: Building center (X,Y) at floor level + offset (Z)
            - View direction: Straight down (0, 0, -1) for floor plan view
            - View angles: Based on building dimensions for proper framing
            - Up vector: North direction (0, 1, 0) for consistent orientation

        Returns:
            bool: True if all view files generated successfully, False if any
                 validation fails, data is missing, or file creation errors occur

        Instance Attributes Set:
            - view_paths_per_level_df: Floor level to view file mapping

        Side Effects:
            - Creates view files in view_file_dir
            - Prints diagnostic information during processing
        """

        self.view_paths_per_level_df = self.__create_floor_level_info(
            self.room_boundaries_df, self.view_file_dir, self.ffl_offset
        )

        if self.view_paths_per_level_df is None:
            return False

        print("\n--- printing view files df ---\n", self.view_paths_per_level_df.to_string())

        # --- Generate all plan view files ---
        # Iterate through each floor level to create view files
        for _, row in self.view_paths_per_level_df.iterrows():
            # Extract data from the current row
            file_path = row['view_file_path']
            z_coordinate = row['ffl_z_coord_with_offset']

            try:
                # Extract the directory path from the file path
                dir_path = os.path.dirname(file_path)

                # Create the directory if it doesn't exist
                os.makedirs(dir_path, exist_ok=True)

                # Create the empty file
                with open(file_path, "w") as fp:
                    pass
                print(f"Successfully created: {file_path}")

                # populate plan view files
                try:
                    view_file_path_obj = Path(file_path)
                    view_file_path_obj.parent.mkdir(parents=True, exist_ok=True)
                    view_content = [
                        "rvu",
                        "-vtl",
                        "-vp",
                        f"{self.x_coord_center:.2f}",
                        f"{self.y_coord_center:.2f}",
                        f"{z_coordinate:.2f}",
                        "-vd",
                        "0",
                        "0",
                        "-1",
                        "-vu",
                        "0",
                        "1",
                        "0",
                        "-vh",
                        f"{self.view_horizontal:.2f}",
                        "-vv",
                        f"{self.view_vertical:.2f}",
                        "-vo",
                        "0",
                        "-va",
                        "0",
                        "-vs",
                        "0",
                        "-vl",
                        "0",
                    ]
                    view_content_str = " ".join(view_content)
                    with open(view_file_path_obj, "w") as vf:
                        vf.write(view_content_str)
                    logging.debug(
                        f"Successfully created view file: {file_path}"
                    )  # Changed to debug for less verbosity if many files
                except Exception as e:
                    logging.error(f"Error creating view file at {file_path}: {e}")

            except Exception as e:
                print(f"Error creating {file_path}: {e}")

        return True  # Indicate success

    def create_aoi_files(self, coordinate_map: "utils.PixelToWorldMap | None" = None) -> bool:
        """Generate AOI files for each room with boundary points and metadata.

        Args:
            coordinate_map: Optional in-memory PixelToWorldMap. If provided, adds
                pixel coordinates to each boundary point.

        Returns:
            bool: True if successful, False if processed CSV not found.

        Output format per file:
            - Headers: room info, view file, floor level, centroid
            - Data: boundary points as "x.xxxx y.yyyy [pixel_x pixel_y]"
            - Files written to outputs/aoi/ as {apartment}_{room}.aoi
        """

        # Check if processed CSV exists (from successful parsing)
        if not hasattr(self, 'processed_room_boundaries_csv_path') or not self.processed_room_boundaries_csv_path.exists():
            logging.error("Processed CSV file not found. Ensure CSV parsing completed successfully.")
            return

        try:
            # Read the CSV file into a pandas DataFrame
            df = pd.read_csv(self.processed_room_boundaries_csv_path)
        except FileNotFoundError:
            logging.error(f"CSV file not found: {self.processed_room_boundaries_csv_path}")
            return
        except Exception as e:
            logging.error(f"Error reading the CSV: {e}")
            return

        # Build per-pixel projection params from the in-memory coordinate map
        coord_map_params = None
        if coordinate_map is not None:
            coord_map_params = {
                'vp_x': coordinate_map.vp_x,
                'vp_y': coordinate_map.vp_y,
                'wu_per_px_x': coordinate_map.world_units_per_pixel_x,
                'wu_per_px_y': coordinate_map.world_units_per_pixel_y,
                'width': coordinate_map.image_width,
                'height': coordinate_map.image_height,
            }
            logging.info(f"Loaded coordinate map parameters: {coord_map_params}")

        # Group the DataFrame by the 'apartment_no' and 'room' columns
        grouped = df.groupby(["apartment_no", "room"])

        print(f"Found {len(grouped)} unique apartment_no/room combinations.")

        # Define worker function for parallel processing
        def _process_single_room(group_data):
            """Process a single room group to generate AOI file content and path."""
            name, group = group_data
            apartment_name, room_name = name
            num_points = len(group)

            # --- 1. Build the content for the text file ---

            # get centre of mass of group
            centroid_x, centroid_y = calc_centroid_of_points(group[["x_coords", "y_coords"]])

            # Determine associated view file based on z_coordinate
            room_z_coord = group['z_coords'].iloc[0]

            # Convert meters to millimeters (integer) for filename
            # Calculate padding width based on all z-coordinates in dataset
            all_z_coords = df['z_coords'].values
            all_z_mm = [int(round(z * 1000)) for z in all_z_coords]
            max_abs_mm = max(abs(z_mm) for z_mm in all_z_mm)
            mm_width = len(str(max_abs_mm))

            # Convert current room z-coordinate to millimeters
            room_z_mm = int(round(room_z_coord * 1000))

            # Format filename with zero-padded millimeter value
            if room_z_mm < 0:
                associated_view_file = f"plan_ffl_-{abs(room_z_mm):0{mm_width}d}.vp"
            else:
                associated_view_file = f"plan_ffl_{room_z_mm:0{mm_width}d}.vp"

            # Header lines
            header_line1 = f"AOI Points File: {apartment_name} {room_name}"
            header_line2 = f"ASSOCIATED VIEW FILE: {associated_view_file}"
            header_line3 = f"FFL z height(m): {room_z_coord}"
            header_line4 = f"CENTRAL x,y: {centroid_x:.4f} {centroid_y:.4f}"

            # Update header to indicate pixel columns if coordinate map is available
            if coord_map_params is not None:
                header_line5 = f"NO. PERIMETER POINTS {num_points}: x,y pixel_x pixel_y positions"
            else:
                header_line5 = f"NO. PERIMETER POINTS {num_points}: x,y positions"

            # Coordinate data lines, formatted to 4 decimal places
            xy_coord_lines = []
            for index, row in group.iterrows():
                world_x = row['x_coords']
                world_y = row['y_coords']

                # Base coordinate line with world coordinates
                line = f"{world_x:.4f} {world_y:.4f}"

                # Add pixel coordinates if coordinate map is available
                if coord_map_params is not None:
                    p = coord_map_params
                    pixel_x = int((world_x - p['vp_x']) / p['wu_per_px_x'] + p['width'] / 2)
                    pixel_y = int(p['height'] / 2 - (world_y - p['vp_y']) / p['wu_per_px_y'])
                    line += f" {pixel_x} {pixel_y}"

                xy_coord_lines.append(line)

            # Combine all parts into the final text content
            file_content = "\n".join(
                [header_line1, header_line2, header_line3, header_line4, header_line5] + xy_coord_lines
            )

            # --- 2. Create a valid filename and save the file ---

            # Clean the room name to make it suitable for a filename
            clean_room_name = re.sub(r"[^\w\s-]", "", room_name).strip()
            clean_room_name = re.sub(r"[-\s]+", "_", clean_room_name)
            filename = f"{apartment_name}_{clean_room_name}.aoi"
            filepath = os.path.join(self.aoi_dir, filename)

            # Write the content to the file
            with open(filepath, "w") as f:
                f.write(file_content)

            return f"File generated: {filepath}"

        # Process all rooms in parallel using CPU cores for workers
        num_workers = min(multiprocessing.cpu_count(), len(grouped))

        print(f"Processing {len(grouped)} rooms using {num_workers} workers...")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            results = list(executor.map(_process_single_room, grouped))

        # Print summary
        print(f"Generated {len(results)} AOI files")

        return True  # Indicate success

    def __parse_aoi_inputs_dir(self) -> None:
        """Build the processed long-format DataFrame from a directory of .aoi files.

        Produces the same columns downstream code expects (apartment_no, room,
        x_coords, y_coords, z_coords in metres) and writes the processed CSV
        to aoi_dir under a stable name, so create_plan_view_files() and
        create_aoi_files() can consume it unchanged.

        Expected .aoi header (as written by scripts/convert_room_boundaries_csv_to_aoi.py):
            AOI Points File: {apt} {room}
            PARENT: {apt}
            CHILD: {room}
            FFL z height(m): {z_m}
            CENTRAL x,y: {cx} {cy}
            NO. PERIMETER POINTS {n}: x,y positions
            {x} {y}
            ...

        Legacy modern .aoi without PARENT/CHILD lines falls back to splitting
        the "AOI Points File:" line on the first space.
        """
        logging.info(f"Loading .aoi files from: {self.aoi_inputs_dir}")
        aoi_files = sorted(self.aoi_inputs_dir.glob("*.aoi"))
        if not aoi_files:
            logging.error(f"No .aoi files found in {self.aoi_inputs_dir}")
            self.room_boundaries_df = pd.DataFrame(columns=REQUIRED_COORDINATE_COLUMNS)
            return

        rows: list[dict[str, Any]] = []
        for path in aoi_files:
            parent, child, ffl_z, vertices = self.__read_aoi_file(path)
            for idx, (x, y) in enumerate(vertices):
                rows.append({
                    "apartment_no": parent,
                    "room": child,
                    "vertex_idx": idx,
                    "x_coords": x,
                    "y_coords": y,
                    "z_coords": ffl_z,
                })

        df = (
            pd.DataFrame(rows, columns=["apartment_no", "room", "vertex_idx", "x_coords", "y_coords", "z_coords"])
            .sort_values(by=["z_coords", "apartment_no", "room", "vertex_idx"])
            .reset_index(drop=True)
        )

        self.processed_room_boundaries_csv_path = Path(self.aoi_dir / "aoi_inputs_processed.csv")
        df.to_csv(self.processed_room_boundaries_csv_path, index=False)
        self.room_boundaries_df = df

        logging.info(
            f"Parsed {len(aoi_files)} .aoi files ({len(df)} vertices). "
            f"Processed CSV saved to: {self.processed_room_boundaries_csv_path}"
        )

    @staticmethod
    def __read_aoi_file(path: Path) -> tuple[str, str, float, list[tuple[float, float]]]:
        """Parse one .aoi file. Returns (parent, child, ffl_z_m, [(x_m, y_m), ...])."""
        text = path.read_text(encoding="utf-8").splitlines()

        parent: str | None = None
        child: str | None = None
        ffl_z: float | None = None
        vertex_start: int | None = None
        header_fallback_line: str | None = None

        for i, line in enumerate(text):
            stripped = line.strip()
            if stripped.startswith("PARENT:"):
                parent = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("CHILD:"):
                child = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("AOI Points File:"):
                header_fallback_line = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("FFL z height(m):"):
                ffl_z = float(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("NO. PERIMETER POINTS"):
                vertex_start = i + 1
                break

        if (parent is None or child is None) and header_fallback_line is not None:
            apt, _, rest = header_fallback_line.partition(" ")
            parent = parent or apt
            child = child or rest

        if parent is None or child is None:
            raise ValueError(f"{path.name}: could not resolve PARENT/CHILD")
        if ffl_z is None:
            raise ValueError(f"{path.name}: missing FFL z height(m)")
        if vertex_start is None:
            raise ValueError(f"{path.name}: missing NO. PERIMETER POINTS header")

        vertices: list[tuple[float, float]] = []
        for line in text[vertex_start:]:
            stripped = line.strip()
            if not stripped:
                continue
            tokens = stripped.split()
            if len(tokens) < 2:
                continue
            vertices.append((float(tokens[0]), float(tokens[1])))

        if not vertices:
            raise ValueError(f"{path.name}: no vertex rows found")

        return parent, child, ffl_z, vertices

    def __parse_room_boundaries_csv(self) -> None:
        """
        Parse and process room boundary CSV data into structured format.
        
        This private method transforms the raw CSV input containing coordinate strings
        into a clean, structured DataFrame ready for geometric analysis. The process:
        
        1. Loads CSV with apartment_no, room, and multiple coordinate string columns
        2. Melts coordinate columns into long format for easier processing  
        3. Extracts X, Y, Z coordinates using regex pattern matching
        4. Converts coordinate values from millimeters to meters (divides by 1000)
        5. Removes rows with invalid/missing coordinate data
        6. Sorts by floor level (z_coords), apartment, and room
        7. Saves processed data to CSV in the AOI output directory
        8. Sets the room_boundaries_df instance attribute
        
        Input CSV Format Expected:
            - Column 0: apartment_no (building unit identifier)
            - Column 1: room (room name/type)  
            - Columns 2+: coordinate strings like \"X_123.45 Y_678.90 Z_012.34\"
            
        Output DataFrame Columns:
            - apartment_no: Building unit identifier
            - room: Room name/type
            - x_coords: X coordinate in meters (converted from mm)
            - y_coords: Y coordinate in meters (converted from mm) 
            - z_coords: Z coordinate in meters (converted from mm)
            
        Side Effects:
            - Creates processed CSV file in aoi_dir
            - Sets self.room_boundaries_df attribute
            - Sets self.processed_room_boundaries_csv_path attribute
            - Logs processing status and any errors
            
        Note:
            This method is called automatically during __post_init__.
            Parsing errors are logged but don't raise exceptions to allow
            the instance to be created even with invalid input data.
        """
        logging.info(f"Loading and parsing data from: {self.room_boundaries_csv_path}")
        try:
            df = (
                pd.read_csv(self.room_boundaries_csv_path, delimiter=",", header=None)
                .melt(id_vars=[0, 1], value_name="coordinate_string")
                .rename(columns={0: "apartment_no", 1: "room"})
                .dropna(subset=["coordinate_string"])
                # Correctly use .pipe() to apply the join logic
                .pipe(
                    lambda df: df.join(
                        df["coordinate_string"]
                        .str.extract(COORDINATE_PATTERN)
                        .rename(columns=dict(enumerate(REQUIRED_COORDINATE_COLUMNS)))
                    )
                )
                .assign(
                    **{
                        col: lambda d, c=col: pd.to_numeric(d[c], errors="coerce") / 1000
                        for col in REQUIRED_COORDINATE_COLUMNS
                    }
                )
                .dropna(subset=REQUIRED_COORDINATE_COLUMNS)
                .sort_values(by=["z_coords", "apartment_no", "room"])
                .reset_index(drop=True)
            )

            logging.info("DataFrame parsed successfully.")

            # send processed room boundaries data to new csv
            self.processed_room_boundaries_csv_path = Path(self.aoi_dir / f"{self.room_boundaries_csv_path.stem}_processed.csv")
            df.to_csv(self.processed_room_boundaries_csv_path, index=False)
            
            logging.info(f"Processed DataFrame saved to: {self.processed_room_boundaries_csv_path}")

            return
        
        except Exception as e:
            logging.error(f"Failed to parse CSV: {e}")
            return None

    def __create_floor_level_info(self, room_boundaries_data: pd.DataFrame, view_dir: str, ffl_offset: float) -> pd.DataFrame | None:
        """
        Create floor level mapping information for view file generation.
        
        Analyzes the room boundary data to identify unique floor levels (Z coordinates)
        and creates a mapping between floor levels and their corresponding view file paths.
        Each unique Z coordinate becomes a separate floor level with its own view file.
        
        Args:
            room_boundaries_data: DataFrame containing parsed room boundary coordinates
                                 with columns including 'z_coords'
            view_dir: Directory path where view files will be generated
            ffl_offset: Height offset to add to floor levels for camera positioning
            
        Returns:
            DataFrame with columns:
                - ffl_z_coord: Floor finished level Z coordinate (meters)
                - view_file_path: Path to corresponding view file (plan_ffl_90000.vp, etc.)
                - ffl_z_coord_with_offset: Camera Z position (floor level + offset)
            Returns None if processing fails or no valid Z coordinates found

        Processing Steps:
            1. Extract and validate Z coordinates from room data
            2. Find unique Z coordinate values representing different floor levels
            3. Sort floor levels from lowest to highest
            4. Convert meter values to millimeters (integer) for filenames
            5. Generate view file paths with millimeter-based naming
            6. Calculate camera positions by adding offset to floor levels
            7. Create output directory if it doesn't exist

        Generated View File Names:
            - plan_ffl_00000.vp: Ground level (0.0m)
            - plan_ffl_90000.vp: Floor at 90.0m height
            - plan_ffl_103180.vp: Floor at 103.18m height
            - etc. (zero-padded millimeter values for correct alphabetical sorting)
            
        Error Handling:
            - Logs errors for invalid Z coordinates or directory creation failures
            - Returns empty DataFrame if no valid Z coordinates found
            - Returns None if critical errors prevent processing
        """
        try:
            z_coords_numeric = pd.to_numeric(room_boundaries_data["z_coords"], errors="coerce")
            unique_z_coords_series = z_coords_numeric.dropna().unique()
            if len(unique_z_coords_series) == 0:
                logging.info("No unique, non-NaN Z-coordinates found for floor level info.")
                return pd.DataFrame(columns=["z_coords", "view_file_path"])
            sorted_unique_z_coords = sorted(unique_z_coords_series)
            logging.info(
                f"Sorted unique Z-Coordinates for floor level DF: {sorted_unique_z_coords}"
            )
        except Exception as e:
            logging.error(f"Error processing 'z_coords' for floor level DF: {e}", exc_info=True)
            return None

        view_dir_path = view_dir
        try:
            view_dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"Failed to create directory {view_dir_path} for floor level DF: {e}")
            return None

        # Convert meters to millimeters (integer) to avoid decimal points in filenames
        # e.g., 90.0m -> 90000mm, 103.18m -> 103180mm, -2.5m -> -02500mm
        z_coords_mm = [int(round(z * 1000)) for z in sorted_unique_z_coords]

        # Determine padding width based on maximum absolute value in millimeters
        max_abs_mm = max(abs(z_mm) for z_mm in z_coords_mm)
        mm_width = len(str(max_abs_mm))

        floor_level_data = []
        for z_val, z_mm in zip(sorted_unique_z_coords, z_coords_mm):
            # Format: zero-padded millimeter value with negative sign if needed
            # Examples: 90000, 103180, -02500
            if z_mm < 0:
                filename = f"plan_ffl_-{abs(z_mm):0{mm_width}d}"
            else:
                filename = f"plan_ffl_{z_mm:0{mm_width}d}"

            floor_level_data.append({
                "ffl_z_coord": z_val,
                "view_file_path": view_dir_path / f"{filename}.vp"
            })

        output_df = pd.DataFrame(floor_level_data)
        output_df["ffl_z_coord_with_offset"] = output_df["ffl_z_coord"] + ffl_offset

        logging.info(f"Generated floor level information DataFrame with {len(output_df)} levels.")

        return output_df


