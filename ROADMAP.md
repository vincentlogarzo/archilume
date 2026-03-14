# Archilume Project Roadmap

This file tracks planned features, optimizations, and known issues for the Archilume framework.

## 🚨 TOP PRIORITY: Bugs & Blocking Issues

- **[BUG] Windows Post-Processing Pipeline Failure (`DaylightRenderer`):** The HDR post-processing commands in `_postprocess_hdr` and `_generate_legends` (in `archilume/core/rendering_pipelines.py`) use Unix-style shell pipes (`pcomb | falsecolor | ra_tiff`) which fail silently on Windows. The `rpict` rendering step completes, but no falsecolor or contour TIFFs/PNGs are produced. The size check (`>= 1000 bytes`) masks the failure. Fix: decompose each piped command chain into intermediate temp files so each step runs as a discrete shell call, compatible with both `cmd.exe`/PowerShell and Linux shells.

---

## 🔴 HIGH PRIORITY: Core Workflow & Output Improvements

- **Grid Resolution:** Support grid size input in millimeters. Auto-calculate `x_res`, `y_res` from room extents.
- **RDP References:** Implement inline `@v{rdp_file_path}` implementation to simplify command outputs.
- **Modular Post-Processing:** Break `Tiff2Animation` into `Wpd2Tiff` and `Tiff2Animation` for clearer function separation.
- **Advanced Reporting:** Replace Excel output with a `wpd2report` module generating PDF/HTML with NSW ADG metrics.
- **Auto-Cleanup:** Move `smart_cleanup` into each workflow's `InputsValidator`. Must happen *after* file naming encodes the scenario grid (resolution, rendering params, etc.) so the cache can distinguish previously completed runs. For the IESVE daylight workflow specifically, the only input the user should need to flag is whether the source `.oct` file has changed — parameter/resolution changes should be inferred automatically from the output file names.
- **Packaging:** Implement Phase 6 to package final results into a timestamped `.zip` deliverable.
- **Standalone Contour & Falsecolor Generators:** Create standalone contour (`cnt`) and falsecolor generators that accept IESVE `.pic` files or Archilume-rendered `.hdr` files, using the same conversion steps as `daylight_workflow_iesve.py`. Integrate these as interactive layers within `room_boundaries_editor.py` so users only need rendered images to perform analysis — no workflow re-run required. Users should be able to switch between raw, contour, and falsecolor layers, adjust parameters (e.g. scale, step size, legend range) per layer, and see updates live in the editor.

## 🟡 MEDIUM PRIORITY: Input Handling & Validation

- **Path Support:** Add support for file paths with spaces (quote all f-strings).
- **Duplicate Handling:** Handle duplicate room names in CSV by auto-appending suffixes.
- **Unit Scaling:** Support OBJ files exported in millimeters (auto-detect and convert to meters). Currently caught using the inputs validator class prior to simulation runs. 
- **Boundary Auto-Gen:** Add option to auto-generate room boundaries from floor plans if CSV is missing.

## 🟡 MEDIUM PRIORITY: Rendering Pipeline Optimizations

- **Multiprocess CPU:** Implement `rtrace` multiprocess rendering for CPU-only systems.
- **Indirect Toggle:** Add toggle to skip indirect lighting calculation for faster compliance-only runs.
- **GPU Batching:** Explore direct `.bat` calls for `accelerad_rpict` to reduce Python overhead.
- **Custom Parameters:** Allow user-defined Radiance parameters as an alternative to presets.

## 🟡 MEDIUM PRIORITY: View Generation & AOI

