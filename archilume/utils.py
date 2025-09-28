# Archilume imports

# Standard library imports
import concurrent.futures
import math
import os
import re
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

def combine_gifs_by_view(image_dir: Path, view_files: list[Path], fps: float=None, output_format: str='gif', number_of_workers: int = 4) -> None:
    """Create separate animated files grouped by view file names using parallel processing.
    
    Scans the image directory for GIF files and groups them by view file names. Creates
    separate animated files for each view in parallel for improved performance.
    
    Args:
        image_dir: Directory containing the GIF files to process
        view_files: List of view file Path objects used to group GIFs by name
        fps: Frames per second for the output animation. If None, defaults to 1 FPS (1 second per frame)
        output_format: Output format - 'gif' or 'mp4' (default: 'gif')
        number_of_workers: Number of parallel workers for processing views (default: 4)
        
    Returns:
        None
        
    Example:
        >>> view_files = [Path('plan_L02.vp'), Path('section_A.vp')]
        >>> combine_gifs_by_view(Path('outputs/images'), view_files, fps=2.0, output_format='mp4', number_of_workers=6)
        >>> combine_gifs_by_view(Path('outputs/images'), view_files, output_format='gif')  # Uses 1 FPS with 4 workers
    """
    def _combine_gifs(gif_paths: list[Path], output_path: Path, duration: int=100, output_format: str='gif') -> None:
        """Combine multiple GIF files into a single animated file.
        
        Takes a list of GIF file paths and combines them sequentially into a single
        animated file. All input GIFs are appended as frames in the output animation.
        
        Args:
            gif_paths: List of Path objects pointing to the input GIF files to combine
            output_path: Path where the combined file will be saved
            duration: Duration in milliseconds for each frame in the output file (default: 100)
            output_format: Output format - 'gif' or 'mp4' (default: 'gif')
            
        Returns:
            None
            
        Raises:
            PIL.UnidentifiedImageError: If any of the input files are not valid images
            FileNotFoundError: If any of the input GIF files don't exist
            PermissionError: If unable to write to the output path
            ValueError: If output_format is not supported
            
        Example:
            >>> gif_files = [Path('frame1.gif'), Path('frame2.gif'), Path('frame3.gif')]
            >>> _combine_gifs(gif_files, Path('animation.gif'), duration=200, output_format='gif')
            >>> _combine_gifs(gif_files, Path('animation.mp4'), duration=200, output_format='mp4')
        """
        
        if output_format.lower() == 'gif':
            gifs = [Image.open(f) for f in gif_paths]
            gifs[0].save(output_path, save_all=True, append_images=gifs[1:], 
                        duration=duration, loop=0)
        elif output_format.lower() == 'mp4':
            try:
                import cv2
            except ImportError:
                raise ImportError("OpenCV (cv2) is required for MP4 output. Install with: pip install opencv-python")
            
            # Get dimensions from first GIF
            first_gif = Image.open(gif_paths[0])
            width, height = first_gif.size
            
            # Set up video writer (fps = 1000/duration for proper timing)
            fps = 1000 / duration if duration > 0 else 10
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video_writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
            
            # Process each GIF and add frames to video
            for gif_path in gif_paths:
                gif = Image.open(gif_path)
                try:
                    while True:
                        # Convert PIL image to OpenCV format (BGR)
                        frame_rgb = gif.convert('RGB')
                        frame_bgr = cv2.cvtColor(np.array(frame_rgb), cv2.COLOR_RGB2BGR)
                        video_writer.write(frame_bgr)
                        gif.seek(gif.tell() + 1)
                except EOFError:
                    pass
            
            video_writer.release()
        else:
            raise ValueError(f"Unsupported output format: {output_format}. Use 'gif' or 'mp4'.")

    gif_files = [path for path in image_dir.glob('*.gif')]
    
    # Filter out previously created result files to avoid circular references
    gif_files = [gif for gif in gif_files if not gif.name.startswith('animated_results_') and gif.name != 'animated_results_grid_all_levels.gif']
    
    if not gif_files:
        print("No GIF files found in the image directory (excluding result files).")
        return
    
    def _process_single_view(view_file: Path) -> str:
        """Process a single view file to create animated output."""
        view_name = view_file.stem
        # Find all GIF files that contain this view name
        view_gif_files = [gif for gif in gif_files if view_name in gif.name]
        
        if not view_gif_files:
            return f"✗ No GIF files found for view: {view_name}"
        
        try:
            # Calculate duration based on number of frames found
            num_frames = len(view_gif_files)
            
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
            
            _combine_gifs(view_gif_files, output_file_path, per_frame_duration, output_format)
            return f"✓ Created {output_format.upper()} animation for {view_name}: {num_frames} frames, {duration/1000:.1f}s at {calculated_fps} FPS"
            
        except Exception as e:
            return f"✗ Error processing {view_name}: {e}"
    
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
                    print(f"✗ Error in parallel view processing: {e}")
    
    print(f"Completed processing {len(view_files)} view animations")

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
    
    # Get image dimensions using simple PIL approach for GIF file
    gif_path = hdr_file_path.parent / f"{hdr_file_path.stem}.gif"
    
    if gif_path.exists():
        # Use GIF file for dimensions (more reliable with PIL)
        width, height = Image.open(gif_path).size
        print(f"GIF dimensions - width: {width}, height: {height}")
    
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

