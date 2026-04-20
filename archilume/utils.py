import concurrent.futures
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import psutil
import pymupdf as fitz
from PIL import Image
from archilume import config


@dataclass(frozen=True)
class PixelToWorldMap:
    """In-memory pixel<->world mapping derived from a Radiance HDR header.

    Captures everything downstream code (Hdr2Wpd, ViewGenerator) used to read
    out of the legacy `pixel_to_world_coordinate_map.txt` file. Built once per
    HDR via `compute_pixel_to_world_map(hdr_path)`.
    """
    hdr_path: Path
    image_width: int
    image_height: int
    world_width_m: float
    world_height_m: float
    vp_x: float
    vp_y: float

    @property
    def world_units_per_pixel_x(self) -> float:
        return self.world_width_m / self.image_width

    @property
    def world_units_per_pixel_y(self) -> float:
        return self.world_height_m / self.image_height

    @property
    def area_per_pixel_m2(self) -> float:
        return self.world_units_per_pixel_x * self.world_units_per_pixel_y



class Timekeeper:
    """Track phase timing for analysis pipelines with context manager support."""

    def __init__(self):
        self.phase_timings = {}
        self.phase_start = None
        self.script_start_time = time.time()
        self._current_phase_name = None
        self._current_print_header = False

    def __call__(self, phase_name: str, print_header: bool = True):
        """
        Use as context manager or legacy timing tracker.

        Usage:
            # As context manager:
            with timekeeper("Phase 1: Description"):
                # work here

            # Legacy mode (for backward compatibility):
            timekeeper("Phase 1: Description")
        """
        # Check if being used as context manager
        self._current_phase_name = phase_name
        self._current_print_header = print_header

        # Legacy behavior: track phase timing and reset timer
        if self.phase_start is not None:
            # This handles the old-style usage
            self.phase_timings[phase_name] = time.time() - self.phase_start
        self.phase_start = time.time()

        # Return self to enable context manager usage
        return self

    def __enter__(self):
        """Enter context manager."""
        if self._current_print_header:
            print(f"\n{'=' * 100}\n{self._current_phase_name}\n{'=' * 100}")
        self.phase_start = time.time()
        return self

    def __exit__(self, *args):
        """Exit context manager and record timing."""
        self.phase_timings[self._current_phase_name] = time.time() - self.phase_start
        self._current_phase_name = None
        self._current_print_header = False

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
            main_phases = [
                "Phase 0: Input 3D Scene Files and Rendering Parameters...",
                "Phase 1: Establishing 3D Scene...",
                "Phase 2: Generate Sky Conditions for Analysis...",
                "Phase 3: Prepare Camera Views...",
                "Phase 4: Executing Rendering Pipeline...",
                "Phase 5: Post-Process Stamping of Results...",
                "Phase 6: Package Final Results and Simulation Summary..."
            ]

        if rendering_subphases is None:
            rendering_subphases = [
                "    Command preparation",
                "    Overcast octree creation",
                "    Overcast rendering (CPU)",
                "    Overcast rendering (GPU)",
                "    Ambient file warming (overture)",
                "    Indirect diffuse rendering",
                "    GPU rendering (total)",
                "    Sunny sky octrees",
                "    Sunlight rendering",
                "    HDR combination & TIFF conversion",
                "    TIFF to PNG conversion"
            ]

        if postprocessing_subphases is None:
            postprocessing_subphases = [
                "  5a: Generate AOI files...",
                "  5b: Generate Sunlit WPD and send to .xlsx...",
                "  5c: Stamp images with results and combine into .apng..."
            ]

        print("\n" + "=" * 80 + "\nANALYSIS COMPLETE\n" + "=" * 80 +
              "\n\nExecution Time Summary:\n" + "-" * 80)

        # Print in organized order
        for phase_name in main_phases:
            if phase_name in self.phase_timings:
                duration = self.phase_timings[phase_name]
                percentage = (duration / total_runtime) * 100
                print(f"{phase_name:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

                # Print sub-phases after Phase 4
                if phase_name == "Phase 4: Executing Rendering Pipeline...":
                    for subphase in rendering_subphases:
                        if subphase in self.phase_timings:
                            duration = self.phase_timings[subphase]
                            percentage = (duration / total_runtime) * 100
                            print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

                # Print sub-phases after Phase 5
                elif phase_name == "Phase 5: Post-Process Stamping of Results...":
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


class PhaseTimer:
    """
    Self-contained phase timing manager with context manager support and reporting.

    Usage:
        # Initialize once at start of script
        timer = PhaseTimer()

        # Use as context manager for each phase
        with timer("Phase 1: Description..."):
            # work here

        # Print final report
        timer.print_report(output_dir=some_path)
    """
    def __init__(self):
        self.phase_timings = {}
        self.script_start_time = time.time()
        self._context_stack = []  # Stack to handle nested timer contexts
        self._phase_hierarchy = {}  # Maps child phases to their parent phase

    def __call__(self, phase_name: str, print_header: bool = True):
        """Prepare for use as context manager."""
        # Track parent-child relationships for nested timers
        if len(self._context_stack) > 0:
            parent_name = self._context_stack[-1]['name']
            self._phase_hierarchy[phase_name] = parent_name

        # Push new context onto stack
        self._context_stack.append({
            'name': phase_name,
            'print_header': print_header,
            'start_time': None
        })
        return self

    def __enter__(self):
        """Enter context manager and optionally print header."""
        if not self._context_stack:
            raise RuntimeError("__enter__ called without __call__")

        context = self._context_stack[-1]
        if context['print_header']:
            print(f"\n{'=' * 100}\n{context['name']}\n{'=' * 100}")
        context['start_time'] = time.time()
        return self

    def __exit__(self, *args):
        """Exit context manager and record timing."""
        if not self._context_stack:
            raise RuntimeError("__exit__ called without matching __enter__")

        context = self._context_stack.pop()
        duration = time.time() - context['start_time']
        self.phase_timings[context['name']] = duration

    def update(self, additional_timings: dict, parent_phase: Optional[str] = None):
        """
        Merge additional timings into phase_timings (e.g., from sub-pipelines).

        Args:
            additional_timings: Dictionary of phase names to durations
            parent_phase: Optional parent phase name. If provided, all phases in
                         additional_timings will be marked as children of this parent.
                         If None, will use the current active phase (top of context stack).
        """
        self.phase_timings.update(additional_timings)

        # Associate these phases with a parent if specified or if we're inside a timer context
        if parent_phase is None and len(self._context_stack) > 0:
            parent_phase = self._context_stack[-1]['name']

        if parent_phase:
            for phase_name in additional_timings.keys():
                self._phase_hierarchy[phase_name] = parent_phase

    def print_report(
        self,
        output_dir: Optional[Path] = None,
        main_phases: Optional[list] = None,
        rendering_subphases: Optional[list] = None,
        postprocessing_subphases: Optional[list] = None
    ) -> None:
        """
        Print a formatted timing report for analysis pipeline execution.

        Auto-detects phase hierarchy from recorded timings based on naming patterns:
        - Lines starting with "Phase N:" are treated as main phases
        - Lines with 4 leading spaces are rendering subphases (under Phase 4)
        - Lines with 2 leading spaces are postprocessing subphases (under Phase 5)
        - All other phases are printed in execution order

        Args:
            output_dir: Optional path to output directory to display at end of report
            main_phases: Optional list to override auto-detected main phases
            rendering_subphases: Optional list to override auto-detected rendering subphases
            postprocessing_subphases: Optional list to override auto-detected postprocessing subphases
        """
        total_runtime = time.time() - self.script_start_time

        # Build subphases_by_parent from the hierarchy tracked during execution
        subphases_by_parent = {}
        for child, parent in self._phase_hierarchy.items():
            if parent not in subphases_by_parent:
                subphases_by_parent[parent] = []
            subphases_by_parent[parent].append(child)

        # Auto-detect phase structure if not provided
        if main_phases is None or rendering_subphases is None or postprocessing_subphases is None:
            detected_main = []
            detected_rendering = []
            detected_postprocessing = []
            other_phases = []

            # Preserve insertion order (Python 3.7+ dict feature)
            for phase_name in self.phase_timings.keys():
                # Skip phases that are children of another phase
                if phase_name in self._phase_hierarchy:
                    # This is a subphase - categorize by indentation
                    if phase_name.startswith('    '):  # 4 spaces = rendering subphase
                        detected_rendering.append(phase_name)
                    elif phase_name.startswith('  '):  # 2 spaces = postprocessing subphase
                        detected_postprocessing.append(phase_name)
                elif re.match(r'^Phase \d+:', phase_name):
                    # This is a main phase
                    detected_main.append(phase_name)
                else:
                    # Other top-level phases (for custom workflows)
                    other_phases.append(phase_name)

            # Use detected phases if not explicitly provided
            if main_phases is None:
                main_phases = detected_main if detected_main else other_phases
            if rendering_subphases is None:
                rendering_subphases = detected_rendering
            if postprocessing_subphases is None:
                postprocessing_subphases = detected_postprocessing

        print("\n" + "=" * 80 + "\nANALYSIS COMPLETE\n" + "=" * 80 +
              "\n\nExecution Time Summary:\n" + "-" * 80)

        # Print in organized order
        for phase_name in main_phases:
            if phase_name in self.phase_timings:
                duration = self.phase_timings[phase_name]
                percentage = (duration / total_runtime) * 100
                print(f"{phase_name:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")

                # Print subphases if they exist for this parent phase
                if phase_name in subphases_by_parent and subphases_by_parent[phase_name]:
                    for subphase in subphases_by_parent[phase_name]:
                        if subphase in self.phase_timings:
                            duration = self.phase_timings[subphase]
                            percentage = (duration / total_runtime) * 100
                            print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")
                # Legacy fallback: for manually specified phases, use old behavior
                elif re.search(r'Phase 4.*Rendering', phase_name, re.IGNORECASE) and rendering_subphases:
                    for subphase in rendering_subphases:
                        if subphase in self.phase_timings:
                            duration = self.phase_timings[subphase]
                            percentage = (duration / total_runtime) * 100
                            print(f"{subphase:<45} {duration:>8.2f}s  ({percentage:>5.1f}%)")
                elif re.search(r'Phase 5.*Post', phase_name, re.IGNORECASE) and postprocessing_subphases:
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
                else:
                    skipped_count += 1
    else:
        # Sequential deletion
        for file_path in file_paths:
            filename, success, error = _delete_single_file(file_path)
            if success:
                deleted_count += 1
            else:
                skipped_count += 1

    # Only print summary if files were actually deleted
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} temporary file(s)")
         
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
        # Track which command index we're on for selective verbose output
        command_counter = {'count': 0, 'total': len(commands), 'completed': 0, 'last_printed_pct': -1, 'last_render_pct': -1}

        def _run_command_with_progress(command: str) -> None:
            """Execute a single command with real-time output streaming."""
            # Increment counter and determine if this is the first command
            command_counter['count'] += 1
            command_counter['last_render_pct'] = -1  # Reset per-command render progress
            is_first = command_counter['count'] == 1
            is_verbose = is_first  # Only show detailed output for first command

            if is_first:
                # Extract a short description from the command
                if ' > ' in command:
                    output_file = command.split(' > ')[-1].strip()
                    print(f"Starting rendering pipeline...")
                if command_counter['total'] > 1:
                    print(f"Processing {command_counter['total']} commands...")
            else:
                # Abbreviated output for subsequent commands - use carriage return to overwrite
                print(f"\r[{command_counter['completed']}/{command_counter['total']}] Processing...", end='', flush=True)

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
                            # Skip repetitive progress messages entirely
                            if 'frozen octree' in stripped.lower():
                                continue
                            if 'rays,' in stripped.lower() and '%' in stripped:
                                try:
                                    pct = float(stripped.split('%')[0].split()[-1])
                                    last = command_counter.get('last_render_pct', -1)
                                    if int(pct) > last:
                                        command_counter['last_render_pct'] = int(pct)
                                        print(f"\r  Rendering: {pct:.0f}%          ", end='', flush=True)
                                except (ValueError, IndexError):
                                    pass
                                continue
                            # Only show errors (always) or other messages for first command
                            if any(kw in stripped for kw in ['error', 'warning']):
                                if sum(c.isprintable() or c.isspace() for c in stripped) / max(len(stripped), 1) > 0.8:
                                    if is_verbose or 'error' in stripped.lower():
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
                            # Skip repetitive progress messages entirely
                            if 'frozen octree' in stripped.lower():
                                continue
                            if 'rays,' in stripped.lower() and '%' in stripped:
                                try:
                                    pct = float(stripped.split('%')[0].split()[-1])
                                    last = command_counter.get('last_render_pct', -1)
                                    if int(pct) > last:
                                        command_counter['last_render_pct'] = int(pct)
                                        print(f"\r  Rendering: {pct:.0f}%          ", end='', flush=True)
                                except (ValueError, IndexError):
                                    pass
                                continue
                            # Only show errors (always) or other messages for first command
                            if any(kw in stripped for kw in ['error', 'warning']):
                                if sum(c.isprintable() or c.isspace() for c in stripped) / max(len(stripped), 1) > 0.8:
                                    if is_verbose or 'error' in stripped.lower():
                                        print(stripped, flush=True)

                # Wait for process to complete and get return code
                return_code = process.wait()

                if return_code == 0:
                    command_counter['completed'] += 1

                    # Calculate percentage and print every 1% milestone
                    total = command_counter['total']
                    completed = command_counter['completed']
                    current_pct = int((completed / total) * 100)
                    last_pct = command_counter['last_printed_pct']

                    # Print on every 1% increment (or first/last command)
                    if current_pct > last_pct or completed == total:
                        line = f"\r[{completed}/{total}] {current_pct}% complete"
                        if completed == total:
                            print(f"{line:<40}", flush=True)  # Final: newline
                        else:
                            print(f"{line:<40}", end='', flush=True)  # In-place update
                        command_counter['last_printed_pct'] = current_pct
                else:
                    # Extract output filename for cleaner error message
                    if ' > ' in command:
                        output_file = command.split(' > ')[-1].strip()
                        print(f"\n⚠ Failed (code {return_code}): {Path(output_file).name}")
                    else:
                        # Fallback to showing just the command name
                        cmd_name = command.split()[0] if command else 'command'
                        print(f"\n⚠ Failed (code {return_code}): {cmd_name}")

            except Exception as e:
                # Always show errors - print on new line
                print(f"\nError executing command '{command}': {e}")
        
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

        # Print summary if multiple commands were executed
        if command_counter['total'] > 1:
            failed = command_counter['total'] - command_counter['completed']
            if failed > 0:
                print(f"\n\n[OK] Completed {command_counter['completed']}/{command_counter['total']} commands ({failed} failed)")
            else:
                print(f"\n\n[OK] Completed all {command_counter['total']} commands")

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

    # Completion message already printed by _execute_commands_with_progress
    pass

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
        >>> view_files = [Path('plan_ffl_90000.vp'), Path('section_A.vp')]
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

