import concurrent.futures
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple, Union
from PIL import Image
import numpy as np
import open3d as o3d
import pandas as pd
import tkinter as tk
from archilume import config

# Visualization color constants
DEFAULT_GLASS_COLOR = [0.0, 0.4, 0.7]  # Ocean blue for glass materials
DEFAULT_MATERIAL_COLOR = [0.7, 0.7, 0.7]  # Gray for non-glass materials
MESH_PALETTE_COLORS = [
    [0.8, 0.2, 0.2],  # Red
    [0.2, 0.8, 0.2],  # Green
    [0.2, 0.2, 0.8],  # Blue
    [0.8, 0.8, 0.2],  # Yellow
    [0.8, 0.2, 0.8],  # Magenta
    [0.2, 0.8, 0.8]   # Cyan
]
WIREFRAME_COLOR = [0.2, 0.2, 0.2]  # Dark gray for wireframe
BACKGROUND_COLOR = [0.1, 0.1, 0.1]  # Dark background


class Timekeeper:
    """Track phase timing for analysis pipelines."""

    def __init__(self):
        self.phase_timings = {}
        self.phase_start = None
        self.script_start_time = time.time()

    def __call__(self, phase_name):
        """Track phase timing and reset timer for next phase."""
        if self.phase_start is not None:
            self.phase_timings[phase_name] = time.time() - self.phase_start
        self.phase_start = time.time()

    def print_report(
        self,
        output_dir: Optional[Path] = None,
        main_phases: Optional[list] = None,
        rendering_subphases: Optional[list] = None,
        postprocessing_subphases: Optional[list] = None
    ) -> None:
        """
        Print a formatted timing report for analysis pipeline execution.

        Args:
            output_dir: Optional path to output directory to display at end of report
            main_phases: Optional list of main phase names in display order
            rendering_subphases: Optional list of rendering sub-phase names
            postprocessing_subphases: Optional list of post-processing sub-phase names
        """
        total_runtime = time.time() - self.script_start_time

        # Default phase ordering if not provided
        if main_phases is None:
            main_phases = ["Phase 1: 3D Scene", "Phase 2: Sky Conditions",
                          "Phase 3: Camera Views", "Phase 4: Rendering",
                          "Phase 5: Post-Processing"]

        if rendering_subphases is None:
            rendering_subphases = ["    Command preparation", "    Overcast octree creation",
                                  "    Ambient file warming (overture)", "    Indirect diffuse rendering",
                                  "    Sunny sky octrees", "    Sunlight rendering",
                                  "    HDR combination & TIFF conversion"]

        if postprocessing_subphases is None:
            postprocessing_subphases = ["  5a: Generate AOI", "  5b: Generate WPD", "  5c: Stamp Images"]

        print("\n" + "=" * 80 + "\nANALYSIS COMPLETE\n" + "=" * 80 +
              "\n\nExecution Time Summary:\n" + "-" * 80)

        # Print in organized order
        for phase_name in main_phases:
            if phase_name in self.phase_timings:
                duration = self.phase_timings[phase_name]
                percentage = (duration / total_runtime) * 100
                print(f"{phase_name:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

                # Print sub-phases after Phase 4
                if phase_name == "Phase 4: Rendering":
                    for subphase in rendering_subphases:
                        if subphase in self.phase_timings:
                            duration = self.phase_timings[subphase]
                            percentage = (duration / total_runtime) * 100
                            print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

                # Print sub-phases after Phase 5
                elif phase_name == "Phase 5: Post-Processing":
                    for subphase in postprocessing_subphases:
                        if subphase in self.phase_timings:
                            duration = self.phase_timings[subphase]
                            percentage = (duration / total_runtime) * 100
                            print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

        print("-" * 80 + f"\n{'Total Runtime':<45} {total_runtime:>8.2f}s  ({total_runtime/60:>5.1f} min)")

        if output_dir:
            print("=" * 80 + f"\n\nOutput directory: {output_dir}\n" + "=" * 80)
        else:
            print("=" * 80)


def parse_mtl_file(mtl_path: Path) -> dict:
    """Parse MTL file and return material definitions.

    Returns a dictionary mapping material names to their properties:
    {
        'material_name': {
            'Kd': [r, g, b],  # diffuse color
            'd': float,       # transparency (dissolve)
            'is_glass': bool  # True if material contains 'glass' or has low opacity
        }
    }
    """
    materials = {}
    current_material = None

    if not mtl_path.exists():
        print(f"Warning: MTL file not found: {mtl_path}")
        return materials

    with open(mtl_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('newmtl '):
                current_material = line[7:].strip()
                materials[current_material] = {
                    'Kd': [0.8, 0.8, 0.8],
                    'd': 1.0,
                    'is_glass': False
                }
            elif line.startswith('Kd ') and current_material:
                parts = line.split()
                if len(parts) >= 4:
                    materials[current_material]['Kd'] = [float(parts[1]), float(parts[2]), float(parts[3])]
            elif line.startswith('d ') and current_material:
                parts = line.split()
                if len(parts) >= 2:
                    materials[current_material]['d'] = float(parts[1])

    # Identify glass materials based on name or transparency
    for mat_name, props in materials.items():
        mat_lower = mat_name.lower()
        if 'glass' in mat_lower or 'gl' in mat_lower or 'glaz' in mat_lower or props['d'] < 0.5:
            props['is_glass'] = True

    return materials


def parse_obj_materials(obj_path: Path) -> dict:
    """Parse OBJ file to extract face-to-material mapping.

    Returns a dictionary:
    {
        'materials': ['mat1', 'mat2', ...],  # material name for each face
        'face_count': int                     # total number of faces
    }
    """
    face_materials = []
    current_material = None

    with open(obj_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('usemtl '):
                current_material = line[7:].strip()
            elif line.startswith('f '):
                face_materials.append(current_material)

    return {
        'materials': face_materials,
        'face_count': len(face_materials)
    }


def display_obj(filenames: Union[str, Path, List[Union[str, Path]]],
                mtl_path: Optional[Path] = None,
                glass_color: Optional[List[float]] = None):
    """Display OBJ files using open3d with enhanced visualization.

    Args:
        filenames: OBJ file path(s) to display
        mtl_path: Optional MTL file path for material definitions
        glass_color: Optional RGB color for glass materials [r, g, b] in range [0, 1]
                    Default is ocean blue [0.0, 0.4, 0.7]
    """
    if isinstance(filenames, (str, Path)):
        filenames = [filenames]

    # Default ocean blue for glass
    if glass_color is None:
        glass_color = DEFAULT_GLASS_COLOR

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

    # Parse MTL file if provided
    materials = {}
    if mtl_path:
        print(f"Loading materials from: {mtl_path.name}")
        materials = parse_mtl_file(mtl_path)
        glass_materials = [name for name, props in materials.items() if props['is_glass']]
        if glass_materials:
            print(f"Found {len(glass_materials)} glass materials: {', '.join(glass_materials[:5])}{' ...' if len(glass_materials) > 5 else ''}")

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

        # Apply material-based coloring if MTL file is provided
        if mtl_path and materials:
            # Parse OBJ file to get face-to-material mapping
            obj_face_info = parse_obj_materials(filename)
            face_materials = obj_face_info['materials']

            # Create per-vertex color array
            num_triangles = len(mesh.triangles)
            vertex_colors = np.zeros((len(mesh.vertices), 3))
            vertex_color_count = np.zeros(len(mesh.vertices))

            # Assign colors per face based on material
            for face_idx, mat_name in enumerate(face_materials):
                if face_idx >= num_triangles:
                    break

                # Determine color for this face
                if mat_name and mat_name in materials:
                    mat_props = materials[mat_name]
                    if mat_props['is_glass']:
                        face_color = glass_color
                    else:
                        face_color = mat_props['Kd']
                else:
                    face_color = DEFAULT_MATERIAL_COLOR

                # Apply color to the three vertices of this triangle
                triangle = mesh.triangles[face_idx]
                for vertex_idx in triangle:
                    vertex_colors[vertex_idx] += face_color
                    vertex_color_count[vertex_idx] += 1

            # Average colors for shared vertices
            for i in range(len(mesh.vertices)):
                if vertex_color_count[i] > 0:
                    vertex_colors[i] /= vertex_color_count[i]

            mesh.vertex_colors = o3d.utility.Vector3dVector(vertex_colors)
            print(f"Applied material-based coloring to {filename.name}")
        else:
            # Apply different colors for each mesh for distinction (fallback)
            color_index = len(valid_files) - 1
            mesh.paint_uniform_color(MESH_PALETTE_COLORS[color_index % len(MESH_PALETTE_COLORS)])

        # Combine meshes
        combined_mesh += mesh
    
    if len(valid_files) == 0:
        print("No valid OBJ files found.")
        return

    # Add ground plane if only one OBJ file
    if len(valid_files) == 1:
        # Calculate bounding box of the combined mesh
        bbox = combined_mesh.get_axis_aligned_bounding_box()
        min_bound = bbox.min_bound
        max_bound = bbox.max_bound

        # Calculate X and Y extents
        x_extent = max_bound[0] - min_bound[0]
        y_extent = max_bound[1] - min_bound[1]
        center_x = (min_bound[0] + max_bound[0]) / 2
        center_y = (min_bound[1] + max_bound[1]) / 2

        # Ground plane size: at least 10x the X,Y bounding box extents
        plane_width = max(x_extent, y_extent) * 10
        plane_height = max(x_extent, y_extent) * 10

        # Create ground plane at the minimum Z level
        ground_z = min_bound[2]

        # Create a simple plane mesh using two triangles
        plane_mesh = o3d.geometry.TriangleMesh()

        # Define the four corners of the plane centered on the model's X,Y center
        half_w = plane_width / 2
        half_h = plane_height / 2
        vertices = [
            [center_x - half_w, center_y - half_h, ground_z],
            [center_x + half_w, center_y - half_h, ground_z],
            [center_x + half_w, center_y + half_h, ground_z],
            [center_x - half_w, center_y + half_h, ground_z]
        ]

        # Two triangles to form the rectangle
        triangles = [
            [0, 1, 2],
            [0, 2, 3]
        ]

        plane_mesh.vertices = o3d.utility.Vector3dVector(vertices)
        plane_mesh.triangles = o3d.utility.Vector3iVector(triangles)
        plane_mesh.compute_vertex_normals()

        # Color the ground plane light gray
        plane_mesh.paint_uniform_color([0.6, 0.6, 0.6])

        # Add plane to combined mesh
        combined_mesh += plane_mesh

        print(f"Ground plane added: {plane_width:.2f} x {plane_height:.2f} units at Z={ground_z:.2f}")

    # Create coordinate frame for reference
    coordinate_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)
    
    # Create wireframe for better structure visualization
    wireframe = o3d.geometry.LineSet.create_from_triangle_mesh(combined_mesh)
    wireframe.paint_uniform_color(WIREFRAME_COLOR)

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
    render_opt.background_color = BACKGROUND_COLOR  # Dark background
    render_opt.mesh_show_back_face = True
    render_opt.mesh_show_wireframe = False  # Wireframe off by default
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
        # Filter out destination paths where the final file (without _temp suffix) already exists
        def check_file_exists(dest_path):
            """Check if destination or its non-temp equivalent exists."""
            dest_str = str(dest_path)
            # If this is a temp file, check if the final (non-temp) version exists
            if '_temp.' in dest_str:
                final_path = dest_str.replace('_temp.', '.')
                return os.path.exists(final_path)
            # Otherwise just check the destination itself
            return os.path.exists(dest_path)

        filtered_paths = [dest for dest in destination_paths if not check_file_exists(dest)]

        if not filtered_paths:
            print(f"All destination paths (or their final versions) already exist. No files to copy.")

        if len(filtered_paths) < len(destination_paths):
            skipped_count = len(destination_paths) - len(filtered_paths)
            print(f"Skipping {skipped_count} existing destination(s) (checking for final file versions).")
        
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
                env['RAYPATH'] = config.RAYPATH

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

def get_hdr_resolution(hdr_file_path: Union[Path, str]) -> tuple[int, int]:
    """
    Extract image resolution (width, height) from an HDR file header.

    Reads the HDR file header to find the resolution line in the format:
    "-Y <height> +X <width>" which is the standard Radiance HDR format.

    Args:
        hdr_file_path (Path or str): Path to the HDR file to read

    Returns:
        tuple[int, int]: A tuple containing (width, height) in pixels

    Raises:
        FileNotFoundError: If HDR file doesn't exist
        ValueError: If resolution line cannot be found or parsed

    Example:
        >>> hdr_path = Path("outputs/images/room_combined.hdr")
        >>> width, height = get_hdr_resolution(hdr_path)
        >>> print(f"Image dimensions: {width}x{height}")
        Image dimensions: 2048x2048
    """
    # Convert to Path object if string is provided
    if isinstance(hdr_file_path, str):
        hdr_file_path = Path(hdr_file_path)

    # Validate that the file exists
    if not hdr_file_path.exists():
        raise FileNotFoundError(f"HDR file not found: {hdr_file_path}")

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

        return (width, height)

    except Exception as e:
        raise ValueError(f"Could not determine image dimensions from HDR file: {e}")

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
        # Step 1: Locate and validate hdr file

        hdr_file_path = next(image_dir.glob('*.hdr'), None)

        if hdr_file_path is None:
            raise FileNotFoundError(f"No HDR files found in {image_dir}")

        print(f"Creating pixel-to-world mapping from: {hdr_file_path.name}")

        # Double-check that the file actually exists on disk
        if not hdr_file_path.exists():
            raise FileNotFoundError(f"HDR file not found: {hdr_file_path}")

        # Step 2: Extract image dimensions

        width, height = get_hdr_resolution(hdr_file_path)

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


def print_timing_report(
    phase_timings: dict,
    total_runtime: float,
    output_dir: Optional[Path] = None,
    main_phases: Optional[list] = None,
    rendering_subphases: Optional[list] = None,
    postprocessing_subphases: Optional[list] = None
) -> None:
    """
    Print a formatted timing report for analysis pipeline execution.

    Args:
        phase_timings: Dictionary mapping phase names to their execution times in seconds
        total_runtime: Total script execution time in seconds
        output_dir: Optional path to output directory to display at end of report
        main_phases: Optional list of main phase names in display order
        rendering_subphases: Optional list of rendering sub-phase names
        postprocessing_subphases: Optional list of post-processing sub-phase names

    Example:
        >>> phase_timings = {"Phase 1: Setup": 5.2, "Phase 2: Render": 120.5}
        >>> print_timing_report(phase_timings, 125.7)
    """
    # Default phase ordering if not provided
    if main_phases is None:
        main_phases = ["Phase 1: 3D Scene", "Phase 2: Sky Conditions",
                      "Phase 3: Camera Views", "Phase 4: Rendering",
                      "Phase 5: Post-Processing"]

    if rendering_subphases is None:
        rendering_subphases = ["    Command preparation", "    Overcast octree creation",
                              "    Ambient file warming (overture)", "    Indirect diffuse rendering",
                              "    Sunny sky octrees", "    Sunlight rendering",
                              "    HDR combination & TIFF conversion"]

    if postprocessing_subphases is None:
        postprocessing_subphases = ["  5a: Generate AOI", "  5b: Generate WPD", "  5c: Stamp Images"]

    print("\n" + "=" * 80 + "\nANALYSIS COMPLETE\n" + "=" * 80 +
          "\n\nExecution Time Summary:\n" + "-" * 80)

    # Print in organized order
    for phase_name in main_phases:
        if phase_name in phase_timings:
            duration = phase_timings[phase_name]
            percentage = (duration / total_runtime) * 100
            print(f"{phase_name:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

            # Print sub-phases after Phase 4
            if phase_name == "Phase 4: Rendering":
                for subphase in rendering_subphases:
                    if subphase in phase_timings:
                        duration = phase_timings[subphase]
                        percentage = (duration / total_runtime) * 100
                        print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

            # Print sub-phases after Phase 5
            elif phase_name == "Phase 5: Post-Processing":
                for subphase in postprocessing_subphases:
                    if subphase in phase_timings:
                        duration = phase_timings[subphase]
                        percentage = (duration / total_runtime) * 100
                        print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

    print("-" * 80 + f"\n{'Total Runtime':<45} {total_runtime:>8.2f}s  ({total_runtime/60:>5.1f} min)")

    if output_dir:
        print("=" * 80 + f"\n\nOutput directory: {output_dir}\n" + "=" * 80)
    else:
        print("=" * 80)


# ============================================================================
# GEOMETRY UTILITIES
# ============================================================================

def get_bounding_box_from_point_coordinates(point_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Generates a Pandas DataFrame containing the 8 corner coordinates of a 3D bounding box
    from an input Pandas DataFrame containing 'x_coords', 'y_coords', and 'z_coords' columns.

    Args:
        point_dataframe (pd.DataFrame): A Pandas DataFrame that must include
                                        'x_coords', 'y_coords', and 'z_coords' columns
                                        representing the coordinates of the points.

    Returns:
        pd.DataFrame: A Pandas DataFrame with 8 rows (one for each corner) and
                      columns ['x_coords', 'y_coords', 'z_coords'].
                      Returns an empty DataFrame if the input DataFrame is empty, doesn't
                      have the required columns, is not a DataFrame, or if an error occurs
                      during min/max calculation.
    """
    # --- 1. Input Validation ---
    # Check if the input is a Pandas DataFrame
    if not isinstance(point_dataframe, pd.DataFrame):
        print("Error: Input must be a Pandas DataFrame.")
        return pd.DataFrame()  # Return an empty DataFrame

    # Check if the DataFrame is empty
    if point_dataframe.empty:
        print("Warning: Input DataFrame is empty. Returning an empty DataFrame.")
        return pd.DataFrame()  # Return an empty DataFrame

    # Check for required columns
    required_columns = ["x_coords", "y_coords", "z_coords"]
    for col in required_columns:
        if col not in point_dataframe.columns:
            print(f"Error: DataFrame is missing the required column '{col}'.")
            return pd.DataFrame()  # Return an empty DataFrame

    # --- 2. Check for numeric data and Find Min/Max Coordinates ---
    try:
        # Check if all required columns contain numeric data
        for col in required_columns:
            if not pd.api.types.is_numeric_dtype(point_dataframe[col]):
                print(f"Error: Column '{col}' must contain numeric data.")
                return pd.DataFrame()

        min_x = point_dataframe["x_coords"].min()
        max_x = point_dataframe["x_coords"].max()
        min_y = point_dataframe["y_coords"].min()
        max_y = point_dataframe["y_coords"].max()
        min_z = point_dataframe["z_coords"].min()
        max_z = point_dataframe["z_coords"].max()
    except TypeError:
        # This can happen if columns are not numeric
        print("Error: Columns 'x_coords', 'y_coords', 'z_coords' must contain numeric data.")
        return pd.DataFrame()  # Return an empty DataFrame
    except Exception as e:
        print(f"Error during min/max calculation: {e}")
        return pd.DataFrame()  # Return an empty DataFrame

    # --- 3. Construct Corner Points ---
    # Based on the min/max values extracted, define the 8 corners.
    corners_list = [
        (min_x, min_y, min_z),  # Bottom-left-front
        (max_x, min_y, min_z),  # Bottom-right-front
        (min_x, max_y, min_z),  # Top-left-front
        (max_x, max_y, min_z),  # Top-right-front
        (min_x, min_y, max_z),  # Bottom-left-back
        (max_x, min_y, max_z),  # Bottom-right-back
        (min_x, max_y, max_z),  # Top-left-back
        (max_x, max_y, max_z),  # Top-right-back
    ]

    # --- 4. Convert list of corners to DataFrame ---
    # The DataFrame will have the same column names as the input for consistency.
    corners_df = pd.DataFrame(corners_list, columns=["x_coords", "y_coords", "z_coords"])

    return corners_df

def get_center_of_bounding_box(box_corners_df: pd.DataFrame) -> Optional[Tuple[float, float, float]]:
    """
    Calculates the center coordinate of a 3D bounding box and returns it as a tuple.

    Args:
        box_corners_df (pd.DataFrame): A Pandas DataFrame with columns
                                       ['x_coords', 'y_coords', 'z_coords']
                                       representing the corner coordinates.

    Returns:
        tuple: A tuple (x, y, z) representing the center coordinate.
               Returns None if input is invalid.
    """
    # --- 1. Input Validation ---
    if (
        not isinstance(box_corners_df, pd.DataFrame)
        or box_corners_df.empty
        or not all(col in box_corners_df.columns for col in ["x_coords", "y_coords", "z_coords"])
    ):
        # print("Error or Warning: Input DataFrame invalid, empty, or missing required columns.") # Optional: keep print for debugging
        return None

    # --- 2. Calculate Min/Max Coordinates ---
    try:
        min_x = box_corners_df["x_coords"].min()
        max_x = box_corners_df["x_coords"].max()
        min_y = box_corners_df["y_coords"].min()
        max_y = box_corners_df["y_coords"].max()
        min_z = box_corners_df["z_coords"].min()
        max_z = box_corners_df["z_coords"].max()
    except (TypeError, Exception):
        # print("Error: Non-numeric data or other issue during min/max calculation.") # Optional
        return None

    # --- 3. Calculate Center Coordinates ---
    x_coord_center = (min_x + max_x) / 2
    y_coord_center = (min_y + max_y) / 2
    z_coord_center = (min_z + max_z) / 2

    # --- 4. Return as tuple ---
    return (x_coord_center, y_coord_center, z_coord_center)

def calculate_dimensions_from_points(df_points: pd.DataFrame, x_col: str = "x_coords", y_col: str = "y_coords") -> Tuple[Optional[float], Optional[float]]:
    """
    Calculates the width (x_max - x_min) and depth (y_max - y_min)
    from a DataFrame of points.

    Args:
        df_points (pd.DataFrame): DataFrame containing the point coordinates.
                                  It must have columns for x and y values.
        x_col (str): The name of the column containing the x-coordinates.
                     Defaults to 'x_coords'.
        y_col (str): The name of the column containing the y-coordinates.
                     Defaults to 'y_coords'.

    Returns:
        tuple[float | None, float | None]: A tuple containing two float values:
                                           (width, depth).
                                           Returns (None, None) if the input
                                           DataFrame is empty, if specified
                                           columns are not found, or if an
                                           error occurs during calculation.
    """
    if df_points.empty:
        return None, None

    if x_col not in df_points.columns or y_col not in df_points.columns:
        return None, None

    try:
        # Ensure columns are numeric and handle potential NaNs that could arise from non-numeric data
        # If min/max is called on an entirely non-numeric or empty (after dropping NaNs) series, it can raise.
        if not pd.api.types.is_numeric_dtype(
            df_points[x_col]
        ) or not pd.api.types.is_numeric_dtype(df_points[y_col]):
            # Attempt to convert to numeric, coercing errors to NaN
            x_series = pd.to_numeric(df_points[x_col], errors="coerce")
            y_series = pd.to_numeric(df_points[y_col], errors="coerce")
            if x_series.isnull().all() or y_series.isnull().all():  # if all values became NaN
                return None, None
        else:
            x_series = df_points[x_col]
            y_series = df_points[y_col]

        x_min = x_series.min()
        x_max = x_series.max()
        y_min = y_series.min()
        y_max = y_series.max()

        # If min or max returned NaN (e.g., if all values were NaN after coercion)
        if pd.isna(x_min) or pd.isna(x_max) or pd.isna(y_min) or pd.isna(y_max):
            return None, None

        width = x_max - x_min
        depth = y_max - y_min

        return float(width), float(depth)

    except Exception:
        return None, None

def calc_centroid_of_points(df: pd.DataFrame, x_col: str = "x_coords", y_col: str = "y_coords") -> Optional[Tuple[float, float]]:
    """
    Calculates the centroid from coordinates in a pandas DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame containing the coordinates.
        x_col (str): The name of the column containing x-coordinates.
        y_col (str): The name of the column containing y-coordinates.

    Returns:
        tuple or None: A tuple (x, y) for the centroid, or None if the DataFrame is empty.
    """
    if df.empty:
        return None

    # Use the built-in .mean() method for efficiency
    centroid_x = df[x_col].mean()
    centroid_y = df[y_col].mean()

    return (centroid_x, centroid_y)

