# utils.py

import concurrent.futures
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union
import open3d as o3d
import pywavefront
from pywavefront.visualization import draw
from PIL import Image
from pathlib import Path


def get_image_dimensions(image_path):
    """
    Opens an image file and prints its dimensions.
    """
    if not os.path.exists(image_path):
        print(f"Error: File not found at '{image_path}'")
        return

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            print(
                f"The dimensions of '{os.path.basename(image_path)}' are: {width}x{height} pixels."
            )
    except Exception as e:
        print(f"Error: Could not read image dimensions. Reason: {e}")

def display_obj_o3d(filename: Path):
    """Displays an OBJ file using the open3d library."""
    print("Visualizing with open3d...")
    # Read the mesh from the file
    mesh = o3d.io.read_triangle_mesh(str(filename))

    # The mesh might need normals for proper lighting
    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    # Display the mesh in an interactive window
    print("-> Close the open3d window to continue.")
    o3d.visualization.draw_geometries([mesh])


def display_obj_pywavefront(filename: Path):
    """Displays an OBJ file using the pywavefront library."""
    print("\nVisualizing with pywavefront...")
    scene = pywavefront.Wavefront(filename, create_materials=True)

    # Display the mesh in an interactive window
    print("-> Close the pywavefront window to exit the script.")
    draw(scene)


def get_files_from_dir(
    directory: str, file_extension: str, identifier: Optional[str] = None
) -> Union[str, List[str]]:
    """
    Retrieves a list of files with a specific extension and optional identifier from a directory.

    Args:
        directory (str): The path to the directory to search.
        file_extension (str): The file extension (e.g., 'txt', 'jpg').
        identifier (str, optional): An identifying word that must be present in the filename. Defaults to None.

    Returns:
        str or list: A single file path (str) if only one file is found,
                     a list of file paths if multiple files are found,
                     or an empty list if no files are found.
    """

    file_list = []
    try:
        for filename in os.listdir(directory):
            if filename.endswith(file_extension):
                if identifier is None or identifier in filename:
                    file_path = os.path.join(directory, filename)
                    file_path = file_path.replace("\\", "/")
                    file_list.append(file_path)
    except FileNotFoundError:
        print(f"Error: Directory '{directory}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    if len(file_list) == 1:
        return file_list[0]  # Return the single file path as a string
    else:
        return file_list  # Return the list (either empty or with multiple paths)


def run_commands_parallel(commands: List[str], number_of_workers: int = 4) -> None:
    """
    Executes a list of commands in parallel using a ThreadPoolExecutor.

    Args:
        commands (list): A list of commands to execute.
        number_of_workers (int, optional): The maximum number of worker threads. Defaults to 4.
    """

    def _run_command(command: Union[str, List[str]], command_name: Optional[str] = None) -> None:
        """
        Executes the given command in the terminal and prints the command and output.

        Args:
            command (str or list): The command to execute (as a string or list of arguments).
            command_name (str, optional): A descriptive name for the command (e.g., "rpict", "ra_tiff"). Defaults to None.
        """
        if command_name:
            print(
                f"Executing {command_name} command: {' '.join(command) if isinstance(command, list) else command}"
            )
        else:
            print(
                f"Executing command: {' '.join(command) if isinstance(command, list) else command}"
            )

        try:
            result = subprocess.run(
                command, shell=isinstance(command, str), capture_output=True, text=True, check=True
            )
            if command_name:
                print(f"{command_name} command executed successfully.")
            else:
                print("Command executed successfully.")

            if result.stdout:
                print(f"Standard output:\n{result.stdout}")
            if result.stderr:
                print(f"Standard error:\n{result.stderr}")

        except subprocess.CalledProcessError as e:
            if command_name:
                print(
                    f"Error executing {command_name} command: {' '.join(command) if isinstance(command, list) else command}"
                )
            else:
                print(
                    f"Error executing command: {' '.join(command) if isinstance(command, list) else command}"
                )

            print(f"Return code: {e.returncode}")
            if e.stderr:
                print(f"Standard error:\n{e.stderr}")

        except FileNotFoundError as e:
            print(f"Error: {e}")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=number_of_workers) as executor:
        futures = [executor.submit(_run_command, command) for command in commands]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # Get the result (or exception if any)
            except Exception as e:
                print(f"An error occurred during command execution: {e}")


