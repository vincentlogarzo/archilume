# Archilume imports

# Standard library imports
import concurrent.futures
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Union
from PIL import Image

# Third-party imports
import numpy as np
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
    
    # View transformation helper functions
    def set_top_view(vis):
        """Set camera to top view (looking down Z-axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([0, 0, -1])
        view_ctrl.set_up([0, 1, 0])
        return False
    
    def set_front_view(vis):
        """Set camera to front view (looking along +Y axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([0, 1, 0])
        view_ctrl.set_up([0, 0, 1])
        return False
    
    def set_back_view(vis):
        """Set camera to back view (looking along -Y axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([0, -1, 0])
        view_ctrl.set_up([0, 0, 1])
        return False
    
    def set_left_view(vis):
        """Set camera to left view (looking along +X axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([1, 0, 0])
        view_ctrl.set_up([0, 0, 1])
        return False
    
    def set_right_view(vis):
        """Set camera to right view (looking along -X axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([-1, 0, 0])
        view_ctrl.set_up([0, 0, 1])
        return False
    
    def set_bottom_view(vis):
        """Set camera to bottom view (looking up Z-axis)"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_front([0, 0, 1])
        view_ctrl.set_up([0, -1, 0])
        return False
    
    def reset_view(vis):
        """Reset to default view"""
        view_ctrl = vis.get_view_control()
        view_ctrl.set_zoom(0.8)
        return False
    
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
    
    # Try to use VisualizerWithKeyCallback if available, otherwise use regular Visualizer
    try:
        vis = o3d.visualization.VisualizerWithKeyCallback()
        has_key_callback = True
    except AttributeError:
        vis = o3d.visualization.Visualizer()
        has_key_callback = False
    
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
    render_opt.mesh_show_wireframe = True  # Show wireframe by default
    render_opt.point_size = 2.0
    render_opt.line_width = 1.0
    
    # Set up view control for better navigation
    view_ctrl = vis.get_view_control()
    
    # Register key callbacks if available
    if has_key_callback:
        try:
            vis.register_key_callback(ord('1'), set_top_view)
            vis.register_key_callback(ord('2'), set_front_view)
            vis.register_key_callback(ord('3'), set_back_view)
            vis.register_key_callback(ord('4'), set_left_view)
            vis.register_key_callback(ord('5'), set_right_view)
            vis.register_key_callback(ord('6'), set_bottom_view)
            vis.register_key_callback(ord('R'), reset_view)
            vis.register_key_callback(ord('r'), reset_view)
        except Exception as e:
            print(f"   Note: Key callback registration failed: {e}")
            has_key_callback = False
    
    if not has_key_callback:
        print("   Note: Keyboard view shortcuts not available in this Open3D version")
    
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
    print("")
    if has_key_callback:
        print("-> Orthographic View Controls:")
        print("   1: Top view (looking down)")
        print("   2: Front view")
        print("   3: Back view") 
        print("   4: Left view")
        print("   5: Right view")
        print("   6: Bottom view (looking up)")
        print("   R: Reset to default view")
    else:
        print("-> Manual View Controls:")
        print("   Use mouse and standard Open3D controls for navigation")
    print("-> Close the window to continue.")
    
    # Run the visualizer
    vis.run()
    vis.destroy_window()

def display_ifc(filename: Path):
    """
    # TODO: Implement IFC file visualization using ifcopenshell, and allow colour checking and editing potentially through ThatOpenCompany
    """
    return None

def copy_files(source_path: Union[Path, str], destination_paths: list[Path]) -> None:
    """
    Concurrently copies a single source file to multiple destination paths
    using a pool of threads.

    Args:
        source_path (str): The full path to the single file to be copied.
        destination_paths (list): A list of strings, where each string is a
                                  full destination path for a new copy.
    
    Returns:
        list: A list of destination paths that were successfully copied to.
    """
    try:
        # Filter out destination paths that already exist
        filtered_paths = [dest for dest in destination_paths if not os.path.exists(dest)]
        
        if not filtered_paths:
            print(f"All destination paths already exist. No files to copy.")
        
        if len(filtered_paths) < len(destination_paths):
            skipped_count = len(destination_paths) - len(filtered_paths)
            print(f"Skipping {skipped_count} existing destination(s).")
        
        # Use a ThreadPoolExecutor to manage the concurrent copy operations.
        with ThreadPoolExecutor() as executor:
            # Schedule shutil.copy to run for each destination path.
            futures = [
                executor.submit(shutil.copy, source_path, dest) for dest in filtered_paths
            ]

            # This loop waits for each copy to finish and will raise an
            # exception if any of the copy operations failed.
            for future in futures:
                future.result()

        print(
            f"Successfully copied '{os.path.basename(source_path)}' to {len(filtered_paths)} locations."
        )

    except Exception as e:
        print(f"An error occurred during the copy operation: {e}")

def delete_files(file_paths: list[Path]) -> None:
    """
    Deletes files from a list of Path objects using pathlib's unlink() method.
    
    Args:
        file_paths (list[Path]): List of Path objects to delete.
    """
    deleted_count = 0
    skipped_count = 0
    
    for file_path in file_paths:
        try:
            if file_path.exists():
                file_path.unlink()
                deleted_count += 1
                print(f"Deleted: {file_path.name}")
            else:
                skipped_count += 1
                print(f"Skipped (not found): {file_path.name}")
        except Exception as e:
            print(f"Error deleting {file_path.name}: {e}")
            skipped_count += 1
    
    print(f"Deletion complete: {deleted_count} deleted, {skipped_count} skipped")
         
def execute_new_radiance_commands(commands: Union[str, list[str]] , number_of_workers: int = 1) -> None:
    """
    Executes Radiance commands in parallel, filtering out commands whose output files already exist.
    
    This function takes a single command string or list of Radiance commands (oconv, rpict, ra_tiff) 
    and executes only those whose output files don't already exist, avoiding redundant computation.
    
    Args:
        commands (str or list[str]): Single command string or list of command strings to execute. 
                                   Each command should be a valid shell command that outputs to a file 
                                   using '>' redirection or specifies an output file as the last argument.
        number_of_workers (int, optional): Number of parallel workers for command execution.
                                         Defaults to 1. Should not exceed 6 for oconv commands.
    
    Returns:
        None: Function executes commands and prints completion message.
        
    Note:
        Commands are filtered based on whether their output files exist. The function
        attempts to extract output paths by splitting on '>' operator first, then
        falls back to using the last space-separated argument for commands like ra_tiff.
    """ 
    def _execute_commands_with_progress(commands: List[str], number_of_workers: int = 1) -> None:
        """
        Executes commands with real-time progress output by streaming stdout/stderr.
        
        Args:
            commands (List[str]): List of commands to execute
            number_of_workers (int): Number of parallel workers
        """
        def _run_command_with_progress(command: str) -> None:
            """Execute a single command with real-time output streaming."""
            print(f"Starting: {command}")
            
            try:
                # Use Popen for real-time output streaming
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1  # Line buffered
                )
                
                # Stream output in real-time
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        print(output.strip())
                
                # Wait for process to complete and get return code
                return_code = process.poll()
                
                if return_code == 0:
                    print(f"✓ Completed successfully: {command}")
                else:
                    print(f"✗ Failed with return code {return_code}: {command}")
                    
            except Exception as e:
                print(f"✗ Error executing command '{command}': {e}")
        
        if number_of_workers == 1:
            # Sequential execution for single worker
            for command in commands:
                _run_command_with_progress(command)
        else:
            # Parallel execution
            with concurrent.futures.ThreadPoolExecutor(max_workers=number_of_workers) as executor:
                futures = [executor.submit(_run_command_with_progress, command) for command in commands]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"Error in parallel execution: {e}")

    # Handle single command string input
    if isinstance(commands, str):
        commands = [commands]
    
    filtered_commands = []
    for command in commands:
        try:
            # First, try splitting by the '>' operator
            output_path = command.split(' > ')[1].strip()
        except IndexError:
            # If that fails, it's likely a command like ra_tiff.
            # Split by spaces and take the last element.
            output_path = command.split()[-1].strip()

        # Now, check if the extracted path exists
        if not os.path.exists(output_path):
            filtered_commands.append(command)

    _execute_commands_with_progress(
        filtered_commands,
        number_of_workers=number_of_workers
    )

    print('All new commands have successfully completed')

