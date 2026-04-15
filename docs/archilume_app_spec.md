# Archilume App — Technical Specification
**Version**: 1.0 — 2026-04-02
**App**: `archilume/apps/archilume_app/`
**Framework**: Reflex 0.8.28.post1
**Purpose**: Web-based HDR Daylight Factor Editor — room polygon drawing, DF% analysis, PDF overlay, export

---

## 1. Overview

`archilume_app` is a Reflex single-page application that replaces the matplotlib `HdrAoiEditor`. It allows users to open an Archilume project, view tone-mapped HDR daylight simulation images, draw room boundary polygons (AOIs), compute Daylight Factor statistics per room, and export Excel reports with archive ZIPs.

The app runs locally at `http://localhost:3000` via `reflex run` from `archilume/apps/archilume_app/`.

---

## 2. Global Layout

```
┌───────────────────────────────────────────────────────────────────────┐
│  Header (40px)   — logo · mode badges · multi-select counter          │
├──┬──────────────────────────────────────────┬───────────────────────  │
│  │                                          │                         │
│S │  Viewport                                │  Right Panel (260px)    │
│i │  ├─ Top Toolbar (32px)                   │  ├─ Parent Apt          │
│d │  │    HDR nav · filename · variant ·     │  ├─ Room Name + Type    │
│e │  │    Undo · Fit · Select All            │  ├─ Save / Delete       │
│b │  │                                       │  ├─ Status bar          │
│a │  └─ Canvas Area (fills remaining)        │  └─ DF% legend          │
│r │       rx.image (base64 PNG)              │                         │
│  │       rx.el.svg (absolutely positioned)  │                         │
│5 │         ├─ Room polygons                 │                         │
│2 │         ├─ Vertex handles (edit mode)    │                         │
│p │         ├─ Drawing preview               │                         │
│x │         ├─ Snap ring                     │                         │
│  │         ├─ Divider polyline              │                         │
│  │         ├─ DF% stamps                    │                         │
│  │         └─ PDF overlay image             │                         │
│  │                                          │                         │
│  ├─ Project Tree (collapsible, 220px)        │                         │
│  │   HDR files → rooms                      │                         │
├──┴──────────────────────────────────────────┴─────────────────────── │
│  Bottom Row (88px) — Validation · Simulation · Floor Plan Controls    │
└───────────────────────────────────────────────────────────────────────┘
```

### 2.1 Layout Files

| Region | File | Size |
|--------|------|------|
| Root composition | `archilume_app/archilume_app.py` | 73 lines |
| Header | `components/header.py` | 63 lines |
| Sidebar | `components/sidebar.py` | 92 lines |
| Viewport | `components/viewport.py` | 590 lines |
| Project tree | `components/project_tree.py` | 101 lines |
| Right panel | `components/right_panel.py` | 130 lines |
| Bottom row | `components/bottom_row.py` | 91 lines |
| Modals | `components/modals.py` | 203 lines |

---

## 3. Sidebar (52px icon bar)

Fixed left column. Buttons are `48×38px` with tooltip on hover (side="right"). Active state renders with `sidebar_act` background and `accent` colour.

| Icon | Tooltip | Handler |
|------|---------|---------|
| `menu` | Toggle Project Browser | `toggle_project_tree` |
| `folder-open` | Open Project | `open_open_project_modal` |
| `folder-plus` | Create New Project | `open_create_project_modal` |
| — divider — | | |
| `archive-restore` | Extract Archive | `open_extract_modal` |
| `file-bar-chart` | Export & Archive | `run_export` |
| — divider — | | |
| `layout-panel-top` | Floor Plan | `toggle_overlay` |
| `refresh-cw` | Change Floor Plan Page | `cycle_overlay_page` |
| `maximize` | Resize Plan Mode | `toggle_overlay_align` |
| — divider — | | |
| `layers` | Toggle Image Layers [T] | `toggle_image_variant` |
| `zoom-in` | Reset Zoom [R] | `reset_zoom` |
| — divider — | | |
| `crosshair` | DF% Placement [P] | `toggle_df_placement` |
| `pen-line` | Edit Mode [E] | `toggle_edit_mode` |
| `corner-down-right` | Ortho [O] | `toggle_ortho` |
| — divider — | | |
| Annotation slider | Aa label + vertical slider | `set_annotation_scale` |
| — spacer — | | |
| `clock-3` | History | (stub) |
| `settings-2` | Settings | (stub) |

