# Archilume HDR AOI Editor — UI Specification

> Framework-agnostic specification for recreating the Dash-based room boundary editor in Reflex (or any component framework).

---

## 1. Global Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                         HEADER BAR (46px)                        │
├────┬──────────┬──────────────────────────────┬───────────────────┤
│LEFT│ PROJECT  │                              │  RIGHT            │
│SIDE│ TREE     │       VIEWPORT               │  PANEL            │
│BAR │ (240–    │       (flex-grow)             │  (220px)          │
│52px│  300px)  │                               │                   │
│    │          │                               │                   │
├────┴──────────┴──────────────────────────────┴───────────────────┤
│                       BOTTOM ROW (~160px)                        │
└──────────────────────────────────────────────────────────────────┘
```

- Root: `display: flex`, full viewport (`100vw × 100vh`), no scroll.
- Left sidebar is `position: fixed`, everything else offset by `margin-left: 52px`.
- Middle row is `display: flex; flex: 1; overflow: hidden` containing project tree, viewport, and right panel.

---

## 2. Design Tokens

### 2.1 Colours

| Token         | Hex       | Usage                                |
|---------------|-----------|--------------------------------------|
| `sidebar`     | `#f5f6f7` | Left sidebar background              |
| `sidebar_act` | `#e8eaed` | Active sidebar button background     |
| `header`      | `#ffffff` | Header bar, panel backgrounds        |
| `panel_bg`    | `#ffffff` | Card / panel surface                 |
| `panel_bdr`   | `#e2e5e9` | Borders throughout                   |
| `viewport`    | `#f0f2f4` | Canvas background                    |
| `text_pri`    | `#1a1f27` | Primary text                         |
| `text_sec`    | `#5a6472` | Secondary text                       |
| `text_dim`    | `#9ba6b2` | Muted / tertiary text                |
| `accent`      | `#0d9488` | Teal accent (primary)                |
| `accent2`     | `#4f6ef7` | Indigo accent (secondary)            |
| `hover`       | `#eef0f3` | Hover highlight                      |
| `btn_on`      | `#ccfbf1` | Active toggle tint (teal)            |
| `btn_off`     | transparent | Inactive toggle                     |
| `danger`      | `#dc2626` | Destructive actions                  |
| `warning`     | `#d97706` | Caution / edit mode                  |
| `success`     | `#059669` | Positive actions                     |
| `deep`        | `#f0f2f4` | Inset input backgrounds              |

### 2.2 Typography

| Token       | Value                             | Usage                    |
|-------------|-----------------------------------|--------------------------|
| `font_head` | `Syne, sans-serif`                | Logo / headings          |
| `font_mono` | `'DM Mono', monospace`            | All body text, labels, inputs, buttons |

Load from Google Fonts:
- `DM Mono` weights 300, 400, 500
- `Syne` weights 400, 600, 700

### 2.3 Common Sizes

- Sidebar icon buttons: 48×auto px, icon 20px, 6px border-radius
- Panel card title: 10px uppercase, letter-spacing 0.08em
- Panel section label: 9px uppercase, letter-spacing 0.12em
- Body text: 11px
- Badges: 9–10px
- Keyboard shortcut badges: 9px, `deep` background, `panel_bdr` border, 3px radius

---

## 3. Left Sidebar

Fixed vertical bar, 52px wide, full viewport height. Flex column, centred items, `sidebar` background, right border.

### Button Groups (top to bottom)

Each button: 48px wide, icon centred, tooltip on hover (right placement). Active state = `sidebar_act` bg + `accent` icon colour.

