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

```bash
python examples/launch_archilume_ui.py --ensure   # reuse if running, launch if not
python examples/launch_archilume_ui.py             # force fresh restart
```

## Playwright

- "Browser already in use" → `browser_close` (ignore failure) → `sleep 2` → `browser_navigate` again. If still fails: user runs **Reload Window** (`Ctrl+Shift+P`).
- `browser_evaluate`: always arrow functions `() => { ... }`. No top-level `var`/`const`/`let`.
- Reflex SVG fill: use `getComputedStyle(el).fill`, not `getAttribute('fill')`.
- Always `browser_close` at end of any Playwright session.
- Screenshots → `C:/Users/VincentLogarzo/AppData/Local/Temp/playwright-mcp`. Never write to repo.
- Test project: **`527DP-gcloud-lowRes-GregW`**.

## Code Review Graph

Structural knowledge graph of the codebase available via MCP (`code-review-graph`).

**Usage rules (token-efficient):**

1. First call: `build_or_update_graph_tool` — builds or incrementally updates the graph.
2. For context: `get_review_context_tool` — token-optimised structural summary.
3. For impact: `get_impact_radius_tool` — blast radius of changed files.
4. For queries: `query_graph_tool` — callers, callees, tests, imports for a target.
5. For search: `semantic_search_nodes_tool` — find code entities by name or meaning.
6. Prefer `detail_level="minimal"` unless more detail is needed.
7. Follow `next_tool_suggestions` in each response for the optimal next step.
8. Target: ≤5 tool calls per task, ≤800 total tokens of graph context.

**When to use:** Code review, understanding call chains, assessing change impact,
architecture questions, onboarding to unfamiliar modules. Skip for simple
single-file edits where the change is self-contained.

**Local storage:** `.code-review-graph/` (gitignored). Built/updated automatically
via `build_or_update_graph_tool` — no manual CLI step needed.

## Reflex UI

Before writing any Reflex UI code: **invoke the `frontend-design` skill**, then search `.claude/skills/reflex-docs/reference/` for relevant patterns. Follow documented patterns — do not invent workarounds when docs exist.

Design standards for this project are in `.claude/skills/reflex-docs/design-standards.md`. Read that file before any UI work.

## Coding Conventions

- **Imports**: All at top of module — never inside functions. Check before adding. `from tkinter import Tk` does not cover `tk.Toplevel` — add `import tkinter as tk` separately.
- **Rendering**: Use `SunlightRenderer`/`DaylightRenderer` — don't call Radiance binaries directly.
- **Parallelism**: `utils.execute_new_radiance_commands`. Respect `config.WORKERS`.
- **Cleanup**: `utils.smart_cleanup()` before re-runs. Verify HDR outputs in `outputs/image/` before post-processing.
- **Units**: SI only — metres, millimetres, lux. Never imperial.

## Code Changes

- When editing TypedDict or dataclass definitions, always update **ALL** locations where that type is constructed or referenced. After adding a field to a TypedDict, grep for every place that type is instantiated and add the new field there too.
- After making multi-file edits, do a final pass to check for: (1) duplicate/leftover imports, (2) accidentally deleted functions, (3) dead code from previous approaches. Run a quick grep for any function names you touched.

## Tech Stack

- This is a **Reflex** (Python web framework) application. Before using any `rx.el.*` component, verify it exists in the project's installed Reflex version by checking imports or docs. Do not assume React-like sub-components (e.g., `rx.el.tspan`) exist.

## Testing & Verification

- Do **NOT** use Playwright for visual verification during iterative debugging loops. Instead, describe what you changed and let the user verify visually. Only use Playwright for automated testing when explicitly asked.

## Session Management

- When a session is running low on context or usage, stop attempting new fixes and instead write a clear handoff summary to `.claude/handoff.md`: what was tried, what the root cause is, and what the next session should do.

## Domain-Specific Notes

- For overlay/positioning/zoom bugs: always check whether values are stored as pixels vs. percentages/fractions, and whether transforms are applied in the right coordinate space. Draw out the transform chain before coding a fix.

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
