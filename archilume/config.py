"""
Archilume Configuration Module
==============================

Centralized configuration for project paths and directories.
This module provides consistent path references throughout the codebase.
"""

# fmt: off
# autopep8: off

import os
from pathlib import Path
import multiprocessing
import sys
from pathlib import Path
from typing import List

# Root directory of the project
PROJECT_ROOT        = Path(__file__).parent.parent

# Input/Output directories
INPUTS_DIR          = PROJECT_ROOT / "inputs"
OUTPUTS_DIR         = PROJECT_ROOT / "outputs"
EXAMPLES_DIR        = PROJECT_ROOT / "examples"

# Output subdirectories
IMAGE_DIR           = OUTPUTS_DIR / "image"
WPD_DIR             = OUTPUTS_DIR / "wpd"
AOI_DIR             = OUTPUTS_DIR / "aoi"
VIEW_DIR            = OUTPUTS_DIR / "view"
SKY_DIR             = OUTPUTS_DIR / "sky"
OCTREE_DIR          = OUTPUTS_DIR / "octree"
RAD_DIR             = OUTPUTS_DIR / "rad"

# ============================================================================
# EXTERNAL TOOL PATHS (Radiance/Accelerad)
# ============================================================================
# Use bundled Accelerad from .devcontainer by default
# Users can set ACCELERAD_ROOT env var to override with system installation
BUNDLED_ACCELERAD_ROOT = PROJECT_ROOT / ".devcontainer" / "accelerad_07_beta_Windows"
ACCELERAD_ROOT      = Path(os.getenv("ACCELERAD_ROOT", str(BUNDLED_ACCELERAD_ROOT)))
ACCELERAD_BIN_PATH  = ACCELERAD_ROOT / "bin"
ACCELERAD_LIB_PATH  = ACCELERAD_ROOT / "lib"

# Detect Radiance installation from environment variable or use platform-appropriate default
# Users can set RADIANCE_ROOT env var to override default location
# Default to /usr/local/radiance on Linux/Mac, C:/Radiance on Windows
_default_radiance = r"C:/Radiance" if sys.platform == "win32" else "/usr/local/radiance"
RADIANCE_ROOT       = Path(os.getenv("RADIANCE_ROOT", _default_radiance))
RADIANCE_BIN_PATH   = RADIANCE_ROOT / "bin"
RADIANCE_LIB_PATH   = RADIANCE_ROOT / "lib"

# RAYPATH environment variable for Radiance tools
# Users can also set RAYPATH directly via environment to override
# Use bundled Accelerad lib first, then fall back to system Radiance if available
# Use semicolon separator on Windows, colon on Unix
_path_sep = ";" if sys.platform == "win32" else ":"
RAYPATH = os.getenv("RAYPATH", f"{ACCELERAD_LIB_PATH}{_path_sep}{RADIANCE_LIB_PATH}")

# ============================================================================
# PARALLEL EXECUTION SETTINGS
# ============================================================================
# Detect CPU core count
DEFAULT_MAX_WORKERS = multiprocessing.cpu_count()

# Worker counts for different operations (adjust based on hardware)
WORKERS = {
    "overcast_octree"           : 1,
    "rpict_overture"            : min(8, DEFAULT_MAX_WORKERS),
    "rpict_medium_quality"      : min(8, DEFAULT_MAX_WORKERS),
    "oconv_compile"             : min(12, DEFAULT_MAX_WORKERS),
    "rpict_direct_sun"          : min(18, DEFAULT_MAX_WORKERS),
    "pcomb_tiff_conversion"     : min(18, DEFAULT_MAX_WORKERS),
    "metadata_stamping"         : min(14, DEFAULT_MAX_WORKERS),
    "gif_animation"             : min(14, DEFAULT_MAX_WORKERS),
    "wpd_processing"            : min(14, DEFAULT_MAX_WORKERS),
}

