# Archilume HDR AOI Editor (Matplotlib) — UI Specification

> Complete specification of the matplotlib/tkinter-based room boundary editor (`matplotlib_app.py`, ~9,580 lines). Sufficient detail to recreate the UI in Reflex or any other framework.

---

## 1. Window & Global Layout

**Framework**: matplotlib figure embedded in a tkinter window via `FigureCanvasTkAgg`.

- **Initial figure size**: `(8, 5)` — intentionally small because the window is immediately maximised via `manager.window.state('zoomed')`.
- **Window title**: `"Archilume – HDR AOI Editor"`
- **DPI**: System default
- **Background**: `#f5f6f7` (light grey)

### Layout Regions (matplotlib figure coordinates)

All positioning uses matplotlib's normalised figure coordinates `(0,0)` = bottom-left, `(1,1)` = top-right.

```
┌────┬─────────────┬─────────────────────────────────────┬─────────┐
│LEFT│ INSTRUCTIONS│            CANVAS                   │  RIGHT  │
│SIDE│ PANEL       │     (0.16, 0.21) to (0.99, 0.93)    │  SIDE-  │
│BAR │ (top-left)  │                                     │  BAR    │
│    │             │                                     │ (tree)  │
│0.03│             │                                     │  0.12w  │
│wide│  INPUT      │                                     │         │
│    │  PANELS     │                                     │         │
│    │  (left col) │                                     │         │
│    │             ├─────────────────────────────────────┤         │
│    │             │         BOTTOM BAR (y=0.93+)        │         │
└────┴─────────────┴─────────────────────────────────────┴─────────┘
```

| Region | X | Y | Width | Height | Purpose |
|--------|---|---|-------|--------|---------|
| Left sidebar | 0.001 | varies | 0.030 | full height | Icon buttons |
| Instructions panel | 0.035 | ~0.02 | ~0.12 | ~0.18 | Keyboard shortcut reference |
| Input panels | 0.035 | ~0.22 | ~0.12 | varies | HDR nav, parent, name, type, save/delete |
| Canvas (main axes) | 0.16 | 0.21 | 0.83 | 0.72 | Image + room boundaries |
| Right sidebar | 0.030 | varies | 0.12 | varies | Room tree browser |
| Bottom bar | 0.16 | 0.93 | ~0.83 | ~0.06 | PDF controls, AOI level, progress |

---

## 2. Design Tokens

### 2.1 Colours

| Token | Hex | Usage |
|-------|-----|-------|
| Background | `#f5f6f7` | Figure background, sidebar |
| Panel bg | `#ffffff` | Input panel cards |
| Border | `#e2e5e9` | Panel borders, dividers |
| Canvas bg | `#f0f2f4` | Canvas axes background |
| Text primary | `#1a1f27` | Labels, room names |
| Text secondary | `#5a6472` | Hints, inactive items |
| Text muted | `#9ba6b2` | Tertiary, disabled |
| Accent (teal) | `#0d9488` | Active toggles, draw mode highlights |
| Accent2 (indigo) | `#4f6ef7` | Status messages, badges |
| Hover | `#eef0f3` | Button hover state |
| Toggle ON bg | `#ccfbf1` | Active toggle button background |
| Danger | `#dc2626` | Delete, warnings |
| Warning | `#d97706` | Edit mode indicators |
| Success | `#059669` | Save button, DF pass |
| Selected room fill | `rgba(13,148,136,0.25)` | Selected room polygon fill |
| Unselected room fill | `rgba(100,116,139,0.15)` | Default room polygon fill |
| Room border (selected) | `#0d9488` | Teal, 2px |
| Room border (unselected) | `#64748b` | Slate, 1px |
| Divider preview | `#4f6ef7` dashed | Divider line preview |
| Edit vertex | `#0d9488` circles, 6px | Edit mode vertex handles |
| Snap highlight | `#facc15` (yellow) | Snap ring on nearby vertices |
| DF stamp dot | `#06b6d4` (cyan) | Stamped DF% reading marker |

### 2.2 Typography

| Usage | Font | Size | Weight |
|-------|------|------|--------|
| Logo | Syne | 17px | 700 |
| All body text | DM Mono | 9–11px | 400 |
| Panel titles | DM Mono | 10px | 500, uppercase, letter-spacing 0.08em |
| Section labels | DM Mono | 9px | 500, uppercase, letter-spacing 0.12em |
| Keyboard badges | DM Mono | 9px | 400 |
| Room labels (canvas) | monospace | zoom-scaled, base ~8pt × annotation_scale | 400 |
| DF% annotations | monospace | zoom-scaled, base ~7pt × annotation_scale | 400 |