---

## 4. Header

40px top bar. Left: Archilume logo + "HDR AOI Editor" title. Centre: mode badges (DRAW / EDIT / DIVIDER / DF% — shown conditionally). Multi-select counter badge. Right: Shortcuts button → opens shortcuts modal.

Mode badges use `rx.cond` to render only the active badge, styled with coloured background from design tokens.

---

## 5. State Architecture

All state lives in **one class**: `EditorState(rx.State)` in `state/editor_state.py`.

### 5.1 Rationale for Single State

Reflex substates that inherit from a parent state cannot cleanly share mutable vars or override event handlers. The original multi-substate design caused import chain errors and delegation failures. The single-class design mirrors the matplotlib editor's architecture.

### 5.2 State Sections

#### §1 — Project
```python
project: str                   # Current project name
available_projects: list[str]  # Scanned from projects/ dir
project_mode: str              # "archilume" | "hdr" | "iesve"
session_path: str              # Full path to aoi_session.json
new_project_name: str          # Create form
new_project_mode: str          # Create form
create_error: str              # Validation message
```

#### §2 — Image Navigation
```python
hdr_files: list[dict]          # [{name, hdr_path, tiff_paths, ...}, ...]
current_hdr_idx: int           # Index into hdr_files
image_variants: list[str]      # Base64 strings for current HDR variants
current_variant_idx: int       # Which variant is displayed
current_image_b64: str         # Active variant base64 data URI
image_width: int               # Pixels
image_height: int              # Pixels
```

#### §3 — Rooms
```python
rooms: list[dict]              # All rooms across all HDR files
selected_room_idx: int         # -1 = none
multi_selected_idxs: list[int] # Ctrl+click accumulator
selected_parent: str           # Populates parent field in right panel
room_name_input: str           # Right panel text input
room_type_input: str           # "BED" | "LIVING" | "NON-RESI" | "CIRC"
```

#### §4 — Interaction Modes
```python
draw_mode: bool                # D key — click to place vertices
edit_mode: bool                # E key — drag vertex handles
divider_mode: bool             # DD — split room by polyline
df_placement_mode: bool        # P key — click to stamp DF% value
ortho_mode: bool               # O key — constrain to H/V
```

Modes are mutually exclusive; `_clear_modes()` resets all before entering a new mode.

#### §5 — Drawing Buffer
```python
draw_vertices: list[dict]      # [{x, y}, ...] vertices in progress
snap_point: dict               # {x, y} if snap active, else {}
preview_point: dict            # {x, y} current mouse position for preview line
```

#### §6 — Editing
```python
dragging_vertex_idx: int       # -1 = not dragging
hover_vertex_idx: int          # -1 = none
hover_edge_idx: int            # -1 = none (gap — not yet rendered)
edit_undo_stack: list[dict]    # Up to 50 vertex snapshots
draw_undo_stack: list[dict]    # Draw mode vertex history
```

#### §7 — Divider
```python
divider_points: list[dict]     # [{x, y}, ...] divider polyline
divider_room_idx: int          # Which room is being split
```

#### §8 — PDF Overlay
```python
overlay_visible: bool
overlay_image_b64: str         # Rasterized PDF page as base64 PNG
overlay_pdf_path: str
overlay_page_idx: int
overlay_page_count: int
overlay_dpi: int               # 72 | 100 | 150 | 200 | 300
overlay_alpha: float           # 0.0–1.0
overlay_align_mode: bool       # Arrow keys nudge overlay
overlay_transforms: dict       # {hdr_name: {x, y, scale, rotation}}
align_points: list[dict]       # Two-point alignment point pairs
```

#### §9 — DF% Analysis
```python
df_images: dict                # {hdr_name: np.ndarray} (not serialised)
df_stamps: list[dict]          # [{x, y, value, hdr_file}, ...]
df_visible: bool               # Show/hide annotations
```

#### §10 — Export
```python
export_progress: int           # 0–100
export_message: str
export_zip_path: str           # Result path shown in toast
archives: list[str]            # Available .zip files
```

#### §11 — UI Chrome
```python
project_tree_open: bool
shortcuts_modal_open: bool
open_project_modal_open: bool
create_project_modal_open: bool
extract_modal_open: bool
accelerad_modal_open: bool
status_message: str
status_colour: str             # "success" | "warning" | "danger" | "accent2"
```