def get_image_dimensions(image_path) -> None:
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

def combine_gifs(gif_paths: list[Path], output_path: Path, duration: int=100) -> None:
    """Combine multiple GIF files into a single animated GIF.
    
    Takes a list of GIF file paths and combines them sequentially into a single
    animated GIF file. All input GIFs are appended as frames in the output animation.
    
    Args:
        gif_paths: List of Path objects pointing to the input GIF files to combine
        output_path: Path where the combined GIF will be saved
        duration: Duration in milliseconds for each frame in the output GIF (default: 100)
        
    Returns:
        None
        
    Raises:
        PIL.UnidentifiedImageError: If any of the input files are not valid images
        FileNotFoundError: If any of the input GIF files don't exist
        PermissionError: If unable to write to the output path
        
    Example:
        >>> gif_files = [Path('frame1.gif'), Path('frame2.gif'), Path('frame3.gif')]
        >>> combine_gifs(gif_files, Path('animation.gif'), duration=200)
    """
    
    gifs = [Image.open(f) for f in gif_paths]
    gifs[0].save(output_path, save_all=True, append_images=gifs[1:], 
                 duration=duration, loop=0)

def combine_gifs_by_view(image_dir: Path, view_files: list[Path], duration: int=500) -> None:
    """Create separate animated GIFs grouped by view file names, plus a combined animation.
    
    Scans the image directory for GIF files and groups them by view file names. Creates
    separate animated GIFs for each view and one combined animation with all GIFs.
    
    Args:
        image_dir: Directory containing the GIF files to process
        view_files: List of view file Path objects used to group GIFs by name
        duration: Duration in milliseconds for each frame in the output GIFs (default: 500)
        
    Returns:
        None
        
    Example:
        >>> view_files = [Path('plan_L02.vp'), Path('section_A.vp')]
        >>> combine_gifs_by_view(Path('outputs/images'), view_files, duration=300)
    """
    gif_files = [path for path in image_dir.glob('*.gif')]
    
    # Filter out previously created result files to avoid circular references
    gif_files = [gif for gif in gif_files if not gif.name.startswith('animated_results_') and gif.name != 'grid_animation_9windows.gif']
    
    if not gif_files:
        print("No GIF files found in the image directory (excluding result files).")
        return
    
    # Create separate animated GIFs for each view file
    for view_file in view_files:
        view_name = view_file.stem
        # Find all GIF files that contain this view name
        view_gif_files = [gif for gif in gif_files if view_name in gif.name]
        
        if view_gif_files:
            output_gif_path = image_dir / f'animated_results_{view_name}.gif'
            # Delete existing file if it exists
            if output_gif_path.exists():
                output_gif_path.unlink()
            combine_gifs(view_gif_files, output_gif_path, duration)
            print(f"Created animation for {view_name}: {len(view_gif_files)} frames")

