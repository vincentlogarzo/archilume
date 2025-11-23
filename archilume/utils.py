import concurrent.futures
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Union
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import numpy as np
import open3d as o3d
import tkinter as tk
from tkinter import filedialog

def select_files(title: str = "Select file(s)") -> Optional[List[str]]:
    """Open file dialog to select multiple files from inputs folder."""
    root = tk.Tk()
    root.withdraw()
    inputs_dir = os.path.join(os.getcwd(), "inputs")
    initial_dir = inputs_dir if os.path.exists(inputs_dir) else os.getcwd()
    file_paths = filedialog.askopenfilenames(initialdir=initial_dir, title=title, parent=root)
    root.destroy()
    return list(file_paths) if file_paths else None

def display_obj(filenames: Union[str, Path, List[Union[str, Path]]]):
    """Display OBJ files using open3d with enhanced visualization."""
    if isinstance(filenames, (str, Path)):
        filenames = [filenames]

    def set_view(front, up):
        def _set(vis):
            vc = vis.get_view_control()
            vc.set_front(front)
            vc.set_up(up)
            return False
        return _set

    views = {
        'top': ([0, 0, -1], [0, 1, 0]), 'front': ([0, 1, 0], [0, 0, 1]),
        'back': ([0, -1, 0], [0, 0, 1]), 'left': ([1, 0, 0], [0, 0, 1]),
        'right': ([-1, 0, 0], [0, 0, 1]), 'bottom': ([0, 0, 1], [0, -1, 0])
    }

    def reset_view(vis):
        vis.get_view_control().set_zoom(0.8)
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

def delete_files(file_paths: list[Path], number_of_workers: int = 1) -> None:
    """
    Deletes files from a list of Path objects using pathlib's unlink() method.

    Args:
        file_paths (list[Path]): List of Path objects to delete.
        number_of_workers (int): Number of worker threads for parallel deletion. Default is 1 (sequential).
    """
    def _delete_single_file(file_path: Path) -> tuple[str, bool, Optional[str]]:
        """Delete a single file and return status."""
        try:
            if file_path.exists():
                file_path.unlink()
                return (file_path.name, True, None)
            else:
                return (file_path.name, False, "not found")
        except Exception as e:
            return (file_path.name, False, str(e))

    deleted_count = 0
    skipped_count = 0

    if number_of_workers > 1 and len(file_paths) > 1:
        # Parallel deletion using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            results = executor.map(_delete_single_file, file_paths)

            for filename, success, error in results:
                if success:
                    deleted_count += 1
                    print(f"Deleted: {filename}")
                else:
                    skipped_count += 1
                    msg = f"Skipped ({error}): {filename}" if error else f"Skipped: {filename}"
                    print(msg)
    else:
        # Sequential deletion
        for file_path in file_paths:
            filename, success, error = _delete_single_file(file_path)
            if success:
                deleted_count += 1
                print(f"Deleted: {filename}")
            else:
                skipped_count += 1
                msg = f"Skipped ({error}): {filename}" if error else f"Skipped: {filename}"
                print(msg)

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