#### §12 — Canvas / Zoom
```python
zoom_level: float              # Default 1.0
pan_x: float                   # CSS translate X (px)
pan_y: float                   # CSS translate Y (px)
annotation_scale: float        # 0.5–2.0 via sidebar slider
```

### 5.3 Key Computed Vars

| Var | Description |
|-----|-------------|
| `current_hdr_name` | Filename of current HDR |
| `current_hdr_count` | "3 / 12" navigation counter |
| `current_variant_label` | "HDR" / "FC" / "CTR" badge text |
| `rooms_for_current_hdr` | Filtered rooms for current HDR file |
| `enriched_rooms` | Rooms + `points_str` + `label_x/y` + colour + DF status fields |
| `draw_points_str` | SVG points string for drawing preview polygon |
| `divider_points_str` | SVG points string for divider polyline |
| `canvas_transform` | `scale(z) translate(px, py)` CSS string |
| `overlay_css_transform` | `translate(x, y) scale(s) rotate(r)` for overlay image |
| `resolved_room_name` | `parent_name + "/" + room_name_input` or just `room_name_input` |

---

## 6. Canvas System

### 6.1 Structure

```python
rx.box(                         # Viewport container — fills available area
    rx.image(src=CanvasState.current_image_b64, width="100%"),
    rx.el.svg(
        # Room polygons, labels, handles rendered here
        width="100%", height="100%",
        style={"position": "absolute", "top": 0, "left": 0},
        on_click=EditorState.handle_canvas_click,
        on_mouse_move=EditorState.handle_mouse_move,
        on_mouse_down=EditorState.handle_mouse_down,
        on_mouse_up=EditorState.handle_mouse_up,
    ),
    style={
        "position": "relative", "overflow": "hidden",
        "transform": EditorState.canvas_transform,
        "transform_origin": "top left",
    },
)
```

### 6.2 Coordinate Conversion

Mouse events from `PointerEventInfo` return page coordinates. A JS bridge converts them to SVG canvas space:

```javascript
function getSvgCoords(e, svgId) {
    const svg = document.getElementById(svgId);
    const rect = svg.getBoundingClientRect();
    const zoom = parseFloat(svg.closest('.canvas-wrapper').style.transform
        .match(/scale\(([\d.]+)\)/)[1]) || 1;
    return {
        x: (e.clientX - rect.left) / zoom,
        y: (e.clientY - rect.top) / zoom,
    };
}
```

Canvas coordinate `(cx, cy)` maps directly to image pixel `(cx, cy)` since `rx.image` fills the container at 100% width.

### 6.3 SVG Rendering Layers (z-order)

1. **Room polygons** — `rx.foreach(enriched_rooms, _render_room)` — filled semi-transparent polygons with stroke
2. **Room labels** — `rx.el.text()` at `(label_x, label_y)` per room
3. **DF annotations** — conditional `rx.el.text()` below labels
4. **DF stamps** — cyan circles + value text
5. **Drawing preview** — dashed polyline + circle at each vertex
6. **Snap ring** — yellow 10px circle at snap point (conditional)
7. **Divider polyline** — dashed magenta polyline (conditional)
8. **Edit handles** — white circles with teal stroke at each vertex of selected room
9. **PDF overlay image** — separate `rx.image` with CSS transform + opacity (inside canvas wrapper)

### 6.4 Room Polygon Colours

| State | Fill | Stroke |
|-------|------|--------|
| Normal | `rgba(90,100,114,0.12)` | `#9ba6b2` |
| Selected | `rgba(13,148,136,0.18)` | `#0d9488` |
| Multi-selected | `rgba(79,110,247,0.15)` | `#4f6ef7` |
| Draw preview | `rgba(13,148,136,0.08)` | `#0d9488` dashed |

### 6.5 Zoom and Pan

- **Scroll wheel**: `on_wheel` event → adjust `zoom_level` (clamped 0.1–10). Zoom origin fixed at cursor position using coordinate arithmetic.
- **Middle-mouse drag**: JS tracks `pointerdown` with `button === 1`, moves via `pointermove`, commits on `pointerup`.
- **CSS transform**: `scale({zoom}) translate({pan_x}px, {pan_y}px)` applied to canvas wrapper div.
- **Reset**: `R` key → `zoom_level=1.0`, `pan_x=0`, `pan_y=0`.
- **Fit**: `F` key → compute bounding box of selected room → set zoom and pan to centre it.

---

