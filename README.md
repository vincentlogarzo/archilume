# Archilume

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python library for Radiance-based architectural daylight and sunlight analysis.

## Overview

Archilume provides preset workflows/tools for creating and validating physically accurate daylight simulations. It provides a bridge for direct input of 3D models from CAD softwares into [Radiance](https://www.radiance-online.org/). It automates geometry conversion, sky generation, camera view setup, rendering, and post-processing into compliance results.

The easiest way to use Archilume is through the included **Docker dev container**, which ships with Python, Radiance, and Accelerad pre-installed — no manual setup required. See [Prerequisites](#prerequisites) to get started.

### Key Features

- **Pre-configured workflows** for sunlight access and daylight factor analysis, ready to run out of the box
- **Room boundary tools** for generating analysis boundaries when they cannot be sourced directly from your 3D modelling software — includes an interactive editor for drawing boundaries on OBJ floor plan slices and a converter for IESVE room data
- **GPU-accelerated rendering** via Accelerad for significantly faster simulations
- **Parallel processing** with multi-core support for computationally intensive operations
- **Compliance reporting** with automated Excel report generation and annotated animations to inform your decisions
- **Cloud-ready** — the dev container setup enables running simulations on cloud provider virtual machines for access to higher compute resources

---

## Prerequisites

All you need to run Archilume:

1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — provides the containerised environment
2. **[VS Code](https://code.visualstudio.com/)** with the **[Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)** extension — lets you develop inside the container

That's it. You do **not** need to install Python, Radiance, or Accelerad — they are all bundled in the dev container.

### Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/vincentlogarzo/archilume.git
   ```
2. Open the project folder in VS Code.
3. When prompted, click **"Reopen in Container"** (or use `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`).
4. Wait for the container to build. Once ready, all dependencies are installed and the environment is fully configured.

### Windows Users — Parallel Rendering Without an NVIDIA GPU

Some of Archilume's parallel rendering features rely on multi-core Radiance tools (`rtpict`) that are only available on Linux. If you are on a Windows machine and do not have a compatible NVIDIA CUDA-enabled GPU for GPU-accelerated rendering, you can still access the full power of Radiance by:

1. Installing **[WSL](https://learn.microsoft.com/en-us/windows/wsl/install)** (Windows Subsystem for Linux).
2. Connecting to WSL through VS Code (install the **[WSL](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl)** extension, then `Ctrl+Shift+P` → `WSL: Connect to WSL`).
3. Reopening this repository **inside the dev container from within the WSL session**.

This gives you a full Linux environment where Radiance's multi-core rendering is available without needing a GPU.

---

## Core Modules

### ObjAoiEditor

Interactive GUI for drawing room boundaries on 2D floor plan slices of OBJ models. Supports hierarchical naming (apartment → sub-room), polygon editing, and exports to CSV for use with `ViewGenerator`.

### Objs2Octree

Converts wavefront object (`.obj`) building models and their corresponding material descriptions (`.mtl`) into a Radiance octree (`.oct`) format. Accepts multiple geometry files (e.g. building + site context) and produces a skyless octree ready for rendering.

### MtlConverter

Converts Wavefront `.mtl` material files (e.g. from Revit OBJ exports) into Radiance material `.rad` files.

### SkyGenerator

Generates Radiance sky files for specific dates, times, and geographic locations. Supports sun-only sky series for sunlight access studies and CIE overcast skies for daylight factor analysis.

### ViewGenerator

Creates Radiance view parameter files from room boundary data. Parses a room boundaries CSV, computes building extents, and generates orthographic plan views and area-of-interest (AOI) files per room per floor level.

### SunlightRenderer

Manages batch sunlight rendering across all sky/view combinations. Supports CPU (`rpict`) and GPU (`accelerad_rpict`) modes with configurable quality presets. Handles ambient file caching, overture passes, HDR compositing, and TIFF output.

### DaylightRenderer

Renders daylight factor analysis from pre-built IESVE octrees. Uses multi-core `rtpict` on Linux for parallel rendering per view. Includes post-processing for falsecolor maps, contour overlays, and legends.

### Hdr2Wpd

Extracts illuminance and daylight factor data from rendered HDR images using AOI polygon masks. Produces `.wpd` (Working Plan Data) files for compliance assessment.

### Wpd2Xlsx

Generates formatted Excel reports from `.wpd` files with raw data, pivot summaries, and compliance metrics with conditional formatting.

### Tiff2Animation

Post-processes rendered TIFFs with metadata annotations and AOI overlays. Creates animated GIF or APNG sequences from time-series renders.

---

## Example Workflows

Pre-configured workflows are available in the [examples/](examples/) directory:

| Workflow | Description |
|----------|-------------|
| [sunlight_access_workflow.py](examples/sunlight_access_workflow.py) | End-to-end sunlight access analysis: OBJ conversion, sky generation, rendering, WPD extraction, Excel reporting, and animated results |
| [daylight_workflow_iesve.py](examples/daylight_workflow_iesve.py) | Daylight factor analysis using pre-built IESVE octrees with falsecolor post-processing |
| [daylight_workflow_obj.py](examples/daylight_workflow_obj.py) | Daylight factor analysis from OBJ geometry |
| [aoi_editor_obj.py](examples/aoi_editor_obj.py) | Launch the interactive room boundary editor on an OBJ model |

---

## Project Structure

```
archilume/
├── .devcontainer/             # Dev container with Radiance & Accelerad
├── archilume/                 # Core package
│   ├── objs2octree.py         # OBJ/MTL → Radiance octree conversion
│   ├── sky_generator.py       # Sky condition generation
│   ├── view_generator.py      # View and AOI file generation
│   ├── rendering_pipelines.py # SunlightRenderer & DaylightRenderer
│   ├── hdr2wpd.py             # HDR → working plan data extraction
│   ├── wpd2xlsx.py            # WPD → Excel compliance reports
│   ├── tiff2animation.py      # Annotated animations from renders
│   ├── mtl_converter.py       # MTL → Radiance material conversion
│   ├── obj_aoi_editor.py      # Interactive room boundary editor
│   ├── radiance_materials.py  # Radiance material primitives library
│   ├── utils.py               # Geometry, timing, and helper utilities
│   └── config.py              # Paths, validation, and defaults
│
├── examples/                  # Pre-configured workflow scripts and tools
├── inputs/                    # Input files (OBJ, MTL, CSV)
├── outputs/                   # Rendered images, reports, animations
└── tests/                     # Test suite
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

- Built on [Radiance](https://www.radiance-online.org/), the industry-standard lighting simulation software
- GPU acceleration powered by [Accelerad](https://nljones.github.io/Accelerad/)
- Uses [PyRadiance](https://github.com/LBNL-ETA/pyradiance) for Python-Radiance integration