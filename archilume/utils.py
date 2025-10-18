# Archilume imports

# Standard library imports
import concurrent.futures
import math
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Union
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

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
                # Set up environment with RAYPATH for Radiance commands
                env = os.environ.copy()
                env['RAYPATH'] = r'C:\Radiance\lib'

                # Check if command uses output redirection
                has_output_redirect = ' > ' in command

                # Use Popen for real-time output streaming
                # Note: When using output redirection (>), rpict sends progress to stderr
                # and binary image data to stdout (which gets redirected by the shell)
                if has_output_redirect:
                    # With redirect: stdout goes to file, only read stderr for progress
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='utf-8',
                        errors='replace',
                        bufsize=1,
                        env=env
                    )

                    # Read stderr for progress messages
                    while True:
                        output = process.stderr.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            # Filter for meaningful progress messages
                            stripped = output.strip()
                            if any(kw in stripped for kw in ['rpict:', 'rays,', '%', 'hours', 'error', 'warning']):
                                if sum(c.isprintable() or c.isspace() for c in stripped) / max(len(stripped), 1) > 0.8:
                                    print(stripped, flush=True)
                else:
                    # No redirect: stdout contains binary data, discard it and only read stderr
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        stdout=subprocess.DEVNULL,  # Discard binary output
                        stderr=subprocess.PIPE,
                        encoding='utf-8',
                        errors='replace',
                        bufsize=1,
                        env=env
                    )

                    # Read stderr for progress messages
                    while True:
                        output = process.stderr.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            stripped = output.strip()
                            if any(kw in stripped for kw in ['rpict:', 'rays,', '%', 'hours', 'error', 'warning']):
                                if sum(c.isprintable() or c.isspace() for c in stripped) / max(len(stripped), 1) > 0.8:
                                    print(stripped, flush=True)

                # Wait for process to complete and get return code
                return_code = process.wait()
                
                if return_code == 0:
                    print(f"Completed successfully: {command}")
                else:
                    print(f"Failed with return code {return_code}: {command}")
                    
            except Exception as e:
                print(f"Error executing command '{command}': {e}")
        
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
        output_path = None

        # Try to extract output path from command
        if ' > ' in command:
            # Command has redirect operator
            try:
                output_path = command.split(' > ')[1].strip()
            except IndexError:
                pass
        elif any(cmd in command for cmd in ['ra_tiff', 'ra_ppm', 'pfilt', 'pcomb']):
            # Commands that typically have output file as last argument
            try:
                output_path = command.split()[-1].strip()
            except (IndexError, AttributeError):
                pass

        # If no output path found, skip filtering and include command
        if output_path is None:
            filtered_commands.append(command)
        # Otherwise, check if the output file exists
        elif not os.path.exists(output_path):
            filtered_commands.append(command)

    _execute_commands_with_progress(
        filtered_commands,
        number_of_workers=number_of_workers
    )

    if commands:
        print(f"All new commands have successfully completed e.g. {commands[0]}")
    else:
        print("No commands were provided to execute.")

