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
class ViewFileGenerator:
    """
    Generates Radiance view files from room boundary data for daylight analysis.
    
    Creates floor plan view files (.vp) containing camera parameters for rendering
    each floor level of a building model. Processes CSV data containing room boundary
    coordinates and generates the necessary view parameters for Radiance simulations.
    
    Example:
        >>> from pathlib import Path
        >>> csv_path = Path("inputs/room_boundaries.csv")
        >>> generator = ViewFileGenerator(
        ...     room_boundaries_csv_path_input=csv_path,
        ...     ffl_offset=1.0  # Camera height above floor level
        ... )
        >>> success = generator.create_aoi_and_view_files()
        
    Parameters:
        room_boundaries_csv_path_input: Path to CSV file containing room boundary coordinates.
                                      CSV should have columns for apartment_no, room, and 
                                      coordinate strings in format "X_123.45 Y_678.90 Z_012.34"
        ffl_offset: Height offset above finished floor level for camera position (meters).
                   Typical value: 1.0 (eye level above floor). Default: 1.0
                                      
    Output:
        - Creates .aoi files in 'outputs/aoi/' directory (one per room)
        - Creates .vp view files in 'outputs/views_grids/' directory (one per floor level)
        - View files contain Radiance camera parameters for top-down floor views
    
    Note:
        Requires accurate and complete room boundary data for proper functioning.
        Coordinates are expected in millimeters and will be converted to meters.
    """

    room_boundaries_csv_path_input: str
    ffl_offset: float = 1.0

    csv_path: Path = field(init=False)
    csv_accessible: bool = field(default=False, init=False)

    room_boundaries_df: pd.DataFrame | None = field(default=None, init=False)
    bounding_box_coordinates: Any = field(default=None, init=False)
    x_coord_center: float | None = field(default=None, init=False)
    y_coord_center: float | None = field(default=None, init=False)
    z_coord_center: float | None = field(default=None, init=False)
    view_horizontal: float | None = field(default=None, init=False)
    view_vertical: float | None = field(default=None, init=False)
    view_paths_per_level_df: pd.DataFrame | None = field(default=None, init=False)

    def __post_init__(self):
        """
        Post-initialization processing, including CSV path validation.
        Sets self.csv_accessible and self.csv_path.
        """
        if not self.room_boundaries_csv_path_input or not isinstance(
            self.room_boundaries_csv_path_input, (str, Path)
        ):
            logging.error(
                f"CSV file path is invalid (not a string or empty): '{self.room_boundaries_csv_path_input}'"
            )
            self.csv_accessible = False
            self.csv_path = None
            return

        try:
            abs_path = os.path.abspath(str(self.room_boundaries_csv_path_input))
        except TypeError:
            logging.error(
                f"Invalid CSV file path type for abspath: {self.room_boundaries_csv_path_input}"
            )
            self.csv_accessible = False
            self.csv_path = None
            return

        self.csv_path = abs_path

        if os.path.exists(self.csv_path):
            if os.path.isfile(self.csv_path):
                logging.info(
                    f"ViewGenerator initialized. CSV file found and is a file: {self.csv_path}"
                )
                self.csv_accessible = True
            else:
                logging.error(f"Path exists but is not a file: {self.csv_path}")
                self.csv_accessible = False
        else:
            logging.warning(f"CSV file not found at the specified path: {self.csv_path}")
            self.csv_accessible = False

    def _generate_point_files(self, csv_path: str, output_dir: str = "outputs/aoi") -> None:
        """
        Generate individual AOI files for each room from processed CSV data.
        
        Creates one .aoi file per room containing boundary coordinates and metadata.
        
        Parameters:
            csv_path: Path to processed CSV file with room boundary coordinates
            output_dir: Directory to save .aoi files (default: 'aoi')
        """
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Read the CSV file into a pandas DataFrame
            df = pd.read_csv(csv_path)
        except FileNotFoundError:
            logging.error(f"CSV file not found: {csv_path}")
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

            # --- Build the content for the text file ---

            # get centre of mass of group
            centroid_x, centroid_y = calc_centroid_of_points(group[["x_coords", "y_coords"]])

            # 1. Header lines
            header_line1 = f"AOI Points File: {apartment_name} {room_name}"
            header_line2 = f"FFL z height(m): {group['z_coords'].iloc[0]}"
            header_line3 = f"CENTRAL x,y: {centroid_x:.4f} {centroid_y:.4f}"
            header_line4 = f"NO. PERIMETER POINTS {num_points}: x,y positions"

            # 2. Coordinate data lines, formatted to 4 decimal places
            xy_coord_lines = []
            for index, row in group.iterrows():
                line = f"{row['x_coords']:.4f} {row['y_coords']:.4f}"
                xy_coord_lines.append(line)

            # 3. Combine all parts into the final text content
            file_content = "\n".join(
                [header_line1, header_line2, header_line3, header_line4] + xy_coord_lines
            )

            # --- Create a valid filename and save the file ---

            # Clean the room name to make it suitable for a filename
            clean_room_name = re.sub(r"[^\w\s-]", "", room_name).strip()
            clean_room_name = re.sub(r"[-\s]+", "_", clean_room_name)
            filename = f"{apartment_name}_{clean_room_name}.aoi"
            filepath = os.path.join(output_dir, filename)

            # Write the content to the file
            with open(filepath, "w") as f:
                f.write(file_content)

        print(f"File generated: {filepath}")

    def _parse_room_boundaries_csv(self) -> pd.DataFrame | None:
        """
        Parse room boundaries CSV into structured DataFrame.
        
        Transforms coordinate strings into numeric x,y,z columns and converts
        from millimeters to meters. Saves processed data to output CSV.
        
        Returns:
            DataFrame with columns: apartment_no, room, x_coords, y_coords, z_coords
            None if parsing fails
        """
        logging.info(f"Loading and parsing data from: {self.csv_path}")
        try:
            coord_cols = ["x_coords", "y_coords", "z_coords"]
            pattern = r"X_(-?\d+\.?\d*)\s+Y_(-?\d+\.?\d*)\s+Z_(-?\d+\.?\d*)"

            df = (
                pd.read_csv(self.csv_path, delimiter=",", header=None)
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

            # Create the new path pointing to the 'outputs/octree' directory
            input_path = Path(self.csv_path)
            outputs_dir = Path("outputs/aoi")
            outputs_dir.mkdir(parents=True, exist_ok=True)
            output_csv_path = str(outputs_dir / f"{input_path.stem}_processed.csv")
            df.to_csv(output_csv_path, index=False)
            logging.info(f"Processed DataFrame saved to: {output_csv_path}")

            self._generate_point_files(output_csv_path)

            return df
        except Exception as e:
            logging.error(f"Failed to parse CSV: {e}")
            return None

    def _create_floor_level_info(
        self, room_boundaries_data: pd.DataFrame, view_subdir: str, ffl_offset: float
    ) -> pd.DataFrame | None:
        current_dir = Path.cwd()
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

        view_dir_path = current_dir / view_subdir
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

    def _populate_view_files(
        self,
        view_file: str,
        x_coord_centre: float,
        y_coord_centre: float,
        z_coord: float,
        vh_val: str = "50",
        vv_val: str = "30",
    ) -> None:
        """
        Write Radiance view parameters to .vp file.
        
        Creates a top-down view configuration for floor plan rendering.
        
        Parameters:
            view_file: Output .vp file path
            x_coord_centre: Camera X position (center of building)
            y_coord_centre: Camera Y position (center of building) 
            z_coord: Camera Z position (floor level + offset)
            vh_val: Horizontal view angle in degrees (default: 50)
            vv_val: Vertical view angle in degrees (default: 30)
        """
        try:
            view_file_path_obj = Path(view_file)
            view_file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            view_content = [
                "rvu",
                "-vtl",
                "-vp",
                str(x_coord_centre),
                str(y_coord_centre),
                str(z_coord),
                "-vd",
                "0",
                "0",
                "-1",
                "-vu",
                "0",
                "1",
                "0",
                "-vh",
                str(vh_val),
                "-vv",
                str(vv_val),
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
                f"Successfully created view file: {view_file}"
            )  # Changed to debug for less verbosity if many files
        except Exception as e:
            logging.error(f"Error creating view file at {view_file}: {e}")

    def create_aoi_and_view_files(self) -> bool:
        """
        Generate AOI and view files from room boundary data.
        
        Main method that processes the CSV data to create:
        1. AOI (Area of Interest) files for each room
        2. View parameter files for each floor level
        
        Uses the ffl_offset specified during class instantiation for camera positioning.
                       
        Returns:
            bool: True if files generated successfully, False if any step fails
            
        Process:
            - Validates CSV file accessibility
            - Parses room boundary coordinates 
            - Calculates building bounding box and center point
            - Determines view dimensions for proper framing
            - Creates view files with camera parameters for each floor
            
        Generated Files:
            - aoi/*.aoi: Room boundary files with coordinate data
            - views_grids/plan_L00.vp, plan_L01.vp, etc: Radiance view parameter files
        """

        # --- 1: Check if CSV is accessible ---
        if not self.csv_accessible:
            return False

        # --- 2: parse room boundary coordinates csv ---
        self.room_boundaries_df = self._parse_room_boundaries_csv()
        print("\n--- printing transformed room boundaries data ---\n", self.room_boundaries_df)

        if self.room_boundaries_df is None or self.room_boundaries_df.empty:
            return False

        try:
            required_cols = ["x_coords", "y_coords", "z_coords"]
            if not all(col in self.room_boundaries_df.columns for col in required_cols):
                return False

            points_df = self.room_boundaries_df[required_cols].dropna()
            if points_df.empty:
                return False

            # --- 3: determine 3D bounding box coords ---
            self.bounding_box_coordinates = get_bounding_box_from_point_coordinates(points_df)
            if self.bounding_box_coordinates is None:
                return False

            # --- 4: Detemrine central x,y,z coordinates ---
            center_coords = get_center_of_bounding_box(self.bounding_box_coordinates)
            if center_coords is None:
                return False
            x, y, z = center_coords

            # Round the center coordinates to 3 decimal places
            self.x_coord_center = round(x, 3)
            self.y_coord_center = round(y, 3)
            self.z_coord_center = round(z, 3)

            print("centre x coordinate: ", self.x_coord_center)
            print("centre y coordinate: ", self.y_coord_center)
            print("centre z coordinate: ", self.z_coord_center)

            # --- 5: Determine view dimensions from central point ---
            dimensions = calculate_dimensions_from_points(self.bounding_box_coordinates)
            if dimensions is None:
                return False
            vh, vv = dimensions

            # Round the view dimensions to 3 decimal places
            self.view_horizontal = round(vh, 3)
            self.view_vertical = round(vv, 3)

        except (AttributeError, Exception):
            return False

        self.view_paths_per_level_df = self._create_floor_level_info(
            self.room_boundaries_df, view_subdir="outputs/views_grids", ffl_offset=self.ffl_offset
        )

        if self.view_paths_per_level_df is None:
            return False

        print("\n--- printing view files df ---\n", self.view_paths_per_level_df.to_string())

        # --- 6: generate all plan view files ---

        # Iterate through each file path in the 'view_file_path' column
        for row in self.view_paths_per_level_df.itertuples(index=False):
            # Extract data from the current row using attribute access
            file_path = row.view_file_path
            z_coordinate = row.ffl_z_coord_with_offset
            try:
                # Extract the directory path from the file path
                dir_path = os.path.dirname(file_path)

                # Create the directory if it doesn't exist
                os.makedirs(dir_path, exist_ok=True)

                # Create the empty file
                with open(file_path, "w") as fp:
                    pass
                print(f"Successfully created: {file_path}")

                # populate these files
                self._populate_view_files(
                    file_path,
                    x_coord_centre=self.x_coord_center,
                    y_coord_centre=self.y_coord_center,
                    z_coord=z_coordinate,
                    vh_val=self.view_horizontal,
                    vv_val=self.view_vertical,
                )

            except Exception as e:
                print(f"Error creating {file_path}: {e}")

        # --- 7: generate axonometric views of building overall

        # TODO: further development below in generating 3D axo views to allow for visualisation of the entire input model and its geometry.  See function get obj bounds below, that could assist in developing this functionality.

        # consideration of get_ob_bounding box if that is better for use in axonometric views.

        return True  # Indicate success



    #TODO: further development below in generating 3D axo views to allow for visualisation of the entire input model and its geometry.  See function get obj bounds below, that could assist in developing this functionality.
    # def _get_obj_bounds(self, filepath: str) -> tuple[float, float, float, float, float, float] | None:
    #     try:
    #         scene = pywavefront.Wavefront(filepath, collect_faces=True, strict=False, create_materials=True)
    #     except FileNotFoundError:
    #         logging.error(f"OBJ File not found: {filepath}")
    #         return None
    #     except Exception as e:
    #         logging.error(f"Error loading OBJ {filepath}: {e}", exc_info=True)
    #         return None
    #     all_vertices_list = []
    #     for mesh in scene.mesh_list:
    #         if mesh.materials:
    #             material = mesh.materials[0]
    #             vertex_format = material.vertex_format; vertex_data = material.vertices
    #             if not vertex_data: continue
    #             vertex_data_np = np.array(vertex_data, dtype=np.float32)
    #             if vertex_format == 'V3F': vertices = vertex_data_np.reshape(-1, 3)
    #             elif vertex_format == 'T2F_V3F': vertices = vertex_data_np.reshape(-1, 5)[:, 2:]
    #             elif vertex_format == 'N3F_V3F': vertices = vertex_data_np.reshape(-1, 6)[:, 3:]
    #             elif vertex_format == 'T2F_N3F_V3F': vertices = vertex_data_np.reshape(-1, 8)[:, 5:]
    #             else: logging.warning(f"Unsupported OBJ vertex format: {vertex_format} in {filepath}"); continue
    #             all_vertices_list.append(vertices)
    #     if not all_vertices_list: logging.warning(f"No vertices found in OBJ: {filepath}"); return None
    #     all_vertices_np = np.vstack(all_vertices_list)
    #     min_coords = np.min(all_vertices_np, axis=0); max_coords = np.max(all_vertices_np, axis=0)
    #     return (min_coords[0], max_coords[0], min_coords[1], max_coords[1], min_coords[2], max_coords[2])
