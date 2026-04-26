# Archilume Project Roadmap

This file tracks planned features, optimizations, and known issues for the Archilume framework.

## 🎯 IMMEDIATE NEXT ACTION

- **Vertical-surface sunlight investigation (new feature).** Extend the sunlight workflow to analyse wall surfaces, not just horizontal floor planes. A vertical AOI becomes another view associated with a room ID — just a new entry in the view list, consumed by the existing `SunlightAccessWorkflow`.
  - **Mode A — Individual wall selection:** user picks specific wall segments in the Reflex app; app generates the corresponding vertical views and submits the job.
  - **Mode B — Blanket boundary sweep:** every vertical surface along a room's boundary is swept automatically, one view per wall face.
  - **Boundary discipline:** users MUST draw room boundaries just inside the wall surface (not on-centre, not outside) — the vertical view origin is offset from the boundary and needs the boundary to hug the inner face of the wall. This is why the daylight-backing reintegration above is a hard prerequisite: without the daylight composite, users can't see the internal wall position clearly enough to draw accurate boundaries.
  - Surface in the app UI as a third "View Type" (alongside the existing horizontal plan views) keyed per room, so results integrate naturally with the existing room-browser tree.

---

## 🚨 TOP PRIORITY: Bugs & Blocking Issues

- **[BUG] Windows Post-Processing Pipeline Failure (`DaylightRenderer`):** The HDR post-processing commands in `_postprocess_hdr` and `_generate_legends` (in `archilume/core/rendering_pipelines.py`) use Unix-style shell pipes (`pcomb | falsecolor | ra_tiff`) which fail silently on Windows. The `rpict` rendering step completes, but no falsecolor or contour TIFFs/PNGs are produced. The size check (`>= 1000 bytes`) masks the failure. Fix: decompose each piped command chain into intermediate temp files so each step runs as a discrete shell call, compatible with both `cmd.exe`/PowerShell and Linux shells.

---

## 🔴 HIGH PRIORITY: Core Workflow & Output Improvements

- **grid_resolution:** Implement grid_resolution into the daylight workflow as it currently seen in the sunlight access workflow.
- **RDP References:** Implement inline `@v{rdp_file_path}` implementation to simplify command outputs.
- **Include gpu rendering option into the daylight workflow.** `examples/workflow_sunlight_access.py` implement the current accelerad_rpict.ps1 into the workflow, and update custom parameter inputs by user in all functions that construct radiance commands. These should all be extracted or potentially utilise pyradiance.
- **Modular Post-Processing:** Break `Tiff2Animation` into `Wpd2Tiff` and `Tiff2Animation` for clearer function separation.
- **Tone-mapping args on `hdr2png`:** Introduce parameter args into `archilume/post/hdr2png.py` so callers can override the `pfilt -1 | ra_tiff -e -4` defaults (exposure, gamma, human-vision preset, scale factor) when they want to adjust tone mapping — e.g. brightening very dark overcast HDRs. Keep the current defaults as a baseline. Future extension: an automated tone-mapping pass that inspects the HDR histogram and picks exposure/gamma per-image for very dark images, so the archilume-app displays readable PNGs without the user having to tune parameters. Surface the knobs through `SunlightRenderer` / `SunlightAccessWorkflow` and eventually the Reflex UI.
- **Advanced Reporting:** Replace Excel output with a `wpd2report` module generating PDF/HTML with NSW ADG metrics.
- **Smart Re-Run Cache (replaces the removed `smart_cleanup`):** Today every workflow run calls `clear_outputs_folder(paths)` and starts from a blank outputs directory. The future goal is a cache that lets users re-run simulations cheaply by reusing prior work — specifically `.amb` ambient files and (where valid) rendered HDRs.

  **Mechanism:** Encode the full parameter grid (resolution, rendering mode/quality, Radiance `-ab/-ad/-as` params, timestep, sky scenario, etc.) as a deterministic suffix on every output filename. `execute_new_radiance_commands` then inspects the planned output path before dispatching:
  - If the target file already exists with a matching suffix → skip the command (cache hit).
  - If a matching `.amb` exists for the current parameter set → reuse it (`-af <path>` in the Radiance call).
  - Otherwise → run fresh and write with the new suffix so future runs can reuse.

  **Scope notes:**
  - Must live *after* the file-naming change so the suffix uniquely identifies each scenario.
  - For the IESVE daylight workflow, the only change flag the user should have to set is whether the source `.oct` file itself has changed; every other parameter change is inferred from output filenames.
  - Move the cache-key logic into each workflow's `InputsValidator` so it happens before any commands are dispatched.