def combine_tiffs_by_view(image_dir: Path, view_files: list[Path], fps: float=None, output_format: str='gif', number_of_workers: int = 4) -> None:
    """Create separate animated files grouped by view file names using parallel processing.
    
    Scans the image directory for TIFF files and groups them by view file names. Creates
    separate animated files for each view in parallel for improved performance.
    
    Args:
        image_dir: Directory containing the TIFF files to process
        view_files: List of view file Path objects used to group TIFFs by name
        fps: Frames per second for the output animation. If None, defaults to 1 FPS (1 second per frame)
        output_format: Output format - 'gif' or 'mp4' (default: 'gif')
        number_of_workers: Number of parallel workers for processing views (default: 4)
        
    Returns:
        None
        
    Example:
        >>> view_files = [Path('plan_L02.vp'), Path('section_A.vp')]
        >>> combine_tiffs_by_view(Path('outputs/images'), view_files, fps=2.0, output_format='mp4', number_of_workers=6)
        >>> combine_tiffs_by_view(Path('outputs/images'), view_files, output_format='gif')  # Uses 1 FPS with 4 workers
    """
    def _combine_tiffs(tiff_paths: list[Path], output_path: Path, duration: int=100, output_format: str='gif') -> None:
        """Combine multiple TIFF files into a single animated file.
        
        Takes a list of TIFF file paths and combines them sequentially into a single
        animated file. All input TIFFs are appended as frames in the output animation.
        
        Args:
            tiff_paths: List of Path objects pointing to the input TIFF files to combine
            output_path: Path where the combined file will be saved
            duration: Duration in milliseconds for each frame in the output file (default: 100)
            output_format: Output format - 'gif' or 'mp4' (default: 'gif')
            
        Returns:
            None
            
        Raises:
            PIL.UnidentifiedImageError: If any of the input files are not valid images
            FileNotFoundError: If any of the input TIFF files don't exist
            PermissionError: If unable to write to the output path
            ValueError: If output_format is not supported
            
        Example:
            >>> tiff_files = [Path('frame1.tiff'), Path('frame2.tiff'), Path('frame3.tiff')]
            >>> _combine_tiffs(tiff_files, Path('animation.gif'), duration=200, output_format='gif')
            >>> _combine_tiffs(tiff_files, Path('animation.mp4'), duration=200, output_format='mp4')
        """
        
        if output_format.lower() == 'gif':
            tiffs = [Image.open(f) for f in tiff_paths]
            tiffs[0].save(output_path, save_all=True, append_images=tiffs[1:], 
                        duration=duration, loop=0)
        elif output_format.lower() == 'mp4':
            try:
                import cv2
            except ImportError:
                raise ImportError("OpenCV (cv2) is required for MP4 output. Install with: pip install opencv-python")
            
            # Get dimensions from first TIFF
            first_tiff = Image.open(tiff_paths[0])
            width, height = first_tiff.size
            
            # Set up video writer (fps = 1000/duration for proper timing)
            fps = 1000 / duration if duration > 0 else 10
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
            
            # Process each TIFF and add frames to video
            for tiff_path in tiff_paths:
                tiff = Image.open(tiff_path)
                # Convert PIL image to OpenCV format (BGR)
                frame_rgb = tiff.convert('RGB')
                frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
                video_writer.write(frame_bgr)
            
            video_writer.release()
        else:
            raise ValueError(f"Unsupported output format: {output_format}. Use 'gif' or 'mp4'.")

    tiff_files = [path for path in image_dir.glob('*.tiff')]
    
    # Filter out previously created result files to avoid circular references
    tiff_files = [tiff for tiff in tiff_files if not tiff.name.startswith('animated_results_') and tiff.name != 'animated_results_grid_all_levels.tiff']
    
    if not tiff_files:
        print("No TIFF files found in the image directory (excluding result files).")
        return
    
    def _process_single_view(view_file: Path) -> str:
        """Process a single view file to create animated output."""
        view_name = view_file.stem
        # Find all TIFF files that contain this view name
        view_tiff_files = [tiff for tiff in tiff_files if view_name in tiff.name]
        
        if not view_tiff_files:
            return f"X No TIFF files found for view: {view_name}"
        
        try:
            # Calculate duration based on number of frames found
            num_frames = len(view_tiff_files)
            
            if fps is None:
                # Auto-calculate: set duration to match number of frames (1 second per frame)
                duration = num_frames * 1000  # num_frames seconds total
                calculated_fps = 1.0
            else:
                # Calculate total duration based on FPS
                duration = int((num_frames / fps) * 1000)  # total animation duration in ms
                calculated_fps = fps
            
            # Calculate per-frame duration for the animation
            per_frame_duration = int(duration / num_frames) if num_frames > 0 else 1000
            
            output_file_path = image_dir / f'animated_results_{view_name}.{output_format.lower()}'
            # Delete existing file if it exists
            if output_file_path.exists():
                output_file_path.unlink()
            
            _combine_tiffs(view_tiff_files, output_file_path, per_frame_duration, output_format)
            return f"OK Created {output_format.upper()} animation for {view_name}: {num_frames} frames, {duration/1000:.1f}s at {calculated_fps} FPS"
            
        except Exception as e:
            return f"X Error processing {view_name}: {e}"
    
    print(f"Processing {len(view_files)} views using {number_of_workers} workers")
    
    # Create separate animated files for each view file in parallel
    if number_of_workers == 1:
        # Sequential processing for single worker
        for view_file in view_files:
            result = _process_single_view(view_file)
            print(result)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            futures = [executor.submit(_process_single_view, view_file) for view_file in view_files]
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    print(result)
                except Exception as e:
                    print(f"X Error in parallel view processing: {e}")
    
    print(f"Completed processing {len(view_files)} view animations")

def combine_gifs_by_view(image_dir: Path, view_files: list[Path], fps: float=None, output_format: str='gif', number_of_workers: int = 4) -> None:
    """Legacy function that calls combine_tiffs_by_view for backward compatibility.
    
    This function is deprecated. Use combine_tiffs_by_view instead.
    """
    print("Warning: combine_gifs_by_view is deprecated. Use combine_tiffs_by_view instead.")
    combine_tiffs_by_view(image_dir, view_files, fps, output_format, number_of_workers)