## 7. Interaction Modes

### 7.1 Draw Mode (D)

1. First click: records first vertex; runs point-in-polygon to auto-detect parent room, sets `selected_parent` and `room_name_input` prefix.
2. Each subsequent click: adds vertex to `draw_vertices`. If within 10px of first vertex (snap ring active), closes polygon.
3. Ortho: if `ortho_mode`, constrains each new point to horizontal or vertical from the last vertex (whichever requires less deviation).
4. Preview: throttled `on_mouse_move` updates `preview_point` → SVG `<polyline>` from last vertex to cursor.
5. **S key or close polygon**: calls `save_room()` → creates room dict → appends to `rooms` → saves session.

### 7.2 Edit Mode (E)

1. Renders white vertex circles for the selected room.
2. **Vertex drag**: `mousedown` on handle → set `dragging_vertex_idx` → `mousemove` updates vertex position live → `mouseup` commits + saves undo snapshot.
3. **Edge click**: `mousedown` near edge midpoint (not on vertex) → inserts two new vertices at click point → immediately starts drag.
4. **Vertex delete**: right-click on vertex (or Delete/Backspace key when `hover_vertex_idx >= 0`) → removes vertex if polygon would have ≥ 3 remaining.
5. **Undo**: `Ctrl+Z` → pops `edit_undo_stack` → restores vertex list.

### 7.3 Divider Mode (DD)

Double-tap D within 400ms. Targets `selected_room_idx` (stored as `divider_room_idx`).

1. Each click adds a point to `divider_points`.
2. Ortho-constrained if `ortho_mode`.
3. **S key**: finalizes divider:
   - `ray_polygon_intersection()` extends first and last segment to room boundary
   - `split_polygon_by_polyline()` walks perimeter, creates two new rooms with `_A` / `_B` suffixes
   - Original room replaced by the two children

### 7.4 DF% Placement Mode (P)

1. Click on canvas → `read_df_at_pixel()` on loaded DF image → append `{x, y, value, hdr_file}` to `df_stamps`.
2. Right-click → `_df_remove_nearest()` removes closest stamp within 20px.
3. Stamps render as cyan 5px circles with value label (2 decimal places, `%` suffix).

### 7.5 Overlay Alignment Mode

Activated by sidebar "Resize Plan Mode" button (`toggle_overlay_align`). While active:
- Arrow keys route to `nudge_overlay(dx, dy)` instead of HDR navigation
- `Ctrl+R` rotates overlay 90°
- Two-click alignment: first pair click sets `align_points[0]` on overlay, second pair click computes affine (translation + scale) between the two point pairs

---

## 8. Keyboard Shortcuts Reference

| Key | Action |
|-----|--------|
| D | Toggle Draw mode |
| DD | Enter Divider mode (400ms double-tap) |
| E | Toggle Edit mode |
| O | Toggle Ortho constraint |
| P | Toggle DF% placement |
| T | Cycle image variant (HDR / Falsecolor / Contour) |
| S | Save current polygon / confirm action |
| Shift+S | Force save session |
| R | Reset zoom |
| F | Fit zoom to selected room |
| Esc | Exit current mode / deselect |
| ↑ / ↓ | Navigate HDR files (or nudge overlay in align mode) |
| ← / → | Nudge overlay in align mode |
| Ctrl+Z | Undo (50-level) |
| Ctrl+A | Select all rooms |
| Ctrl+R | Rotate overlay 90° |
| Delete / Backspace | Delete hovered vertex (edit mode) |

Keyboard capture: global `keydown` listener injected via `rx.script`. Skips events when target is `INPUT`, `TEXTAREA`, or `SELECT`.

---

## 9. Session Persistence

Session file: `{project_dir}/inputs/aoi/{project_name}/aoi_session.json`

### 9.1 JSON Schema

```json
{
  "rooms": [
    {
      "name": "Apt01/BedA",
      "parent": "Apt01",
      "room_type": "BED",
      "hdr_file": "level_01.hdr",
      "vertices": [[120.5, 340.2], [280.0, 340.2], [280.0, 480.0], [120.5, 480.0]]
    }
  ],
  "df_stamps": [
    {"x": 200.0, "y": 400.0, "value": 1.25, "hdr_file": "level_01.hdr"}
  ],
  "overlay_transforms": {
    "level_01.hdr": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0}
  },
  "current_hdr_idx": 0,
  "version": "2"
}
```