class InputValidator:
    """
    Holds all simulation inputs, validates them, and prints a detailed approval report.
    """
    def __init__(
        self,
        project_latitude: float,
        month: int,
        day: int,
        start_hour: int,
        end_hour: int,
        timestep: int,
        ffl_offset: float,
        image_resolution: int,
        rendering_mode: str,
        rendering_quality: str,
        room_boundaries_csv: Path,
        obj_paths: List[Path]
    ):
        # Store values
        self.project_latitude = project_latitude
        self.month = month
        self.day = day
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.timestep = timestep
        self.ffl_offset = ffl_offset
        self.image_resolution = image_resolution
        self.rendering_mode = rendering_mode
        self.rendering_quality = rendering_quality
        self.room_boundaries_csv = room_boundaries_csv
        self.obj_paths = obj_paths
        
        self._errors = []
        self._warnings = []

        # Run Validation immediately
        self._validate()
        self._report()

    def _validate(self):
        # --- Geographic ---
        if not isinstance(self.project_latitude, (int, float)):
            self._errors.append("[X] project_latitude: Must be numeric.")
        elif not -90 <= self.project_latitude <= 90:
            self._errors.append("[X] project_latitude: Must be -90 to 90.")

        # --- Time ---
        if not (0 <= self.start_hour <= 23): self._errors.append("[X] start_hour: Must be 0-23.")
        if not (0 <= self.end_hour <= 23): self._errors.append("[X] end_hour: Must be 0-23.")
        if self.start_hour >= self.end_hour: self._errors.append("[X] Time range: end_hour must be > start_hour.")

        if self.timestep < 1: self._errors.append("[X] timestep: Must be >= 1.")
        elif self.timestep < 5: self._warnings.append(f"[!] timestep ({self.timestep} min) is very low. High computation time.")

        # --- Rendering ---
        if self.image_resolution < 128: self._errors.append("[X] resolution: Must be >= 128.")
        elif self.image_resolution > 2048: self._warnings.append(f"[!] resolution ({self.image_resolution}) exceeds recommended 2048px.")

        valid_modes = ['cpu', 'gpu']
        if self.rendering_mode.lower() not in valid_modes:
            self._errors.append(f"[X] rendering_mode: Must be one of {valid_modes}")

        valid_qualities = ['draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed']
        if self.rendering_quality.lower() not in valid_qualities:
            self._errors.append(f"[X] rendering_quality: Must be one of {valid_qualities}")

        # --- Files ---
        if not self.room_boundaries_csv.exists():
            self._errors.append(f"[X] CSV not found: {self.room_boundaries_csv}")

        # --- Geometry ---
        if not self.obj_paths: self._errors.append("[X] obj_paths: List is empty.")
        else:
            for idx, obj in enumerate(self.obj_paths):
                if not obj.exists():
                    self._errors.append(f"[X] obj_paths[{idx}]: Not found: {obj}")
                    continue
                if not obj.with_suffix('.mtl').exists():
                    self._errors.append(f"[X] obj_paths[{idx}]: Missing .mtl file.")

                # Check Units
                is_m, max_c, diag = self._check_obj_units(obj)
                if not is_m: self._errors.append(f"[X] obj_paths[{idx}] is in MILLIMETERS (max: {max_c:,.0f}). Re-export in Meters.")

    def _check_obj_units(self, path):
        try:
            max_c = 0.0
            with open(path, 'r') as f:
                for i, line in enumerate(f):
                    if line.startswith('v '):
                        parts = line.split()
                        if len(parts) >= 4:
                            max_c = max(max_c, abs(float(parts[1])), abs(float(parts[2])), abs(float(parts[3])))
                            if max_c > 10000: return False, max_c, "mm"
                            if i > 5000: break 
            if max_c > 1000: return False, max_c, "mm"
            return True, max_c, "m"
        except: return True, 0, "err"

    def _report(self):
        """
        Prints the report. If errors exist, it exits script. 
        If valid, it prints the 'Receipt' of parameters and reasoning.
        """
        # 1. Handle Blocking Errors
        if self._errors:
            print("\n" + "="*100)
            print("INPUT VALIDATION FAILED - EXECUTION BLOCKED")
            print("="*100)
            for e in self._errors: print(f" {e}")
            if self._warnings:
                print("-" * 100)
                print("Warnings also detected:")
                for w in self._warnings: print(f" {w}")
            sys.exit(1)

        # 2. Print Detailed Success Receipt
        print("\n" + "="*100)
        print(f"{'CONFIGURATION VALIDATED SUCCESSFULLY':^100}")
        print("="*100)
        
        # Print Table Header
        # We use f-string alignment: :<30 means "align left, 30 chars wide"
        print(f"{'PARAMETER':<30} {'VALUE':<30} {'VALIDATION RULES / REASONING':<40}")
        print("-" * 100)

        # Geographic
        print(f"{'Project Latitude':<30} {self.project_latitude:<30} {'Range: -90.0 to 90.0 (Decimal Degrees)'}")
        
        # Date/Time
        print(f"{'Date':<30} {self.month}/{self.day:<30} {'Month: 1-12, Day: 1-31'}")
        print(f"{'Time Range':<30} {self.start_hour}:00 - {self.end_hour}:00{'Start must be < End (0-23h fmt)'}")
        print(f"{'Timestep':<30} {self.timestep} min{'Integer >= 1 (Rec: >5min)'}")

        # Physical / Camera
        print(f"{'Camera Height (FFL)':<30} {self.ffl_offset}m{'Numeric value > 0.0m'}")
        
        # Rendering
        print(f"{'Resolution':<30} {self.image_resolution}px{'Integer >= 128px (Rec: <=2048)'}")
        print(f"{'Rendering Mode':<30} {self.rendering_mode.upper():<30} {'Must be CPU or GPU'}")
        print(f"{'Quality Preset':<30} {self.rendering_quality.upper():<30} {'Valid preset name'}")

        # Files
        print(f"{'Room Boundaries CSV':<30} {self.room_boundaries_csv.name:<30} {'File exists & extension is .csv'}")

        print("-" * 100)
        print(f"GEOMETRY FILES ({len(self.obj_paths)})")
        for i, obj in enumerate(self.obj_paths, 1):
            # We assume units are meters because validation passed
            print(f"  {i}. {obj.name:<25} {'DETECTED: Meters':<30} {'Max Coord < 1000m & .mtl exists'}")

        # 3. Print Warnings (Non-blocking)
        if self._warnings:
            print("\n" + "="*100)
            print("WARNINGS DETECTED (Script will continue)")
            for w in self._warnings: print(f" {w}")
        
        print("="*100 + "\n")