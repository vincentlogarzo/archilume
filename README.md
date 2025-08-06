# Archilume

A Python project for geometric calculations and 3D data processing.

## Installation

1. Ensure you have Python 3.7+ installed
2. Install dependencies using pip:

```bash
pip install -r requirements.txt
```

### Dependencies

The project requires:
- pytest>=7.0.0 - Testing framework
- pytest-mock>=3.10.0 - Mock testing utilities
- pandas>=1.5.0 - Data manipulation and analysis
- pillow>=9.0.0 - Image processing
- open3d>=0.16.0 - 3D data processing

## Running Linter

`pre-commit run --all`

## Running Tests

To run the test suite:

```bash
pytest
```

For verbose output:

```bash
pytest -v
```

To run tests in a specific file:

```bash
pytest tests/test_geometric_calculations.py
```

The test suite includes comprehensive tests for geometric calculation functions including bounding box calculations, dimension calculations, and centroid computations.


## Project Structure

This project follows a standard directory structure for input/output workflows:

### Input Files (`inputs/`)
- **IFC files**: Building Information Model files exported from CAD software
- **OBJ files**: Wavefront geometry files (must be exported in meters, not millimeters)
- **MTL files**: Material definition files corresponding to OBJ files
- **CSV files**: Room boundary data for view generation

### Output Files (`outputs/`)
- **`octrees/`**: Generated Radiance octree files (.oct)
- **`results/`**: Rendered images (HDR, TIFF) and analysis results
- **`sky/`**: Generated sky files for time-series analysis

### Other Directories
- **`aoi/`**: Area of interest files generated from room boundaries
- **`views_grids/`**: View definition files (.vp) for rendering
- **`examples/`**: Example scripts and workflows
- **`examples/sample_data/`**: Sample input files for testing

### File Naming Guidelines
- Avoid spaces and special characters in filenames
- Use consistent naming conventions across OBJ/MTL file pairs
- Ensure geometry files are exported in meters (not millimeters)
- Follow Radiance naming conventions for compatibility