def create_grid_gif(gif_paths: list[Path], image_dir: Path, grid_size: tuple=(3, 3), 
                   target_size: tuple=(200, 200), duration: int=500) -> None:
    """Create a grid layout GIF combining multiple individual GIFs.
    
    Takes multiple GIF files and combines them into a single animated GIF with a grid layout.
    Each individual GIF is resized to fit within the grid cells.
    
    Args:
        gif_paths: List of Path objects pointing to input GIF files
        output_path: Path where the grid GIF will be saved
        grid_size: Tuple (cols, rows) defining the grid dimensions (default: 3x3)
        target_size: Tuple (width, height) for each cell in pixels (default: 200x200)
        duration: Duration in milliseconds for each frame (default: 500)
        
    Returns:
        None
        
    Example:
        >>> gif_files = [Path('view1.gif'), Path('view2.gif'), Path('view3.gif')]
        >>> create_grid_gif(gif_files, Path('grid_animation.gif'), grid_size=(2, 2))
    """
    if not gif_paths:
        print("No GIF files provided for grid creation.")
        return
    
    output_path = image_dir / "animated_results_grid_all_levels.gif"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Delete existing output file if it exists
    if output_path.exists():
        output_path.unlink()
    
    cols, rows = grid_size
    cell_width, cell_height = target_size
    total_width = cols * cell_width
    total_height = rows * cell_height
    
    # Load all GIFs and get their frame counts
    gifs_data = []
    max_frames = 0
    
    for gif_path in gif_paths[:cols * rows]:  # Limit to grid capacity
        gif = Image.open(gif_path)
        frames = []
        try:
            while True:
                # Resize frame to fit cell
                frame = gif.copy().resize((cell_width, cell_height), Image.Resampling.LANCZOS)
                frames.append(frame)
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        
        gifs_data.append(frames)
        max_frames = max(max_frames, len(frames))
    
    # Create grid frames
    grid_frames = []
    for frame_idx in range(max_frames):
        grid_frame = Image.new('RGB', (total_width, total_height), (0, 0, 0))
        
        for i, gif_frames in enumerate(gifs_data):
            row = i // cols
            col = i % cols
            
            # Use modulo to loop shorter GIFs
            frame = gif_frames[frame_idx % len(gif_frames)]
            
            x = col * cell_width
            y = row * cell_height
            grid_frame.paste(frame, (x, y))
        
        grid_frames.append(grid_frame)
    
    # Save grid animation
    if grid_frames:
        grid_frames[0].save(
            output_path,
            save_all=True,
            append_images=grid_frames[1:],
            duration=duration,
            loop=0
        )
        print(f"Created grid animation: {len(grid_frames)} frames, {len(gifs_data)} views in {cols}x{rows} grid")