---

## 3. Left Sidebar

Vertical strip, 0.030 figure-width, left edge. Contains stacked icon buttons with 0.036 vertical step.

### Button Construction

Each button:
- Axes: 0.030 × 0.030 (square)
- Rounded rectangle background (4px corner radius via Bézier paths)
- Shadow effect (offset grey rect behind)
- Hover: background shifts to `#eef0f3`
- Active: background = `#ccfbf1`, icon colour = `#0d9488`
- Tooltip on hover (positioned right of button)

### Buttons (top to bottom)

| # | Icon | ID/Method | Tooltip | Shortcut | Default |
|---|------|-----------|---------|----------|---------|
| 1 | Hamburger (3 lines) | `_on_menu_toggle` | "Toggle Project Browser" | — | OFF |
| 2 | Folder | `_on_project_click` | "Open / Create Project" | — | — |
| — | *divider* | | | | |
| 3 | Extract/unzip | `_on_extract_click` | "Extract Archive" | — | — |
| 4 | Export/download | `_on_export_report` | "Export & Archive" | — | — |
| — | *divider* | | | | |
| 5 | Floor plan | `_on_overlay_toggle` | "Floor Plan: OFF" | — | OFF |
| 6 | Cycle arrow | `_on_overlay_page_cycle` | "Change Floor Plan Page" | — | — |
| 7 | Resize arrows | `_on_overlay_align_toggle` | "Resize Plan Mode: OFF" | — | OFF |
| — | *divider* | | | | |
| 8 | Layers | `_on_image_toggle_click` | "Toggle Image Layers" | T | — |
| 9 | Zoom-fit | `_on_reset_zoom_click` | "Reset Zoom" | R | — |
| — | *divider* | | | | |
| 10 | Crosshairs | `_on_placement_toggle` | "DF% Placement: OFF" | P | OFF |
| 11 | Pencil/edit | `_on_edit_mode_toggle` | "Boundary Edit Mode: OFF" | E | OFF |
| 12 | Ortho grid | `_on_ortho_toggle` | "Ortho Lines: ON" | O | ON |
| — | *divider* | | | | |
| 13 | Annotation scale slider | `_on_annotation_scale_change` | — | — | 1.0 |
| — | *spacer to bottom* | | | | |
| 14 | Restart | `_on_restart_click` | "Restart Editor" | — | — |
| 15 | DPI presets | `_on_overlay_dpi_click` | "PDF Resolution" | — | 150 |

### Annotation Scale Slider

Vertical slider, range 0.5–2.0, step 0.05, default 1.0. Label "Aa" above. Controls font size multiplier for all room labels and DF annotations on canvas.

### Icon Rendering

All icons are drawn programmatically using matplotlib path primitives (lines, arcs, Bézier curves) — not image assets. Each icon is ~14×14 virtual units rendered into the button's axes. Methods: `_draw_menu_icon`, `_draw_icon_image`, `_draw_layer_icon`, `_draw_export_icon`, `_draw_extract_icon`, `_draw_edit_icon`, `_draw_ortho_icon`, `_draw_save_icon`, `_draw_delete_icon`, `_draw_reset_icon`, `_draw_floorplan_icon`, `_draw_cycle_icon`, `_draw_zoom_fit_icon`, `_draw_resize_icon`, `_draw_restart_icon`, `_draw_crosshairs_icon`.

---

## 4. Instructions Panel (Top-Left)

Positioned above the input panels, shows a compact keyboard shortcut reference. Always visible.

Content (two-column: key → description):

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate HDR files |
| T | Toggle image variant |
| D | Toggle draw mode |
| DD | Room divider mode |
| E | Toggle edit mode |
| O | Toggle ortho lines |
| P | DF% placement mode |
| S | Save room |
| F | Fit zoom to room |
| R | Reset zoom |
| Ctrl+Z | Undo |
| Ctrl+A | Select all rooms |
| Ctrl+R | Rotate overlay 90° |
| Shift+S | Force save session |
| Esc | Exit mode / deselect |
| Q | Quit |

---

## 5. Input Panels (Left Column)

Below the instructions panel, stacked vertically. Each panel is a card with title bar and content area.

### 5.1 HDR Navigation

- **Prev/Next buttons**: `◀` / `▶` arrows flanking a filename label
- **Filename display**: Current HDR stem (e.g. `level_01_north`)
- **Index display**: "1 / 4" format
- **Variant badge**: Shows current layer type — "HDR", "TIFF (falsecolor)", "TIFF (contour)", etc. Clickable to cycle.

### 5.2 Parent Apartment