def compute_pixel_to_world_map(hdr_path_or_dir: Path) -> PixelToWorldMap:
    """Compute the pixel<->world mapping from a Radiance HDR header.

    Accepts either a direct HDR path or a directory (in which case the first
    `*.hdr` / `*.pic` is used). Pure compute — no files are written.
    """
    try:
        if hdr_path_or_dir.is_dir():
            hdr_file_path = (
                next(hdr_path_or_dir.glob('*.hdr'), None)
                or next(hdr_path_or_dir.glob('*.pic'), None)
            )
            if hdr_file_path is None:
                raise FileNotFoundError(f"No HDR files found in {hdr_path_or_dir}")
        else:
            hdr_file_path = hdr_path_or_dir

        if not hdr_file_path.exists():
            raise FileNotFoundError(f"HDR file not found: {hdr_file_path}")

        width, height = get_hdr_resolution(hdr_file_path)

        with open(hdr_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            view_line = next((line.strip() for line in f if line.startswith('VIEW=')), None)

        if not view_line:
            raise ValueError("No VIEW line found in HDR file header")

        vp_match = re.search(r'-vp\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', view_line)
        if not vp_match:
            raise ValueError("Could not extract -vp values from VIEW line")
        vp_x, vp_y, _vp_z = map(float, vp_match.groups())

        # FIXME: assumes orthographic (-vtl) view — vh/vv are world dims directly.
        vh = float(re.search(r'-vh\s+([\d.-]+)', view_line).group(1))
        vv = float(re.search(r'-vv\s+([\d.-]+)', view_line).group(1))

        coord_map = PixelToWorldMap(
            hdr_path=hdr_file_path,
            image_width=width,
            image_height=height,
            world_width_m=vh,
            world_height_m=vv,
            vp_x=vp_x,
            vp_y=vp_y,
        )
        print(f"Pixel-to-world: {width}x{height}px -> {vh:.3f}x{vv:.3f}m "
              f"(per-pixel {coord_map.world_units_per_pixel_x:.6f}x{coord_map.world_units_per_pixel_y:.6f}m)")
        return coord_map

    except Exception as e:
        print(f"Error computing pixel-to-world mapping: {e}")
        raise RuntimeError("Failed to compute pixel-to-world coordinate map") from e


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
# IESVE AOI CONVERSION UTILITIES
# ============================================================================

def iesve_aoi_to_room_boundaries_csv(
    iesve_room_data_path: Path,
    output_dir: Path,
) -> Path:
    """
    Convert IESVE .aoi files into a room_boundaries CSV compatible with ViewGenerator.

    Reads each .aoi file from the same directory as iesve_room_data_path, matches its
    Space ID against the IESVE room data spreadsheet to obtain the room name and Z height,
    then writes the combined boundary data as a headerless CSV with coordinates in
    millimeters (as expected by ViewGenerator).

    Output path is auto-generated as {AOI_DIR}/{input_stem}_boundaries.csv

    Args:
        iesve_room_data_path: Path to the IESVE room data spreadsheet (.xlsx disguised as .csv).
                              The .aoi files are expected in the same directory.

    Returns:
        Path to the written CSV file
    """
    output_path = output_dir / f"{Path(iesve_room_data_path).stem}_boundaries.csv"
    aoi_dir = iesve_room_data_path.parent

    # Load IESVE room data - build lookup: Space ID -> (Space Name, Z height in meters)
    room_df = pd.read_excel(iesve_room_data_path)
    room_lookup = {
        row["Space ID"]: (row["Space Name (Real)"], row["Min. Height (m) (Real)"])
        for _, row in room_df.iterrows()
    }

    rows = []
    skipped = []

    for aoi_file in sorted(aoi_dir.glob("*.aoi")):
        with open(aoi_file, "r") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        # Parse ZONE line: "ZONE BL00000A B L3"
        zone_parts = lines[1].split(maxsplit=2)  # ["ZONE", "BL00000A", "B L3"]
        space_id = zone_parts[1]

        if space_id not in room_lookup:
            skipped.append(space_id)
            continue

        space_name, z_height_m = room_lookup[space_id]
        z_mm = z_height_m * 1000

        # Parse coordinate lines (after "POINTS N" header) - convert m to mm for ViewGenerator
        coord_strings = []
        for line in lines[3:]:
            parts = line.split()
            if len(parts) >= 2:
                x_mm = float(parts[0]) * 1000
                y_mm = float(parts[1]) * 1000
                coord_strings.append(f"X_{x_mm:.3f} Y_{y_mm:.3f} Z_{z_mm:.3f}")

        row = [space_id, space_name] + coord_strings
        rows.append(",".join(str(v) for v in row))

    # Pad all rows to the same column count (required by pd.read_csv)
    max_cols = max(row.count(",") + 1 for row in rows) if rows else 0
    padded_rows = []
    for row in rows:
        num_cols = row.count(",") + 1
        row += "," * (max_cols - num_cols)
        padded_rows.append(row)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(padded_rows) + "\n")

    print(f"Room boundaries CSV written: {output_path}")
    print(f"  Rooms written: {len(rows)}, Skipped (no match): {len(skipped)}")
    if skipped:
        print(f"  Skipped Space IDs: {skipped}")

    return output_path


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


