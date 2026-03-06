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
ARCHIVE_DIR         = PROJECT_ROOT / "archive"

# Output subdirectories
IMAGE_DIR           = OUTPUTS_DIR / "image"
WPD_DIR             = OUTPUTS_DIR / "wpd"
AOI_DIR             = OUTPUTS_DIR / "aoi"
VIEW_DIR            = OUTPUTS_DIR / "view"
SKY_DIR             = OUTPUTS_DIR / "sky"
OCTREE_DIR          = OUTPUTS_DIR / "octree"
RAD_DIR             = OUTPUTS_DIR / "rad"

# ============================================================================
# GCLOUD CLI PATH
# ============================================================================
_default_gcloud_root = Path.home() / "google-cloud-sdk"
GCLOUD_SDK_ROOT     = Path(os.getenv("GCLOUD_SDK_ROOT", str(_default_gcloud_root)))
GCLOUD_EXECUTABLE   = GCLOUD_SDK_ROOT / "bin" / "gcloud"

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

# ============================================================================
# GOOGLE CLOUD SDK PATH
# ============================================================================
# Detect Google Cloud SDK installation
# Users can set GCLOUD_SDK_ROOT env var to override default location
if sys.platform == "win32":
    # Windows: typical installation in %LOCALAPPDATA%\Google\Cloud SDK
    _default_gcloud = Path.home() / "AppData" / "Local" / "Google" / "Cloud SDK" / "google-cloud-sdk"
else:
    # Unix: typical installation in home directory
    _default_gcloud = Path.home() / "google-cloud-sdk"

GCLOUD_SDK_ROOT = Path(os.getenv("GCLOUD_SDK_ROOT", str(_default_gcloud)))
GCLOUD_BIN_PATH = GCLOUD_SDK_ROOT / "bin"

# Determine the correct gcloud executable name based on platform
_gcloud_exe = "gcloud.cmd" if sys.platform == "win32" else "gcloud"
GCLOUD_EXECUTABLE = GCLOUD_BIN_PATH / _gcloud_exe

# RAYPATH environment variable for Radiance tools
# Users can also set RAYPATH directly via environment to override
# Use bundled Accelerad lib first, then fall back to system Radiance if available
# Use semicolon separator on Windows, colon on Unix
_path_sep = ";" if sys.platform == "win32" else ":"
RAYPATH = os.getenv("RAYPATH", f"{ACCELERAD_LIB_PATH}{_path_sep}{RADIANCE_LIB_PATH}")

# ============================================================================
# CALENDAR
# ============================================================================
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ============================================================================
# PARALLEL EXECUTION SETTINGS
# ============================================================================
# Detect CPU core count
DEFAULT_MAX_WORKERS = multiprocessing.cpu_count()

# Worker counts for different operations (adjust based on hardware)
WORKERS = {
    "overcast_octree"           : 1,
    "rpict_overture"            : min(64, DEFAULT_MAX_WORKERS),
    "rpict_medium_quality"      : min(64, DEFAULT_MAX_WORKERS),
    "oconv_compile"             : min(64, DEFAULT_MAX_WORKERS),
    "rpict_direct_sun"          : min(64, DEFAULT_MAX_WORKERS),
    "pcomb_tiff_conversion"     : min(64, DEFAULT_MAX_WORKERS),
    "metadata_stamping"         : min(64, DEFAULT_MAX_WORKERS),
    "gif_animation"             : min(64, DEFAULT_MAX_WORKERS),
    "wpd_processing"            : min(64, DEFAULT_MAX_WORKERS),
}

#TODO: determine if radiance binaries can be used in place in the devcontainer. Instead of installing on the local machine. That way a user would not need to install radiance on windows if using the dev container to work. 
 