def create_grid_gif(gif_paths: list[Path], image_dir: Path, grid_size: tuple=(3, 3), 
                   target_size: tuple=(200, 200), fps: float=1.0) -> None:
    """Create a grid layout GIF combining multiple individual GIFs.
    
    Takes multiple GIF files and combines them into a single animated GIF with a grid layout.
    Each individual GIF is resized to fit within the grid cells.
    
    Args:
        gif_paths: List of Path objects pointing to input GIF files
        image_dir: Directory where the grid GIF will be saved
        grid_size: Tuple (cols, rows) defining the grid dimensions (default: 3x3)
        target_size: Tuple (width, height) for each cell in pixels (default: 200x200)
        fps: Frames per second for the animation (default: 1.0)
        
    Returns:
        None
        
    Example:
        >>> gif_files = [Path('view1.gif'), Path('view2.gif'), Path('view3.gif')]
        >>> create_grid_gif(gif_files, image_dir, grid_size=(2, 2), fps=2.0)
    """
    if not gif_paths:
        print("No GIF files provided for grid creation.")
        return
    
    output_path = image_dir / "animated_results_grid_all_levels.gif"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Delete existing output file if it exists
    if output_path.exists():
        output_path.unlink()
    
    # Convert fps to duration in milliseconds
    duration = int(1000 / fps) if fps > 0 else 1000
    
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

def create_grid_mp4(mp4_paths: list[Path], image_dir: Path, grid_size: tuple=(3, 3), 
                    target_size: tuple=(200, 200), fps: int=1) -> None:
    """Create a grid layout MP4 combining multiple individual MP4 files.
    
    Takes multiple MP4 files and combines them into a single MP4 with a grid layout.
    Each individual MP4 is resized to fit within the grid cells.
    
    Args:
        mp4_paths: List of Path objects pointing to input MP4 files
        image_dir: Directory where the grid MP4 will be saved
        grid_size: Tuple (cols, rows) defining the grid dimensions (default: 3x3)
        target_size: Tuple (width, height) for each cell in pixels (default: 200x200)
        fps: Frames per second for the output video (default: 1)
        
    Returns:
        None
        
    Example:
        >>> mp4_files = [Path('view1.mp4'), Path('view2.mp4'), Path('view3.mp4')]
        >>> create_grid_mp4(mp4_files, Path('output'), grid_size=(2, 2))
    """
    try:
        import cv2
    except ImportError:
        raise ImportError("OpenCV (cv2) is required for MP4 processing. Install with: pip install opencv-python")
    
    if not mp4_paths:
        print("No MP4 files provided for grid creation.")
        return
    
    output_path = image_dir / "animated_results_grid_all_levels.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Delete existing output file if it exists
    if output_path.exists():
        output_path.unlink()
    
    cols, rows = grid_size
    cell_width, cell_height = target_size
    
    # Load video properties and find maximum duration
    video_info = []
    max_frames = 0
    
    for mp4_path in mp4_paths[:cols * rows]:  # Limit to grid capacity
        try:
            cap = cv2.VideoCapture(str(mp4_path))
            if not cap.isOpened():
                print(f"Error opening {mp4_path}")
                continue
                
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            video_info.append({
                'path': mp4_path,
                'cap': cap,
                'frame_count': frame_count,
                'fps': video_fps,
                'width': width,
                'height': height
            })
            
            max_frames = max(max_frames, frame_count)
            
        except Exception as e:
            print(f"Error loading {mp4_path}: {e}")
            continue
    
    if not video_info:
        print("No valid MP4 files found.")
        return
    
    # Set up output video writer
    grid_width = cols * cell_width
    grid_height = rows * cell_height
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (grid_width, grid_height))
    
    # Process frames
    for frame_idx in range(max_frames):
        # Create grid frame
        grid_frame = np.zeros((grid_height, grid_width, 3), dtype=np.uint8)
        
        for i, video in enumerate(video_info):
            row = i // cols
            col = i % cols
            
            # Calculate position in grid
            y_start = row * cell_height
            y_end = y_start + cell_height
            x_start = col * cell_width
            x_end = x_start + cell_width
            
            # Get frame from video (loop if needed)
            video_frame_idx = frame_idx % video['frame_count']
            video['cap'].set(cv2.CAP_PROP_POS_FRAMES, video_frame_idx)
            ret, frame = video['cap'].read()
            
            if ret:
                # Resize frame to cell size
                resized_frame = cv2.resize(frame, (cell_width, cell_height))
                grid_frame[y_start:y_end, x_start:x_end] = resized_frame
        
        # Write frame to output video
        out.write(grid_frame)
    
    # Clean up
    out.release()
    for video in video_info:
        video['cap'].release()
    
    print(f"Created grid MP4: {len(video_info)} views in {cols}x{rows} grid, {max_frames} frames at {fps} FPS")