# ============================================================================
# SMART CLEANUP UTILITIES
# ============================================================================

def clear_outputs_folder(paths: "config.ProjectPaths", retain_amb_files: bool = False, retain_octree: bool = False) -> None:
    """
    Remove all files from the outputs folder while preserving directory structure.

    Args:
        retain_amb_files: If True, keeps .amb files in the images directory.
                         If False, removes all files.
        retain_octree: If True, keeps the entire octree folder and its contents.
                      If False, removes octree files like other folders.
    """
    outputs_dir = paths.outputs_dir

    if not outputs_dir.exists():
        print(f"Outputs directory does not exist: {outputs_dir}")
        return

    # Recursively remove files while preserving directories
    def clear_directory(directory: Path, keep_amb: bool = False, skip_octree: bool = False):
        for item in directory.iterdir():
            # Skip entire octree directory if retain_octree is True
            if skip_octree and item.is_dir() and item.name == "octree":
                print(f"Retained: {item.relative_to(outputs_dir)}/ (entire folder)")
                continue

            if item.is_file():
                # Skip .amb files if retain_amb_files is True and we're in images directory
                if keep_amb and item.suffix == ".amb":
                    print(f"Retained: {item.relative_to(outputs_dir)}")
                    continue
                item.unlink()
                print(f"Removed: {item.relative_to(outputs_dir)}")
            elif item.is_dir():
                # Apply amb retention only to images directory
                should_keep_amb = retain_amb_files and item.name == "images"
                clear_directory(item, keep_amb=should_keep_amb, skip_octree=False)

    clear_directory(outputs_dir, skip_octree=retain_octree)
    print(f"\nOutputs folder cleanup complete. Directory structure preserved.")


