# Archilume

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python framework for Radiance-based architectural daylight and sunlight simulations. Archilume converts 3D CAD models (OBJ/MTL, IFC) into physically accurate lighting analyses with a Reflex-based web editor for boundary drawing, result review, and export.

---

## Quick Start

### Option A — Desktop App (No Code Required)

For people who want to run Archilume without installing Python or Radiance. Everything runs in Docker containers on your machine or a Google Cloud VM.

**Requirements:**

1. Install a Docker runtime. [Docker Desktop](https://www.docker.com/products/docker-desktop/) works on Windows 10/11, macOS, and Linux, but its [subscription terms](https://www.docker.com/pricing/) require a paid plan for organisations above 250 employees or USD 10M revenue. Free alternatives that work with this distribution: [Rancher Desktop](https://rancherdesktop.io/), [OrbStack](https://orbstack.dev/) (macOS), [Colima](https://github.com/abiosoft/colima) (macOS/Linux), or the standalone Docker Engine on Linux.
2. Download [`archilume.zip` from the latest GitHub Release](https://github.com/vincentlogarzo/archilume/releases/latest/download/archilume.zip) and unzip it anywhere.
3. Launch using the one-action entry point for your OS:

| Platform | Action |
| --- | --- |
| **Windows** | Double-click **`launch-archilume.cmd`**. |
| **macOS** | Double-click **`launch-archilume.command`** in Finder. (First time only: right-click → **Open** to approve Gatekeeper.) |
| **Linux** | From a terminal in the unzipped folder, run `./launch-archilume.sh`. |

Each launcher performs the same six stages: verifies Docker is running (starts Docker Desktop if needed on Windows/macOS), tears down any stale `archilume` stack, checks port 3000 for conflicts, brings the frontend + backend + engine containers up, polls `/ping-frontend` until healthy, and opens <http://localhost:3000> in your browser. First launch pulls the three images from Docker Hub (~1–3 minutes); subsequent launches reuse the cached copies (~30 seconds).

#### Common to all platforms

The Archilume app reads and writes data in the `projects/` folder next to the `docker-compose-archilume.yml` file.

Stop Archilume from Docker Desktop, or run:

```bash
docker compose -f docker-compose-archilume.yml -p archilume down
```

Refresh to the latest published images before the next launch:

```bash
docker compose -f docker-compose-archilume.yml -p archilume pull
```

See [.docker/README.md](.docker/README.md) for the end-user troubleshooting guide shipped inside the zip.

### Option B — Dev Container (Recommended for Developers)

The dev container bundles Python 3.12, Radiance, and Accelerad so there is nothing to install manually.

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.

```bash
git clone https://github.com/vincentlogarzo/archilume.git
```

Open the folder in VS Code and click **"Reopen in Container"** when prompted (or `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`). Once the container finishes building, the environment is ready.

### Option C — Native Python

```bash
git clone https://github.com/vincentlogarzo/archilume.git
cd archilume
uv sync
uv run python examples/launch_archilume_app.py
```

Requires a local Radiance install on `PATH` (or pointed at via `RADIANCE_ROOT`). Accelerad is optional for GPU rendering on Windows — see [GPU Rendering (Accelerad) — Driver Compatibility](#gpu-rendering-accelerad--driver-compatibility) for the mandatory NVIDIA driver ceiling before enabling GPU mode.

---

## Key Features

- **Reflex web app** (`archilume_app`) for drawing/editing room boundary polygons, launching workflows, reviewing rendered frames and compliance results, and exporting archives.
- **Pre-configured workflows** for sunlight access (time-series) and daylight factor (CIE overcast).
- **Multiple geometry inputs** — OBJ/MTL exports (e.g. Revit, SketchUp, Autodesk Forma). IFC inspection/stripping utilities included; full IFC ingest is on the roadmap.
- **GPU-accelerated rendering** via Accelerad on Windows (`accelerad_rpict`).
- **Parallel CPU rendering** via `rpict`/`rtpict` for Linux and the dev container.
- **FastAPI engine layer** (`archilume.api`) so the Reflex UI and external tooling can submit workflow jobs over HTTP and stream logs.
- **Compliance reporting** — Excel reports, contour and falsecolor overlays, annotated sunlight animations (APNG/MP4).
- **Cloud-ready** — GCP VM provisioning via `GCPVMManager` for remote, long-running renders.

---

## Example Scripts

The scripts in [examples/](examples/) are thin wrappers around the workflow classes, useful for headless runs, Docker engine containers, and CI smoke tests.

| Script | Description |
| ------ | ----------- |
| [launch_archilume_app.py](examples/launch_archilume_app.py) | Launch the Reflex web editor. Supports `--ensure` (reuse a running dev server), `--fast` (skip compile + cleanup), and `--force-compile`. |
| [workflow_sunlight_access.py](examples/workflow_sunlight_access.py) | Sunlight exposure: OBJ → octree → sky series → rendering → HDR/PNG time-series for the app to load. |
| [workflow_daylight_iesve.py](examples/workflow_daylight_iesve.py) | Daylight factor analysis from IESVE octrees with falsecolor and contour post-processing. |
| [workflow_daylight_iesve_api.py](examples/workflow_daylight_iesve_api.py) | Same daylight job, submitted via the in-process FastAPI engine — exercises the same path as the Docker engine container. |
| [launch_google_cloud_vm.py](examples/launch_google_cloud_vm.py) | Provision and manage a GCP VM for remote simulation runs via `GCPVMManager`. |

Run a workflow:

```bash
uv run python examples/workflow_sunlight_access.py
```

---

## Simulation Stages

Core flow: **Geometry → Octree → Sky + Views → Rendering → Post-Processing → Reports**

1. **Geometry conversion** — OBJ/MTL files are translated to Radiance format and compiled into an octree (`.oct`) via `Objs2Octree`. IFC models can be inspected and stripped with `geo/` utilities.
2. **Sky generation** — `SkyGenerator` produces time-series sunny skies (sunlight access) or CIE overcast skies (daylight factor).
3. **View & AOI generation** — `ViewGenerator` parses room boundaries, computes building extents, and generates orthographic plan views and AOI masks per room/level.
4. **Rendering** — `SunlightRenderer` (multi-phase HDR compositing, CPU or GPU) and `DaylightRenderer` (falsecolor + contour overlays).
5. **Post-processing** — `Hdr2Wpd` extracts illuminance from HDR using AOI polygon masks. `Tiff2Animation` stamps metadata and builds GIF/APNG/MP4.
6. **Reporting** — Excel reports via `Wpd2Xlsx`; contour and falsecolor layers surfaced inside the Reflex viewport.

---

## Project Structure

### Simulation Projects

Every simulation runs inside a named **project folder** under `projects/`. Each project is fully self-contained.

```text
projects/
└── <project_name>/
    ├── inputs/           # Source files: OBJ, MTL, IFC, CSV, AOI, PDF plans
    │   ├── aoi/          # Editor-drawn room boundary .aoi files (auto-created)
    │   └── plans/        # PDF floor plans for overlay in the editor
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

All workflows and the app accept a `project` name that resolves every path:

```python
from archilume import config
from archilume.workflows import SunlightAccessWorkflow

project = "ProjectXYZ"
paths = config.get_project_paths(project)

SunlightAccessWorkflow().run(
    project             = project,
    building_latitude   = -37.8134,
    month               = 6,
    day                 = 21,
    start_hour          = 9,
    end_hour            = 15,
    timestep_min        = 15,
    ffl_offset_mm       = 1000,
    grid_resolution_mm  = 15,
    aoi_inputs_dir      = paths.aoi_inputs_dir,
    obj_paths           = [paths.inputs_dir / "model.obj"],
)
```

### Repository Layout

```text
archilume/
├── .devcontainer/                          # Docker dev container (Radiance + Accelerad)
├── .docker/                                # End-user Docker distribution
│   ├── Dockerfile
│   ├── docker-compose-archilume.yml
│   ├── launch-archilume.cmd                # Windows launcher
│   ├── _launch-archilume.ps1               # PowerShell implementation
│   └── README.md                           # End-user troubleshooting guide
│
├── archilume/                              # Core package
│   ├── core/                               # Simulation engine
│   │   ├── objs2octree.py                  #   OBJ/MTL → Radiance octree
│   │   ├── sky_generator.py                #   Sky condition generation
│   │   ├── view_generator.py               #   View and AOI file generation
│   │   ├── rendering_pipelines.py          #   SunlightRenderer & DaylightRenderer
│   │   ├── mtl_converter.py                #   Wavefront MTL → Radiance materials
│   │   ├── radiance_materials.py           #   Radiance material primitives
│   │   └── accelerad_rpict.ps1             #   Accelerad GPU launcher (Windows)
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
│   ├── workflows/                          # Orchestrated pipelines
│   │   ├── sunlight_access_workflow.py     #   Full sunlight access pipeline
│   │   └── iesve_daylight_workflow.py      #   IESVE daylight factor pipeline
│   │
│   ├── api/                                # FastAPI engine layer
│   │   ├── app.py                          #   FastAPI app + router mount
│   │   ├── routes/                         #   Job submission + status endpoints
│   │   ├── jobs.py                         #   JobManager (background workflow runs)
│   │   ├── models.py                       #   Pydantic request/response models
│   │   └── run.py                          #   Standalone uvicorn entrypoint
│   │
│   ├── apps/                               # Interactive tools
│   │   ├── archilume_app/                  #   Reflex web editor (primary UI)
│   │   │   └── archilume_app/
│   │   │       ├── archilume_app.py        #     Top-level page composition
│   │   │       ├── components/             #     Header, sidebar, viewport, modals
│   │   │       ├── state/                  #     Reflex State subclasses
│   │   │       ├── lib/                    #     Image/export/canvas helpers
│   │   │       └── styles.py               #     Colour tokens, fonts, layout
│   │   └── octree_viewer.py                #   3D octree viewer
│   │
│   ├── infra/                              # Cloud infrastructure
│   │   └── gcp_vm_manager.py               #   GCP VM lifecycle management
│   │
│   ├── config.py                           # ProjectPaths, tool paths, environment detection
│   ├── project.py                          # Project-level config/state
│   └── utils.py                            # Parallel execution, timing, geometry helpers
│
├── examples/                               # Workflow scripts + app launcher
├── projects/                               # Per-project simulation data (inputs + outputs)
├── docs/                                   # Spec + design notes
└── tests/                                  # Test suite
```

---

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
pytest
pytest tests/test_sky_generator.py         # single file

# Run a workflow
uv run python examples/workflow_sunlight_access.py
uv run python examples/workflow_daylight_iesve.py

# Launch the Reflex web editor
uv run python examples/launch_archilume_app.py --ensure   # reuse running dev server
uv run python examples/launch_archilume_app.py            # fresh restart

# Run a workflow through the in-process FastAPI engine
uv run python examples/workflow_daylight_iesve_api.py
```

---

## Configuration

`archilume.config` manages all path resolution and environment detection:

- **Tool paths** — Automatically finds Radiance and Accelerad binaries. Override with `RADIANCE_ROOT` and `ACCELERAD_ROOT` environment variables.
- **Project paths** — `config.get_project_paths("myproject")` returns a `ProjectPaths` object with every directory for that project. Workflows call `paths.create_dirs()` automatically at startup. The Reflex app does not — project directories appear only when the corresponding upload field receives a file.
- **Worker count** — Parallel operations respect `config.WORKERS` (defaults to CPU count).
- **Platform awareness** — Detects Windows vs Linux, bundled vs system Radiance, GPU availability.

---

## GPU Rendering (Accelerad) — Driver Compatibility

GPU rendering in the Sunlight Access workflow uses **Accelerad 0.7 beta** (bundled in `.devcontainer/accelerad_07_beta_Windows/`). Accelerad 0.7 beta links against the **OptiX 6.0 client runtime**, and NVIDIA removed OptiX 6 support from driver branches **after R581**. If you run GPU mode on a newer driver, `accelerad_rpict` fails immediately with:

```text
accelerad_rpict: internal - Error reading OptiX library. Update your graphics driver.
```

The workflow will then write header-only HDR stubs and abort.

### Required driver ceiling

| Status | NVIDIA driver | Notes |
| --- | --- | --- |
| ✅ Known-good | **R580 U2 (580.97)** — Aug 2025 | Confirmed working with Accelerad 0.7 beta on RTX A1000 (Ampere, CC 8.6). |
| ✅ Likely OK | Any driver **≤ R581** | Per Nathaniel Jones (Accelerad author) — see [radiance-online thread](https://discourse.radiance-online.org/t/optix-error-for-rtx5080/6966). |
| ❌ Broken | R582 and newer (incl. R595.x) | OptiX 6 client runtime fails to load. |

Before enabling GPU mode, check your driver:

```powershell
nvidia-smi
```

If the reported version is above 580.97, either downgrade (below) or set `rendering_mode = "cpu"` in your workflow script.

### Downgrade procedure

In-place NVIDIA installer is **not sufficient** — the DriverStore retains the newer `nvoptix.dll` and the OptiX error persists. Use DDU.

1. **Download** [Display Driver Uninstaller (DDU)](https://www.wagnardsoft.com/display-driver-uninstaller-DDU) and the target NVIDIA driver (e.g. R580 U2 from the [NVIDIA driver search](https://www.nvidia.com/Download/Find.aspx)).
2. **Disable Windows Update driver delivery** (Settings → Windows Update → Advanced options → *Receive updates for other Microsoft products* → OFF). Windows 11 will re-push the latest driver automatically otherwise.
3. **Disconnect from the internet**, reboot into **Safe Mode** (Shift + Restart → Troubleshoot → Advanced options → Startup Settings → press 4).
4. In Safe Mode run DDU → select NVIDIA → **Clean and restart**.
5. After the reboot, run the R580 installer → **Custom install** → tick **Perform a clean installation**.
6. Verify with `nvidia-smi` (should report `Driver Version: 580.97`).
7. Run `.devcontainer\accelerad_07_beta_Windows\demo\test_accelerad_rpict.bat` — it should produce `test_rpict.hdr` above 10 KB.
8. Re-enable Windows Update driver delivery if desired.

### Docker / dev container users

The dev container runs on Linux via WSL2. Accelerad is Windows-host-only and not active inside the container — the driver ceiling only applies if you intend to run the Windows-native workflow with `rendering_mode = "GPU"`.

### Long-term

A community port of Accelerad to OptiX 7 (via NVIDIA's OWL framework) has been mentioned in the Accelerad forum. When it lands, this driver ceiling is lifted. Track progress at the [Accelerad GitHub](https://github.com/nljones/Accelerad).

---

## License

MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgements

- [Radiance](https://www.radiance-online.org/) — industry-standard lighting simulation
- [Accelerad](https://nljones.github.io/Accelerad/) — GPU-accelerated rendering
- [PyRadiance](https://github.com/LBNL-ETA/pyradiance) — Python–Radiance integration
- [Reflex](https://reflex.dev/) — Python web framework powering the editor