- **Cycle button**: Cycles through parent options (apartment-level rooms on current HDR)
- **Display**: Shows current parent name or "(None)"
- Auto-detection: When first vertex is placed in draw mode, auto-selects parent if click falls inside an existing parent polygon.

### 5.3 Room Name

- **TextBox** (matplotlib TextBox widget): Editable text input
- Placeholder hint: "e.g. BED1"
- **Preview label** below: Shows resolved full name "→ U101_BED1" (parent prefix + typed name)
- Debounced update on text change

### 5.4 Room Type

Four toggle buttons in a row:

| Button | Label | Default |
|--------|-------|---------|
| 1 | BED | Active (default type) |
| 2 | LIVING | — |
| 3 | NON-RESI | — |
| 4 | CIRC | — |

- Mutually exclusive selection
- Active: teal bg (`#ccfbf1`), teal border, teal text
- Inactive: `#f0f2f4` bg, grey border, grey text
- Multi-select: applies type to all selected rooms

### 5.5 Action Buttons

Three icon buttons beside the room type row:

| Icon | Action | Shortcut | Colour |
|------|--------|----------|--------|
| Floppy disk | Save room | S | Green (`#d1fae5` bg) |
| Trash | Delete room | — | Red (`#fee2e2` bg) |
| Refresh | Reset session | — | Grey |

---

## 6. Canvas (Main Viewport)

Central axes occupying most of the figure. Displays the image with room boundary overlays.

### 6.1 Image Display

- Rendered via `ax.imshow()` with `extent=[0, width, height, 0]` (origin top-left)
- Image types: HDR (tone-mapped), false-colour TIFF, contour TIFF
- Toggle between variants with T key
- Zoom: scroll wheel centred on cursor position
- Pan: middle-mouse-button drag (or space+drag)

### 6.2 Room Polygon Rendering

Each room rendered as:

1. **Polygon patch** (`matplotlib.patches.Polygon`):
   - Fill: semi-transparent (selected = teal 25%, unselected = slate 15%)
   - Border: selected = teal 2px, unselected = slate 1px
   - Line width scales with zoom via `_zoom_linewidth()`

2. **Label** (`ax.text()`):
   - Position: centroid of polygon (corner-weighted pole logic via `_polygon_label_point()`)
   - Text: room name (e.g. "U101_BED1")
   - Font size: zoom-scaled × `_annotation_scale`
   - Background: semi-transparent white bbox
   - Colour: teal if selected, dark grey otherwise

3. **DF% annotation lines** (below label):
   - Multiple lines showing DF results: "DF avg: 1.2%", "Above 1.0%: 85%", etc.
   - Colour-coded: green (≥ threshold), amber (< threshold), red (< 50% of threshold)
   - Font size slightly smaller than room label

### 6.3 Drawing-in-Progress

When draw mode is active and vertices have been placed:
- **Scatter markers** at each placed vertex (teal dots)
- **Line segments** connecting vertices (teal solid line)
- **Preview line** from last vertex to cursor (teal dashed, ortho-constrained if enabled)
- **Snap ring**: yellow circle highlight when cursor is near an existing vertex (10px threshold)

### 6.4 Edit Mode Visuals

When edit mode is active on selected room:
- **Vertex handles**: scatter markers at all polygon vertices (teal circles, ~6px)
- **Hover highlight**: vertex or edge under cursor gets enlarged/highlighted marker
- **Edge hover**: thick line segment preview when hovering over an edge

### 6.5 Divider Mode Visuals

When divider mode is active:
- **Placed points**: cyan/indigo markers at each placed divider point
- **Segment lines**: solid lines connecting placed points
- **Preview line**: dashed line from last point to cursor (ortho-constrained)
- **Boundary crossing indicators**: where the divider line will intersect the room polygon

### 6.6 PDF Floor Plan Overlay

When overlay is visible:
- Rasterised PDF page composited as `ax.imshow()` with configurable alpha (0.0–1.0)
- Transform: offset_x, offset_y, scale_x, scale_y, rotation_90
- **Alignment mode**: arrow keys nudge position (accelerating hold), two-point click registration

### 6.7 DF% Stamps

When placement mode has been used:
- **Cyan dots** at stamped positions
- **Text labels** beside each dot showing DF% value (e.g. "1.23%")
- Right-click removes nearest stamp

### 6.8 Zoom & Pan Behaviour

- **Scroll zoom**: Centred on cursor, symmetric x/y scaling
- **Middle-drag pan**: Drag to reposition view
- **Reset zoom** (R key): Returns to full image extents
- **Fit to room** (F key): Zooms to bounding box of selected room + padding
- **View ratio**: `_view_ratio()` returns current zoom level (1.0 = full image)
- **Zoom-dependent sizing**: Font sizes and line widths scale so they appear constant on screen regardless of zoom via `_zoom_fontsize()` and `_zoom_linewidth()`

