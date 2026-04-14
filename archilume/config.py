"""
Archilume Configuration Module
==============================

Centralized configuration for project paths and directories.

All simulation paths are scoped per-project via `get_project_paths(project_name)`,
which returns a `ProjectPaths` instance containing every directory needed for a
simulation run. Each project is fully self-contained under `projects/<project_name>/`.

Tool-path constants (Radiance, Accelerad, GCloud) remain module-level globals.
"""

# fmt: off
# autopep8: off

import os
from dataclasses import dataclass
from pathlib import Path
import multiprocessing
import sys
from typing import List

# Root directory of the project
PROJECT_ROOT        = Path(__file__).parent.parent

# Top-level projects directory — each simulation project lives here
PROJECTS_DIR        = Path(os.getenv("ARCHILUME_PROJECTS_DIR", str(PROJECT_ROOT / "projects")))

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

# ============================================================================
# PER-PROJECT PATH MANAGEMENT
# ============================================================================

@dataclass(frozen=True)
class ProjectPaths:
    """All filesystem paths for a single named project.

    Use `get_project_paths(project_name)` to construct an instance.
    Call `create_dirs()` once at the start of a workflow run to ensure
    all directories exist before writing to them.
    """
    project_name:   str
    project_dir:    Path
    inputs_dir:     Path   # projects/<name>/inputs/
    outputs_dir:    Path   # projects/<name>/outputs/
    archive_dir:    Path   # projects/<name>/archive/
    aoi_inputs_dir: Path   # projects/<name>/inputs/aoi/   — editor-drawn .aoi files
    plans_dir:      Path   # projects/<name>/inputs/plans/ — PDF floor plans
    pic_dir:        Path   # projects/<name>/inputs/pic/   — input HDR/pic files
    image_dir:      Path   # projects/<name>/outputs/image/
    wpd_dir:        Path   # projects/<name>/outputs/wpd/
    aoi_dir:        Path   # projects/<name>/outputs/aoi/  — pipeline coordinate maps
    view_dir:       Path   # projects/<name>/outputs/view/
    sky_dir:        Path   # projects/<name>/outputs/sky/
    octree_dir:     Path   # projects/<name>/outputs/octree/
    rad_dir:        Path   # projects/<name>/outputs/rad/

    def create_dirs(self) -> None:
        """Create all project directories. Call once at the start of a workflow run."""
        for d in (
            self.inputs_dir,
            self.outputs_dir,
            self.archive_dir,
            self.aoi_inputs_dir,
            self.plans_dir,
            self.pic_dir,
            self.image_dir,
            self.wpd_dir,
            self.aoi_dir,
            self.view_dir,
            self.sky_dir,
            self.octree_dir,
            self.rad_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def get_project_paths(project_name: str) -> ProjectPaths:
    """Return all filesystem paths for the named project under projects/<project_name>/."""
    project_dir = PROJECTS_DIR / project_name
    inputs_dir  = project_dir / "inputs"
    outputs_dir = project_dir / "outputs"
    return ProjectPaths(
        project_name   = project_name,
        project_dir    = project_dir,
        inputs_dir     = inputs_dir,
        outputs_dir    = outputs_dir,
        archive_dir    = project_dir / "archive",
        aoi_inputs_dir = inputs_dir / "aoi",
        plans_dir      = inputs_dir / "plans",
        pic_dir        = inputs_dir / "pic",
        image_dir      = outputs_dir / "image",
        wpd_dir        = outputs_dir / "wpd",
        aoi_dir        = outputs_dir / "aoi",
        view_dir       = outputs_dir / "view",
        sky_dir        = outputs_dir / "sky",
        octree_dir     = outputs_dir / "octree",
        rad_dir        = outputs_dir / "rad",
    )
