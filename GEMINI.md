# Gemini Instructions for Archilume

This file provides project-specific instructions, coding standards, and common commands for the Archilume repository.

## Project Overview

Archilume is a Python-based framework designed to automate Radiance-based architectural daylight and sunlight simulations. It bridges the gap between 3D CAD models (OBJ/MTL) and physically accurate lighting analysis engines (Radiance and Accelerad).

### Core Capabilities

- **Geometry Pipeline:** Converts OBJ/MTL files to Radiance RAD format and compiles them into frozen octrees.
- **Sky Generation:** Generates sunny sky series (for sunlight access) and CIE overcast skies (for daylight factor).
- **Rendering Engines:** Supports both CPU (`rpict`, `rtpict` on Linux) and GPU (`accelerad_rpict`) rendering.
- **Post-Processing:** Automated falsecolor maps, contour overlays, AOI (Area of Interest) extraction, and Excel reporting.
- **Interactive Tools:** Dash-based applications for drawing boundaries directly on 3D floor plan slices.

## Technology Stack

- **Language:** Python 3.12+ (managed via `uv`)
- **Simulation:** Radiance (CPU), Accelerad (GPU)
- **Data Science:** `numpy`, `pandas`, `scikit-image`
- **Visualization:** `plotly`, `dash`, `opencv-python`, `pillow`
- **PDF/IFC:** `pymupdf` (fitz), `ifcopenshell`
- **Cloud:** Integration with Google Cloud Platform (GCP) for VM-based simulations.

## Key Modules & Architecture

- `archilume/config.py`: Centralized configuration. Detects tool paths (Radiance/Accelerad) and manages project directories (`inputs/`, `outputs/`, `intermediates/`).
- `archilume/workflows.py`: High-level simulation orchestrators. Currently hosts the `SunlightAccessWorkflow` and its `Inputs` validator class.
- `archilume/rendering_pipelines.py`: Orchestrates complex rendering tasks. 
    - `SunlightRenderer`: Handles multi-phase rendering (overcast indirect baseline + sunny direct sun).
    - `DaylightRenderer`: Handles daylight factor simulations.
- `archilume/objs2octree.py`: Manages the geometry conversion lifecycle using `obj2rad` and `oconv`.
- `archilume/sky_generator.py`: Interfaces with `gensky` to produce time-series sky files.
- `archilume/utils.py`: A comprehensive suite of utilities for parallel command execution, timing (`PhaseTimer`), geometry calculations, and smart cleanup of outputs.

## Coding Standards & Conventions

- **Path Management:** Always use `pathlib.Path` for file system operations. Refer to `archilume.config` for standard project paths.
- **Parallelism:** Utilize `utils.execute_new_radiance_commands` for running Radiance tools in parallel. Respect `config.WORKERS` limits to avoid system exhaustion.
- **Environment Variables:**
    - `ACCELERAD_ROOT`: Override path to Accelerad.
    - `RADIANCE_ROOT`: Override path to Radiance.
    - `RAYPATH`: Managed automatically by `config.py` but can be overridden.
- **Interactive Apps:** Use `app.run(debug=True)` for Dash applications.
- **Platform Awareness:** Be mindful of Windows vs. Linux (WSL) differences, especially for `rtpict` (multi-core Radiance), which is Linux-only.
- **Markdown Formatting:** Ensure all headings (#, ##, ###, etc.) are surrounded by blank lines (one above and one below) to comply with MD022 standards.

## Common Commands

### Environment Setup

- **Install dependencies:** `uv sync`

### Testing

- **Run all tests:** `pytest`
- **Run specific test:** `pytest tests/test_sky_generator.py`

### Running Workflows & Examples

- **Sunlight Access Workflow:** `python examples/sunlight_access_workflow.py`
- **Daylight Factor (IESVE):** `python examples/daylight_workflow_iesve.py`
- **AOI Editor (OBJ):** `python examples/obj_aoi_editor.py`
- **Interactive Viewer:** `python apps/viewer.py`

## Development Workflow

1. **Validation:** Use `Workflow.Inputs` classes to check simulation parameters. Note: Validation logic is transitioning from centralized classes to decentralized checks inside respective subfunctions.
2. **Execution:** Prefer `SunlightRenderer` or `DaylightRenderer` classes for orchestrating simulations rather than calling Radiance binaries directly.
3. **Cleanup:** Use `utils.smart_cleanup()` to intelligently clear previous results based on what parameters (resolution, timestep, mode) have changed.
4. **Verification:** Always verify HDR outputs by checking if they exist in `outputs/image/` before proceeding to post-processing.