# ── PDF Floor Plan Utilities ──────────────────────────────────────────────────

def rasterize_pdf_page(
    pdf_path: Path,
    page_index: int,
    dpi: int = 150,
) -> np.ndarray:
    """Rasterize one PDF page to an RGBA numpy array at the given DPI.

    Output pixel dimensions are determined by the PDF page's physical size in mm
    (1 pt = 25.4/72 mm) scaled to the requested DPI. A 150 DPI default gives
    a good balance of sharpness and memory for typical A1/A0 floor plans.

    Returns (H, W, 4) uint8 array with alpha=255.
    """

    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    rect = page.rect  # dimensions in points (72 pts = 1 inch = 25.4 mm)

    # scale = target DPI / PDF native DPI (72)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)

    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3).copy()
    doc.close()

    # Convert RGB → RGBA
    rgba = np.zeros((img.shape[0], img.shape[1], 4), dtype=np.uint8)
    rgba[:, :, :3] = img
    rgba[:, :, 3] = 255
    return rgba


def make_lines_only(
    rgba: np.ndarray,
    white_threshold: int = 240,
) -> np.ndarray:
    """Make near-white pixels fully transparent, keeping dark linework opaque.

    Uses integer-based luminance calculation (faster than float) to identify
    near-white pixels and set their alpha channel to 0. Modifies the array
    in-place to reduce memory overhead.

    Returns the modified (H, W, 4) uint8 array.
    """
    # Using integer weights for luminance: 0.299*256~77, 0.587*256~150, 0.114*256~29
    # This avoids float conversions and is much faster for large images.
    r = rgba[:, :, 0].astype(np.uint16)
    g = rgba[:, :, 1].astype(np.uint16)
    b = rgba[:, :, 2].astype(np.uint16)
    lum = (r * 77 + g * 150 + b * 29) >> 8

    rgba[lum > white_threshold, 3] = 0
    return rgba


