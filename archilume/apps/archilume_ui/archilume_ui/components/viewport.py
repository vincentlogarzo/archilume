"""Viewport — spec §6. SVG canvas with image, room polygons, drawing tools, overlays."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, KBD_BADGE


# ---------------------------------------------------------------------------
# §6.1 Top toolbar
# ---------------------------------------------------------------------------

def _toolbar_btn(icon: str, label: str, shortcut: str = "", on_click=None) -> rx.Component:
    children = [
        rx.icon(tag=icon, size=14),
        rx.text(label, style={"font_family": FONT_MONO, "font_size": "11px",
                               "margin_left": "4px"}),
    ]
    if shortcut:
        children.append(rx.text(shortcut, style=KBD_BADGE))
    return rx.button(
        *children,
        variant="ghost", size="1",
        on_click=on_click,
        style={"color": COLORS["text_sec"], "gap": "4px"},
    )


def _top_toolbar() -> rx.Component:
    return rx.flex(
        # HDR nav
        rx.flex(
            rx.icon_button(rx.icon(tag="chevron-up", size=14),
                           variant="outline", size="1",
                           on_click=lambda: EditorState.navigate_hdr(-1)),
            rx.icon_button(rx.icon(tag="chevron-down", size=14),
                           variant="outline", size="1",
                           on_click=lambda: EditorState.navigate_hdr(1)),
            gap="2px",
        ),
        # Filename
        rx.text(
            EditorState.current_hdr_name,
            style={"font_family": FONT_MONO, "font_size": "11px",
                    "color": COLORS["text_pri"], "margin_left": "8px"},
        ),
        # Variant toggle badge
        rx.button(
            EditorState.current_variant_label,
            variant="outline", size="1",
            on_click=EditorState.toggle_image_variant,
            style={
                "font_family": FONT_MONO, "font_size": "10px",
                "margin_left": "6px",
                "color": COLORS["accent"],
                "border_color": COLORS["accent"],
            },
        ),
        # Index
        rx.text(
            EditorState.current_hdr_count,
            style={"font_family": FONT_MONO, "font_size": "10px",
                    "color": COLORS["text_dim"], "margin_left": "6px"},
        ),
        rx.spacer(),
        _toolbar_btn("undo", "Undo", "Ctrl+Z", on_click=EditorState.undo),
        _toolbar_btn("expand", "Fit", "F", on_click=EditorState.fit_zoom),
        _toolbar_btn("square-check", "Select All", "Ctrl+A",
                     on_click=EditorState.select_all_rooms),
        align="center",
        style={"padding": "4px 8px", "gap": "4px"},
        background=COLORS["panel_bg"],
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )


# ---------------------------------------------------------------------------
# §6.2.2 Floating tool palette
# ---------------------------------------------------------------------------

_PALETTE_TOOLS = [
    ("git-commit-horizontal", "Draw Polygon", "D", EditorState.toggle_draw_mode),
    ("scissors", "Room Divider", "DD", EditorState.toggle_divider_mode),
    ("pen-line", "Edit Mode", "E", EditorState.toggle_edit_mode),
    ("crosshair", "DF% Placement", "P", EditorState.toggle_df_placement),
    ("search", "Zoom", "", None),
    ("move", "Pan", "", None),
    ("corner-down-right", "Ortho Lines", "O", EditorState.toggle_ortho),
    ("undo-2", "Undo Last", "Ctrl+Z", EditorState.undo),
]


def _floating_palette() -> rx.Component:
    rows = []
    for i, (icon, label, shortcut, handler) in enumerate(_PALETTE_TOOLS):
        row_style: dict = {
            "padding": "4px 12px",
            "gap": "6px",
            "cursor": "pointer",
            "_hover": {"background": COLORS["hover"]},
        }
        if i < len(_PALETTE_TOOLS) - 1:
            row_style["border_bottom"] = "1px solid"

        children: list[rx.Component] = [
            rx.icon(tag=icon, size=14, style={"color": COLORS["text_sec"]}),
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "11px",
                                   "color": COLORS["text_pri"]}),
        ]
        if shortcut:
            children.append(rx.spacer())
            children.append(rx.text(shortcut, style=KBD_BADGE))

        rows.append(
            rx.flex(
                *children,
                align="center",
                style=row_style,
                border_bottom_color=COLORS["panel_bdr"] if i < len(_PALETTE_TOOLS) - 1 else None,
                on_click=handler,
            )
        )

    return rx.box(
        *rows,
        style={
            "position": "absolute",
            "bottom": "20px",
            "left": "50%",
            "transform": "translateX(-50%)",
            "border_radius": "8px",
            "box_shadow": "0 2px 8px rgba(0,0,0,0.08)",
            "min_width": "200px",
            "z_index": "10",
        },
        background=COLORS["panel_bg"],
        border="1px solid", border_color=COLORS["panel_bdr"],
    )


# ---------------------------------------------------------------------------
# §6.2.3 Overlay alignment panel
# ---------------------------------------------------------------------------

def _overlay_align_panel() -> rx.Component:
    def _field(label: str, step: float, default: float = 0, on_change=None):
        return rx.flex(
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "10px",
                                   "color": COLORS["text_dim"], "width": "60px"}),
            rx.input(
                type="number",
                default_value=str(default),
                step=str(step),
                on_change=on_change,
                style={"font_family": FONT_MONO, "font_size": "11px", "width": "80px"},
                size="1",
            ),
            align="center", gap="4px",
        )

    return rx.cond(
        EditorState.overlay_align_mode,
        rx.box(
            rx.text("Overlay Alignment", style={
                "font_family": FONT_MONO, "font_size": "10px",
                "text_transform": "uppercase",
                "padding": "6px 8px",
            },
            color=COLORS["text_dim"],
            border_bottom="1px solid", border_color=COLORS["panel_bdr"],
            ),
            rx.flex(
                _field("Offset X", 1, on_change=EditorState.set_overlay_offset_x),
                _field("Offset Y", 1, on_change=EditorState.set_overlay_offset_y),
                _field("Scale X", 0.01, 1.0, on_change=EditorState.set_overlay_scale_x),
                _field("Scale Y", 0.01, 1.0, on_change=EditorState.set_overlay_scale_y),
                _field("Alpha", 0.05, 0.6, on_change=EditorState.set_overlay_alpha),
                direction="column", gap="4px",
                style={"padding": "8px"},
            ),
            style={
                "position": "absolute",
                "top": "12px", "right": "12px",
                "border_radius": "8px",
                "box_shadow": "0 2px 8px rgba(0,0,0,0.08)",
                "z_index": "10",
                "min_width": "180px",
            },
            background=COLORS["panel_bg"],
            border="1px solid", border_color=COLORS["panel_bdr"],
        ),
        rx.fragment(),
    )


# ---------------------------------------------------------------------------
# Zoom indicator + Progress bar
# ---------------------------------------------------------------------------

def _zoom_indicator() -> rx.Component:
    return rx.text(
        EditorState.zoom_pct,
        style={
            "position": "absolute",
            "bottom": "8px", "right": "8px",
            "font_family": FONT_MONO, "font_size": "10px",
            "color": COLORS["text_dim"],
            "background": "rgba(255,255,255,0.8)",
            "padding": "2px 6px",
            "border_radius": "3px",
        },
    )


def _progress_bar() -> rx.Component:
    return rx.cond(
        EditorState.progress_visible,
        rx.box(
            rx.box(
                style={
                    "height": "100%",
                    "background": COLORS["accent"],
                    "width": EditorState.progress_pct_str,
                    "transition": "width 0.3s ease",
                },
            ),
            rx.text(
                EditorState.progress_msg,
                style={
                    "position": "absolute", "inset": "0",
                    "display": "flex", "align_items": "center", "justify_content": "center",
                    "font_family": FONT_MONO, "font_size": "10px", "color": COLORS["text_pri"],
                },
            ),
            style={"position": "relative", "height": "18px"},
            background=COLORS["deep"],
            border_top="1px solid", border_color=COLORS["panel_bdr"],
        ),
        rx.fragment(),
    )


# ---------------------------------------------------------------------------
# Room polygon renderer (used by rx.foreach)
# ---------------------------------------------------------------------------

def _render_room(room: dict) -> rx.Component:
    """Render a single enriched room dict as SVG polygon + label + DF annotation."""
    return rx.fragment(
        rx.el.polygon(
            points=room["vertices_str"],
            fill=rx.cond(room["selected"], COLORS["room_fill_selected"], COLORS["room_fill_unselected"]),
            stroke=rx.cond(room["selected"], COLORS["room_stroke_selected"], COLORS["room_stroke_unselected"]),
            stroke_width=rx.cond(room["selected"], "2", "1"),
            cursor="pointer",
            on_click=EditorState.select_room(room["idx"]),
        ),
        # Room name label
        rx.el.text(
            room["name"],
            x=room["label_x"],
            y=room["label_y"],
            text_anchor="middle",
            dominant_baseline="middle",
            fill=rx.cond(room["selected"], COLORS["accent"], COLORS["text_pri"]),
            font_size="10",
            font_family="DM Mono, monospace",
            style={"pointer_events": "none"},
        ),
        # DF annotation (below label)
        rx.cond(
            room["df_lines"] != "",
            rx.el.text(
                room["df_lines"],
                x=room["label_x"],
                y=room["df_label_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill=rx.cond(
                    room["df_status"] == "pass", COLORS["success"],
                    rx.cond(room["df_status"] == "marginal", COLORS["warning"], COLORS["danger"]),
                ),
                font_size="8",
                font_family="DM Mono, monospace",
                style={"pointer_events": "none"},
            ),
            rx.fragment(),
        ),
    )


def _render_edit_handle(vert: dict) -> rx.Component:
    """Render a vertex handle circle for edit mode."""
    return rx.el.circle(
        cx=vert["x"].to(str),
        cy=vert["y"].to(str),
        r="5",
        fill=COLORS["edit_vertex"],
        stroke="white",
        stroke_width="1",
        cursor="grab",
    )


def _render_stamp(stamp: dict) -> rx.Component:
    """Render a DF% stamp dot + value."""
    return rx.fragment(
        rx.el.circle(
            cx=stamp["x"].to(str),
            cy=stamp["y"].to(str),
            r="4",
            fill=COLORS["df_stamp"],
        ),
        rx.el.text(
            stamp["value"].to(str) + "%",
            x=stamp["x"].to(str),
            y=stamp["y"].to(str),
            fill=COLORS["df_stamp"],
            font_size="9",
            font_family="DM Mono, monospace",
            dominant_baseline="middle",
            style={"pointer_events": "none"},
        ),
    )


# ---------------------------------------------------------------------------
# JavaScript for coordinate conversion and event bridging
# ---------------------------------------------------------------------------

_CANVAS_JS = rx.script("""
(function() {
    // Throttle helper
    let lastMoveTime = 0;
    const MOVE_THROTTLE_MS = 67; // ~15fps

    function getSvgCoords(svg, e) {
        const rect = svg.getBoundingClientRect();
        const vb = svg.viewBox.baseVal;
        if (!vb || vb.width === 0 || vb.height === 0) {
            return {x: e.clientX - rect.left, y: e.clientY - rect.top};
        }
        const scaleX = vb.width / rect.width;
        const scaleY = vb.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX + vb.x,
            y: (e.clientY - rect.top) * scaleY + vb.y,
        };
    }

    function setupCanvas() {
        const svg = document.getElementById('editor-svg');
        if (!svg) { setTimeout(setupCanvas, 200); return; }

        // Click
        svg.addEventListener('click', function(e) {
            const c = getSvgCoords(svg, e);
            applyEvent('editor_state.handle_canvas_click', {
                data: {x: c.x, y: c.y, button: e.button, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey}
            });
        });

        // Right-click
        svg.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            const c = getSvgCoords(svg, e);
            applyEvent('editor_state.handle_canvas_click', {
                data: {x: c.x, y: c.y, button: 2, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey}
            });
        });

        // Mouse move (throttled)
        svg.addEventListener('mousemove', function(e) {
            const now = Date.now();
            if (now - lastMoveTime < MOVE_THROTTLE_MS) return;
            lastMoveTime = now;
            const c = getSvgCoords(svg, e);
            applyEvent('editor_state.handle_mouse_move', {data: {x: c.x, y: c.y}});
        });

        // Mouse down (for edit drag)
        svg.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return;
            const c = getSvgCoords(svg, e);
            applyEvent('editor_state.handle_mouse_down', {data: {x: c.x, y: c.y}});
        });

        // Mouse up
        svg.addEventListener('mouseup', function(e) {
            applyEvent('editor_state.handle_mouse_up', {data: {}});
        });

        // Wheel (zoom)
        svg.addEventListener('wheel', function(e) {
            e.preventDefault();
            const c = getSvgCoords(svg, e);
            applyEvent('editor_state.handle_wheel', {data: {deltaY: e.deltaY, x: c.x, y: c.y}});
        }, {passive: false});

        // Middle-mouse pan
        let panning = false, panStartX = 0, panStartY = 0;
        svg.addEventListener('mousedown', function(e) {
            if (e.button === 1) { // Middle
                e.preventDefault();
                panning = true;
                panStartX = e.clientX;
                panStartY = e.clientY;
            }
        });
        window.addEventListener('mousemove', function(e) {
            if (!panning) return;
            const dx = e.clientX - panStartX;
            const dy = e.clientY - panStartY;
            panStartX = e.clientX;
            panStartY = e.clientY;
            // Send pan delta — we'll handle in Python as direct pan offset
            applyEvent('editor_state.handle_wheel', {data: {deltaY: 0, panDx: dx, panDy: dy}});
        });
        window.addEventListener('mouseup', function(e) {
            if (e.button === 1) panning = false;
        });
    }

    if (document.readyState === 'complete') setupCanvas();
    else window.addEventListener('load', setupCanvas);
})();
""")


# ---------------------------------------------------------------------------
# SVG Canvas
# ---------------------------------------------------------------------------

def _svg_canvas() -> rx.Component:
    return rx.box(
        # Background image
        rx.cond(
            EditorState.current_image_b64 != "",
            rx.image(
                src=EditorState.current_image_b64,
                style={
                    "width": "100%", "height": "100%",
                    "object_fit": "contain", "display": "block",
                },
            ),
            rx.box(
                rx.text(
                    "No image loaded — open a project to begin",
                    style={"font_family": FONT_MONO, "font_size": "12px", "color": COLORS["text_dim"]},
                ),
                style={"width": "100%", "height": "100%",
                        "display": "flex", "align_items": "center", "justify_content": "center"},
            ),
        ),
        # PDF overlay
        rx.cond(
            EditorState.overlay_visible,
            rx.cond(
                EditorState.overlay_image_b64 != "",
                rx.image(
                    src=EditorState.overlay_image_b64,
                    style={
                        "position": "absolute", "top": "0", "left": "0",
                        "opacity": EditorState.overlay_alpha_str,
                        "transform": EditorState.overlay_css_transform,
                        "transform_origin": "top left",
                        "pointer_events": "none",
                    },
                ),
                rx.fragment(),
            ),
            rx.fragment(),
        ),
        # SVG overlay
        rx.el.svg(
            # Room polygons
            rx.foreach(EditorState.enriched_rooms, _render_room),

            # Edit mode vertex handles
            rx.cond(
                EditorState.edit_mode,
                rx.foreach(EditorState.selected_room_vertices, _render_edit_handle),
                rx.fragment(),
            ),

            # Drawing-in-progress polyline
            rx.cond(
                EditorState.has_draw_vertices,
                rx.el.svg.polyline(
                    points=EditorState.draw_points_str,
                    fill="none",
                    stroke=COLORS["accent"],
                    stroke_width="1.5",
                ),
                rx.fragment(),
            ),

            # Draw preview line
            rx.cond(
                EditorState.has_draw_vertices & EditorState.has_preview,
                rx.el.line(
                    x1=EditorState.last_draw_vertex["x"].to(str),
                    y1=EditorState.last_draw_vertex["y"].to(str),
                    x2=EditorState.preview_point["x"].to(str),
                    y2=EditorState.preview_point["y"].to(str),
                    stroke=COLORS["accent"],
                    stroke_width="1",
                    stroke_dasharray="5,3",
                ),
                rx.fragment(),
            ),

            # Draw vertex dots
            rx.foreach(
                EditorState.draw_vertices,
                lambda v: rx.el.circle(
                    cx=v["x"].to(str), cy=v["y"].to(str), r="4",
                    fill=COLORS["accent"],
                ),
            ),

            # Snap ring
            rx.cond(
                EditorState.has_snap,
                rx.el.circle(
                    cx=EditorState.snap_point["x"].to(str),
                    cy=EditorState.snap_point["y"].to(str),
                    r="12", fill="none",
                    stroke=COLORS["snap_highlight"], stroke_width="2",
                ),
                rx.fragment(),
            ),

            # Divider polyline
            rx.cond(
                EditorState.has_divider_points,
                rx.el.svg.polyline(
                    points=EditorState.divider_points_str,
                    fill="none",
                    stroke=COLORS["divider_preview"],
                    stroke_width="2",
                    stroke_dasharray="6,3",
                ),
                rx.fragment(),
            ),

            # DF stamps
            rx.foreach(EditorState.current_hdr_stamps, _render_stamp),

            id="editor-svg",
            width="100%",
            height="100%",
            viewBox=EditorState.svg_viewbox,
            preserveAspectRatio="xMidYMid meet",
            style={
                "position": "absolute", "top": "0", "left": "0",
                "pointer_events": "all",
            },
        ),
        # JS bridge for coordinate conversion
        _CANVAS_JS,
        style={
            "position": "relative", "flex": "1", "overflow": "hidden",
            "transform": EditorState.canvas_transform,
            "transform_origin": "center center",
        },
        background=COLORS["viewport"],
    )


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def viewport() -> rx.Component:
    return rx.flex(
        _top_toolbar(),
        rx.box(
            _svg_canvas(),
            _floating_palette(),
            _overlay_align_panel(),
            _zoom_indicator(),
            style={"position": "relative", "flex": "1", "overflow": "hidden"},
        ),
        _progress_bar(),
        direction="column",
        style={"flex": "1", "overflow": "hidden"},
    )
