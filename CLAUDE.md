# CLAUDE.md

## Platform & Environment

**Runs on Windows and Linux.** Before any terminal command, detect OS:

```bash
python -c "import sys; print(sys.platform)"
# win32 → PowerShell syntax | linux → bash syntax
```

- **Windows**: PowerShell commands. `rtpict` multi-core and `rsync` unavailable. AcceleradRT (GPU) works natively.
- **Linux (dev container)**: All tools available including `rtpict`. Recommended setup: `.devcontainer/` bundles Python 3.12, Radiance, Accelerad.
- **Package manager**: Always `uv` (`uv add`, `uv sync`, `uv run`) — never `pip`.
- **Paths**: Always `pathlib.Path` in Python. UTF-8 for file I/O.

**Current environment:** Native Windows (not dev container)

## Project Overview

Archilume is a Python framework for Radiance-based architectural daylight and sunlight simulations. Converts OBJ/MTL and IFC models into physically accurate lighting analyses with compliance reporting.

## Common Commands

```bash
uv sync                                           # install dependencies
pytest                                            # run all tests
python examples/workflow_sunlight_access.py       # sunlight access example
python examples/workflow_daylight_iesve.py        # daylight/IESVE example
python examples/launch_archilume_ui.py            # launch Reflex UI (preferred)
python examples/launch_hdr_editor.py              # launch HDR/AOI matplotlib editor
python examples/launch_obj_editor.py              # launch OBJ/AOI editor
```

## Architecture

**Pipeline:** Geometry → Octree → Sky + Views → Rendering → Post-Processing → Reports

1. **Geometry** (`core/objs2octree.py`): OBJ/MTL → Radiance RAD → octree via `obj2rad`/`oconv`. `MtlConverter` handles MTL → Radiance materials.
2. **Geo** (`geo/`): IFC/OBJ inspection, cleaning, stripping, and boundary extraction (`obj2boundaries.py`).
3. **Sky** (`core/sky_generator.py`): Time-series sunny skies (sunlight access) or CIE overcast (daylight factor) via `gensky`.
4. **Views/AOI** (`core/view_generator.py`): Parses room boundaries CSV, generates orthographic plan views (.vp) and AOI boundary files.
5. **Rendering** (`core/rendering_pipelines.py`):
   - `SunlightRenderer`: overcast baseline → sunny series → HDR compositing (`pcomb`) → TIFF. CPU (`rpict`) or GPU (`accelerad_rpict`).
   - `DaylightRenderer`: `rtpict` (Linux only), falsecolor post-processing, contour overlays.
6. **Post-processing** (`post/`): `Hdr2Wpd` extracts illuminance via AOI masks. `Tiff2Animation` stamps metadata, creates GIF/APNG.
7. **Reporting**: `Wpd2Xlsx` generates Excel reports with compliance metrics.
8. **Workflows** (`workflows/`): `IESVEDaylightWorkflow`, `SunlightAccessWorkflow` — high-level orchestrators; use these, not the pipeline classes directly.

**Key modules:**

- `config.py`: Path management, tool resolution, `RAYPATH`, `WORKERS`. Override via `RADIANCE_ROOT`/`ACCELERAD_ROOT`.
- `utils.py`: `execute_new_radiance_commands` (parallel), `smart_cleanup()`, geometry helpers, HDR utilities.
- `project.py`: Project-level config/state.
- `apps/matplotlib_app.py`: Main matplotlib HDR+AOI editor entry point.
- `apps/obj_aoi_editor_matplotlib.py`: OBJ AOI editor.
- `apps/project_config.py`: Project config UI.
- `apps/reflex_editor/`: Reflex-based web editor (WIP).
- `GCPVMManager` (`infra/`): GCP VM lifecycle. Config at `~/.archilume_gcp_config.json`. SSH `User` must match VM's provisioned username — never assume or change it.

## Launching the Reflex App

Use the launcher — it reuses an already-running dev server or launches one:

```bash
# Reuse if running, launch if not (fast path for Claude sessions):
python examples/launch_archilume_ui.py --ensure

# Force a fresh restart (kills stale backends):
python examples/launch_archilume_ui.py
```

`--ensure` checks `:3000` first — exits instantly if already serving. Otherwise kills stale backends, launches, and polls until ready (no blind sleep).

Playwright uses its own sandboxed Chromium — not the user's browser.

## Playwright "Browser Already In Use" Fix

`Error: Browser is already in use for ...mcp-chrome-...` = stale session lock. Auto-recover — do NOT ask the user:

1. `browser_close` (will fail — expected, ignore).
2. `sleep 2`.
3. `browser_navigate` again — MCP server re-initialises on retry.

If step 3 still fails: tell user to run **Reload Window** (`Ctrl+Shift+P` → "Reload Window"). Do NOT tell them to restart VS Code.