| Group          | Buttons (icon → ID → tooltip)                                                                 |
|----------------|-----------------------------------------------------------------------------------------------|
| Navigation     | `menu` → `sb-menu` → "Toggle Project Browser"                                                |
|                | `folder-open` → `sb-open-project` → "Open Project"                                           |
|                | `folder-plus` → `sb-create-project` → "Create New Project"                                   |
| *divider*      |                                                                                               |
| Archive        | `archive-restore` → `sb-extract` → "Extract Archive"                                         |
|                | `file-bar-chart` → `sb-export` → "Export & Archive"                                          |
| *divider*      |                                                                                               |
| Floor plan     | `layout-panel-top` → `sb-overlay-toggle` → "Floor Plan: OFF"                                 |
|                | `refresh-cw` → `sb-overlay-page` → "Change Floor Plan Page"                                  |
|                | `maximize` → `sb-overlay-align` → "Resize Plan Mode: OFF"                                    |
| *divider*      |                                                                                               |
| Image/View     | `layers` → `sb-image-toggle` → "Toggle Image Layers [T]"                                     |
|                | `zoom-in` → `sb-reset-zoom` → "Reset Zoom [R]"                                               |
| *divider*      |                                                                                               |
| Drawing tools  | `crosshair` → `sb-placement` → "DF% Placement: OFF [P]"                                      |
|                | `pen-line` → `sb-edit-mode` → "Boundary Edit Mode: OFF [E]"                                  |
|                | `corner-down-right` → `sb-ortho` → "Ortho Lines: ON [O]" *(active by default)*               |
| *divider*      |                                                                                               |
| Annotation     | Vertical slider: label "Aa" (9px, centred), range 0.5–2.0, step 0.05, default 1.0, height 80px |
| *divider*      |                                                                                               |
| *flex spacer*  |                                                                                               |
| Bottom         | `clock-3` → `sb-history` → "History"                                                         |
|                | `settings-2` → `sb-settings` → "Settings"                                                    |

**Divider**: 1px high line, `panel_bdr` colour, 50% opacity, 6px vertical margin, 8px horizontal margin.

**Icons**: Lucide icon set throughout (e.g. `lucide:menu`, `lucide:folder-open`).

---

## 4. Header Bar

Height 46px, white background, bottom border, flex row aligned centre.

### Elements (left to right)

1. **Logo**: "Archilume" — `font_head`, 700 weight, 17px, -0.02em letter-spacing
2. **Vertical divider**: 1px × 18px, `panel_bdr`
3. **Workflow label**: "HDR AOI Editor" — `font_mono`, 11px, `text_sec`
4. **Project status badge**: e.g. "No project loaded" — 10px, `deep` bg, `panel_bdr` border, 3px radius
5. **Mode badges** (conditionally visible):
   - `DRAW` — teal on `btn_on` bg, `accent` border
   - `EDIT` — amber `#92400e` on `#fef3c7` bg, `warning` border
   - `DIVIDER` — blue `#1e40af` on `#dbeafe` bg, `accent2` border
6. *flex spacer*
7. **Multi-select counter** (hidden until rooms selected): "N rooms selected" — indigo badge
8. **Shortcuts button**: keyboard icon + "Shortcuts" label, opens modal

---

## 5. Project Tree Panel

Left of viewport, 240–300px width, white background, right border, flex column.

### 5.1 Header Row

- Label: "Project Browser" — 10px uppercase, `text_dim`
- Two icon buttons: Expand All (`unfold-horizontal`), Collapse All (`fold-horizontal`)

### 5.2 Tree Structure

Dynamic, populated from `EditorState`. Each row:

```
[indent] [chevron ▶/▼ or spacer] [icon 13px] [label 11px mono] [badge?] [eye icon] [cog icon]
```

- **Indent**: `depth × 14px`
- **Chevron**: down if expanded, right if collapsed, 14px spacer if leaf
- **Highlight**: selected row gets `hover` bg + `accent` text/icon colour
- **Dimmed**: hidden layers at 45% opacity
- **Badge**: optional tag (e.g. room type) — 9px, `accent2` on `#eef4fe`, `panel_bdr` border
- **Eye icon**: 12px `lucide:eye`, toggles visibility
- **Cog icon**: 12px `lucide:settings-2`, opens room settings

#### Hierarchy

```
▼ [HDR filename]                          (icon: lucide:image)
  ▶ Layer 1 – False Colour TIFF           (icon: lucide:palette)
  ▶ Layer 2 – Contour TIFF                (icon: lucide:git-branch)
  ▶ Layer 3 – PDF Floor Plan Overlay       (icon: lucide:file-text)
  ▼ Layer 4 – Room Boundaries             (icon: lucide:layout)
    ▼ U101       [BED badge]   👁 ⚙       (icon: lucide:box, parent room)
        U101_BED1              👁 ⚙       (icon: lucide:square, child room)
        U101_LIV1              👁 ⚙
    ▼ U102       [LIVING badge] 👁 ⚙
        U102_BED1              👁 ⚙
```

### 5.3 Footer: AOI Level Indicator

