# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Platform & Environment

**This project runs on Windows.** Always consider Windows compatibility:

- Use `pathlib.Path` or `os.path` instead of Unix paths
- Avoid `rsync` (use `tar`/`scp` instead)
- Use PowerShell-compatible commands
- Handle Unicode encoding issues (e.g., UTF-8 for file I/O)

**This project uses `uv` for Python dependency management, NOT pip.** Always use `uv add`, `uv sync`, and `uv run` — never pip.

## Project Overview

Archilume is a Python framework for automated Radiance-based architectural daylight and sunlight simulations. It converts 3D CAD models (OBJ/MTL, IFC) into physically accurate lighting analyses with compliance reporting.

## Common Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run all tests
pytest

# Run a single test file
pytest tests/test_sky_generator.py

# Run example workflows
python examples/sunlight_access_workflow.py
python examples/daylight_workflow_iesve.py

# Launch interactive editors
python examples/obj_aoi_editor.py
python apps/hdr_aoi_editor.py
```

## Architecture

### Simulation Pipeline

The core flow is: **Geometry → Octree → Sky + Views → Rendering → Post-Processing → Reports**

1. **Geometry conversion** (`objs2octree.py`): OBJ/MTL files → Radiance RAD → compiled octree (.oct) via `obj2rad` and `oconv`. `MtlConverter` handles Wavefront MTL → Radiance material translation using primitives from `radiance_materials.py`.
2. **Sky generation** (`sky_generator.py`): Produces time-series sunny skies (sunlight access) or CIE overcast skies (daylight factor) via `gensky`.
3. **View/AOI generation** (`view_generator.py`): Parses room boundaries CSV, computes building extents, generates orthographic plan views (.vp) and AOI boundary files per room/level.
4. **Rendering** (`rendering_pipelines.py`): Two renderer classes:
   - `SunlightRenderer`: Multi-phase (overcast indirect baseline → sunny direct series → HDR compositing via `pcomb` → TIFF conversion). Supports CPU (`rpict`) and GPU (`accelerad_rpict`).
   - `DaylightRenderer`: Sequential rendering with `rtpict` (Linux multi-core only), falsecolor post-processing, contour overlays.
5. **Post-processing**: `Hdr2Wpd` extracts illuminance from HDR using AOI polygon masks. `Tiff2Animation` stamps metadata, draws AOI overlays, creates GIF/APNG animations.
6. **Reporting**: `Wpd2Xlsx` generates formatted Excel reports with pivot summaries and compliance metrics.

### Workflow Orchestration

`workflows.py` contains `SunlightAccessWorkflow` with a nested `Inputs` validator class. The `run()` method orchestrates the full pipeline. Example scripts in `examples/` show how to configure and launch workflows.

### Key Infrastructure

- **`config.py`**: Centralized path management and environment detection. Resolves Radiance/Accelerad tool paths (platform-aware: Windows vs Linux, bundled vs system). Manages `RAYPATH`, worker counts, project directories (`inputs/`, `outputs/`). Override tool paths via `RADIANCE_ROOT` and `ACCELERAD_ROOT` env vars.
- **`utils.py`**: Parallel command execution (`execute_new_radiance_commands`), timing (`PhaseTimer`/`Timekeeper`), geometry calculations (centroid, bounding box), HDR helpers, `smart_cleanup()` for output management, CSV conversions.
- **Interactive editors**: `ObjAoiEditor` (matplotlib-based, uses `MeshSlicer` for 3D→2D via PyVista) and `HdrAoiEditor` (Dash/Plotly web app in `apps/`). Both support hierarchical room naming and export boundaries for the pipeline.

### Cloud Integration

`GCPVMManager` handles GCP VM lifecycle (creation, SSH, Docker deployment). Config stored at `~/.archilume_gcp_config.json`.

## GCP / Infrastructure

When updating SSH config for GCP VMs with new IPs, ensure the `User` field matches the VM's system username (typically set during VM provisioning). Do not assume or change the username without explicit instruction.

## Code Modification Rules

When renaming files, classes, or modules, **only rename exactly what the user requests.** Do not rename related files or add suffixes unless explicitly asked.

## Workflow Expectations

Before making code changes, briefly explain your approach and get confirmation. Do not start editing until the user agrees with the plan.

## Git Workflow

Always commit and push changes after completing a task unless told otherwise. Verify git status and ensure all modified files are staged.

**Before every commit, scan all staged changes for sensitive information:**

- API keys, tokens, secrets, or passwords (hardcoded or in config files)
- Private keys or certificates (`.pem`, `.key`, `.p12`, etc.)
- Cloud credentials or service account files (`.json` GCP/AWS/Azure credentials)
- SSH private keys or known-hosts with internal IPs
- `.env` files or any file containing `SECRET`, `PASSWORD`, `TOKEN`, `API_KEY` patterns
- Internal hostnames, IP addresses, or infrastructure details that should not be public

If any sensitive data is found, **stop and alert the user** before proceeding. Do not commit or push until the issue is resolved.

## Units

Always use SI units (metres, millimetres, kilograms, lux, etc.) in all discussions, code comments, and documentation. Never use imperial units (inches, feet, miles, etc.).

## Coding Conventions

- **Paths**: Always use `pathlib.Path`. Reference `archilume.config` for standard project paths.
- **Parallelism**: Use `utils.execute_new_radiance_commands` for Radiance tool parallelism. Respect `config.WORKERS` limits.
- **Platform**: `rtpict` (multi-core rendering) is Linux-only. Be mindful of Windows/Linux/WSL differences throughout.
- **Dash apps**: Use `app.run(debug=True)` for development.
- **Rendering classes**: Prefer `SunlightRenderer`/`DaylightRenderer` over calling Radiance binaries directly.
- **Cleanup**: Use `utils.smart_cleanup()` to clear previous results based on changed parameters.
- **Verification**: Check HDR outputs exist in `outputs/image/` before proceeding to post-processing.
- **Imports**: All `import` statements must be placed at the top of the module. Never place imports inside functions or methods. Before adding an import, check if it already exists in the file.

## Development Environment

The recommended setup is the **Docker dev container** (`.devcontainer/`), which bundles Python 3.12, Radiance, and Accelerad. Native Windows setup requires manual Radiance installation and `uv sync` for Python dependencies.

## Claude Code Instructions

**Before giving platform-specific advice, determine the execution environment:**

1. **Check the system context** — Note the OS (Windows/Linux/macOS) and current working directory
2. **Verify container/WSL status** — Determine if running in dev container, WSL, or native
3. **Audit all command suggestions** for platform compatibility:
   - Use `pathlib.Path` and forward slashes in Python (cross-platform)
   - Use PowerShell syntax on Windows (not Unix bash)
   - Always recommend `uv` for package management (never `pip`)
   - Flag Linux-only tools (`rtpict` multi-core, `rsync`) if on Windows
   - Remember AcceleradRT works natively on Windows; `rtpict` requires Linux
4. **Flag any platform clashes** before suggesting terminal commands

**Current environment:** Native Windows (not WSL, not dev container)

**Tool availability by platform:**

- **Native Windows**: Accelerad, AcceleradRT (GPU), basic Radiance tools
- **WSL/Linux**: `rtpict` (multi-core rendering), Accelerad (needs GPU passthrough)
- **Dev container**: All tools bundled and optimized