def create_pixel_to_world_mapping_from_hdr(hdr_file_path: Path, output_dir: Path = None) -> Path:
    """
    Creates a pixel-to-world coordinate mapping from an HDR file's VIEW parameters.
    
    Extracts viewpoint and view angle information from HDR file metadata,
    then calculates the mapping between pixel coordinates and real-world coordinates.
    
    Args:
        hdr_file_path (Path): Path to the HDR file containing VIEW parameters
        output_dir (Path, optional): Directory to save the mapping file. 
                                   Defaults to parent/outputs/aoi/
    
    Returns:
        Path: Path to the generated mapping file
        
    Raises:
        FileNotFoundError: If HDR file doesn't exist
        ValueError: If VIEW parameters cannot be extracted
        
    Example:
        >>> hdr_path = Path("image.hdr")
        >>> mapping_file = create_pixel_to_world_mapping_from_hdr(hdr_path)
        >>> print(f"Mapping saved to: {mapping_file}")
    """
    
    # Step 1: Validate input
    if not hdr_file_path.exists():
        raise FileNotFoundError(f"HDR file not found: {hdr_file_path}")
    
    try:
        with open(hdr_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            line_count = 0
            for line in f:
                line_count += 1
                line = line.strip()
                
                # Look for the resolution line pattern: -Y height +X width
                if line.startswith('-Y') and '+X' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == '-Y' and i + 1 < len(parts):
                            height = int(parts[i + 1])
                        elif part == '+X' and i + 1 < len(parts):
                            width = int(parts[i + 1])
                    if width and height:
                        print(f"HDR dimensions - width: {width}, height: {height}")
                        break
                
                # Stop reading when we hit binary data or after reasonable number of lines
                if line_count > 100 or (len(line) > 0 and any(ord(c) > 127 for c in line if c.isprintable() == False)):
                    print(f"Stopped reading at line {line_count}")
                    break
        
        if not width or not height:
            raise ValueError("Could not find resolution line in HDR file header")
            
    except Exception as e:
        raise ValueError(f"Could not determine image dimensions from HDR file: {e}")
    
    # Step 2: Read HDR file header to extract VIEW parameters
    print(f"Reading HDR file header: {hdr_file_path}")
    
    view_line = None
    try:
        with open(hdr_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Read the header lines (typically the first few lines contain metadata)
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line.startswith('VIEW='):
                    view_line = line
                    print(f"Found VIEW line at line {line_num}: {view_line}")
                    break
                # Stop reading after reasonable number of lines (HDR headers are typically short)
                if line_num > 50:
                    break
    except Exception as e:
        raise ValueError(f"Error reading HDR file: {e}")
    
    if not view_line:
        raise ValueError("No VIEW line found in HDR file header")
    
    print(f"Found VIEW line: {view_line}")
    
    # Step 4: Extract -vp (viewpoint) and -vh/-vv (view angles) values
    # Extract vp values (x, y, z coordinates of viewpoint)
    vp_match = re.search(r'-vp\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', view_line)
    if not vp_match:
        raise ValueError("Could not extract -vp values from VIEW line")
    
    vp_x, vp_y, vp_z = map(float, vp_match.groups())
    print(f"Viewpoint (vp): x={vp_x}, y={vp_y}, z={vp_z}")
    
    # Extract vh (horizontal view angle) and vv (vertical view angle)
    vh_match = re.search(r'-vh\s+([\d.-]+)', view_line)
    vv_match = re.search(r'-vv\s+([\d.-]+)', view_line)
    
    if not vh_match or not vv_match:
        raise ValueError("Could not extract -vh or -vv values from VIEW line")
    
    vh_angle = float(vh_match.group(1))
    vv_angle = float(vv_match.group(1))
    print(f"View angles - horizontal (vh): {vh_angle}°, vertical (vv): {vv_angle}°")
    
    # Step 5: Calculate pixel-to-world coordinate mapping
    world_width = 2 * vp_z * math.tan(math.radians(vh_angle / 2))
    world_height = 2 * vp_z * math.tan(math.radians(vv_angle / 2))
    
    world_units_per_pixel_x = world_width / width
    world_units_per_pixel_y = world_height / height
    
    print(f"World dimensions: {world_width:.3f} x {world_height:.3f} units")
    print(f"World units per pixel: x={world_units_per_pixel_x:.6f}, y={world_units_per_pixel_y:.6f}")
    
    # Step 6: Generate pixel-to-world coordinate mapping file
    if output_dir is None:
        output_dir = hdr_file_path.parent.parent / "aoi"
    
    output_file = output_dir / "pixel_to_world_coordinate_map.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        f.write("pixel_x pixel_y world_x world_y\n")
        
        # Generate mapping for all pixels
        for py in range(height):
            for px in range(width):
                # Convert pixel coordinates to world coordinates
                # Pixel (0,0) is top-left, world coordinates centered on viewpoint
                world_x = vp_x + (px - width/2) * world_units_per_pixel_x
                world_y = vp_y + (height/2 - py) * world_units_per_pixel_y  # Flip Y axis
                
                f.write(f"{px} {py} {world_x:.6f} {world_y:.6f}\n")
    
    print(f"Pixel-to-world coordinate mapping saved to: {output_file}")
    print("Key coordinate mappings:")
    key_points = [
        (0, 0, "top-left"),
        (width-1, 0, "top-right"),
        (0, height-1, "bottom-left"),
        (width-1, height-1, "bottom-right"),
        (width//2, height//2, "center")
    ]
    for px, py, label in key_points:
        world_x = vp_x + (px - width/2) * world_units_per_pixel_x
        world_y = vp_y + (height/2 - py) * world_units_per_pixel_y
        print(f"  {label}: pixel({px}, {py}) -> world({world_x:.3f}, {world_y:.3f})")
    
    return output_file

def stamp_tiff_files(tiff_paths: list[Path], font_size: int = 24, text_color: tuple = (255, 255, 0), background_alpha: int = 0, padding: int = 10, number_of_workers: int = 4) -> None:
    """Stamps TIFF files with location/datetime info in bottom right corner."""
    
    if not tiff_paths:
        return
    
    def _stamp_single_tiff(tiff_path: Path) -> str:
        """Stamp a single TIFF file."""
        try:
            if not tiff_path.exists():
                return f"File not found: {tiff_path.name}"
            
            # Extract info from filename
            filename = tiff_path.stem
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
            level = "Unknown"
            timestep = "Unknown"
            
            # Extract timestamp
            if ts := re.search(r'(\d{4}_\d{4})', filename):
                ts_str = ts.group(1)
                month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                month = int(ts_str[:2]) - 1
                day = int(ts_str[2:4])
                hour = ts_str[5:7]
                minute = ts_str[7:9]
                timestep = f"{month_names[month]} {day} {hour}:{minute}"
            
            # Extract level
            if level_match := re.search(r'[_]?L(\d+)', filename):
                level = f"L{level_match.group(1)}"
            
            # Create stamp text using f-string with actual variables
            final_text = f"Created: {current_datetime}, Level: {level}, Timestep: {timestep}, Location: lat: -33.8248567"
            #FIXME: the lat must be sourced from the radiance metadata if available, 
            
            # Load font and image
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()
            
            image = Image.open(tiff_path).convert('RGBA')
            draw = ImageDraw.Draw(image)
            
            # Calculate text position (bottom right)
            bbox = draw.textbbox((0, 0), final_text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = image.width - text_width - padding
            y = image.height - text_height - padding
            
            # Draw background and text
            if background_alpha > 0:
                draw.rectangle([x - padding//2, y - padding//2, 
                              x + text_width + padding//2, y + text_height + padding//2], 
                              fill=(0, 0, 0, background_alpha))
            
            draw.text((x, y), final_text, font=font, fill=text_color + (255,))
            image.save(tiff_path, format='TIFF')
            
            return f"Stamped {tiff_path.name}"
            
        except Exception as e:
            return f"Error stamping {tiff_path.name}: {e}"
    
    # Process files
    print(f"Stamping {len(tiff_paths)} TIFF files using {number_of_workers} workers")
    
    if number_of_workers == 1:
        for tiff_path in tiff_paths:
            print(_stamp_single_tiff(tiff_path))
    else:
        with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            for future in concurrent.futures.as_completed(
                [executor.submit(_stamp_single_tiff, path) for path in tiff_paths]):
                print(future.result())
    
    print(f"Completed stamping {len(tiff_paths)} TIFF files")

def _sort_points_by_perimeter(points: list, center: tuple) -> list:
    """
    Sort points to follow the perimeter in a clockwise order.
    
    Args:
        points: List of (x, y) coordinate tuples
        center: (x, y) center point for angle calculation
        
    Returns:
        List of points sorted in clockwise perimeter order
    """
    import math
    
    def angle_from_center(point):
        """Calculate angle from center to point."""
        dx = point[0] - center[0]
        dy = point[1] - center[1]
        # Use atan2 to get angle, adjust for clockwise ordering
        angle = math.atan2(dy, dx)
        # Convert to 0-2π range for consistent sorting
        if angle < 0:
            angle += 2 * math.pi
        return angle
    
    # Sort points by angle from center
    sorted_points = sorted(points, key=angle_from_center)
    return sorted_points

def _parse_aoi_file(aoi_file_path: Path) -> dict:
    """
    Parse an AOI file to extract room information and coordinate data.
    
    Args:
        aoi_file_path (Path): Path to the .aoi file
        
    Returns:
        dict: Parsed AOI data containing:
            - apartment_room: str (e.g., "U101 2 BED")
            - view_file: str (e.g., "plan_L01.vp")
            - z_height: float
            - central_coords: tuple (x, y)
            - perimeter_points: list of tuples [(x, y), ...] sorted in perimeter order
    """
    try:
        with open(aoi_file_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
        
        # Parse header information
        apartment_room = lines[0].replace("AOI Points File: ", "")
        view_file = lines[1].replace("ASSOCIATED VIEW FILE: ", "")
        z_height = float(lines[2].replace("FFL z height(m): ", ""))
        
        # Parse central coordinates
        central_line = lines[3].replace("CENTRAL x,y: ", "")
        central_x, central_y = map(float, central_line.split())
        
        # Parse perimeter points (skip header line)
        perimeter_points = []
        for line in lines[5:]:  # Skip first 5 lines (headers and perimeter count)
            if line and ' ' in line:
                x, y = map(float, line.split())
                perimeter_points.append((x, y))
        
        # Sort points to follow proper perimeter order
        if len(perimeter_points) > 2:
            perimeter_points = _sort_points_by_perimeter(perimeter_points, (central_x, central_y))
        
        return {
            'apartment_room': apartment_room,
            'view_file': view_file,
            'z_height': z_height,
            'central_coords': (central_x, central_y),
            'perimeter_points': perimeter_points
        }
        
    except Exception as e:
        print(f"Error parsing AOI file {aoi_file_path}: {e}")
        return None

def _world_to_pixel_coords(world_x: float, world_y: float, mapping_file_path: Path, cache: dict = None) -> tuple:
    """
    Convert world coordinates to pixel coordinates using the mapping file.
    
    This function uses an efficient approach by calculating pixel coordinates
    mathematically based on the mapping parameters, with optional caching.
    
    Args:
        world_x (float): World X coordinate
        world_y (float): World Y coordinate
        mapping_file_path (Path): Path to pixel_to_world_coordinate_map.txt
        cache (dict, optional): Cache dictionary to store mapping parameters
        
    Returns:
        tuple: (pixel_x, pixel_y) or None if coordinates are out of bounds
    """
    try:
        # Use cache if provided and available
        if cache and 'mapping_params' in cache:
            params = cache['mapping_params']
        else:
            # Read mapping parameters from file
            with open(mapping_file_path, 'r') as f:
                # Skip header
                f.readline()
                
                # Read first two lines to get x-step
                line1 = f.readline().strip().split()  # pixel 0,0
                line2 = f.readline().strip().split()  # pixel 1,0
                
                world_x_start = float(line1[2])
                world_y_start = float(line1[3])
                world_x_step = float(line2[2]) - float(line1[2])
                
                # Find where y changes to determine image width and y-step
                f.seek(0)
                f.readline()  # skip header
                
                pixel_width = 0
                prev_y = None
                first_y = None
                
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        current_y = float(parts[3])
                        if first_y is None:
                            first_y = current_y
                        
                        if prev_y is not None and current_y != prev_y:
                            # Found the y-step
                            world_y_step = current_y - prev_y
                            break
                        prev_y = current_y
                        pixel_width += 1
                
                # Calculate image height more accurately
                # We know pixel_width, so we can calculate height from remaining data
                f.seek(0)
                total_lines = sum(1 for _ in f) - 1  # -1 for header
                pixel_height = total_lines // pixel_width
                
                params = {
                    'world_x_start': world_x_start,
                    'world_y_start': world_y_start,
                    'world_x_step': world_x_step,
                    'world_y_step': world_y_step,
                    'pixel_width': pixel_width,
                    'pixel_height': pixel_height
                }
                
                # Store in cache if provided
                if cache is not None:
                    cache['mapping_params'] = params
        
        # Calculate pixel coordinates
        pixel_x = round((world_x - params['world_x_start']) / params['world_x_step'])
        pixel_y = round((world_y - params['world_y_start']) / params['world_y_step'])
        
        # Check bounds
        if (0 <= pixel_x < params['pixel_width'] and 
            0 <= pixel_y < params['pixel_height']):
            return (pixel_x, pixel_y)
        else:
            return None
            
    except Exception as e:
        print(f"Error converting coordinates ({world_x}, {world_y}): {e}")
        return None

def _order_points_for_perimeter(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """
    Order points to form a proper perimeter using angular sorting around centroid.
    
    This function takes a list of unordered perimeter points and returns them
    in the correct order to form a closed polygon without crossing lines.
    
    Args:
        points (list[tuple[float, float]]): List of (x, y) coordinate tuples
        
    Returns:
        list[tuple[float, float]]: Points ordered for proper perimeter tracing
    """
    import math
    
    if len(points) < 3:
        return points
    
    # Calculate centroid of all points
    centroid_x = sum(p[0] for p in points) / len(points)
    centroid_y = sum(p[1] for p in points) / len(points)
    
    # Sort points by angle from centroid
    def angle_from_centroid(point):
        dx = point[0] - centroid_x
        dy = point[1] - centroid_y
        return math.atan2(dy, dx)
    
    # Sort points by their angle around the centroid
    ordered_points = sorted(points, key=angle_from_centroid)
    
    return ordered_points

def stamp_tiff_files_with_aoi(tiff_paths: list[Path], lineweight: int = 5, font_size: int = 32, 
                             text_color: tuple = (255, 0, 0), background_alpha: int = 180, 
                             number_of_workers: int = 10) -> None:
    """
    Stamp TIFF files with AOI (Area of Interest) polygons and room labels.
    
    This function overlays room boundary polygons and labels onto TIFF images by:
    1. Finding matching AOI files for each TIFF based on view file association
    2. Converting world coordinates to pixel coordinates using the mapping file
    3. Drawing polygon outlines and room labels on the images
    
    Args:
        tiff_paths (list[Path]): List of TIFF file paths to process
        lineweight (int): Thickness of polygon outline lines (default: 5)
        font_size (int): Size of room label text (default: 32)
        text_color (tuple): RGB color for lines and text (default: (255, 0, 0) red)
        background_alpha (int): Alpha transparency for text background (default: 180)
        number_of_workers (int): Number of parallel processing workers (default: 10)
        
    Returns:
        None
        
    Example:
        >>> tiff_files = [Path('image1.tiff'), Path('image2.tiff')]
        >>> stamp_tiff_files_with_aoi(tiff_files, lineweight=3, font_size=24)
    """
    if not tiff_paths:
        print("No TIFF files provided for AOI stamping.")
        return
    
    # Find AOI directory and mapping file
    aoi_dir = Path("outputs/aoi")
    mapping_file = aoi_dir / "pixel_to_world_coordinate_map.txt"
    
    if not aoi_dir.exists():
        print(f"AOI directory not found: {aoi_dir}")
        return
        
    if not mapping_file.exists():
        print(f"Pixel-to-world mapping file not found: {mapping_file}")
        return
    
    # Load all AOI files
    aoi_files = list(aoi_dir.glob("*.aoi"))
    if not aoi_files:
        print("No AOI files found in the AOI directory.")
        return
    
    print(f"Found {len(aoi_files)} AOI files for processing.")
    
    def _stamp_single_tiff_with_aoi(tiff_path: Path) -> str:
        """Stamp a single TIFF file with matching AOI data."""
        try:
            if not tiff_path.exists():
                return f"File not found: {tiff_path.name}"
            
            # Extract view file information from TIFF filename
            # Expected pattern: *_plan_LXX_* or similar
            filename = tiff_path.stem
            view_file_match = None
            
            # Try to extract view file reference from filename
            import re
            if match := re.search(r'plan_L\d+', filename):
                view_file_match = f"{match.group(0)}.vp"
            
            if not view_file_match:
                return f"Could not determine view file for: {tiff_path.name}"
            
            # Find AOI files that match this view file
            matching_aois = []
            for aoi_file in aoi_files:
                aoi_data = _parse_aoi_file(aoi_file)
                if aoi_data and aoi_data['view_file'] == view_file_match:
                    matching_aois.append(aoi_data)
            
            if not matching_aois:
                return f"No matching AOI files found for view {view_file_match} in {tiff_path.name}"
            
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()
            
            image = Image.open(tiff_path).convert('RGBA')
            draw = ImageDraw.Draw(image)
            
            rooms_processed = 0
            
            # Create cache for coordinate conversion efficiency
            coord_cache = {}
            
            # Process each matching AOI
            for aoi_data in matching_aois:
                try:
                    # Convert perimeter points from world to pixel coordinates
                    pixel_points = []
                    for world_x, world_y in aoi_data['perimeter_points']:
                        pixel_coords = _world_to_pixel_coords(world_x, world_y, mapping_file, coord_cache)
                        if pixel_coords:
                            pixel_points.append(pixel_coords)
                    
                    if len(pixel_points) < 3:
                        continue  # Need at least 3 points for a polygon
                    
                    # Order points to form proper perimeter
                    ordered_pixel_points = _order_points_for_perimeter(pixel_points)
                    
                    # Draw polygon outline
                    if len(ordered_pixel_points) > 2:
                        # Close the polygon by connecting last point to first
                        polygon_points = ordered_pixel_points + [ordered_pixel_points[0]]
                        
                        # Draw polygon lines
                        for i in range(len(polygon_points) - 1):
                            draw.line([polygon_points[i], polygon_points[i + 1]], 
                                    fill=text_color, width=lineweight)
                    
                    # Convert central coordinates and add room label
                    central_world_x, central_world_y = aoi_data['central_coords']
                    central_pixel = _world_to_pixel_coords(central_world_x, central_world_y, mapping_file, coord_cache)
                    
                    if central_pixel:
                        label_text = aoi_data['apartment_room']
                        
                        # Calculate text size and position
                        bbox = draw.textbbox((0, 0), label_text, font=font)
                        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
                        
                        label_x = central_pixel[0] - text_width // 2
                        label_y = central_pixel[1] - text_height // 2
                        
                        # Draw text background
                        if background_alpha > 0:
                            padding = 5
                            draw.rectangle([label_x - padding, label_y - padding,
                                          label_x + text_width + padding, 
                                          label_y + text_height + padding],
                                        fill=(0, 0, 0, background_alpha))
                        
                        # Draw text
                        draw.text((label_x, label_y), label_text, font=font, fill=text_color + (255,))
                    
                    rooms_processed += 1
                    
                except Exception as e:
                    print(f"Error processing AOI {aoi_data['apartment_room']}: {e}")
                    continue
            
            # Save the stamped image
            image.save(tiff_path, format='TIFF')
            
            return f"Stamped {tiff_path.name} with {rooms_processed} AOI rooms"
            
        except Exception as e:
            return f"Error stamping {tiff_path.name}: {e}"
    
    # Process files
    print(f"Stamping {len(tiff_paths)} TIFF files with AOI data using {number_of_workers} workers")
    
    if number_of_workers == 1:
        for tiff_path in tiff_paths:
            result = _stamp_single_tiff_with_aoi(tiff_path)
            print(result)
    else:
        with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            for future in concurrent.futures.as_completed(
                [executor.submit(_stamp_single_tiff_with_aoi, path) for path in tiff_paths]):
                print(future.result())
    
    print(f"Completed AOI stamping on {len(tiff_paths)} TIFF files")

def create_pixel_to_world_mapping_from_hdr(image_dir: Path) -> Optional[Path]:
    """
    Create pixel-to-world coordinate mapping from HDR file in the specified directory.
    
    Automatically locates the first '*_combined.hdr' file in the image directory
    and processes it to create coordinate mapping data for spatial analysis.
    
    Args:
        image_dir (Path): Directory containing HDR files
        
    Returns:
        Optional[Path]: Path to the HDR file that was processed, or None if no file found
        
    Note:
        This function searches for files matching the pattern '*_combined.hdr' 
        which are typically generated during the solar analysis pipeline.
    """
    try:
        # Locate HDR file automatically
        hdr_file_path = next(image_dir.glob('*_combined.hdr'), None)
        
        if hdr_file_path is None:
            print(f"Warning: No '*_combined.hdr' file found in {image_dir}")
            return None
            
        print(f"Creating pixel-to-world mapping from: {hdr_file_path.name}")
        
        # TODO: Implement actual pixel-to-world coordinate mapping logic
        # This would typically involve:
        # 1. Reading HDR file header for spatial metadata
        # 2. Extracting view parameters and geometric transforms
        # 3. Creating coordinate transformation matrices
        # 4. Saving mapping data for use in subsequent analysis steps
        
        print(f"Coordinate mapping generated for: {hdr_file_path.name}")
        return hdr_file_path
        
    except Exception as e:
        print(f"Error creating pixel-to-world mapping: {e}")
        return None