def copy_files_concurrently(source_path: str, destination_paths: list):
    """
    Concurrently copies a single source file to multiple destination paths
    using a pool of threads.

    Args:
        source_path (str): The full path to the single file to be copied.
        destination_paths (list): A list of strings, where each string is a
                                  full destination path for a new copy.
    """
    try:
        # Use a ThreadPoolExecutor to manage the concurrent copy operations.
        with ThreadPoolExecutor() as executor:
            # Schedule shutil.copy to run for each destination path.
            futures = [
                executor.submit(shutil.copy, source_path, dest) for dest in destination_paths
            ]

            # This loop waits for each copy to finish and will raise an
            # exception if any of the copy operations failed.
            for future in futures:
                future.result()

        print(
            f"Successfully copied '{os.path.basename(source_path)}' to {len(destination_paths)} locations."
        )

    except Exception as e:
        print(f"An error occurred during the copy operation: {e}")
        # Optionally re-raise the exception if you want the calling code to handle it
        # raise


@dataclass
class AddMissingModifiers:
    """
    Processes a Radiance .rad file and an accompanying .mtl file to find
    modifiers defined in the .rad file that are missing from the .mtl file,
    and appends default definitions for them.
    """

    rad_filepath: str
    mtl_filepath: str

    # These fields are for internal state and results, not constructor arguments.
    # They are initialized via default_factory or in __post_init__.
    modifiers: list[str] = field(init=False, default_factory=list)
    # missing_materials is initialized as an empty list.
    # It can be set to None by _find_missing_modifiers to indicate an error during its computation.
    missing_materials: list[str] | None = field(init=False, default_factory=list)

    def __post_init__(self):
        """
        Post-initialization checks, primarily for file existence.
        This method is automatically called after the dataclass __init__.
        """
        if not os.path.exists(self.rad_filepath):
            raise FileNotFoundError(f".rad file not found: {self.rad_filepath}")
        if not os.path.exists(self.mtl_filepath):
            raise FileNotFoundError(f"Radiance .mtl file not found: {self.mtl_filepath}")

    def __get_modifiers_from_rad(self) -> bool:
        """
        Extracts unique modifiers from the .rad file and stores them in self.modifiers.

        Returns:
            bool: True if successful, False otherwise.
        """
        extracted_words = set()
        blank_line_found = False
        try:
            with open(self.rad_filepath, encoding="utf-8") as file:
                for line in file:
                    line = line.rstrip("\n")
                    if not line.strip():
                        blank_line_found = True
                    elif blank_line_found:
                        words = line.split()
                        if words:
                            extracted_words.add(words[0])
                        blank_line_found = False
            self.modifiers = sorted(list(extracted_words))  # Store sorted list
            return True
        except Exception as e:
            print(f"An error occurred while reading {self.rad_filepath}: {e}")
            self.modifiers = []  # Ensure it's an empty list on error
            return False

    def __find_missing_modifiers(self) -> bool:
        """
        Finds unique material names from self.modifiers not in the Radiance .mtl file.
        Stores them in self.missing_materials. If an error occurs, self.missing_materials is set to None.

        Returns:
            bool: True if successful (even if no missing materials), False on error.
        """
        if not self.modifiers:  # No modifiers to check against
            self.missing_materials = []
            return True

        current_missing_materials = []
        try:
            with open(self.mtl_filepath, encoding="utf-8") as file:
                radiance_mtl_content = file.read()
                radiance_defined_materials = set(
                    re.findall(r"void\s+\w+\s+(\w+)", radiance_mtl_content)
                )

            for material_name in self.modifiers:
                if material_name not in radiance_defined_materials:
                    current_missing_materials.append(material_name)

            self.missing_materials = sorted(
                list(set(current_missing_materials))
            )  # Store sorted list
            return True
        except Exception as e:
            print(
                f"An error occurred while reading or parsing the Radiance MTL file ({self.mtl_filepath}): {e}"
            )
            self.missing_materials = None  # Indicate an error state
            return False

    def __append_missing_modifiers(self) -> bool:
        """
        Appends default Radiance material definitions for self.missing_materials
        to the .mtl file if they are not already present.

        Returns:
            bool: True if successful or no materials to append, False on error.
        """

        def _default_radiance_material(material_name: str) -> list[str]:
            return [
                f"# {material_name}",
                f"void plastic {material_name}",
                "0",
                "0",
                "5 0.5 0.5 0.5 0.0 0.0",  # Default grey plastic
                "",
            ]

        if self.missing_materials is None:
            print("Cannot append materials: an error occurred when finding missing materials.")
            return False

        if not self.missing_materials:
            return True

        try:
            with open(self.mtl_filepath, "r+", encoding="utf-8") as file:
                content = file.read()
                existing_defined_materials = set(re.findall(r"void\s+\w+\s+(\w+)", content))

                materials_to_actually_append = [
                    mat for mat in self.missing_materials if mat not in existing_defined_materials
                ]

                if materials_to_actually_append:
                    file.seek(0, os.SEEK_END)
                    if content and not content.endswith(
                        ("\n", "\r\n")
                    ):  # Check for existing newline
                        file.write("\n")

                    file.write("\n# Default materials added for missing modifiers:\n")
                    for material_name in materials_to_actually_append:
                        material_definition = _default_radiance_material(material_name)
                        for line_content in material_definition:
                            file.write(line_content + "\n")
                    print(f"{len(materials_to_actually_append)} default material(s) appended.")
                else:
                    print(
                        "All previously identified missing materials are already defined or no new materials to append."
                    )
            return True
        except Exception as e:
            print(f"An error occurred while writing to {self.mtl_filepath}: {e}")
            return False

    def process_files(self) -> None:
        """
        Main processing method to find and append missing modifiers.
        """
        print(f"Processing .rad file: {self.rad_filepath}")
        print(f"Processing .mtl file: {self.mtl_filepath}")

        if not self.__get_modifiers_from_rad():
            print("Failed to get modifiers from .rad file. Aborting.")
            return

        if self.modifiers:
            print(
                f"\nFound {len(self.modifiers)} unique modifier(s) in {os.path.basename(self.rad_filepath)}."
            )
        else:
            print(f"\nNo modifiers found in {os.path.basename(self.rad_filepath)}.")
            return

        if not self.__find_missing_modifiers():
            print("Failed to find missing modifiers. Aborting.")
            return

        if self.missing_materials is None:
            print("\nError occurred during material comparison. Cannot proceed with appending.")
        elif self.missing_materials:
            print(
                f"\nFound {len(self.missing_materials)} missing material(s) that need definitions in {os.path.basename(self.mtl_filepath)}:"
            )
            for material_name in self.missing_materials:
                print(f"  {material_name}")

            if self.__append_missing_modifiers():
                print(f"\nSuccessfully processed missing materials for {self.mtl_filepath}")
            else:
                print(f"\nFailed to append default materials to {self.mtl_filepath}.")
        else:
            print(
                f"\nAll modifiers from {os.path.basename(self.rad_filepath)} were found in {os.path.basename(self.mtl_filepath)}."
            )

        print("\nProcessing complete.")