---

## 7. Right Sidebar (Room Tree Browser)

Toggleable panel (hamburger menu button). Width 0.12 figure-units. Contains a hierarchical tree view.

### 7.1 Header

- Title: "Project Browser" (uppercase, 10px, muted)
- Expand All / Collapse All icon buttons

### 7.2 Tree Hierarchy

```
▼ HDR: level_01_north                    [image icon]
  ▶ False Colour TIFF                    [palette icon]    👁
  ▶ Contour TIFF                         [branch icon]     👁
  ▶ PDF Floor Plan                       [file icon]       👁
  ▼ Room Boundaries                      [layout icon]
    ▼ U101            [BED]              [box icon]    👁 ⚙
        U101_BED1                        [square icon] 👁 ⚙
        U101_LIV1                        [square icon] 👁 ⚙
    ▼ U102            [LIVING]           [box icon]    👁 ⚙
        U102_BED1                        [square icon] 👁 ⚙
▶ HDR: level_01_south                    [image icon]
▶ HDR: level_02_north                    [image icon]
```

### Row Structure

Each row (rendered as matplotlib text + patches in scrollable axes):

```
[indent padding] [▶/▼ chevron] [icon] [label text] [badge?] [eye icon] [gear icon]
```

- **Indent**: depth × 14px equivalent
- **Chevron**: clickable expand/collapse (triangular arrow)
- **Icon**: per-type (image, palette, layout, box, square)
- **Label**: 11px mono, truncated with ellipsis if too long
- **Badge**: optional room type tag (e.g. "BED") — indigo on light blue
- **Eye**: visibility toggle — click to show/hide layer
- **Gear**: settings — click to select/configure room

### Interaction

- Click on HDR row: navigate to that HDR file
- Click on TIFF row: switch to that variant
- Click on room row: select that room
- Click on eye: toggle room/layer visibility
- Click on chevron: expand/collapse subtree
- Ctrl+click room: multi-select
- Shift+click room: range-select from last clicked

### Hit Detection

Tree rows use pre-computed hit boxes (`_tree_hit_boxes`, `_tree_chevron_hit_boxes`, `_tree_gear_hit_boxes`) for fast click detection on the axes.

---

## 8. Bottom Bar

Horizontal strip at y=0.93, spanning the canvas width. Contains:

### 8.1 PDF Resolution Radio

Label "PDF Resolution:" + radio buttons: **72**, **100**, **150** (default), **200**, **300** DPI.

Selecting a value re-rasterises the PDF overlay at the chosen resolution.

### 8.2 AOI Level Cycle

- Label showing current FFL/level value
- "Change" button: cycles to next FFL group
- Only relevant in IESVE mode (multiple AOI levels per image)

### 8.3 Reset Level Alignment

Button to clear manual overlay transform overrides for the current level, reverting to inherited/default alignment.

### 8.4 Progress Bar

Hidden by default. Shown during export operations:
- Filled rectangle (teal) with width proportional to progress (0–100%)
- Centred text overlay: "Exporting… 45%" or stage description
- Polled every ~400ms from background export thread

---

## 9. Interaction Modes

### 9.1 Default / Selection Mode

| Input | Action |
|-------|--------|
| Left-click on room | Select room (updates right panel, highlights polygon) |
| Ctrl+click room | Add/remove from multi-selection |
| Shift+click room | Range-select in tree order |
| Ctrl+A | Select all rooms on current HDR |
| Right-click canvas | Context menu: "Copy image to clipboard" |
| Scroll wheel | Zoom centred on cursor |
| Middle-drag | Pan |
| ↑/↓ keys | Navigate HDR files |
| T key | Cycle image variant |

### 9.2 Draw Mode (D key)

| Input | Action |
|-------|--------|
| Left-click | Place vertex (snaps to nearby vertices within 10px) |
| Mouse move | Preview line from last vertex to cursor (dashed, ortho if enabled) |
| Right-click | Undo last vertex |
| S key | Close polygon and save room |
| Esc | Cancel and exit draw mode |
| First vertex | Auto-detect parent apartment (point-in-polygon test) |

Ortho constraint (when O is ON): preview line snaps to nearest horizontal or vertical direction from previous vertex.

### 9.3 Edit Mode (E key)

Requires a selected room.