### 9.2 Atomic Write

Session is written to a `.tmp` file and then renamed via `os.replace()`, preventing partial writes from corrupting the session.

Auto-save fires after every mutation that changes rooms, stamps, or overlay transforms.

---

## 10. Library Modules (`lib/`)

Pure Python — no Reflex imports. Used by `EditorState` via standard method calls.

### 10.1 `image_loader.py`

| Function | Description |
|----------|-------------|
| `load_image_as_base64(path)` | LRU cache (15 entries). Detects HDR or TIFF. Returns `data:image/png;base64,...` |
| `_load_hdr(path)` | Calls `pvalue -h -H -df` → float32 numpy. Falls back to manual RGBE parser. |
| `_tonemap(arr)` | 99th percentile normalization + gamma 2.2 → uint8 PIL image |
| `scan_hdr_files(image_dir)` | Returns list of `{name, hdr_path, tiff_paths}` dicts |
| `rasterize_pdf_page(pdf_path, page, dpi)` | PyMuPDF → PIL → base64 PNG |
| `get_image_dimensions(path)` | Returns `(width, height)` without full load |

### 10.2 `geometry.py`

| Function | Description |
|----------|-------------|
| `point_in_polygon(x, y, verts)` | Winding number algorithm |
| `polygon_centroid(verts)` | Shoelace formula → `(cx, cy)` |
| `polygon_label_point(verts)` | Tries centroid; falls back to grid search for concave polygons |
| `snap_to_vertex(x, y, all_rooms, threshold=10)` | Returns nearest vertex across all rooms within threshold, or None |
| `ortho_constrain(x, y, last_x, last_y)` | Returns point snapped to nearest H/V from last vertex |
| `find_nearest_edge(x, y, verts, threshold=8)` | Returns `(edge_idx, t)` or None |
| `ray_polygon_intersection(p1, p2, verts)` | Extends segment to polygon boundary |
| `split_polygon_by_polyline(verts, polyline)` | Returns two vertex lists |
| `make_unique_name(name, existing_names)` | Appends `_2`, `_3` etc. if collision |

### 10.3 `session_io.py`

`load_session(path)` → dict. `save_session(path, data)` → atomic write. `build_session_dict(state)` → extracts serializable fields from `EditorState`.

### 10.4 `df_analysis.py`

DF% thresholds: `BED=0.5%`, `LIVING=1.0%`, `NON-RESI=2.0%`, `CIRC=None`.

| Function | Description |
|----------|-------------|
| `compute_room_df(df_image, vertices, room_type)` | Polygon mask → mean/median/pct_above/pass_status |
| `load_df_image(hdr_path)` | HDR → luminance float32 array |
| `read_df_at_pixel(df_image, x, y)` | Single pixel value |

Pass status: `>= 100%` pixels above threshold → `"pass"`, `>= 50%` → `"marginal"`, else `"fail"`.

### 10.5 `export_pipeline.py`

`export_report(rooms, hdr_files, image_dir, output_dir, ...)` → runs three phases synchronously:
1. Overlay PNG per HDR (PIL draw polygons on tone-mapped image)
2. Excel report via `openpyxl` (`aoi_report_daylight.xlsx`)
3. ZIP archive of `output_dir` → `{project_name}_{timestamp}.zip`

---

## 11. Modals

| Modal | Trigger | Content |
|-------|---------|---------|
| Shortcuts | Header button | Two-column keyboard shortcut reference table |
| Open Project | Sidebar folder-open | Dropdown of scanned projects + Open button |
| Create Project | Sidebar folder-plus | Name input, mode dropdown, image dir path, PDF path, IESVE file (conditional) |
| Extract Archive | Sidebar archive-restore | Dropdown of .zip files + Extract button |
| AcceleradRT | Bottom row | Model selection, resolution, launch button |

---

## 12. Project Configuration

Project config stored at `projects/{name}/project.toml`:

```toml
[project]
name = "MyProject"
mode = "archilume"  # or "hdr" or "iesve"

[paths]
image_dir = "outputs/image"
pdf_path = "inputs/floor_plans/plan.pdf"
iesve_room_data = ""  # optional
```

Loaded via `archilume.apps.project_config.ProjectConfig`. Standard paths derived from `archilume.config` when not overridden.

---

## 13. Design Tokens

Defined in `styles.py`. All components reference these constants.

### Colours (`COLORS` dict)