- **Packaging:** Implement Phase 6 to package final results into a timestamped `.zip` deliverable.
- **Standalone Contour & Falsecolor Generators:** Create standalone contour (`cnt`) and falsecolor generators that accept IESVE `.pic` files or Archilume-rendered `.hdr` files, using the same conversion steps as `daylight_workflow_iesve.py`. Integrate these as interactive layers within `room_boundaries_editor.py` so users only need rendered images to perform analysis — no workflow re-run required. Users should be able to switch between raw, contour, and falsecolor layers, adjust parameters (e.g. scale, step size, legend range) per layer, and see updates live in the editor.

## 🟡 MEDIUM PRIORITY: CLI / Headless Execution

- **[CLI] Convert Headline Workflow Examples to argparse CLI Style:** Refactor the headline workflow example scripts so user inputs (project name, paths, mode, hours, resolution, GPU toggle, etc.) are exposed as `argparse` command-line flags instead of hardcoded constants at the top of each file.

  **Primary use case — GCP VM / Docker compute jobs:** The strongest motivation is quick spin-up and testing of the compute image on a GCP VM. Once we have a built `archilume-compute` image (see Docker Packaging section below), the workflow is:
  1. SSH into VM.
  2. `docker run -d --name arch -v /workspace:/workspace archilume-compute:latest sleep infinity` (one-time launch).
  3. `docker exec arch python examples/workflow_sunlight_access.py --project 527DP --hours 9,12,15` for each test run, no code edit needed.

  This means we can iterate on different projects/parameters on the VM without rebuilding the image, editing files inside the container, or maintaining a separate "test runner" script.

  **Secondary use cases:** cron/batch automation, CI smoke tests, reproducible "run this exact command" sharing between team members.

  **Where CLI does NOT add value (do not waste effort here):**
  - Reflex UI and the planned FastAPI engine layer call workflow classes via `import` directly — CLI is irrelevant to them.
  - Local dev where the developer is already editing example scripts in their IDE — editing constants at the top is fine.
  - Claude/agent-driven runs — agents can write `python -c "from archilume.workflows import ...; ...run()"` just as easily as a CLI invocation, so CLI gives no agent-ergonomics benefit.

  **Files to convert (priority order, only if/when actually needed for VM testing):**
  1. `examples/workflow_sunlight_access.py`
  2. `examples/workflow_daylight_iesve.py`
  3. `examples/workflow_daylight_iesve_api.py`

  The `launch_archilume_app.py` GUI script is **out of scope** — it opens an interactive editor with no headless/container use case.

  **Implementation rules:**
  - Keep the workflow class APIs (`SunlightAccessWorkflow`, `IESVEDaylightWorkflow`) untouched. Example scripts become thin argparse wrappers around the existing class.
  - Use `argparse.ArgumentParser` with `--help` text describing every flag.
  - Provide sensible defaults so `python examples/workflow_sunlight_access.py --project 527DP` still works without specifying every flag.
  - Validate paths via `pathlib.Path`; fail loudly with a clear message if a required input is missing.
  - Print the resolved config back to stdout before running, so `docker logs arch` shows exactly what was executed.

---

## 🟡 MEDIUM PRIORITY: Input Handling & Validation

- **[CRITICAL] Input File Validity Tests & Validator Refinement:** The archilume-app upload validators currently reject valid files (false positives), blocking users at the very first step of new project setup. Write a detailed, parameterised test suite covering every supported input format (OBJ, MTL, IFC, CSV room boundaries, IESVE `.pic`/`.oct`, HDR) with fixtures for: known-good files, known-bad files, and the awkward middle cases (mm-scaled OBJs, non-ASCII material names, duplicate room names, missing `mtllib` refs, IFC schema mismatches, CSVs with trailing blank lines, etc.). Use the test results to refine the validator logic so the rejection message tells the user *exactly* which rule failed and what to fix. This is a critical onboarding step — if a user can't tell whether their files are valid, they can't start a project. Target: zero false-positive rejections on the known-good fixture set, and human-readable diagnostics on every failure path.
- **Path Support:** Add support for file paths with spaces (quote all f-strings).
- **Duplicate Handling:** Handle duplicate room names in CSV by auto-appending suffixes.
- **Unit Scaling:** Support OBJ files exported in millimeters (auto-detect and convert to meters). Currently caught using the inputs validator class prior to simulation runs. 
- **Boundary Auto-Gen:** Add option to auto-generate room boundaries from floor plans if CSV is missing.

## 🟡 MEDIUM PRIORITY: Rendering Pipeline Optimizations

