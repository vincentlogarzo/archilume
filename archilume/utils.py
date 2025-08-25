# Archilume imports

# Standard library imports
import concurrent.futures
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Union

# Third-party imports
import open3d as o3d
import tkinter as tk
from tkinter import filedialog
from PIL import Image


def select_files(title: str = "Select file(s)") -> Optional[List[str]]:
    """
    Opens a file dialog to select multiple files from inputs folder.

    Args:
        title (str): Dialog window title. Defaults to "Select file(s)".

    Returns:
        List[str] or None: List of file paths if files are selected,
                          None if dialog is cancelled.
    """
    root = tk.Tk()
    root.withdraw()
    
    # Set initial directory to inputs folder, fall back to current dir if not found
    inputs_dir = os.path.join(os.getcwd(), "inputs")
    initial_dir = inputs_dir if os.path.exists(inputs_dir) else os.getcwd()

    file_paths = filedialog.askopenfilenames(
        initialdir=initial_dir,
        title=title,
        parent=root,
    )
    root.destroy()
    return list(file_paths) if file_paths else None

def display_obj(filenames: Union[str, Path, List[Union[str, Path]]]):
    """Displays one or more OBJ files using the open3d library with enhanced visualization and navigation."""
    # Handle single file input
    if isinstance(filenames, (str, Path)):
        filenames = [filenames]
    
    print(f"Visualizing {len(filenames)} OBJ file(s) with open3d...")
    
    combined_mesh = o3d.geometry.TriangleMesh()
    valid_files = []
    
    # Load and combine all meshes
    for filename in filenames:
        # Convert to Path object if string
        if isinstance(filename, str):
            filename = Path(filename)
        
        print(f"Loading: {filename.name}")
        
        # Read the mesh from the file
        mesh = o3d.io.read_triangle_mesh(str(filename))

        if len(mesh.vertices) == 0:
            print(f"Warning: No vertices found in {filename.name}")
            continue
        
        valid_files.append(filename)
        
        # Compute normals for proper lighting
        if not mesh.has_vertex_normals():
            mesh.compute_vertex_normals()

        # Apply different colors for each mesh for distinction
        color_index = len(valid_files) - 1
        colors = [[0.8, 0.2, 0.2], [0.2, 0.8, 0.2], [0.2, 0.2, 0.8], [0.8, 0.8, 0.2], [0.8, 0.2, 0.8], [0.2, 0.8, 0.8]]
        mesh.paint_uniform_color(colors[color_index % len(colors)])
        
        # Combine meshes
        combined_mesh += mesh
    
    if len(valid_files) == 0:
        print("No valid OBJ files found.")
        return
    
    # Create coordinate frame for reference
    coordinate_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)
    
    # Create wireframe for better structure visualization
    wireframe = o3d.geometry.LineSet.create_from_triangle_mesh(combined_mesh)
    wireframe.paint_uniform_color([0.2, 0.2, 0.2])

    # Create a visualizer with custom controls
    file_names = [f.name for f in valid_files]
    window_title = f"OBJ Viewer - {', '.join(file_names)}" if len(valid_files) <= 3 else f"OBJ Viewer - {len(valid_files)} files"
    
    vis = o3d.visualization.Visualizer()
    vis.create_window(window_name=window_title, width=1200, height=800)
    
    # Add geometries
    vis.add_geometry(combined_mesh)
    vis.add_geometry(wireframe)
    vis.add_geometry(coordinate_frame)
    
    # Get render option and enable additional features
    render_opt = vis.get_render_option()
    render_opt.show_coordinate_frame = True
    render_opt.background_color = [0.1, 0.1, 0.1]  # Dark background
    render_opt.mesh_show_back_face = True
    render_opt.mesh_show_wireframe = False  # We have custom wireframe
    render_opt.point_size = 2.0
    render_opt.line_width = 1.0
    
    # Set up view control for better navigation
    view_ctrl = vis.get_view_control()
    
    # Center the view on the mesh
    vis.poll_events()
    vis.update_renderer()
    view_ctrl.set_zoom(0.8)
    
    # Display enhanced controls
    print("-> Enhanced Navigation Controls:")
    print("   Mouse + drag: Rotate view")
    print("   Mouse wheel: Zoom in/out")
    print("   Ctrl + mouse drag: Pan view")
    print("   R: Reset view")
    print("   F: Toggle fullscreen")
    print("   H: Print help")
    print("   Q or ESC: Exit")
    print("   S: Save screenshot")
    print("   P: Toggle point cloud mode")
    print("   L: Toggle lighting")
    print("   W: Toggle wireframe mode")
    print("-> Close the window to continue.")
    
    # Run the visualizer
    vis.run()
    vis.destroy_window()

def display_ifc(filename: Path):
    """
    TODO: Implement IFC file visualization using ifcopenshell, and allow colour checking and editing potentially through ThatOpenCompany
    """
    return None

def get_files_from_dir(directory: str, file_extension: str, identifier: Optional[str] = None) -> Union[str, List[str]]:
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

def run_commands_parallel(commands: List[str], number_of_workers: int = 1) -> None:
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
            print(f"Executing {command_name} command: {' '.join(command) if isinstance(command, list) else command}")
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
                print(f"Error executing {command_name} command: {' '.join(command) if isinstance(command, list) else command}")
            else:
                print(f"Error executing command: {' '.join(command) if isinstance(command, list) else command}"
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

