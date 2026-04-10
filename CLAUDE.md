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
uv sync                                          # install dependencies
pytest                                           # run all tests
python examples/sunlight_access_workflow.py      # example workflow
python examples/launch_archilume_ui.py           # launch Reflex UI
cd archilume/apps/archilume_ui && uv run reflex run  # direct Reflex launch
```

## Architecture

**Pipeline:** Geometry → Octree → Sky + Views → Rendering → Post-Processing → Reports

1. **Geometry** (`objs2octree.py`): OBJ/MTL → Radiance RAD → octree via `obj2rad`/`oconv`. `MtlConverter` handles MTL → Radiance materials.
2. **Sky** (`sky_generator.py`): Time-series sunny skies (sunlight access) or CIE overcast (daylight factor) via `gensky`.
3. **Views/AOI** (`view_generator.py`): Parses room boundaries CSV, generates orthographic plan views (.vp) and AOI boundary files.
4. **Rendering** (`rendering_pipelines.py`):
   - `SunlightRenderer`: overcast baseline → sunny series → HDR compositing (`pcomb`) → TIFF. CPU (`rpict`) or GPU (`accelerad_rpict`).
   - `DaylightRenderer`: `rtpict` (Linux only), falsecolor post-processing, contour overlays.
5. **Post-processing**: `Hdr2Wpd` extracts illuminance via AOI masks. `Tiff2Animation` stamps metadata, creates GIF/APNG.
6. **Reporting**: `Wpd2Xlsx` generates Excel reports with compliance metrics.

**Key modules:**

- `config.py`: Path management, tool resolution, `RAYPATH`, `WORKERS`. Override via `RADIANCE_ROOT`/`ACCELERAD_ROOT`.
- `utils.py`: `execute_new_radiance_commands` (parallel), `smart_cleanup()`, geometry helpers, HDR utilities.
- `GCPVMManager`: GCP VM lifecycle. Config at `~/.archilume_gcp_config.json`. SSH `User` field must match VM's provisioned username — do not assume or change it.

## Launching the Reflex App

Always launch via the launcher script — do not ask the user to do it, do not use `uv run reflex run` directly:

```bash
cd c:/Projects/archilume && python examples/launch_archilume_ui.py &
```

The launcher handles stale backend cleanup automatically before starting Reflex.

Poll until ready (repeat until `200`):

```bash
sleep 15 && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Playwright uses its own sandboxed Chromium — not the user's browser.

## Playwright "Browser Already In Use" Fix

When `browser_navigate` or `browser_close` returns `Error: Browser is already in use for ...mcp-chrome-...`, the Playwright MCP server has a stale session lock from a prior conversation.

**Execute this recovery sequence automatically — do NOT ask the user to do any of these steps:**

1. Call `browser_close` (it will also fail — that's expected, ignore the error).
2. Run `sleep 2` via Bash.
3. Call `browser_navigate` again. The MCP server re-initialises on the second attempt.

Only if step 3 still fails: ask the user to run **Reload Window** (`Ctrl+Shift+P` → "Reload Window") in VS Code. This restarts all extension processes including the Playwright MCP server without closing VS Code.

**Do NOT tell the user to restart VS Code.** Reload Window is enough and is non-disruptive.

## Post-Edit UI Verification

After modifying `archilume_ui`, use Playwright MCP to **functionally test** changes.

1. Start the Reflex app if not running (see above).
2. `browser_navigate` to `http://localhost:3000` — always call this, do not pre-check.
3. `browser_snapshot` first to get element refs — never guess selectors.
4. Interact with changed elements (click, fill, hover, key press).
5. Screenshot after each interaction. Compare specifically: spacing, font sizes, exact colors, alignment, border-radius, shadows, interactive states.
6. `browser_console_messages` — check for JS errors.
7. **Minimum 2 comparison rounds** — screenshot → compare → fix → repeat. Stop only when no visible differences remain.
8. Screenshots are written to `C:/Users/VincentLogarzo/AppData/Local/Temp/playwright-mcp` — never to the repo.

**Key tools:** `browser_snapshot`, `browser_click`, `browser_fill_form`, `browser_press_key`, `browser_select_option`, `browser_hover`, `browser_take_screenshot`, `browser_console_messages`.

**`browser_evaluate` syntax:** Always arrow functions — `() => { ... }`. No top-level `var`/`const`/`let`.

**Reflex SVG styles:** Use `window.getComputedStyle(element).fill` — not `element.getAttribute('fill')` (always returns `null`).

## Reflex UI — Always Do First

Before writing any Reflex UI code, every session, no exceptions: **invoke the `frontend-design` skill**.

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

## Workflow & Git

- **Before code changes**: Briefly explain approach, get confirmation. Do not edit until agreed.
- **Renaming**: Only rename exactly what the user requests — no related files or suffixes.
- **Commits/pushes**: Only when explicitly instructed.
- **Pre-commit scan**: Check for API keys, tokens, private keys, `.pem`/`.key`/`.p12`, GCP/AWS credential JSONs, `.env` files, internal IPs. Stop and alert if found.
