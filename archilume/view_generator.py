# Archilume imports
from archilume.utils import (
    calc_centroid_of_points,
    calculate_dimensions_from_points,
    get_center_of_bounding_box,
    get_bounding_box_from_point_coordinates,
)
from archilume import config

# Standard library imports
import logging
import multiprocessing
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

# Third-party imports
import pandas as pd
import numpy as np

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
    room_boundaries_csv_path: Path
    ffl_offset: float

    # Fixed - not user configurable but accessible from instance
    processed_room_boundaries_csv_path: Path        = field(init=False)
    view_file_dir: Path = field(init                = False, default_factory=lambda: config.VIEW_DIR)
    aoi_dir: Path = field(init                 = False, default_factory=lambda: config.AOI_DIR)
    room_boundaries_df: pd.DataFrame | None         = field(init=False, default=None)
    bounding_box_coordinates: Any                   = field(init=False, default=None)
    x_coord_center: float | None                    = field(init=False, default=None)
    y_coord_center: float | None                    = field(init=False, default=None)
    z_coord_center: float | None                    = field(init=False, default=None)
    view_horizontal: float | None                   = field(init=False, default=None)
    view_vertical: float | None                     = field(init=False, default=None)
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

        # Check if CSV file exists
        if not self.room_boundaries_csv_path.exists():
            print(f"\nError: Room boundaries CSV not found at {self.room_boundaries_csv_path}")
            import sys
            sys.exit(1)

        # Create the output directory if it doesn't exist
        os.makedirs(self.aoi_dir, exist_ok=True)
        os.makedirs(self.view_file_dir, exist_ok=True)

        # Run csv parser to restructure the room boundaries data for use
        self.__parse_room_boundaries_csv()
        
    def create_plan_view_files(self) -> bool:
        """
        Generate Radiance view parameter files for each floor level.

        Creates .vp view files containing camera parameters for top-down orthographic
        rendering of building floor plans. Each file represents a different floor level
        with camera positioning optimized for architectural visualization.

        Processing Workflow:
            1. Loads processed room boundary data from CSV file
            2. Validates required coordinate columns exist and contain valid data
            3. Calculates building-wide 3D bounding box from all room coordinates
            4. Determines building center point for camera positioning
            5. Calculates view dimensions for proper framing
            6. Maps floor levels to view file paths using floor level information
            7. Generates individual view parameter files for each floor level
            8. Populates each file with complete Radiance view parameters

        Geometric Calculations:
            - Bounding box: Encompasses all room boundary points across all floors
            - Center point: 3D centroid of the bounding box for camera positioning
            - View dimensions: Used for horizontal/vertical view angle parameters
            - Camera heights: Floor level + ffl_offset for each level

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
            - room_boundaries_df: Processed coordinate data
            - bounding_box_coordinates: 3D building bounds
            - x_coord_center, y_coord_center, z_coord_center: Building center
            - view_horizontal, view_vertical: Calculated view dimensions  
            - view_paths_per_level_df: Floor level to view file mapping

        Error Handling:
            - Validates processed CSV file is available and not empty
            - Checks for required coordinate columns
            - Handles geometry calculation failures gracefully
            - Creates output directories as needed
            - Logs errors but continues processing when possible
            - Returns False on critical failures that prevent completion

        Prerequisites:
            - CSV file must be successfully parsed during __post_init__
            - Processed room boundary data must be available
            - No dependency on create_aoi_files() - operates independently

        Side Effects:
            - Creates view files in view_file_dir
            - Sets multiple instance attributes for building geometry
            - Prints diagnostic information during processing
        """

        self.room_boundaries_df = pd.read_csv(self.processed_room_boundaries_csv_path)
        if self.room_boundaries_df.empty:
            return False

        try:
            if not all(col in self.room_boundaries_df.columns for col in REQUIRED_COORDINATE_COLUMNS):
                return False
            points_df = self.room_boundaries_df[REQUIRED_COORDINATE_COLUMNS].dropna()
            if points_df.empty:
                return False

            self.bounding_box_coordinates = get_bounding_box_from_point_coordinates(points_df)
            center_coords = get_center_of_bounding_box(self.bounding_box_coordinates)
            dimensions = calculate_dimensions_from_points(self.bounding_box_coordinates)
            
            if self.bounding_box_coordinates is None or center_coords is None or dimensions is None:
                return False

            self.x_coord_center, self.y_coord_center, self.z_coord_center = [round(c, 3) for c in center_coords]
            self.view_horizontal, self.view_vertical = [round(d, 3) for d in dimensions]
            
            print(f"Centre coordinates: ({self.x_coord_center}, {self.y_coord_center}, {self.z_coord_center})")
            
        except Exception:
            return False

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
                        str(self.x_coord_center),
                        str(self.y_coord_center),
                        str(z_coordinate),
                        "-vd",
                        "0",
                        "0",
                        "-1",
                        "-vu",
                        "0",
                        "1",
                        "0",
                        "-vh",
                        str(self.view_horizontal),
                        "-vv",
                        str(self.view_vertical),
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

    def create_aoi_files(self, coordinate_map_path: Path | None = None) -> bool:
        """Generate AOI files for each room with boundary points and metadata.

        Args:
            coordinate_map_path: Optional coordinate map file. If provided, adds pixel
                               coordinates via nearest neighbor lookup.

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

        # Load coordinate map if provided
        coord_map_df = None
        world_coords = None
        if coordinate_map_path is not None and Path(coordinate_map_path).exists():
            try:
                logging.info(f"Loading coordinate map from: {coordinate_map_path}")
                coord_map_df = pd.read_csv(
                    coordinate_map_path,
                    sep=r'\s+',  # whitespace delimiter
                    comment='#',  # skip header comments
                    names=['pixel_x', 'pixel_y', 'world_x', 'world_y']
                )
                # Extract world coordinates as numpy array for nearest neighbor lookup
                world_coords = coord_map_df[['world_x', 'world_y']].values
                logging.info(f"Loaded {len(coord_map_df)} coordinate mappings")
            except Exception as e:
                logging.error(f"Error loading coordinate map: {e}")
                coord_map_df = None
                world_coords = None

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
            if world_coords is not None:
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
                if world_coords is not None and coord_map_df is not None:
                    # Find nearest neighbor using simple numpy distance calculation
                    # Calculate Euclidean distance: sqrt((x2-x1)^2 + (y2-y1)^2)
                    distances = np.sqrt(
                        (world_coords[:, 0] - world_x)**2 +
                        (world_coords[:, 1] - world_y)**2
                    )
                    index_nearest = np.argmin(distances)

                    # Get corresponding pixel coordinates
                    pixel_x = int(coord_map_df.iloc[index_nearest]['pixel_x'])
                    pixel_y = int(coord_map_df.iloc[index_nearest]['pixel_y'])

                    # Append pixel coordinates to line
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

        # Print all results
        for result in results:
            print(result)

        return True  # Indicate success

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