def stamp_gif_files(gif_paths: list[Path], stamp_text: str, font_size: int = 24, 
                   text_color: tuple = (255, 255, 255), background_color: tuple = (0, 0, 0), 
                   background_alpha: int = 180, padding: int = 10, number_of_workers: int = 4) -> None:
    """
    Stamps individual GIF files with a given input string in the bottom right corner using parallel processing.
    Can use template strings with {time} and {datetime} placeholders that get replaced with timestamp from filename.
    
    Args:
        gif_paths (list[Path]): List of Path objects pointing to GIF files to stamp
        stamp_text (str): Text template to stamp on each GIF. Can include {time} and {datetime} placeholders.
        font_size (int, optional): Size of the text font. Defaults to 24.
        text_color (tuple, optional): RGB color of the text. Defaults to white (255, 255, 255).
        background_color (tuple, optional): RGB color of text background. Defaults to black (0, 0, 0).
        background_alpha (int, optional): Alpha transparency of background (0=transparent, 255=opaque). Defaults to 180.
        padding (int, optional): Padding around the text in pixels. Defaults to 10.
        number_of_workers (int, optional): Number of parallel workers for processing. Defaults to 4.
    
    Returns:
        None
        
    Example:
        >>> gif_files = [Path('image1.gif'), Path('image2.gif')]
        >>> stamp_gif_files(gif_files, 'Simulated on {datetime} for {time} lat, lon: -33.8248567, 151.2385034')
        >>> stamp_gif_files(gif_files, 'Custom text', background_alpha=0)  # Fully transparent background
        >>> stamp_gif_files(gif_files, 'Custom text', number_of_workers=8)  # Use 8 parallel workers
    """
    from PIL import ImageDraw, ImageFont
    from datetime import datetime
    
    if not gif_paths:
        print("No GIF files provided to stamp.")
        return
    
    print(f"Stamping {len(gif_paths)} GIF files with text: '{stamp_text}' using {number_of_workers} workers")
    
    def _stamp_single_gif(gif_path: Path) -> str:
        """
        Stamps a single GIF file with the given text.
        
        Args:
            gif_path (Path): Path to the GIF file to stamp
            
        Returns:
            str: Status message for this file
        """
        try:
            if not gif_path.exists():
                return f"File not found: {gif_path.name}"

            # Extract timestamp from filename and format the stamp text
            final_text = stamp_text
            filename = gif_path.stem
            timestamp_match = re.search(r'(\d{4}_\d{4})', filename)
            
            if timestamp_match and ('{time}' in stamp_text or '{datetime}' in stamp_text):
                timestamp = timestamp_match.group(1)
                month_day = timestamp[:4]  # e.g., "0621"
                hour_min = timestamp[5:]   # e.g., "0900"
                
                # Convert to readable format
                month = month_day[:2]
                day = month_day[2:]
                hour = hour_min[:2]
                minute = hour_min[2:]
                
                # Format as "June 21 09:00"
                month_names = {
                    "01": "January", "02": "February", "03": "March", "04": "April",
                    "05": "May", "06": "June", "07": "July", "08": "August", 
                    "09": "September", "10": "October", "11": "November", "12": "December"
                }
                
                month_name = month_names.get(month, f"Month{month}")
                formatted_time = f"{month_name} {int(day)} {hour}:{minute}"
                
                # Get current datetime

                current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                # Replace placeholders in template
                final_text = stamp_text.format(time=formatted_time, datetime=current_datetime)
            
            # Try to load a font for this worker (each thread loads its own)
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                try:
                    font = ImageFont.load_default()
                except:
                    font = None
            
            # Open the GIF
            gif = Image.open(gif_path)
            
            # Prepare to store all frames
            frames = []
            
            # Process each frame
            try:
                while True:
                    frame = gif.copy()
                    
                    # Convert to RGBA to handle transparency properly
                    if frame.mode != 'RGBA':
                        frame = frame.convert('RGBA')
                    
                    # Create a drawing context
                    draw = ImageDraw.Draw(frame)
                    
                    # Get text dimensions
                    if font:
                        bbox = draw.textbbox((0, 0), final_text, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]
                    else:
                        # Fallback estimation if font loading failed
                        text_width = len(final_text) * 8
                        text_height = 16
                    
                    # Calculate position for bottom right corner
                    x = frame.width - text_width - padding
                    y = frame.height - text_height - padding
                    
                    # Draw background rectangle
                    rect_x1 = x - padding//2
                    rect_y1 = y - padding//2
                    rect_x2 = x + text_width + padding//2
                    rect_y2 = y + text_height + padding//2
                    
                    draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], 
                                 fill=background_color + (background_alpha,))  # Configurable transparency background
                    
                    # Draw the text
                    if font:
                        draw.text((x, y), final_text, font=font, fill=text_color + (255,))
                    else:
                        draw.text((x, y), final_text, fill=text_color + (255,))
                    
                    frames.append(frame)
                    gif.seek(gif.tell() + 1)
                    
            except EOFError:
                # End of frames
                pass
            
            # Save the stamped GIF
            if frames:
                # Preserve original GIF properties
                duration = gif.info.get('duration', 100)
                loop = gif.info.get('loop', 0)
                
                frames[0].save(
                    gif_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=duration,
                    loop=loop,
                    format='GIF'
                )
                
                return f"Stamped {gif_path.name} ({len(frames)} frames)"
            else:
                return f"No frames found in {gif_path.name}"
            
        except Exception as e:
            return f"Error stamping {gif_path.name}: {e}"
    
    # Process GIFs in parallel
    if number_of_workers == 1:
        # Sequential processing for single worker
        for gif_path in gif_paths:
            result = _stamp_single_gif(gif_path)
            print(result)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            futures = [executor.submit(_stamp_single_gif, gif_path) for gif_path in gif_paths]
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    print(result)
                except Exception as e:
                    print(f"✗ Error in parallel processing: {e}")
    
    print(f"Completed stamping {len(gif_paths)} GIF files")