## Post-Edit UI Verification

After any `archilume_ui` change, use **tiered verification** — match effort to the type of change:

### Tier 1 — Text, spacing, logic, state changes

1. `browser_navigate` → `http://localhost:3000`.
2. `browser_snapshot` → verify DOM structure and text content.
3. `browser_console_messages` → check JS errors.
4. **No screenshots** unless snapshot reveals something unexpected.

### Tier 2 — Visual changes (colors, fonts, shadows, borders)

1. `browser_navigate` → `http://localhost:3000`.
2. `browser_snapshot` → get element refs.
3. **One screenshot** → compare against intent.
4. Fix if needed → **one more screenshot** only if changes were made.
5. `browser_console_messages` → check JS errors.

### Tier 3 — Layout, new components, major redesigns

1. `browser_navigate` → `http://localhost:3000`.
2. `browser_snapshot` → get element refs.
3. Interact with changed elements. Screenshot after each action.
4. Compare: spacing, font sizes, colors, alignment, border-radius, shadows, interactive states.
5. `browser_console_messages` → check JS errors.
6. Minimum 2 rounds: screenshot → compare → fix → repeat. Stop only when diff is clean.

### Cleanup — always do last

Call `browser_close` at the end of every verification session to prevent stale MCP locks in the next conversation.

Screenshots → `C:/Users/VincentLogarzo/AppData/Local/Temp/playwright-mcp`. Never write to repo.

**Gotchas:**

- `browser_evaluate`: always arrow functions `() => { ... }`. No top-level `var`/`const`/`let`.
- Reflex SVG fill: `window.getComputedStyle(el).fill` — not `el.getAttribute('fill')` (always `null`).

## Reflex UI — Always Do First

Before writing any Reflex UI code, every session, no exceptions: **invoke the `frontend-design` skill**.

**Then**: search `.claude/skills/reflex-docs/reference/` for the relevant Reflex component or pattern (`grep -ri "<topic>"` on that directory). Read matched files and follow documented patterns — do not invent workarounds when docs exist. If no match, state that explicitly before proceeding.

**If a reference image is provided:** match layout, spacing, typography, and color exactly. Use placeholder content where needed (`https://placehold.co/`). Do not improve or add to the design — just match it.

**If no reference image:** design from scratch using the standards below.

## Reflex UI Design Standards

Target audience: architects and engineers. UI must feel precise and professional.

- **Colors**: No default Tailwind palette (indigo-500 etc.). Derive a custom palette. Use radial gradients for depth; SVG noise for texture.
- **Typography**: Never the same font for headings and body. Pair display/serif + clean sans. Headings: tight tracking (`-0.03em`). Body: generous line-height (`1.7`).
- **Shadows & Depth**: Layered, color-tinted shadows (low opacity). Clear z-plane system: base → elevated → floating.
- **Animations**: Only `transform` and `opacity`. Never `transition-all`. Spring-style easing.
- **Interactive States**: Every clickable element needs hover, focus-visible, and active states — no exceptions.
- **Images**: Gradient overlay (`from-black/60`) + `mix-blend-multiply` color treatment layer.
- **Spacing**: Consistent tokens — not arbitrary Tailwind steps.

## Coding Conventions

- **Imports**: All at top of module — never inside functions. Check before adding. `from tkinter import Tk` does not cover `tk.Toplevel` — add `import tkinter as tk` separately.
- **Rendering**: Use `SunlightRenderer`/`DaylightRenderer` — don't call Radiance binaries directly.
- **Parallelism**: `utils.execute_new_radiance_commands`. Respect `config.WORKERS`.
- **Cleanup**: `utils.smart_cleanup()` before re-runs. Verify HDR outputs in `outputs/image/` before post-processing.
- **Units**: SI only — metres, millimetres, lux. Never imperial.

## Project Root Hygiene

**Never create files or directories in the project root (`c:/Projects/archilume/`) without explicit approval.**

Before any edit or code generation that would:

- Create a new file or directory at the project root level
- Output files to the project root (e.g. generated reports, logs, temp files, configs)
- Add code that writes to `Path(".")`, `Path(__file__).parent` when that resolves to root, or any unqualified relative path

**Stop. Notify the user.** Explain what would land in root and why, then ask where it should go instead. Do not proceed until redirected.

This applies to both direct file creation (Write/Edit tool) and code that would produce runtime output at root.

## Workflow & Git

- **Before code changes**: Briefly explain approach, get confirmation. Do not edit until agreed.
- **Renaming**: Only rename exactly what the user requests — no related files or suffixes.
- **Commits/pushes**: Only when explicitly instructed.
- **Pre-commit scan**: Check for API keys, tokens, private keys, `.pem`/`.key`/`.p12`, GCP/AWS credential JSONs, `.env` files, internal IPs. Stop and alert if found.
