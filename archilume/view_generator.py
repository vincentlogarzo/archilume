# Archilume imports
from archilume.geometry_utils import (
    calc_centroid_of_points,
    calculate_dimensions_from_points,
    get_center_of_bounding_box,
    get_bounding_box_from_point_coordinates,
)

# Standard library imports
import logging
import os
import re
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

# Third-party imports
import pandas as pd

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
        aoi_file_dir: Directory for generated AOI files (outputs/aoi/)
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
    view_file_dir: Path = field(init                = False, default = Path(__file__).parent.parent / "outputs" / "views_grids")
    aoi_file_dir: Path = field(init                 = False, default = Path(__file__).parent.parent / "outputs" / "aoi")
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
        os.makedirs(self.aoi_file_dir, exist_ok=True)
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
            - Naming: plan_L00.vp (ground floor), plan_L01.vp (second floor), etc.
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
            required_cols = ["x_coords", "y_coords", "z_coords"]
            if not all(col in self.room_boundaries_df.columns for col in required_cols):
                return False
            points_df = self.room_boundaries_df[required_cols].dropna()
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

    def create_aoi_files(self) -> bool:
        """
        Generate Area of Interest (AOI) files for each room from boundary data.

        Creates individual AOI files containing room-specific information for daylight
        analysis. Each file includes room metadata, boundary coordinates, centroid
        calculations, and associated view file references organized by floor level.

        Processing Workflow:
            1. Validates that processed CSV file exists from successful parsing
            2. Loads and groups room boundary data by apartment and room
            3. For each room group:
               - Calculates room centroid from boundary points
               - Determines associated view file based on floor level (Z coordinate)
               - Formats boundary coordinates to 4 decimal places
               - Generates structured file content with headers and data
               - Creates sanitized filename from apartment and room names
               - Writes AOI file to output directory

        Generated AOI File Format:
            - Header Line 1: \"AOI Points File: {apartment} {room}\"
            - Header Line 2: \"ASSOCIATED VIEW FILE: plan_L##.vp\"
            - Header Line 3: \"FFL z height(m): {floor_level}\"
            - Header Line 4: \"CENTRAL x,y: {centroid_x} {centroid_y}\"
            - Header Line 5: \"NO. PERIMETER POINTS {count}: x,y positions\"
            - Data Lines: One per boundary point as \"x.xxxx y.yyyy\"

        Output Files:
            - Location: outputs/aoi/ directory
            - Naming: {apartment_no}_{sanitized_room_name}.aoi
            - Content: Room boundary points and metadata for each room
            - Count: One file per unique apartment_no/room combination

        Returns:
            bool: True if all AOI files generated successfully, False if validation
                 fails or processed CSV file is not available

        Error Handling:
            - Validates processed CSV file exists before proceeding
            - Logs errors for missing files or read failures
            - Handles special characters in room names for filename compatibility
            - Provides fallback view file names for unmatched floor levels
            - Continues processing other rooms if individual room processing fails

        Prerequisites:
            - CSV file must be successfully parsed during __post_init__
            - processed_room_boundaries_csv_path must be set and file must exist

        Side Effects:
            - Creates AOI files in the aoi_file_dir
            - Prints progress messages for each generated file
            - Does not modify instance attributes (unlike create_view_files)
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

        # Group the DataFrame by the 'apartment_no' and 'room' columns
        grouped = df.groupby(["apartment_no", "room"])

        print(f"Found {len(grouped)} unique apartment_no/room combinations.")

        # Process each group
        for name, group in grouped:
            apartment_name, room_name = name
            num_points = len(group)

            # --- 1. Build the content for the text file ---

            # get centre of mass of group
            centroid_x, centroid_y = calc_centroid_of_points(group[["x_coords", "y_coords"]])
            
            # Determine associated view file based on z_coordinate
            room_z_coord = group['z_coords'].iloc[0]
            
            # Get unique z coordinates and find which level this room belongs to
            all_z_coords = sorted(df['z_coords'].unique())
            try:
                level_index = all_z_coords.index(room_z_coord)
                associated_view_file = f"plan_L{level_index:02}.vp"
            except ValueError:
                # Fallback if z_coord not found in unique list
                associated_view_file = "plan_L#ERROR_LVL_NOT_FOUND.vp"

            # Header lines
            header_line1 = f"AOI Points File: {apartment_name} {room_name}"
            header_line2 = f"ASSOCIATED VIEW FILE: {associated_view_file}"
            header_line3 = f"FFL z height(m): {room_z_coord}"
            header_line4 = f"CENTRAL x,y: {centroid_x:.4f} {centroid_y:.4f}"
            header_line5 = f"NO. PERIMETER POINTS {num_points}: x,y positions"

            # Coordinate data lines, formatted to 4 decimal places
            xy_coord_lines = []
            for index, row in group.iterrows():
                line = f"{row['x_coords']:.4f} {row['y_coords']:.4f}"
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
            filepath = os.path.join(self.aoi_file_dir, filename)

            # Write the content to the file
            with open(filepath, "w") as f:
                f.write(file_content)

            print(f"File generated: {filepath}")

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
            - Creates processed CSV file in aoi_file_dir
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
            coord_cols = ["x_coords", "y_coords", "z_coords"]
            pattern = r"X_(-?\d+\.?\d*)\s+Y_(-?\d+\.?\d*)\s+Z_(-?\d+\.?\d*)"

            df = (
                pd.read_csv(self.room_boundaries_csv_path, delimiter=",", header=None)
                .melt(id_vars=[0, 1], value_name="coordinate_string")
                .rename(columns={0: "apartment_no", 1: "room"})
                .dropna(subset=["coordinate_string"])
                # Correctly use .pipe() to apply the join logic
                .pipe(
                    lambda df: df.join(
                        df["coordinate_string"]
                        .str.extract(pattern)
                        .rename(columns=dict(enumerate(coord_cols)))
                    )
                )
                .assign(
                    **{
                        col: lambda d, c=col: pd.to_numeric(d[c], errors="coerce") / 1000
                        for col in coord_cols
                    }
                )
                .dropna(subset=coord_cols)
                .sort_values(by=["z_coords", "apartment_no", "room"])
                .reset_index(drop=True)
            )

            logging.info("DataFrame parsed successfully.")

            # send processed room boundaries data to new csv
            self.processed_room_boundaries_csv_path = Path(self.aoi_file_dir / f"{self.room_boundaries_csv_path.stem}_processed.csv")
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
                - view_file_path: Path to corresponding view file (plan_L00.vp, etc.)
                - ffl_z_coord_with_offset: Camera Z position (floor level + offset)
            Returns None if processing fails or no valid Z coordinates found
            
        Processing Steps:
            1. Extract and validate Z coordinates from room data
            2. Find unique Z coordinate values representing different floor levels
            3. Sort floor levels from lowest to highest
            4. Generate view file paths with sequential naming (plan_L00, plan_L01, etc.)
            5. Calculate camera positions by adding offset to floor levels
            6. Create output directory if it doesn't exist
            
        Generated View File Names:
            - plan_L00.vp: Ground/lowest floor level
            - plan_L01.vp: Second floor level  
            - plan_L02.vp: Third floor level
            - etc.
            
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

        floor_level_data = [
            {"ffl_z_coord": z_val, "view_file_path": view_dir_path / f"plan_L{i:02}.vp"}
            for i, z_val in enumerate(sorted_unique_z_coords)
        ]
        output_df = pd.DataFrame(floor_level_data)
        output_df["ffl_z_coord_with_offset"] = output_df["ffl_z_coord"] + ffl_offset

        logging.info(f"Generated floor level information DataFrame with {len(output_df)} levels.")

        return output_df