- Icon: `lucide:layers-2` + level label text + "Change" button (`accent2`, small bordered)
- Separated by top border

---

## 6. Viewport

Flex-grow centre area. Flex column: toolbar → canvas → progress bar.

### 6.1 Top Toolbar

Flex row, white background, bottom border, 6px padding.

| Element | Detail |
|---------|--------|
| HDR nav buttons | `▲` / `▼` chevron button group |
| Filename | 11px mono, `text_pri` |
| Variant badge | "HDR" or "TIFF" — clickable toggle, `accent` on `btn_on`, `accent` border |
| Index | "1 / 4" — 10px, `text_dim` |
| *spacer* | |
| Undo button | undo icon + "Undo" + `Ctrl+Z` kbd badge |
| Fit button | expand icon + "Fit" + `F` kbd badge |
| Select All button | check-square icon + "Select All" + `Ctrl+A` kbd badge |

### 6.2 Canvas Area

`position: relative`, flex-grow, overflow hidden. Contains:

#### 6.2.1 Plotly Graph (or equivalent interactive canvas)

Full width/height. Config: scroll-zoom enabled, mode bar hidden, double-click resets view.

The figure itself renders:
- **Background image**: base64-encoded HDR/TIFF as `layout.images` (positioned at `(0, 0)`, sized to image dimensions)
- **Optional overlay layers**: false-colour TIFF, contour TIFF, PDF floor plan (each as additional `layout.images` with configurable opacity)
- **Room polygons**: `go.Scatter` traces with `fill="toself"`, semi-transparent fill, coloured borders
- **Room labels**: `go.Scatter` traces with `mode="text"`, room name positioned at polygon centroid
- **DF% annotations**: second text layer with compliance-coloured results (green/amber/red)
- **Drawing-in-progress vertices**: scatter points + lines for polygon being drawn
- **Divider line preview**: dashed line when in divider mode
- **Edit mode vertex handles**: scatter markers at polygon vertices
- **Grid**: dot grid at configurable spacing (default 50px), `#c4cad1` dots

#### 6.2.2 Floating Tool Palette

Absolutely positioned, bottom-centre (`bottom: 20px, left: 50%, translateX(-50%)`). White card with shadow, 8px radius.

| Icon | Label | Shortcut | ID |
|------|-------|----------|----|
| `git-commit-horizontal` | Draw Polygon | D | `tool-draw` |
| `scissors` | Room Divider | DD | `tool-divider` |
| `pen-line` | Edit Mode | E | `tool-edit` |
| `crosshair` | DF% Placement | P | `tool-dfplace` |
| `search` | Zoom | — | `tool-zoom` |
| `move` | Pan | — | `tool-pan` |
| `corner-down-right` | Ortho Lines | O | `tool-ortho` |
| `undo-2` | Undo Last | Ctrl+Z | `tool-undo-fp` |

Each row: flex, icon + label + kbd badge, separated by 1px `panel_bdr` bottom border (except last).

#### 6.2.3 Overlay Alignment Panel

Absolutely positioned top-right (`top: 12px, right: 12px`). Hidden by default, shown when overlay align mode is active. White card with shadow.

Fields (each: label 60px + number input 80px):
- Offset X (step 1)
- Offset Y (step 1)
- Scale X (step 0.01, default 1.0)
- Scale Y (step 0.01, default 1.0)
- Alpha (step 0.05, range 0.0–1.0, default 0.6)

#### 6.2.4 Zoom Indicator

Absolutely positioned bottom-right. Read-only label showing current zoom %, e.g. "100%".

### 6.3 Progress Bar

Hidden by default (`display: none`). Height 18px, `deep` background, top border. Contains:
- Fill div (teal `accent`, animated width transition)
- Centred text overlay with percentage/message

---

## 7. Right Panel

220px wide, min 200px, white background, left border, 8px padding, vertical scroll.

### 7.1 Panel Cards

Each card: white bg, `panel_bdr` border, 6px radius, 8px bottom margin. Title bar: 10px uppercase mono, bottom border.

#### Parent Apartment

- Prev/Next chevron buttons flanking a centred text input
- Input shows current parent name or "(None)"

#### Room Name

- Text input with placeholder "e.g. BED1 → U101_BED1"
- Preview text below (10px, `accent2`) showing resolved full name

#### Room Type