- **Multiprocess CPU:** Implement `rtrace` multiprocess rendering for CPU-only systems.
- **Indirect Toggle:** Add toggle to skip indirect lighting calculation for faster compliance-only runs.
- **GPU Batching:** Explore direct `.bat` calls for `accelerad_rpict` to reduce Python overhead.
- **Custom Parameters:** Allow user-defined Radiance parameters as an alternative to presets.
- **Accelerad OptiX 7 port (external dependency):** Accelerad 0.7 beta is the terminal release from upstream and ships only the OptiX 6 runtime. NVIDIA drivers newer than R581 have dropped OptiX 6 support, which pins GPU users to ≤ R580 (see [README — GPU Rendering](README.md#gpu-rendering-accelerad--driver-compatibility)). Nathaniel Jones (Accelerad author) mentioned a community effort to port Accelerad to the OptiX 7 API via NVIDIA's OWL framework on the radiance-online forum. When that port lands, bundle the updated `accelerad_rpict.exe` into `.devcontainer/` and drop the driver ceiling from the README. No archilume code change is blocked on this — it is purely an upstream dependency upgrade. Track: [Accelerad GitHub](https://github.com/nljones/Accelerad) and the [radiance-online OptiX thread](https://discourse.radiance-online.org/t/optix-error-for-rtx5080/6966).

## 🟡 MEDIUM PRIORITY: View Generation & AOI

- **Early AOI Gen:** Move AOI generation earlier in the pipeline (it doesn't need HDRs).
- **Dynamic Bounds:** Implement per-level bounding boxes instead of building-wide uniform views.
- **Elevations:** Support vertical view positions for facade and elevation analysis.
- **Interactive Tweak:** Create an interface for manual AOI boundary adjustments with persistence.

## 🟢 LOW PRIORITY: Performance, Cross-Platform & Deployment

- **Compressed PNG Output:** Convert TIFF outputs from `SunlightAccessWorkflow` to compressed PNG (as already done in the daylight workflow). PNG files are significantly more compact than TIFFs, reducing storage footprint for large time-series simulation runs.
- **Encoded-video sunlight playback (MP4/WebM for large renders):** After `SunlightAccessWorkflow` writes the per-frame PNGs, run an optional `ffmpeg` pass to produce a per-view H.264 MP4 (with AV1/WebM as a future fallback) at the source resolution. The Reflex viewport swaps `<img>` for `<video autoplay loop muted>` when the MP4 exists, keeping the SVG room-polygon + DF annotation layer on top unchanged. Benefits scale with render size — at ≥100 frames and ≥2K resolution: ~10× transport reduction (inter-frame compression exploits the slow-moving sun between timesteps), GPU hardware decode instead of per-tick CPU base64/PNG swap, single HTTP request instead of N per view, and zero backend round-trip during playback. Costs: an `ffmpeg` encode step per view (~5–30 s), re-encode on exposure changes, minor scrub latency (GOP decode), and codec loss — mitigated by CRF 18 (visually lossless) or CRF 0 (bit-exact, still smaller than the PNG sequence). Keep the URL-per-frame path as the default and fallback when no MP4 has been encoded; the video path is an opt-in accelerator for large deliverables. Gate behind a workflow flag (e.g. `encode_playback_video: bool = False` on `SunlightAccessWorkflow`) and a per-project toggle in the Reflex UI. Compliance metrics always read the underlying HDR, not the displayed MP4, so lossy frames do not affect correctness.
- **GPU Optimization:** Use `nvmath-python` for GPU-accelerated matrix operations during WPD extraction.
- **Parallel Compilation:** Run sky/view generation in parallel with `oconv` compilation.
- **Pre-processing:** Add Blender decimation scripts to pre-process site context OBJs.
- **Bundling:** Create wrapper scripts to bundle Radiance binaries within the package.
- **Cloud Costs:** Implement cost-analysis reporting for GCP G4 instances.
- **Job Scheduling:** Implement a queue system for overnight batch rendering of multiple models.
- **In-App Bug Reporting & Diagnostics Bundle:** Add a "Report Bug" entry in the Reflex app header that opens `https://github.com/vincentlogarzo/archilume/issues/new` in a new tab. Pair it with an expanded DBG mode that, when toggled on, (a) widens state-diff coverage to viewport/overlay/project fields, (b) installs JS hooks for `window.onerror`, `unhandledrejection`, `console.error/warn`, and a 30-entry pointer-event ring buffer, (c) captures browser info (UA, DPR, viewport, screen) at session start, and (d) exposes a "Copy logs" action that bundles the unified log tail, `debug_trace.json`, state snapshot, and system info into a single redaction-aware Markdown file at `~/.archilume/logs/diagnostics_{timestamp}.md`. When DBG is on, "Report Bug" first builds the bundle, copies its path to the clipboard, then opens the issues page — user pastes the file into the new issue. Reuses the existing `archilume_app/lib/debug.py` infrastructure (rotating file logger, correlation IDs, `_safe_repr` PII redaction, `DebugTrace` ring buffer). Ship alongside a `.github/ISSUE_TEMPLATE/bug_report.md` that prompts the user to attach the Markdown bundle and describe what they were doing when the bug occurred. Rationale: closes the feedback loop with users, auto-captures the environment data that turns "doesn't work" reports into reproducible ones, and does it all without custom backend / telemetry infra — GitHub Issues is the whole stack.

## 🧹 REFACTORING & CODE CLEANUP

- **Objs2Octree:** Move `obj_paths` from instance variable to method argument in `create_skyless_octree_for_analysis()`.
- **Security:** Refactor all `subprocess` calls to use `shell=False` and list-based arguments.
- **Deeper `rx.var` validation for archilume_app.** The current guards (`scripts/check_state_refs.py` + `tests/test_app_compiles.py`) catch two failure modes: (1) component references an `EditorState.X` that was never defined, and (2) Reflex page compilation raises at all. They do NOT catch subtler bugs in computed vars. Expand the validation layer to cover:
  - **Return-type ↔ component-prop mismatches.** e.g. `calib_rect_svg_x: float` passed into `rx.el.rect(x=...)` which wants `str | int` — only surfaces as `TypeError: Invalid var passed for prop`. A test could introspect every `@rx.var` return annotation and every component prop it flows into, flagging mismatches statically.
  - **Dependency-graph completeness.** Reflex only re-evaluates a computed var when a declared dependency changes; missing deps produce stale UI. Enumerate every `self.X` access inside a `@rx.var` body and confirm each is either a state var or another computed var on the same class.
  - **`rx.cond` truthiness safety.** `if not self.some_var:` inside a handler raises `VarTypeError` on certain Reflex 0.9 proxies — catch via AST scan of `editor_state.py` for bare boolean checks on state vars, suggest the `self.__dict__.get("x")` guard pattern when unavoidable.
  - **Evaluatability smoke test.** For each `@rx.var`, construct a default-initialised `EditorState` in-process and invoke the getter; fail if it raises. Currently an error only surfaces when a user hits the page that renders that var.

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
- **Cross-Platform Accessibility:** Ensure the App image handles interactive GUI components via a web browser (Dash/Reflex) to eliminate the need for local Python or Radiance installations on Windows/Mac.
- **FastAPI Inter-Container API (Low Priority):** Add a FastAPI server to the Archilume-Compute image so the Reflex UI (Archilume-App) can submit simulation jobs via HTTP. Endpoints for job submission (`POST /jobs/{workflow_type}`), status polling (`GET /jobs/{id}`), and result retrieval. Enables multi-container orchestration, job queuing, and future multi-user support. Until then, use shared volume + `docker exec` for simplicity.

---

## 🖼️ HDR AOI EDITOR (INTERACTIVE)

### Core Architecture

- **Per-Image Session Files (Major Refactor):** Replace the single `aoi_session.json` with per-image session files (e.g. `527DP_plan_ffl_14300.session.json`). Everything in the editor is fundamentally linked to the `.hdr`/`.pic` image — room boundaries, PDF underlay alignment, DF calculations, layer visibility. Per-image sessions would mean:
  - Dropping a new `.hdr` into the folder automatically works — no existing session to corrupt.
  - Different resolutions of the same level (e.g. `_half` variants, lightwell crops) each store their own correctly-projected coordinates without needing runtime re-projection workarounds.
  - Removing an image cleanly removes its state.
  - The global `_aoi_level_map` concept becomes unnecessary — each image session knows its own level/FFL.
  - Migration path: one-time conversion from existing single-session format; rooms with `world_vertices` can be re-projected per image automatically.
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
- **[TEST & FIX] PDF Page Shifting in HDR Editor:** The feature to swap PDF pages/levels for the underlay in the HDR editor is fragile and unresponsive. Test and debug the page shifting functionality to ensure smooth, reliable switching between levels when using PDF underlays. *Pending re-test after pdf.js migration — the rasterise-on-page-change round-trip has been removed (pdf.js renders client-side); confirm whether residual fragility is now resolved or whether a separate state-ordering bug remains.*

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

## ✅ Phase 2: Refactoring `GCPVMManager` — DONE

The "Docker-on-SSD" strategy (LSSD format/mount, Docker `data-root` relocation, engine pull/run) is implemented in [archilume/infra/cos_startup.sh](archilume/infra/cos_startup.sh) and runs on every COS boot. The Python manager (`archilume/infra/gcp_vm_manager.py`) is now a ~240-line orchestrator: `setup`/`delete`/`tunnel`/`restart`/`list`.

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