| Input | Action |
|-------|--------|
| Hover over vertex | Vertex highlight (enlarged marker) |
| Left-drag vertex | Move vertex to new position |
| Hover over edge | Edge highlight (thick line) |
| Shift+left-drag edge | Translate both endpoints perpendicular to edge |
| Left-click on edge | Insert two new vertices, start dragging one |
| Right-click vertex | Delete vertex (if polygon has ≥4 vertices) |
| Delete/Backspace | Delete hovered vertex |
| Ctrl+Z | Undo last vertex operation (up to 50 levels) |
| S key | Save edits and exit edit mode |
| E key | Exit edit mode |
| F key | Fit zoom to selected room |

**Blitting optimisation**: During vertex/edge drag, background is captured once and only the dragged patch is redrawn per frame (~30fps throttle).

### 9.4 Divider Mode (DD — double-tap D)

Requires a selected room. Splits a room along a multi-segment ortho polyline.

| Input | Action |
|-------|--------|
| Left-click | Place polyline point (ortho-constrained: H or V from previous) |
| Mouse move | Preview dashed line to cursor |
| Right-click | Undo last point |
| S key | Finalise: find boundary intersections, split room into two sub-rooms |
| Esc | Cancel and exit divider mode |

Algorithm:
1. User clicks polyline points inside the room
2. First/last segments are extended to room boundary via ray-polygon intersection
3. Room polygon is split along the polyline into two polygons
4. Original room is replaced with two child rooms (inheriting parent, type)

### 9.5 Placement Mode (P key)

DF% illuminance stamp placement.

| Input | Action |
|-------|--------|
| Left-click | Read DF% from loaded DF image at cursor position, stamp cyan dot + value |
| Right-click | Remove nearest stamp within threshold |

Stamps are per-HDR and persist in session.

### 9.6 Overlay Alignment Mode

Activated via sidebar button when PDF overlay is visible.

**Arrow key nudging**:
- Arrow keys move overlay offset (accelerates if held: starts at 1px, ramps up)
- Ctrl+R: rotate overlay 90° clockwise

**Two-point alignment**:
1. Click point on PDF overlay → marker placed
2. Click corresponding point on HDR image → marker placed
3. Second pair of points → compute affine transform (translation + scale)
4. S key: accept alignment, save transform
5. Esc: discard changes

### 9.7 Multi-Select Mode

Not a distinct mode — works alongside default selection:

| Input | Action |
|-------|--------|
| Ctrl+click | Toggle room in/out of multi-selection set |
| Shift+click | Range-select (from last clicked room in tree order) |
| Ctrl+A | Select all rooms on current HDR |
| Room type button | Apply type to all multi-selected rooms |
| Delete | Delete all multi-selected rooms |

Header shows badge: "N rooms selected" when multi-selection is active.

---

## 10. Modal Dialogs

### 10.1 Project Dialog

Triggered by: sidebar project button (`_on_project_click`)

**tkinter Toplevel dialog** with two sections:

#### Create New Project
- **Project name** text input
- **Mode** dropdown: "archilume" (default), "hdr", "iesve"
- **PDF path** file picker (optional)
- **Image directory** folder picker (optional)
- **IESVE room data** file picker (optional, shown for iesve mode)
- **Create** button → creates project.toml, directories, reloads editor

#### Open Existing Project
- **Dropdown** listing all projects in `projects/` directory
- **Open** button → reloads editor with selected project

### 10.2 Archive Extract Dialog

Triggered by: sidebar extract button (`_on_extract_click`)

**tkinter file dialog** + confirmation:
1. File picker: browse `archive_dir/` for `.zip` files
2. Confirmation: "This will overwrite current AOI files. Continue?"
3. Extracts ZIP contents to project output directory
4. Reloads editor session

### 10.3 Canvas Context Menu

Triggered by: right-click on canvas (when not in a special mode)

**tkinter Menu** popup at cursor:
- "Copy image to clipboard" → captures current viewport at full quality, copies to Windows clipboard via `win32clipboard` / PIL

---

## 11. State Management

### 11.1 Core State Variables

#### Paths & Project
| Variable | Type | Description |
|----------|------|-------------|
| `project` | str \| None | Current project name |
| `project_input_dir` | Path | Project input directory |
| `project_aoi_dir` | Path | AOI boundary file directory |
| `archive_dir` | Path | Archive ZIP directory |
| `wpd_dir` | Path | WPD (per-pixel data) directory |
| `image_dir` | Path | HDR/TIFF image directory |
| `session_path` | Path | Session JSON file path |
| `_overlay_pdf_path` | Path \| None | PDF floor plan file |

