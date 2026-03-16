# Archilume

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python framework for Radiance-based architectural daylight and sunlight simulations. Archilume converts 3D CAD models (OBJ/MTL, IFC) into physically accurate lighting analyses with compliance reporting.

---

## Quick Start

### Option A — Dev Container (Recommended)

The dev container bundles Python 3.12, Radiance, and Accelerad so there is nothing to install manually.

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.

```bash
git clone https://github.com/vincentlogarzo/archilume.git
```

Open the folder in VS Code and click **"Reopen in Container"** when prompted (or `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`). Once the container finishes building, the environment is ready.

### Option B — Native Windows

1. Install **[Python 3.12+](https://www.python.org/downloads/)**.
2. Install **[Radiance](https://www.radiance-online.org/)** (and optionally [Accelerad](https://nljones.github.io/Accelerad/) for GPU rendering).
3. Clone and install dependencies:

   ```powershell
   git clone https://github.com/vincentlogarzo/archilume.git
   cd archilume
   pip install uv
   uv sync
   ```

4. Verify Radiance is on your `PATH`:

   ```powershell
   rpict -version
   ```

   If Radiance is installed elsewhere, set `RADIANCE_ROOT` to its install directory (the folder containing `bin/`). Optionally set `ACCELERAD_ROOT` for GPU tools.

---

## Key Features

- **Pre-configured workflows** for sunlight access and daylight factor analysis
- **Multiple geometry inputs** — OBJ/MTL exports (e.g. from Revit) and IFC models
- **Interactive editors** for drawing room boundaries on floor plans (OBJ slicing) and editing AOIs on HDR renders
- **GPU-accelerated rendering** via Accelerad
- **Parallel processing** with multi-core support for batch operations
- **Compliance reporting** — Excel reports with pivot summaries, annotated GIF/APNG animations
- **Cloud-ready** — GCP VM provisioning for remote simulations

---

## Example Workflows

Pre-configured workflow scripts in [examples/](examples/):

| Script | Description |
| ------ | ----------- |
| [sunlight_access_workflow.py](examples/sunlight_access_workflow.py) | End-to-end sunlight access: OBJ → octree → sky series → rendering → HDR analysis → Excel report → animation |
| [daylight_workflow_iesve.py](examples/daylight_workflow_iesve.py) | Daylight factor analysis from IESVE octrees with falsecolor post-processing |
| [room_boundaries_editor.py](examples/room_boundaries_editor.py) | Launch the interactive room boundary editor on an OBJ model |
| [gcp_launch_vm.py](examples/gcp_launch_vm.py) | Provision and manage a GCP VM for remote simulation runs |

Run a workflow:

```bash
uv run python examples/sunlight_access_workflow.py
```

---

## Simulation Stages

The core flow is: **Geometry → Octree → Sky + Views → Rendering → Post-Processing → Reports**

1. **Geometry conversion** — OBJ/MTL files are translated to Radiance format and compiled into an octree (`.oct`) via `Objs2Octree`. IFC models can be inspected and stripped with `geo` utilities.
2. **Sky generation** — `SkyGenerator` produces time-series sunny skies (sunlight access) or CIE overcast skies (daylight factor).
3. **View & AOI generation** — `ViewGenerator` parses room boundaries, computes building extents, and generates orthographic plan views and AOI masks per room/level.
4. **Rendering** — `SunlightRenderer` (multi-phase HDR compositing, CPU or GPU) and `DaylightRenderer` (falsecolor + contour overlays). Both support configurable quality presets.
5. **Post-processing** — `Hdr2Wpd` extracts illuminance from HDR using AOI polygon masks. `Tiff2Animation` stamps metadata and creates GIF/APNG animations.

---

## Project Structure

### Simulation Projects

Every simulation runs inside a named **project folder** under `projects/`. Each project is fully self-contained — you can work on multiple projects simultaneously without any file collisions.

```text
projects/
└── <project_name>/
    ├── inputs/           # Your source files: OBJ, MTL, IFC, CSV, AOI, PDF plans
    │   ├── aoi/          # Editor-drawn room boundary .aoi files (auto-created)
    │   └── plans/        # PDF floor plans for overlay in editors
    ├── outputs/          # All simulation results (written by the pipeline)
    │   ├── image/        # Rendered HDR, TIFF, PNG images and animations
    │   ├── wpd/          # Illuminance working plane data and Excel reports
    │   ├── aoi/          # Pipeline-generated AOI coordinate maps
    │   ├── view/         # Radiance view parameter files (.vp)
    │   ├── sky/          # Sky condition files (.sky, .rad)
    │   ├── octree/       # Compiled octree files (.oct)
    │   └── rad/          # Radiance geometry files (.rad)
    └── archive/          # Timestamped .zip exports of outputs
```

All workflows and editors require a `project` name, which automatically resolves every path:

```python
from archilume.workflows import SunlightAccessWorkflow

inputs = SunlightAccessWorkflow.InputsValidator(
    project             = "ProjectXYZ",   # resolves to projects/ProjectXYZ/
    room_boundaries_csv = "Model_room_boundaries.csv",
    obj_paths           = ["3DModel_withWindows.obj"],
    # ... other parameters
)
```

### Repository Layout

```text
archilume/
├── .devcontainer/                          # Docker dev container (Radiance + Accelerad)
├── archilume/                              # Core package
│   ├── core/                               # Simulation engine
│   │   ├── objs2octree.py                  #   OBJ/MTL → Radiance octree
│   │   ├── sky_generator.py                #   Sky condition generation
│   │   ├── view_generator.py               #   View and AOI file generation
│   │   ├── rendering_pipelines.py          #   SunlightRenderer & DaylightRenderer
│   │   ├── mtl_converter.py                #   Wavefront MTL → Radiance materials
│   │   └── radiance_materials.py           #   Radiance material primitives
│   │
│   ├── geo/                                # Geometry utilities
│   │   ├── ifc_inspector.py                #   IFC model inspection
│   │   ├── ifc_strip.py                    #   IFC element extraction
│   │   ├── obj2boundaries.py               #   OBJ → room boundary extraction
│   │   ├── obj_cleaner.py                  #   OBJ geometry cleanup
│   │   └── obj_inspector.py                #   OBJ model inspection
│   │
│   ├── post/                               # Post-processing
│   │   ├── hdr2wpd.py                      #   HDR → illuminance data extraction
│   │   ├── tiff2animation.py               #   Annotated GIF/APNG from renders
│   │   └── apng2mp4.py                     #   APNG → MP4 conversion
│   │
│   ├── apps/                               # Interactive editors
L161- │   │   ├── obj_aoi_editor_matplotlib.py    #   Room boundary editor (matplotlib)
L162- │   │   ├── hdr_aoi_editor_matplotlib.py    #   HDR AOI editor (matplotlib)
L163- │   │   └── octree_viewer.py                #   3D octree viewer

│   │
│   ├── workflows/                          # Orchestrated pipelines
│   │   ├── sunlight_access_workflow.py     #   Full sunlight access pipeline
│   │   └── iesve_daylight_workflow.py      #   IESVE daylight factor pipeline
│   │
│   ├── infra/                              # Cloud infrastructure
│   │   └── gcp_vm_manager.py               #   GCP VM lifecycle management
│   │
│   ├── config.py                           # ProjectPaths, tool paths, environment detection
│   └── utils.py                            # Parallel execution, timing, geometry helpers
│
├── examples/                               # Workflow scripts, editor launchers, migration util
├── projects/                               # Per-project simulation data (inputs + outputs)
└── tests/                                  # Test suite
```

---

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
pytest
pytest tests/test_sky_generator.py      # single file

# Run a workflow
uv run python examples/sunlight_access_workflow.py

# Launch interactive editors
uv run python examples/room_boundaries_editor.py
```

---

## Configuration

`archilume.config` manages all path resolution and environment detection:

- **Tool paths** — Automatically finds Radiance and Accelerad binaries. Override with `RADIANCE_ROOT` and `ACCELERAD_ROOT` environment variables.
- **Project paths** — `config.get_project_paths("myproject")` returns a `ProjectPaths` object with every directory for that project. Workflows call `paths.create_dirs()` automatically at startup.
- **Worker count** — Parallel operations respect `config.WORKERS` (defaults to CPU count).
- **Platform awareness** — Detects Windows vs Linux, bundled vs system Radiance, GPU availability.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgements

- [Radiance](https://www.radiance-online.org/) — industry-standard lighting simulation
- [Accelerad](https://nljones.github.io/Accelerad/) — GPU-accelerated rendering
- [PyRadiance](https://github.com/LBNL-ETA/pyradiance) — Python–Radiance integration