@dataclass
class ObjToOctree:
    """
    Converts material definitions from a Wavefront .mtl file
    (e.g., exported from Revit) into a Radiance material description file.

    The converter processes common .mtl properties like diffuse color ('Kd')
    and dissolve/opacity ('d') to create Radiance 'plastic' (for opaque)
    or 'glass' (for transparent/translucent) materials.

    Attributes:
        mtl_file_path (str): The full path to the input .mtl file used for conversion.
        output_file_name (str | None): The full path to the generated Radiance .mtl file.
                                     This is set upon successful conversion, otherwise None.
        converted_content (str | None): The Radiance formatted string of the materials.
                                       Set upon successful conversion, otherwise None.
    """

    # User inputs
    input_mtl_file_path: str | None = None
    obj_file_path: str | None = None

    # variables for use within class functions
    radiance_mtl_file_path: str | None = None
    rad_file_path: str | None = None

    def __convert_mtl_materials(self, mtl_content: str) -> str:  # <-- Added self
        """
        Converts .mtl material entries to Radiance material format.
        Args:
            mtl_content: The content of the .mtl file as a string.
        Returns:
            The converted content as a string.
        """

        def _format_radiance_glass(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void glass {name}",
                "0",
                "0",
                f"3 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f}",
            ]

        def _format_radiance_plastic(material):
            name = material["name"]
            kd = material.get("Kd", [0.0, 0.0, 0.0])
            return [
                f"\n# {name}",
                f"void plastic {name}",
                "0",
                "0",
                f"5 {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f} 0.000 0.005",
            ]

        lines = mtl_content.splitlines()
        converted_lines = ["# Third line parameters: R G B Sp Rg"]
        current_material = {}

        for line in lines:
            line = line.strip()
            if line.startswith("newmtl"):
                if current_material:
                    if current_material.get("d", 1.0) < 1.0:
                        converted_lines.extend(_format_radiance_glass(current_material))
                    elif current_material.get("d", 1.0) == 1.0:
                        converted_lines.extend(_format_radiance_plastic(current_material))
                material_name = line.split(" ", 1)[1]
                current_material = {"name": material_name}
            elif line.startswith("Kd"):
                current_material["Kd"] = [float(x) for x in line.split()[1:]]
            elif line.startswith("d"):
                current_material["d"] = float(line.split()[1])
            elif line and not line.startswith("#"):
                pass

        if current_material:
            if current_material.get("d", 1.0) < 1.0:
                converted_lines.extend(_format_radiance_glass(current_material))
            elif current_material.get("d", 1.0) == 1.0:
                converted_lines.extend(_format_radiance_plastic(current_material))

        return "\n".join(converted_lines)

    def parse_mtl_file(self) -> None:
        """
        Read .mtl file specified by mtl_file_to_parse, convert its content, and save.
        Updates the instance's mtl_file_path, output_file_name, and converted_content.

        Args:
            mtl_file_to_parse (str): The full path to the .mtl file to parse.
        """

        try:
            with open(self.input_mtl_file_path) as file:
                mtl_content = file.read()

            # Call instance method convert_mtl_materials using self
            converted_content = self.__convert_mtl_materials(mtl_content)  # <-- Use self.

            # Create the output file name
            # Use self.input_mtl_file_path for deriving output name
            self.radiance_mtl_file_path = (
                os.path.splitext(self.input_mtl_file_path)[0] + "_radiance.mtl"
            )

            # Write the output to the new file
            with open(self.radiance_mtl_file_path, "w") as output_file:
                output_file.write("#Radiance Map file:\n")
                output_file.write(converted_content)

            print(f"Radiance material file created: {self.radiance_mtl_file_path}")

        except FileNotFoundError:
            # Use self.mtl_file_path in error message
            print(f"Error: File not found at {self.radiance_mtl_file_path}")
        except Exception as e:
            print(f"An error occurred: {e}")

    def obj_to_rad(self, obj_file_to_parse: str, mtl_file_to_parse: str) -> None:
        """
        convert obj file to radiance description file ready to be compiled into an octree for rendering scenes.
        obj2rad "C:\\VE Projects\\! - code\\Run 1\1_obj_and_sky_to_oct\222050_R22_86 COWLES RD.obj" > 222050_R22_86 COWLES RD.rad
        Obj files must be exported from Revit in meters not mm.
        """

        self.obj_file_path = obj_file_to_parse  # Set/update the instance attribute
        self.input_mtl_file_path = mtl_file_to_parse  # Set/update the instance attribute

        try:
            output_rad_file_name = obj_file_to_parse.replace(".obj", ".rad")
            self.rad_file_path = output_rad_file_name

            print(f"Attempting to convert \n {obj_file_to_parse} \n to \n {output_rad_file_name}")
            # Ensure the rad_file directory exists

            os.makedirs(os.path.dirname(output_rad_file_name), exist_ok=True)

            # Run the obj2rad command
            command = ["obj2rad", obj_file_to_parse]
            with open(output_rad_file_name, "w") as rad_output:
                subprocess.run(command, stdout=rad_output, check=True)

            # Verify if the rad_file was created
            if not os.path.exists(output_rad_file_name):
                raise FileNotFoundError(f"Expected RAD file not found: {output_rad_file_name}")
            print(f"Successfully converted \n {obj_file_to_parse} \n to \n {output_rad_file_name}")
            print(
                f"Attempting to add missing modifiers to \n {self.radiance_mtl_file_path} \n from \\ n {self.rad_file_path}"
            )

            # parse original .mtl file
            self.parse_mtl_file()

            AddMissingModifiers(self.rad_file_path, self.radiance_mtl_file_path).process_files()

        except Exception as e:
            print(f"Error converting {obj_file_to_parse} \n to \n {output_rad_file_name}: {e}")
            raise

    def rad_to_octree(self, output_dir: str = "octrees") -> None:
        r"""
        Runs the oconv command to generate frozen skyless octree for use in rendering. Sky file will be added just prior to rendering.
        must use command prompt intead of powershell in vs code as its default coding is utf-8
        Example from IESVE
        To use the below command prompt, a sky file must be added. Note that the rest of this function produces skyless octress for later processing with sunny sky files.
        oconv -f sky/Jun21_1100_ss.sky lib/87example_radiance.mtl lib/87cowles.rad > octrees/87_example_Jun21_1100_ss.oct
        oconv -f lib\87cowles_noWindows_radiance.mtl lib\87cowles_noWindows.obj
        """

        geometry_rad_base = os.path.basename(self.rad_file_path)
        geometry_rad_base_no_ext = os.path.splitext(geometry_rad_base)[0]

        output_filename = os.path.join(output_dir, f"{geometry_rad_base_no_ext}_skyless.oct")
        command = ["oconv", "-f", self.radiance_mtl_file_path, self.rad_file_path]
        with open(output_filename, "w") as outfile:
            process = subprocess.Popen(command, stdout=outfile, stderr=subprocess.PIPE)
            _, stderr = process.communicate()

        if stderr:
            print(f"Error running oconv : {stderr.decode()}")
        else:
            print(f"Successfully generated: {output_filename}")