#### Image Navigation
| Variable | Type | Description |
|----------|------|-------------|
| `hdr_files` | list[dict] | All discovered HDR files with variant info |
| `current_hdr_idx` | int | Index into `hdr_files` |
| `image_variants` | list[Path] | HDR + associated TIFFs for current floor |
| `current_variant_idx` | int | Currently displayed variant |
| `_image_cache` | dict | Thread-safe LRU cache (up to 15 images) |

#### Room Data
| Variable | Type | Description |
|----------|------|-------------|
| `rooms` | list[dict] | All rooms. Each: `{name, parent, vertices, world_vertices, hdr_file, room_type, ffl, visible, df_cache}` |
| `selected_room_idx` | int \| None | Currently selected room |
| `multi_selected_room_idxs` | set[int] | Multi-selection set |
| `selected_parent` | str \| None | Current parent apartment |
| `parent_options` | list[str] | Available parents for current HDR |

#### Mode Flags
| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `draw_mode` | bool | False | Polygon drawing active |
| `edit_mode` | bool | False | Vertex editing active |
| `divider_mode` | bool | False | Room divider active |
| `placement_mode` | bool | False | DF% stamp placement |
| `ortho_mode` | bool | True | Constrain to H/V |
| `_align_mode` | bool | False | Overlay alignment active |

#### Editing State
| Variable | Type | Description |
|----------|------|-------------|
| `edit_room_idx` | int \| None | Room being edited |
| `edit_vertex_idx` | int \| None | Vertex being dragged |
| `edit_edge_room_idx` | int \| None | Edge being dragged (Shift+drag) |
| `edit_edge_idx` | int \| None | Edge index |
| `_edit_drag_origin` | tuple \| None | Vertex pos at drag start |
| `hover_room_idx` | int \| None | Room under cursor |
| `hover_vertex_idx` | int \| None | Vertex under cursor |
| `hover_edge_room_idx` | int \| None | Edge under cursor |

#### Divider State
| Variable | Type | Description |
|----------|------|-------------|
| `_divider_room_idx` | int \| None | Room being divided |
| `_divider_points` | list[tuple] | Placed polyline points |
| `_divider_snap_pt` | tuple \| None | Snapped vertex highlight |

#### Undo Stacks
| Variable | Max Depth | Description |
|----------|-----------|-------------|
| `_edit_undo_stack` | 50 | Edit mode vertex snapshots |
| `_draw_undo_stack` | 50 | Draw mode ops (create/delete/rename/type) |

#### Overlay / PDF
| Variable | Type | Description |
|----------|------|-------------|
| `_overlay_visible` | bool | PDF overlay shown |
| `_overlay_alpha` | float | Overlay transparency (0–1) |
| `_overlay_raster_dpi` | int | PDF rasterisation DPI (default 150) |
| `_overlay_page_idx` | int | Current PDF page index |
| `_overlay_transforms` | dict | Per-HDR: `{offset_x, offset_y, scale_x, scale_y, rotation_90, page_idx, is_manual}` |
| `_overlay_rgba` | ndarray | Rasterised PDF page (H, W, 4) |

#### Daylight Factor
| Variable | Type | Description |
|----------|------|-------------|
| `_df_image` | ndarray | Current HDR's DF% image (H, W) |
| `_room_df_results` | dict | room_idx → list of result strings |
| `_df_stamps` | dict | hdr_name → list of (x, y, df_val, px, py) |
| `DF_THRESHOLDS` | dict | `{BED: 0.5, LIVING: 1.0, NON-RESI: 2.0}` |

#### Zoom & Display
| Variable | Type | Description |
|----------|------|-------------|
| `_image_width`, `_image_height` | int | Current image dimensions |
| `original_xlim`, `original_ylim` | tuple | Full image axis limits |
| `_annotation_scale` | float | Label size multiplier (0.5–2.0) |

#### Pan
| Variable | Type | Description |
|----------|------|-------------|
| `_pan_active` | bool | Currently panning |
| `_pan_start` | tuple | Pan start position |

#### IESVE
| Variable | Type | Description |
|----------|------|-------------|
| `_iesve_room_data_path` | Path \| None | IESVE room data CSV |
| `_aoi_level_idx` | int | Current FFL group index |
| `_aoi_level_map` | dict | pic_name → assigned FFL value |

### 11.2 Cached Matplotlib Artists

| Cache | Type | Purpose |
|-------|------|---------|
| `_room_patch_cache` | dict[int → Polygon] | Room polygon patches (avoid recreating) |
| `_room_label_cache` | dict[int → Text] | Room name text objects |
| `_df_text_cache` | list[Text] | DF% annotation texts |
| `_edit_vertex_scatter` | PathCollection | Edit mode vertex markers |