def get_pdf_info(pdf_path: Path) -> dict:
    """Return page count and per-page dimensions for a PDF file.

    Returns ``{'page_count': int, 'pages': [{'index', 'width_pt', 'height_pt', 'label'}, ...]}``.
    """

    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(doc.page_count):
        rect = doc[i].rect
        pages.append({
            "index": i,
            "width_pt": rect.width,
            "height_pt": rect.height,
            "label": f"Page {i + 1} ({rect.width:.0f}\u00d7{rect.height:.0f} pt)",
        })
    count = doc.page_count
    doc.close()
    return {"page_count": count, "pages": pages}


def start_cpu_logger(log_path: Path) -> threading.Event:
    """Start a background CPU/memory logger using psutil.

    Logs CPU, memory, and top process stats every 30 seconds to *log_path*.

    Args:
        log_path: File path where the log will be written.

    Returns:
        A stop event — pass it to :func:`stop_cpu_logger` to halt logging.
    """
    stop_event = threading.Event()

    def _log_loop():
        psutil.cpu_percent(percpu=True)  # prime — first call always returns 0.0
        with open(log_path, "w") as f:
            while not stop_event.wait(timeout=30.0):
                ts = time.strftime("%H:%M:%S")
                cpu_total = psutil.cpu_percent(interval=None)
                per_core  = psutil.cpu_percent(percpu=True)
                freq      = psutil.cpu_freq()
                load1, load5, load15 = psutil.getloadavg()
                vm = psutil.virtual_memory()
                sw = psutil.swap_memory()
                procs = sorted(
                    psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]),
                    key=lambda p: p.info.get("cpu_percent") or 0.0,
                    reverse=True,
                )[:5]

                f.write(f"=== {ts} ===\n")
                freq_str = f"{freq.current:.0f} MHz" if freq else "n/a"
                f.write(f"CPU total: {cpu_total:.1f}%  freq: {freq_str}  "
                        f"load avg: {load1:.2f} {load5:.2f} {load15:.2f}\n")
                core_str = "  ".join(f"C{i}:{v:.0f}%" for i, v in enumerate(per_core))
                f.write(f"Cores: {core_str}\n")
                cached  = getattr(vm, "cached", None)
                buffers = getattr(vm, "buffers", None)
                mem_str = (
                    f"Mem: used {vm.used/1e6:.0f} MB / {vm.total/1e6:.0f} MB  "
                    f"avail {vm.available/1e6:.0f} MB"
                )
                if cached is not None:
                    mem_str += f"  cached {cached/1e6:.0f} MB"
                if buffers is not None:
                    mem_str += f"  buffers {buffers/1e6:.0f} MB"
                f.write(mem_str + "\n")
                f.write(f"Swap: used {sw.used/1e6:.0f} MB / {sw.total/1e6:.0f} MB\n")
                f.write(f"{'PID':>7}  {'CPU%':>6}  {'MEM MB':>8}  NAME\n")
                for p in procs:
                    try:
                        rss = (p.info["memory_info"].rss if p.info.get("memory_info") else 0) / 1e6
                        f.write(
                            f"{p.info['pid']:>7}  {p.info['cpu_percent']:>6.1f}  "
                            f"{rss:>8.1f}  {p.info['name']}\n"
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                f.write("\n")
                f.flush()

    thread = threading.Thread(target=_log_loop, daemon=True, name="cpu_logger")
    thread.start()
    stop_event._thread = thread  # type: ignore[attr-defined]
    print(f"CPU logger started -> {log_path}")
    return stop_event


def stop_cpu_logger(stop_event: threading.Event | None) -> None:
    """Stop the background CPU/memory logger started by :func:`start_cpu_logger`."""
    if stop_event is None:
        return
    stop_event.set()
    thread = getattr(stop_event, "_thread", None)
    if thread is not None:
        thread.join(timeout=5)
    print("CPU logger stopped")