def execute_new_pvalue_commands(commands: Union[str, list[str]], number_of_workers: int = 1, threshold: float = 0.0) -> None:
    """
    Executes pvalue commands with real-time filtering of output, processing only files that don't already exist.

    This function takes pvalue commands (e.g., 'pvalue -b +di input.hdr > output.txt') and executes them
    while filtering the output to include only lines where the 3rd column is greater than the threshold.
    This is a cross-platform alternative to: pvalue ... | awk '$3 > 0' > output.txt

    Optimized for large datasets (millions of lines) with:
    - Inline filtering (no chunking overhead)
    - Fast path for threshold <= 0 (no filtering)
    - Large buffer sizes (512KB)
    - ThreadPoolExecutor for I/O-bound parallelism

    Args:
        commands (str or list[str]): Single command string or list of pvalue command strings to execute.
                                   Each command should be in format: 'pvalue -b +di input.hdr > output.txt'
        number_of_workers (int, optional): Number of parallel workers for command execution. Defaults to 1.
        threshold (float, optional): Minimum value for 3rd column to include in output. Defaults to 0.0.

    Returns:
        None: Function executes commands and prints completion message with point counts.

    Note:
        Commands are filtered based on whether their output files exist. The function
        extracts the output path from the '>' operator and only processes commands whose
        output files don't already exist.

    Example:
        >>> execute_new_pvalue_commands('pvalue -b +di input.hdr > output.txt', threshold=1e-9)
        >>> execute_new_pvalue_commands(['pvalue -b +di in1.hdr > out1.txt', 'pvalue -b +di in2.hdr > out2.txt'], number_of_workers=4)
    """

    def _execute_pvalue_with_filter(command: str, threshold: float) -> int:
        """Execute a single pvalue command with inline filtering - optimized for maximum speed."""
        print(f"Starting: {command}")

        try:
            # Parse command to extract input file and output file
            if ' > ' not in command:
                raise ValueError(f"Command must include output redirection (>): {command}")

            cmd_part, output_path = command.split(' > ', 1)
            output_path = output_path.strip()

            # Parse pvalue command parts
            pvalue_cmd_parts = cmd_part.strip().split()

            # Ensure output directory exists
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Set up environment with RAYPATH for Radiance commands
            env = os.environ.copy()
            env['RAYPATH'] = r'C:\Radiance\lib'

            # Execute pvalue command and filter output
            count = 0
            with open(output_file, 'w', buffering=524288) as outfile:  # 512KB write buffer
                process = subprocess.Popen(
                    pvalue_cmd_parts,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=524288,  # 512KB buffer
                    env=env
                )

                in_header = True

                # OPTIMIZED: Direct line-by-line filtering (no chunking overhead)
                if threshold <= 0:
                    # Fast path: no filtering, write everything
                    for line in process.stdout:
                        if in_header:
                            outfile.write(line)
                            if line.strip().startswith('-Y') and '+X' in line:
                                in_header = False
                            continue
                        outfile.write(line)
                        count += 1
                else:
                    # Filter mode: inline filtering without chunking
                    for line in process.stdout:
                        if in_header:
                            outfile.write(line)
                            if line.strip().startswith('-Y') and '+X' in line:
                                in_header = False
                            continue

                        # Fast inline filter - no intermediate storage
                        parts = line.split()
                        if len(parts) >= 3 and float(parts[2]) > threshold:
                            outfile.write(line)
                            count += 1

                # Capture any stderr output
                stderr_output = process.stderr.read()
                if stderr_output:
                    print(f"pvalue stderr: {stderr_output.strip()}")

                # Wait for process to complete
                return_code = process.wait()

                if return_code == 0:
                    print(f"Completed successfully: {command} -> Filtered {count:,} points")
                    return count
                else:
                    print(f"Failed with return code {return_code}: {command}")
                    return 0

        except Exception as e:
            print(f"Error executing command '{command}': {e}")
            return 0

    # Handle single command string input
    if isinstance(commands, str):
        commands = [commands]

    # Filter out commands whose output files already exist
    filtered_commands = []
    for command in commands:
        if ' > ' in command:
            try:
                output_path = command.split(' > ')[1].strip()
                if not os.path.exists(output_path):
                    filtered_commands.append(command)
                else:
                    print(f"Output already exists, skipping: {output_path}")
            except IndexError:
                filtered_commands.append(command)
        else:
            filtered_commands.append(command)

    # Execute commands with filtering
    total_points = 0
    if number_of_workers == 1:
        # Sequential execution
        for command in filtered_commands:
            total_points += _execute_pvalue_with_filter(command, threshold)
    else:
        # Parallel execution with ThreadPoolExecutor
        # Note: ThreadPoolExecutor is appropriate here because most time is spent waiting
        # on subprocess I/O (pvalue execution), not CPU-bound Python operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=number_of_workers) as executor:
            futures = [executor.submit(_execute_pvalue_with_filter, command, threshold) for command in filtered_commands]
            for future in concurrent.futures.as_completed(futures):
                try:
                    total_points += future.result()
                except Exception as e:
                    print(f"Error in parallel execution: {e}")

    if filtered_commands:
        print(f"All pvalue commands completed. Total filtered points: {total_points}")
    else:
        print("No new pvalue commands to execute (all output files already exist).")

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