| Key | Value | Used for |
|-----|-------|---------|
| `sidebar` | `#f5f6f7` | Sidebar + panels background |
| `panel_bg` | `#ffffff` | Right panel, modals |
| `panel_bdr` | `#e2e5e9` | All borders |
| `viewport` | `#f0f2f4` | Canvas background |
| `text_pri` | `#1a1f27` | Primary text |
| `text_sec` | `#5a6472` | Labels, secondary text |
| `text_dim` | `#9ba6b2` | Hints, counters |
| `accent` | `#0d9488` | Active states, teal highlight |
| `accent2` | `#4f6ef7` | Divider mode, secondary accent |
| `hover` | `#eef0f3` | Button hover background |
| `sidebar_act` | `#e8eaed` | Active sidebar button |
| `danger` | `#dc2626` | Delete, fail status |
| `warning` | `#d97706` | Marginal status |
| `success` | `#059669` | Pass status |

### Typography

- `FONT_HEAD`: `"Syne", sans-serif` — headings
- `FONT_MONO`: `"DM Mono", monospace` — code, labels, UI text
- Fonts loaded via Google Fonts (`GOOGLE_FONTS_URL`)

---

## 14. Launch Instructions

```bash
# From project root
cd archilume/apps/archilume_app

# First run — install dependencies
uv sync

# Launch development server
uv run reflex run

# Opens at http://localhost:3000
```

On first load, `init_on_load` fires: scans `projects/` directory. If exactly one project exists, it auto-opens. Otherwise, the Open Project or Create Project modal should be used.

---

## 15. Known Gaps vs. Matplotlib Editor

The following features from `HdrAoiEditor` (matplotlib) are not yet implemented. See `docs/archilume_app_gap_report.md` for full details and fix effort estimates.

| Gap | Severity | Effort |
|-----|----------|--------|
| Hierarchical project tree (expand/collapse) | Low | ~100 lines |
| Image prefetching (adjacent HDR preload) | Low | ~30 lines |
| Shift+click range select | Low | ~15 lines |
| Edge hover highlight in edit mode | Low | ~40 lines |
| Shift+drag edge translation | Low | ~50 lines |
| Arrow-key hold acceleration (overlay nudge) | Very Low | ~15 lines |
| Multi-line DF annotation colour per line | Low | ~40 lines |
| Right-click context menu | Very Low | ~40 lines |
| Clipboard image copy | Very Low | ~30 lines |
| IESVE AOI file import | Medium | ~80 lines |
| Non-blocking export (progress bar) | Low | ~40 lines when API available |

**Coverage**: 47 of 52 features implemented (90%). All critical paths functional.

---

## 16. File Tree

```
archilume/apps/archilume_app/
├── rxconfig.py                    # App config, Tailwind colours, SitemapPlugin
├── requirements.txt               # reflex, pillow, numpy, openpyxl, pymupdf
└── archilume_app/
    ├── __init__.py
    ├── archilume_app.py            # Page composition, app definition, keyboard script
    ├── styles.py                  # COLORS, FONT_MONO, FONT_HEAD, reusable style dicts
    ├── state/
    │   ├── __init__.py            # re-exports EditorState
    │   └── editor_state.py        # Single unified state (~1,552 lines)
    ├── components/
    │   ├── __init__.py
    │   ├── header.py              # Top bar, mode badges, multi-select counter
    │   ├── sidebar.py             # 52px icon bar, annotation slider
    │   ├── viewport.py            # Top toolbar + SVG canvas + all rendering
    │   ├── project_tree.py        # HDR/room tree panel
    │   ├── right_panel.py         # Property inspector, DF legend
    │   ├── bottom_row.py          # Validation, simulation, floor plan controls
    │   └── modals.py              # All dialogs
    └── lib/
        ├── __init__.py
        ├── image_loader.py        # HDR/TIFF → base64, LRU cache, PDF rasterize
        ├── geometry.py            # Snap, ortho, point-in-polygon, split, intersect
        ├── session_io.py          # JSON load/save (atomic write)
        ├── df_analysis.py         # DF% polygon stats, load HDR as luminance
        └── export_pipeline.py     # Excel + overlay PNGs + ZIP
```

---

*Specification generated from implemented code — `archilume_app` v1.0, 2026-04-02.*
*For feature gap details see `docs/archilume_app_gap_report.md`.*
*For matplotlib editor reference see `docs/matplotlib_editor_ui_spec.md`.*