- Button group (flex wrap): `BED`, `LIVING`, `NON-RESI`, `CIRC`
- Active button: `btn_on` bg, `accent` border+text
- Inactive: `deep` bg, `panel_bdr` border, `text_sec` text
- Size: 10px, 3px radius, 3px padding

#### Actions

- Two-column row:
  - **Save** (col-7): green — `#d1fae5` bg, `#065f46` text, `#059669` border, save icon + "Save" + `S` kbd
  - **Delete** (col-5): red — `#fee2e2` bg, `#991b1b` text, `#dc2626` border, trash icon + "Delete"

### 7.2 Status Bar

Below cards. Flex row: coloured dot (6px circle, `accent2`) + status message text (11px, `accent2`). Background `deep`, `panel_bdr` border, 4px radius.

Status colours:
- Ready/idle: `accent2` (indigo)
- Drawing: `accent` (teal)
- Error: `danger` (red)

### 7.3 DF% Results Legend

Below status. Conditionally visible (shown when DF results exist). Three rows:
- Green `#059669` dot: "≥ threshold (pass)"
- Amber `#d97706` dot: "< threshold (marginal)"
- Red `#dc2626` dot: "< 50% of threshold (fail)"

---

## 8. Bottom Row

Flex row, `sidebar` background, top border, 10px padding, min-height 160px, horizontal scroll if needed.

### 8.1 Model Validation (320px)

Card with three action rows (icon + label):
- `zap` (accent): "AcceleratedRT Preview"
- `scan-search` (dim): "Preview simulation boundary checks"
- `brush` (dim): "Cleaning tools"
- Info callout: indigo background, "Done here before Sun Merger"

### 8.2 Simulation Manager (280px)

Card with:
- **Scenario grid** dropdown: Default, Summer Solstice, Winter Solstice, Equinox
- **Review Simulation** action button (play-circle icon)
- **Connect to Cloud** action button (cloud-upload icon)
- **Compliance framework** dropdown + heart icon button:
  - Options: BESS, Green Star, NABERS, EN 17037, WELL
  - Default: BESS

### 8.3 Floor Plan Controls (flex-grow, min 220px)

Card with:
- **PDF Resolution** radio group (inline): 72, 150, 300, 600 — default 150
- **Reset Level Alignment** action button (rotate-ccw icon)
- **Change AOI Level** action button (layers-2 icon)

---

## 9. Modals

All modals: centred, mono font throughout.

### 9.1 Keyboard Shortcuts

Triggered by header "Shortcuts" button. Two-column list:

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate HDR files |
| T | Toggle image variant (HDR/TIFF) |
| D | Toggle draw mode |
| DD | Enter room divider mode |
| E | Toggle edit mode |
| Click vertex | Select vertex for move (edit mode) |
| Click canvas | Move selected vertex to position |
| Delete/Backspace | Delete selected vertex (edit mode, ≥4 verts) |
| O | Toggle ortho lines |
| P | Toggle DF% placement mode |
| S | Save room / confirm divider |
| F | Fit zoom to selected room |
| R | Reset zoom |
| Ctrl+Z | Undo |
| Ctrl+A | Select all rooms |
| Shift+S | Force save session |
| Ctrl+R | Rotate overlay 90° |
| Esc | Exit mode / deselect |

### 9.2 Open Project

- Dropdown listing available projects
- Open + Cancel buttons

### 9.3 Create New Project

- Text input for project name
- Validation feedback (red, 10px)
- Create (green) + Cancel buttons

### 9.4 Extract Archive

- Dropdown listing `archive_dir/*.zip` files
- Warning text: "This will overwrite the current project AOI files and reload the session."
- Extract & Reload (red/danger) + Cancel buttons

---

## 10. State Management

### 10.1 Client-side Stores

| Store ID | Type | Purpose |
|----------|------|---------|
| `store-trigger` | int | Incremented to force full UI re-render |
| `store-draw-vertices` | list[{x, y}] | Vertices of polygon currently being drawn |
| `store-divider-points` | list[{x, y}] | Points of divider line being drawn |
| `keyboard-event` | string (JSON) | Last keyboard event captured by JS |
| `store-grid-spacing` | int | Dot grid spacing in pixels (default 50) |
| `store-grid-visible` | bool | Whether dot grid is shown |

### 10.2 Server-side State (`EditorState`)

Singleton holding all domain data. Key properties:

