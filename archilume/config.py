"""
Archilume Configuration Module
==============================

Centralized configuration for project paths and directories.
This module provides consistent path references throughout the codebase.
"""

from pathlib import Path

# Root directory of the project
PROJECT_ROOT = Path(__file__).parent.parent

# Input/Output directories
INPUTS_DIR = PROJECT_ROOT / "inputs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# Output subdirectories
IMAGE_DIR = OUTPUTS_DIR / "image"
WPD_DIR = OUTPUTS_DIR / "wpd"
AOI_DIR = OUTPUTS_DIR / "aoi"
VIEW_DIR = OUTPUTS_DIR / "view"
SKY_DIR = OUTPUTS_DIR / "sky"
OCTREE_DIR = OUTPUTS_DIR / "octree"
RAD_DIR = OUTPUTS_DIR / "rad"
