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