def create_pixel_to_world_coord_map(image_dir: Path) -> Optional[Path]:
    """
    Create pixel-to-world coordinate mapping from HDR file in the specified directory.

    Automatically locates the first '*_combined.hdr' file in the image directory,
    extracts viewpoint and view angle information from HDR file metadata, then
    calculates the mapping between pixel coordinates and real-world coordinates.
    The mapping file is saved to the output directory for use in spatial analysis.

    Args:
        image_dir (Path): Directory containing HDR files
        output_dir (Path, optional): Directory to save the mapping file.
                                     If None, defaults to image_dir.parent/aoi/

    Returns:
        Optional[Path]: Path to the HDR file that was processed, or None if processing failed

    Raises:
        FileNotFoundError: If HDR file doesn't exist
        ValueError: If VIEW parameters or image dimensions cannot be extracted

    Note:
        This function searches for files matching the pattern '*_combined.hdr'
        which are typically generated during the solar analysis pipeline.
        The mapping file format is: # pixel_x pixel_y world_x world_y (commented header)
        followed by whitespace-delimited numeric data rows

    Example:
        >>> image_dir = Path("outputs/images")
        >>> hdr_path = create_pixel_to_world_coord_map(image_dir)
        >>> if hdr_path:
        ...     print(f"Mapping created from: {hdr_path}")
    """
    try:
        # ===================================================================
        # STEP 1: LOCATE AND VALIDATE HDR FILE
        # ===================================================================
        # Search for an HDR file in the specified directory
        # The glob pattern '*.hdr' finds any HDR file
        # next() returns the first match, or None if no files found
        hdr_file_path = next(image_dir.glob('*.hdr'), None)

        if hdr_file_path is None:
            print(f"Warning: No '*_combined.hdr' file found in {image_dir}")
            return None

        print(f"Creating pixel-to-world mapping from: {hdr_file_path.name}")

        # Double-check that the file actually exists on disk
        if not hdr_file_path.exists():
            raise FileNotFoundError(f"HDR file not found: {hdr_file_path}")

        # ===================================================================
        # STEP 2: EXTRACT IMAGE DIMENSIONS FROM HDR FILE
        # ===================================================================
        # HDR files contain a header with metadata followed by binary image data
        # We need to find a line like: "-Y 600 +X 800" which means:
        #   - Image is 800 pixels wide (X dimension)
        #   - Image is 600 pixels tall (Y dimension)
        # Initialize dimension variables
        
        width = None
        height = None

        try:
            # Open file with UTF-8 encoding, ignoring any decode errors
            with open(hdr_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                line_count = 0
                for line in f:
                    line_count += 1
                    line = line.strip()

                    # Look for the resolution line pattern: -Y height +X width
                    # This is the standard Radiance HDR format for image dimensions
                    if line.startswith('-Y') and '+X' in line:
                        parts = line.split()  # Split line into individual tokens
                        # Parse the dimensions from the format: -Y <height> +X <width>
                        for i, part in enumerate(parts):
                            if part == '-Y' and i + 1 < len(parts):
                                height = int(parts[i + 1])
                            elif part == '+X' and i + 1 < len(parts):
                                width = int(parts[i + 1])
                        # If we found both dimensions, we're done
                        if width and height:
                            print(f"HDR dimensions - width: {width}, height: {height}")
                            break

                    # Safety check: Stop reading if we've gone too far or hit binary data
                    # HDR headers are typically < 100 lines, and binary data has non-printable chars
                    if line_count > 100 or (len(line) > 0 and any(ord(c) > 127 for c in line if not c.isprintable())):
                        print(f"Stopped reading at line {line_count}")
                        break

            # Validate that we actually found the dimensions
            if not width or not height:
                raise ValueError("Could not find resolution line in HDR file header")

        except Exception as e:
            raise ValueError(f"Could not determine image dimensions from HDR file: {e}")

        # ===================================================================
        # STEP 3: EXTRACT VIEW PARAMETERS FROM HDR FILE
        # ===================================================================
        # The HDR file contains a VIEW line with camera information, e.g.:
        # VIEW= -vtl v -vp 50.0 30.0 1.5 -vd 0 1 0 -vu 0 0 1 -vh 45 -vv 45
        # This tells us:
        #   -vtl: orthographic view type (v = perspective)
        #   -vp: viewpoint position (x, y, z coordinates of camera)
        #   -vd: view direction (where camera is looking)
        #   -vu: view up vector (which way is "up")
        #   -vh: horizontal view angle in degrees (field of view width)
        #   -vv: vertical view angle in degrees (field of view height)

        print(f"Reading HDR file header: {hdr_file_path}")

        # Find the VIEW line in the HDR header
        with open(hdr_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            view_line = next((line.strip() for line in f if line.startswith('VIEW=')), None)

        if not view_line:
            raise ValueError("No VIEW line found in HDR file header")

        print(f"Found VIEW line: {view_line}")

        # ===================================================================
        # STEP 4: PARSE VIEWPOINT AND VIEW ANGLE VALUES
        # ===================================================================
        # Now we extract specific values from the VIEW line using regex patterns

        # Extract -vp (viewpoint): The 3D position of the camera
        # Regex pattern: "-vp" followed by 3 numbers (can be negative, decimals)
        # Example: "-vp 50.0 30.0 1.5" means camera at position (50, 30, 1.5) meters

        vp_match = re.search(r'-vp\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', view_line)
        if not vp_match:
            raise ValueError("Could not extract -vp values from VIEW line")

        vp_x, vp_y, vp_z = map(float, vp_match.groups())
        print(f"Viewpoint (vp): x={vp_x}, y={vp_y}, z={vp_z}")

        # Extract -vh (horizontal view angle) and -vv (vertical view angle)
        # These define the camera's field of view in degrees
        # Example: -vh 45 means the camera sees 45° horizontally
        vh = float(re.search(r'-vh\s+([\d.-]+)', view_line).group(1))
        vv = float(re.search(r'-vv\s+([\d.-]+)', view_line).group(1))
        print(f"View distance - horizontal (vh): {vh}m, vertical (vv): {vv}m")

        #FIXME: future iteration should determine if -vtl or -vtv is used in the view line. This will determeine how the real world dimensions are calculated. 

        # ===================================================================
        # STEP 5: CALCULATE WORLD DIMENSIONS AND PIXEL SCALE
        # ===================================================================
        # For orthographic views (-vtl), vh and vv are direct real-world dimensions
        # Example: -vh 50.0 -vv 30.0 means the image shows a 50m x 30m area
        # Calculate how many meters (or world units) each pixel represents
        # If image is 800 pixels wide and covers 50 meters, then each pixel = 50/800 = 0.0625m
        # vh = horizontal view dimension (X-axis width)
        # vv = vertical view dimension (Y-axis height)
        world_units_per_pixel_x = vh / width
        world_units_per_pixel_y = vv / height

        print(f"World dimensions: {vh:.3f} x {vv:.3f} units")
        print(f"World units per pixel: x={world_units_per_pixel_x:.6f}, y={world_units_per_pixel_y:.6f}")

        # ===================================================================
        # STEP 6: GENERATE AND SAVE THE PIXEL-TO-WORLD MAPPING FILE
        # ===================================================================
        # Now we create a text file that maps every pixel to its world coordinate
        # This file will be used later for spatial analysis (e.g., AOI stamping)


        output_file = hdr_file_path.parent.parent / "aoi" / "pixel_to_world_coordinate_map.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the mapping file
        with open(output_file, 'w') as f:
            # Write view_line as first header line
            f.write(f"# VIEW: {view_line}\n")
            # Write image dimensions as second header line
            f.write(f"# Image dimensions in pixels: width={width}, height={height}\n")
            # Write world dimensions as third header line
            f.write(f"# World dimensions in meters: width={vh:.6f}, height={vv:.6f}\n")
            # Write column header line
            f.write("# pixel_x pixel_y world_x world_y\n")

            # Map each pixel to world coordinates (pixel 0,0 = top-left, world coords centered on viewpoint)
            for py in range(height):
                for px in range(width):
                    world_x = vp_x + (px - width/2) * world_units_per_pixel_x
                    world_y = vp_y + (height/2 - py) * world_units_per_pixel_y  # Y-axis flipped
                    f.write(f"{px} {py} {world_x:.6f} {world_y:.6f}\n")

        print(f"Pixel-to-world coordinate mapping saved to: {output_file}")

        # Display some example mappings to verify correctness
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

        print(f"Coordinate mapping generated for: {hdr_file_path.name}")
        return output_file

    except Exception as e:
        print(f"Error creating pixel-to-world mapping: {e}")
        return None