### 11.3 Performance Optimisations

- **Blitting**: During vertex/edge drag, background captured once, only moving elements redrawn
- **Hover throttle**: Vertex/edge hover detection runs at max ~15fps
- **Drag throttle**: Vertex drag redraws at max ~30fps
- **Vectorised hover**: Pre-built numpy arrays for all vertices/edges on current HDR
- **Image prefetch**: Background thread loads adjacent HDR/TIFF images
- **PDF prefetch**: Background thread rasterises PDF pages ahead of navigation

---

## 12. Session Persistence

### 12.1 Session File

**Path**: `{project_aoi_dir}/aoi_session.json`

**Contents**:
```json
{
  "rooms": [
    {
      "name": "U101_BED1",
      "parent": "U101",
      "vertices": [[x1,y1], [x2,y2], ...],
      "world_vertices": [[wx1,wy1], ...],
      "hdr_file": "level_01_north",
      "room_type": "BED",
      "ffl": 10.5,
      "visible": true
    }
  ],
  "df_stamps": {
    "level_01_north": [[x, y, df_val, px, py], ...]
  },
  "overlay_transforms": {
    "level_01_north": {
      "offset_x": 0, "offset_y": 0,
      "scale_x": 1.0, "scale_y": 1.0,
      "rotation_90": 0,
      "page_idx": 0,
      "is_manual": false
    }
  },
  "selected_parent": "U101",
  "current_hdr_idx": 0,
  "annotation_scale": 1.0,
  "overlay_dpi": 150,
  "overlay_visible": false,
  "overlay_alpha": 0.6,
  "window_settings": {
    "x": 100, "y": 100,
    "width": 1920, "height": 1080,
    "maximized": true
  }
}
```

### 12.2 Auto-Save

Session is auto-saved on every mutation:
- Room create/delete/edit
- Room type change
- Overlay transform change
- DF stamp add/remove
- HDR navigation
- Window close

`Shift+S` forces an immediate full save.

### 12.3 Load Priority

1. Try `aoi_session.json` (full state)
2. Fall back to `.aoi` files (Archilume format — pixel coordinates)
3. Fall back to IESVE AOI files (world coordinates, projected to pixels)

---

## 13. Export & Archive Operations

### 13.1 Export Report (sidebar button)

Runs in background thread with progress bar:

**Phase 1 — Compute**: For each HDR file (parallel via ThreadPoolExecutor):
- Extract per-pixel illuminance/DF for every room polygon (using `Hdr2Wpd`)
- Compute summary statistics: mean DF%, area above threshold, compliance %

**Phase 2 — Write Excel**:
- `aoi_report_daylight.xlsx` with per-room sheets and pivot summary table
- Per-room CSV files in `aoi_pixel_data/`

**Phase 3 — Image overlays**:
- `*_aoi_overlay.png`: TIFF with room boundary polygons, labels, DF results drawn on top
- `*_aoi_pdf_underlay.png`: Full-resolution HDR with PDF underlay composited + room boundaries

### 13.2 Archive

After export: ZIP all output files into `archive_dir/{project}_{timestamp}.zip`

### 13.3 Extract Archive

Select ZIP from archive folder → extract to project output directory → reload session.

---

## 14. Geometry & Snapping

### 14.1 Vertex Snapping

- Threshold: 10 pixels (in data coordinates, scaled by zoom)
- Snaps to existing vertices of all rooms on current HDR
- Visual: yellow ring highlight at snap point
- Method: `_snap_to_vertex()` — finds nearest vertex within threshold

### 14.2 Edge Snapping

- Threshold: 10 pixels perpendicular distance
- Snaps to nearest point on any room edge
- Method: `_snap_to_edge()` — perpendicular projection onto line segments

### 14.3 Ortho Constraint

When enabled (O key, default ON):
- Draw mode: preview line snaps to nearest H or V direction from last vertex
- Divider mode: each segment constrained to H or V from previous point
- Edit mode: vertex drag can be ortho-constrained

### 14.4 Point-in-Polygon

- Used for: room selection (click detection), parent auto-detect, containment validation
- Method: matplotlib `Path.contains_point()` or custom winding number

### 14.5 Room Division Geometry

1. **Ray-polygon intersection** (`_ray_polygon_intersection`): Extend divider line to find where it crosses room boundary
2. **Polygon splitting** (`_split_polygon_by_polyline`): Walk polygon perimeter, split at intersection points into two sub-polygons
3. **Validation**: Both resulting polygons must have ≥3 vertices and nonzero area

---

## 15. Daylight Factor (DF%) Analysis

### 15.1 Loading DF Image