def execute_new_radiance_commands(commands: List[str], number_of_workers: int = 1) -> None:
    """
    This code is running the below line in the terminal with various combinations of inputs .oct and .sky files.
    oconv -i octrees/87cowles_skyless.oct sky/sunny_sky_0621_0900.sky > octrees/87cowles_sunny_sky_0621_0900.oct
    rpict -vf views_grids/plan_L01.vp -x 1024 -y 1024 -ab 3 -ad 128 -ar 64 -as 64 -ps 6 octrees/87cowles_SS_0621_1030.oct > results/87cowles_plan_L01_SS_0621_1030.hdr
    ra_tiff results/87cowles_SS_0621_1030.hdr results/87cowles_SS_0621_1030.tiff

    # Accelerad rpict
    must set cuda enable GPU prior to executing the accelerad_rpict command below.
    check CUDA GPUs
    nvidia-smi
    Command
    med | accelerad_rpict -vf views_grids\floorplate_view_L1.vp -x 1024 -y 1024 -ab 1 -ad 1024 -ar 256 -as 256 -ps 5 octrees/untitled_Jun21_0940.oct > results/untitled_floor_plate_Jun21_0940_med_accelerad.hdr

    high |  rpict -vf views_grids\view.vp -x 1024 -y 1024 -ab 2 -ad 1024 -ar 256 -as 256 -ps 5 octrees/untitled_Jun21_0940.oct > results/untitled_floor_plate_Jun21_0940_high.hdr
    """
    filtered_commands = []
    for command in commands:
        # Add this check to skip empty or whitespace-only strings
        if not command or not command.strip():
            continue
        try:
            # First, try splitting by the '>' operator
            output_path = command.split(" > ")[1].strip()
        except IndexError:
            # If that fails, it's likely a command like ra_tiff.
            # Split by spaces and take the last element.
            output_path = command.split()[-1].strip()

        # Now, check if the extracted path exists
        if not os.path.exists(output_path):
            filtered_commands.append(command)

    run_commands_parallel(
        filtered_commands,
        number_of_workers=number_of_workers,  # number of workers should not go over 6 for oconv
    )

    print("All new commands have successfully completed")

    return