- `project`: current project name
- `hdr_paths`: list of HDR/TIFF image paths
- `current_hdr_index`: index into `hdr_paths`
- `rooms`: list of room dicts `{name, type, parent, vertices, visible, hdr_name}`
- `selected_room_idx`: currently selected room index (or None)
- `multi_selected_room_idxs`: set of selected room indices for bulk ops
- `selected_parent`: current parent apartment name
- `draw_mode`: bool — polygon drawing active
- `edit_mode`: bool — vertex editing active
- `divider_mode`: bool — room divider active
- `ortho_lines`: bool — constrain to 90° angles (default True)
- `overlay_visible`: bool — PDF floor plan overlay shown
- `overlay_align_mode`: bool — overlay positioning active
- `overlay_transforms`: dict per HDR → `{offset_x, offset_y, scale_x, scale_y, alpha}`
- `show_image`: bool — HDR/TIFF background visible
- `image_variant`: "hdr" | "tiff" — which image layer to show
- `annotation_scale`: float — label size multiplier
- `undo_stack`: list of undoable operations
- `df_results`: dict of room → DF% compliance data

### 10.3 Polling Intervals

| ID | Interval | Purpose |
|----|----------|---------|
| `keyboard-poll` | 150ms | Reads `window._lastKeyEvent` via clientside callback |
| `export-poll` | 400ms | Checks export progress (disabled until export starts) |

---

## 11. Interaction Behaviours

### 11.1 Canvas Click

- **Draw mode**: Append click point to `store-draw-vertices`. If ortho enabled, snap to nearest 90° from previous vertex. On first vertex, auto-detect parent apartment via point-in-polygon.
- **Edit mode**: If click near a vertex (within threshold), select it. Subsequent click moves it. Delete/Backspace removes selected vertex (if polygon has ≥4).
- **Divider mode**: Append point to `store-divider-points`. Two points define the divider line.
- **DF% placement mode**: Set the DF annotation position for the selected room.
- **Default (select mode)**: Click inside a room polygon to select it. Shift+click for multi-select.

### 11.2 HDR Navigation

- Up/Down arrows or `▲`/`▼` buttons cycle through HDR files.
- Updates background image, room polygons (filtered to current HDR), overlay, and DF results.
- Blocked during overlay align mode.

### 11.3 Save Room (S key or Save button)

- In draw mode: closes polygon, creates room with current parent + name + type.
- In divider mode: splits the selected room along the divider line.
- Otherwise: updates selected room's name/type from right panel inputs.

### 11.4 Session Persistence

- Auto-saves room data to project AOI directory on every mutation.
- `Shift+S` forces a full session save.
- Session files are per-project, stored alongside AOI boundary CSVs.

---

## 12. Asset Dependencies

- **Icons**: Lucide icon set (via `dash-iconify` in Dash; use equivalent Lucide React/Reflex package)
- **Fonts**: Google Fonts — DM Mono (300/400/500), Syne (400/600/700)
- **CSS framework**: Bootstrap 5 (via `dash-bootstrap-components`; Reflex has built-in Radix/Tailwind)
- **Charting**: Plotly.js (via `dcc.Graph`; Reflex can embed Plotly or use `rx.plotly`)
- **Keyboard capture**: Custom JS sets `window._lastKeyEvent` on `keydown`, polled by interval

---

## 13. Reflex Migration Notes

- Replace `html.Div(style={...})` with Reflex components + `rx.box`, `rx.flex`, `rx.text`, etc. and inline `style` or Tailwind classes.
- Replace `dbc.Button` / `dbc.Input` / `dbc.Select` with `rx.button` / `rx.input` / `rx.select`.
- Replace `dcc.Store` with Reflex `rx.State` vars (server-side state is native in Reflex).
- Replace `dcc.Graph` + Plotly with `rx.plotly` or an HTML5 Canvas component for lower-latency interaction.
- Replace clientside JS keyboard polling with Reflex `rx.event` handlers or `on_key_down` props.
- Replace `dcc.Interval` polling with Reflex `rx.event` periodic tasks or WebSocket push.
- Replace `dbc.Modal` with `rx.dialog` (Radix-based).
- Replace `dbc.Tooltip` with `rx.tooltip`.
- Replace `DashIconify` with `rx.icon` (Lucide built-in) or a Lucide React wrapper.
- `EditorState` can map almost directly to a Reflex `rx.State` subclass, with methods becoming event handlers.