- **Early AOI Gen:** Move AOI generation earlier in the pipeline (it doesn't need HDRs).
- **Dynamic Bounds:** Implement per-level bounding boxes instead of building-wide uniform views.
- **Elevations:** Support vertical view positions for facade and elevation analysis.
- **Interactive Tweak:** Create an interface for manual AOI boundary adjustments with persistence.

## 🟢 LOW PRIORITY: Performance, Cross-Platform & Deployment

- **Compressed PNG Output:** Convert TIFF outputs from `SunlightAccessWorkflow` to compressed PNG (as already done in the daylight workflow). PNG files are significantly more compact than TIFFs, reducing storage footprint for large time-series simulation runs.
- **GPU Optimization:** Use `nvmath-python` for GPU-accelerated matrix operations during WPD extraction.
- **Parallel Compilation:** Run sky/view generation in parallel with `oconv` compilation.
- **Pre-processing:** Add Blender decimation scripts to pre-process site context OBJs.
- **Bundling:** Create wrapper scripts to bundle Radiance binaries within the package.
- **Cloud Costs:** Implement cost-analysis reporting for GCP G4 instances.
- **Job Scheduling:** Implement a queue system for overnight batch rendering of multiple models.

## 🧹 REFACTORING & CODE CLEANUP

- **Objs2Octree:** Move `obj_paths` from instance variable to method argument in `create_skyless_octree_for_analysis()`.
- **Security:** Refactor all `subprocess` calls to use `shell=False` and list-based arguments.

---

## 🏛️ DAYLIGHT FACTOR WORKFLOW (IESVE & OBJ)

### Core Architecture

- **OBJ Input Use Case:** Enable direct input of OBJ files for the daylight workflow, allowing for full octree compilation (sky + geometry) within Archilume rather than relying solely on pre-built IESVE octrees.
- **Scenario Grid:** Implement a variant/scenario grid system with matching file naming conventions to allow running permutations (different materials/params) in the most efficient order.
- **Raw File Compilation:** Automate the compilation of raw geometry and .map files into octrees based on the scenario grid.
- **GPU Mode:** Add support for GPU rendering in the Daylight pipeline (similar to Sunlight workflow) to enable fast processing on Windows machines.

### Post-Processing & Validation

- **Editor Integration:** Move image post-processing (falsecolor/contours) from the Renderer into the AOI Editor.
- **WPD Consistency:** Ensure room boundaries created from AOIs enforce consistent width, height, and center points to maintain pixel-to-world mapping alignment across all levels.

---

## ☁️ CLOUD INFRASTRUCTURE & VM MANAGEMENT (GCP)

- **Image-Based Setup:** Transition from 10-minute setup scripts to pre-built Docker images on GCP Artifact Registry. Bake in: apt deps, Radiance, Accelerad, uv, Python venv, and repository (git pull on start).
- **Service Account Auth:** Authenticate Docker on VM via service account attached to the instance, eliminating the need for `gcloud` CLI inside the container.
- **DevContainer :** Issue where dev container cannot use compatible GPU on machine. 
- **Permission Debugging:** Re-evaluate and fix permissions errors encountered during container builds inside the VM environment.

---

## 🐳 DOCKER PACKAGING & DISTRIBUTION

- **Two-Image Strategy:**
    1. **Archilume-Compute:** A headless, performance-optimized image containing the full simulation stack (Radiance/Accelerad/Python) for heavy CLI-based workloads.
    2. **Archilume-App:** A user-facing interactive image that bundles the Dash-based applications (AOI Editor, Viewers).
- **One-Command Launch:** Enable new users to simply install Docker Desktop and run `docker run archilume-app` to open a web-based portal to the entire suite of tools.
- **Cross-Platform Accessibility:** Ensure the App image handles interactive GUI components via a web browser (Dash) to eliminate the need for local Python or Radiance installations on Windows/Mac.

---

## 🖼️ HDR AOI EDITOR (INTERACTIVE)

### Core Architecture

- **Multi-Resolution Reuse:** Allow pre-existing AOI boundaries to be reused across images rendered at different resolutions by storing vertices in normalized [0,1] or world coordinates.
- **Self-Contained Transform:** Derive pixel to world transform directly from the .hdr header (VIEW= parameters) and pixel dimensions, removing map file dependency.
- **State Machine Integration:** Replace scattered mode-tracking attributes with a single explicit state machine to prevent invalid combined states.
- **Unified Undo Stack:** Consolidate independent undo stacks into a single ordered stack of JSON state snapshots for consistent restoration.

### Drawing & Editing Tools

- **Sub-room Snapping:** Improve sub-room polygon placement with duplicate point prevention and edge/vertex snapping to parent boundaries.
- **Rectangle Tool:** Add a dedicated rectangle tool to drawing mode for faster room creation.
- **Room Divider Fixes:** Ensure the divider tool auto-closes unclosed polygons and prevents clashes/overlaps with existing boundaries.
- **Input Guarding:** Suppress or explicitly handle scroll, pan, and right-click events during draw mode to prevent accidental vertex placement.
- **Wall-Thickness Inset:** Add option to pull compliant areas inward by a user-specified wall thickness distance.

### Hierarchy & Grouping

- **2-Tier Hierarchy:** Enforce a strict 2-tier AOI hierarchy (parent room / sub-room).
- **Room Grouping:** Allow multi-select grouping of rooms to evaluate aggregate results for apartments.
- **Auto-Grouping:** Implement level-based auto-grouping by floor level for separate AOI export.
- **Copy Across Levels:** Add "Copy boundaries up/down" actions for selected rooms or entire floors.

### UI/UX & Visualization

- **Room List Search & Filter:** Add a search/filter bar to the saved rooms panel so users can filter visible rooms by name, type (e.g. BED, LIVING, CIRC), or sub-room prefix. Filtering should hide non-matching rooms from the list and dim (but not remove) their boundaries on the canvas so spatial context is preserved.
- **Dynamic Labeling:** Update result label positions using a two-pass approach: identify high-DF facade edges and use pole-of-inaccessibility for fallback.
- **Compliance Overlays:** Display building/floor level BESS pass/fail summaries in a fixed UI panel; add pass/fail toggle overlays with image export. Results are shown on a room by room basis at the moment.
- **Post-Processing Integration:** Integrate CNT and DF false-color generation into the viewer with automated temp file management.
- **Hotkey Mirroring:** Mirror all hotkeys as labeled UI buttons with context-sensitive grey-out states.
- **Viewport Optimization:** Remove side border gaps in the UI to maximize the image viewport.

### Workflow & Simulation

- **Integrated Controls:** Add simulation and post-processing controls directly to the UI to run the full daylight IESVE workflow locally. <- this item is to progress to a docker image that launches a dash web UI to control everything. The user can click through pre-configured workflows, and auhment whatever parameters they are allow to augment.
- **Permutation Grid:** Add 5×5 permutation grid for quality, LRV, and VLT variables to evaluate sensitivity for failing rooms.
- **Boundary Management:** Allow deletion of boundaries and restoration from source AOI files within the UI.

### IESVE .pic Compatibility

- **Migrate Post-Processing into Room Boundary Editor:** For this to be viable, the `df_cnt` (contour) and `df_false` (falsecolor) conversion steps currently handled in the rendering pipeline would need to be surfaced within `room_boundaries_editor.py`, so the editor can produce annotated outputs independently.
- **[TEST & FIX] PDF Page Shifting in HDR Editor:** The feature to swap PDF pages/levels for the underlay in the HDR editor is fragile and unresponsive. Test and debug the page shifting functionality to ensure smooth, reliable switching between levels when using PDF underlays.

### Notes

- **Prerequisites:** `daylight_workflow_iesve.py` must be run before use of this editor.
- **Map Generation:** Pixel-to-world coordinate maps must be generated per resolution if resolution-specific mapping is used.


# Archilume: Docker-Based GCP Transition Plan

## 🎯 Objective

Transition from the current 10-minute script-based VM setup to a Docker-based "Pull & Play" architecture. This will reduce setup time to < 1 minute, ensure environment parity between local/remote, and optimize the use of high-speed local SSDs.

---

## 🏗️ Phase 1: Docker Image Engineering

**Goal:** Bake all heavy dependencies into a single, GPU-ready image.

### 1.1 Create the `Dockerfile`

- **Base Image:** `nvidia/cuda:12.4.1-devel-ubuntu22.04` (to support Accelerad/GPU).
- **Baked-in Tools:**
    - Radiance 6.1 (Linux binaries).
    - Accelerad (compiled from source).
    - Python 3.12 (via `uv`).
    - System deps: `libgl1`, `libtiff-tools`, `build-essential`.
- **Environment:** Pre-set `RAYPATH`, `PATH`, and `UV_LINK_MODE`.

### 1.2 Setup Google Artifact Registry

- Create a private repository: `australia-southeast1-docker.pkg.dev/<project>/archilume`.
- Authenticate local machine and VM to this registry.

---

## 🚀 Phase 2: Refactoring `GCPVMManager`

**Goal:** Shift the Python manager from "System Installer" to "Orchestrator."

### 2.1 The "Docker-on-SSD" Strategy

Modify `setup()` in `archilume/gcp_vm_manager.py`:

1.  **Format/Mount SSD:** (Keep existing logic).
2.  **Redirect Docker Storage:** 
    - Create `/mnt/disks/localssd/docker`.
    - Update `/etc/docker/daemon.json` to set `"data-root": "/mnt/disks/localssd/docker"`.
    - Restart Docker.
3.  **Auth & Pull:**
    - `gcloud auth configure-docker <region>-docker.pkg.dev`.
    - `docker pull <image-url>:latest`.

### 2.2 The Execution Command

Replace the "Cloning & Setup" step with a robust `docker run` template:

```bash
docker run --rm -it \
  --gpus all \
  -v /mnt/disks/localssd/workspace:/workspace \
  -w /workspace \
  <image-url>:latest \
  /bin/bash
```

---

## 📂 Phase 3: Mounting & Data Strategy

**Goal:** Ensure zero data loss and maximum performance.

- **Workspace Mount:** The entire `/mnt/disks/localssd/workspace` folder is mounted as a volume.
- **Persistent Code:** Use `git clone` on the SSD once, but run the Python interpreter from the Docker container. This allows editing code via VS Code Remote-SSH while using the container's environment.
- **Output Management:** All results written to `/workspace/outputs` on the SSD remain after the container exits.

---

## 🛠️ Phase 4: CI/CD Automation

**Goal:** One command to update the remote environment.

- Create a `build_and_push.sh` script:
    1. `docker build -t archilume-env .`
    2. `docker tag archilume-env <gcp-url>:latest`
    3. `docker push <gcp-url>:latest`

---

## 📈 Success Metrics

- **Setup Time:** Reduced from ~600s to <45s.
- **Stability:** Elimination of "failed to install Radiance" or "broken symlink" errors on the VM.
- **Performance:** GPU utilization verified via `nvidia-smi` inside the container.

---

## 📝 Future Notes for Execution

- Check the version of `libtiff` required by Radiance (currently symlinked in `setup.sh`).
- Ensure the Service Account attached to the VM has `Artifact Registry Reader` permissions.
- Consider a `docker-compose.yml` for more complex multi-container tasks (e.g., Dash dashboard + Simulation).
