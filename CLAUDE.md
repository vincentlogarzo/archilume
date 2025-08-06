# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Archilume is a Python wrapper for Radiance rendering engine designed for building daylight analysis and SEPP65 compliance simulations. The project converts building geometry from IFC/OBJ files into Radiance octree files and performs parallel rendering operations for daylighting studies.

## Key Architecture

### Core Modules (`archilume/`)
- **`geometry_utils.py`**: Geometric calculations including bounding boxes, centroids, and dimensions from point coordinates
- **`rad_utils.py`**: Main Radiance workflow classes:
  - `SkyFileGenerator`: Creates Radiance sky files for time series analysis
  - `ViewGenerator`: Processes room boundary data and generates view files for rendering
- **`utils.py`**: File operations, parallel command execution, and conversion utilities:
  - `ObjToOctree`: Converts Wavefront OBJ/MTL to Radiance RAD/MTL format
  - `AddMissingModifiers`: Ensures all geometry has corresponding material definitions
- **`material_conversions.py`**: Material property conversion between formats
- **`ui_utils.py`**: User interface utilities for file selection

### Workflow Pipeline
1. **Geometry Conversion**: IFC → OBJ → Radiance RAD format
2. **Material Processing**: MTL → Radiance material definitions with auto-generation of missing modifiers
3. **Sky Generation**: Time-series sky files for specific locations and dates
4. **View Setup**: Floor plan views and area-of-interest (AOI) files from room boundaries
5. **Rendering**: Parallel execution of Radiance rpict commands for multiple time steps

## Common Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Alternative with pip
pip install -r requirements.txt
```

### Testing
```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Run specific test file
pytest tests/test_geometric_calculations.py
```

### Code Quality
```bash
# Run linting and formatting
pre-commit run --all
```

### Example Usage
```python
# Generate sky files
from archilume.rad_utils import SkyFileGenerator
generator = SkyFileGenerator(lat=-33.87, lon=-151.21, std_meridian=-150, 
                           year=2024, month=6, day=21, 
                           start_hour_24hr_format=9, end_hour_24hr_format=15)
generator.generate_sunny_sky_series()

# Convert geometry
from archilume.utils import ObjToOctree
converter = ObjToOctree()
converter.obj_to_rad("model.obj", "model.mtl")
converter.rad_to_octree()

# Process room boundaries for views
from archilume.rad_utils import ViewGenerator
view_gen = ViewGenerator("room_boundaries.csv")
view_gen.create_aoi_and_view_files(ffl_offset=1.0)
```

## Key File Locations

- **Input geometry**: `inputs/` (IFC, OBJ, MTL files)
- **Generated octrees**: `outputs/octrees/` 
- **Rendering results**: `outputs/results/` (HDR, TIFF images and GIFs)
- **Sky files**: `outputs/sky/` 
- **View definitions**: `views_grids/` (VP files)
- **Area of interest files**: `aoi/` (AOI files)

## External Dependencies

This project requires Radiance lighting simulation tools to be installed and available in PATH:
- `gensky` - Sky file generation
- `obj2rad` - OBJ to Radiance conversion  
- `oconv` - Octree compilation
- `rpict` - Ray-tracing renderer
- `ra_tiff` - HDR to TIFF conversion

## Important Notes

- **File paths**: All geometry files must be exported in meters (not millimeters)
- **No spaces**: Filenames should not contain spaces or special characters that could break terminal commands
- **SEPP65 compliance**: Default material assignments use 50% light reflectance plastic materials suitable for NSW SEPP65 daylight analysis
- **Coordinate system**: Project uses standard Radiance coordinate conventions
- **Parallel processing**: Rendering commands are executed in parallel using ThreadPoolExecutor (default 4 workers for oconv, configurable for other operations)

## Testing Approach

The project uses pytest with comprehensive tests for geometric calculation functions. Test files are located in `tests/` directory focusing on:
- Bounding box calculations
- Dimension calculations  
- Centroid computations
- Edge cases and error handling