- For Archilume mode: load HDR, extract luminance channel → convert to DF%
- For IESVE mode: load `.pic` file, undo EXPOSURE header adjustment
- Cached per HDR in `_df_image_cache`

### 15.2 Computing Room Results

For each room on current floor:
1. Create polygon mask from room vertices
2. Extract DF% values within mask from `_df_image`
3. Compute: mean DF%, median, area above threshold, compliance percentage
4. Determine threshold by room type: BED=0.5%, LIVING=1.0%, NON-RESI=2.0%

### 15.3 Display

- **Room label annotations**: Below room name, colour-coded lines:
  - Green (`#059669`): ≥ threshold (pass)
  - Amber (`#d97706`): < threshold but ≥ 50% (marginal)
  - Red (`#dc2626`): < 50% of threshold (fail)
- **Legend strip**: In bottom bar, showing colour key
- **DF stamps**: Cyan dots with per-pixel DF% values

### 15.4 Thresholds

| Room Type | DF% Threshold |
|-----------|---------------|
| BED | 0.5% |
| LIVING | 1.0% |
| NON-RESI | 2.0% |
| CIRC | (no threshold) |

---

## 16. Threading & Performance

### 16.1 Background Threads

| Thread | Purpose | Trigger |
|--------|---------|---------|
| Image prefetch | Load adjacent HDR/TIFF images | HDR navigation |
| PDF prefetch | Rasterise adjacent PDF pages | Page cycle |
| DF computation | Compute room DF results | HDR navigation, room edit |
| Export worker | Full export pipeline | Export button |

### 16.2 Thread Safety

- `_image_cache_lock` (Lock): Protects shared image cache
- `_prefetching_hdrs` (set): Tracks in-flight prefetch operations
- ThreadPoolExecutor for parallel HDR export processing

### 16.3 Rendering Performance

- **Blitting**: Background captured once during drag operations; only changed artists redrawn
- **Throttling**: Hover detection at ~15fps, drag updates at ~30fps
- **Vectorised hit-testing**: Pre-built numpy arrays for all vertices/edges (`_rebuild_hover_arrays`)
- **Cached artists**: Room patches, labels, and DF texts cached and reused across redraws

---

## 17. File I/O Summary

### Reads
| File | Format | Purpose |
|------|--------|---------|
| `*.hdr`, `*.pic` | Radiance HDR | Floor plan images (via `pvalue` or imageio) |
| `*.tif`, `*.tiff` | TIFF | False-colour, contour overlays |
| `*.pdf` | PDF | Floor plan underlay (rasterised via `rasterize_pdf_page`) |
| `aoi_session.json` | JSON | Session restore |
| `*.aoi` | Custom text | Archilume AOI boundary files |
| `*.csv` | CSV | IESVE room data, legacy boundary format |
| `project.toml` | TOML | Project configuration |

### Writes
| File | Format | Purpose |
|------|--------|---------|
| `aoi_session.json` | JSON | Session persistence |
| `aoi_report_daylight.xlsx` | Excel | DF compliance report |
| `aoi_pixel_data/*.csv` | CSV | Per-room illuminance data |
| `*_aoi_overlay.png` | PNG | Room boundaries on TIFF |
| `*_aoi_pdf_underlay.png` | PNG | HDR + PDF underlay composite |
| `*.aoi` | Custom text | Exported AOI boundary files |
| `archive/*.zip` | ZIP | Timestamped output archive |

---

## 18. Differences from Dash Editor

The Dash editor (`dash_app.py`) is a web-based reimplementation. Key differences:

| Feature | Matplotlib Editor | Dash Editor |
|---------|-------------------|-------------|
| Rendering | matplotlib + tkinter | Plotly.js + Dash |
| Icons | Programmatic matplotlib paths | Lucide (dash-iconify) |
| State | Instance variables | Server-side `EditorState` singleton + client stores |
| Keyboard | matplotlib `key_press_event` | JS polling via `window._lastKeyEvent` (150ms) |
| Blitting | Native matplotlib blit | N/A (Plotly handles own rendering) |
| Context menu | tkinter Menu popup | Not yet implemented |
| Copy to clipboard | win32clipboard + PIL | Not yet implemented |
| Two-point alignment | Full implementation | Stub only |
| Edge snap | Full implementation | Not yet ported |
| Excel export | Full openpyxl export | Not yet ported |
| Overlay image export | Full PIL compositing | Not yet ported |
| Bottom panels | PDF controls + progress | Model Validation + Simulation Manager + Floor Plan Controls |

The Dash editor adds aspirational panels (Model Validation, Simulation Manager, Compliance Framework) that don't exist in the matplotlib version.