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
        variant="outline", size="1",
        on_click=on_click,
        style={
            "color": COLORS["text_sec"],
            "gap": "4px",
            "border_color": COLORS["panel_bdr"],
            "box_shadow": "0 1px 2px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.06)",
        },
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
                "font_family": FONT_MONO, "font_size": "14px",
                "margin_left": "6px",
                "color": COLORS["accent"],
                "border_color": COLORS["accent"],
            },
        ),
        # Index
        rx.text(
            EditorState.current_hdr_count,
            style={"font_family": FONT_MONO, "font_size": "14px",
                    "color": COLORS["text_dim"], "margin_left": "6px"},
        ),
        rx.spacer(),
        # Grid controls
        rx.flex(
            rx.button(
                rx.icon(tag="grid-3x3", size=14),
                rx.text("Grid", style={"font_family": FONT_MONO, "font_size": "11px",
                                        "margin_left": "4px"}),
                variant="outline", size="1",
                on_click=EditorState.toggle_grid,
                style={
                    "color": rx.cond(EditorState.grid_visible, COLORS["accent"], COLORS["text_sec"]),
                    "border_color": rx.cond(EditorState.grid_visible, COLORS["accent"], COLORS["panel_bdr"]),
                    "gap": "4px",
                },
            ),
            rx.cond(
                EditorState.grid_visible,
                rx.flex(
                    rx.input(
                        default_value="50",
                        type="number",
                        min="5", max="1000", step="5",
                        on_change=EditorState.set_grid_spacing,
                        style={"font_family": FONT_MONO, "font_size": "11px",
                               "width": "55px"},
                        size="1",
                    ),
                    rx.text("mm", style={"font_family": FONT_MONO, "font_size": "11px",
                                          "color": COLORS["text_dim"]}),
                    align="center", gap="2px",
                ),
                rx.fragment(),
            ),
            align="center", gap="4px",
        ),
        _toolbar_btn("undo", "Undo", "Ctrl+Z", on_click=EditorState.undo),
        _toolbar_btn("expand", "Fit", "F", on_click=EditorState.fit_zoom),
        _toolbar_btn("zoom-in", "Reset Zoom", "R", on_click=EditorState.reset_zoom),
        _toolbar_btn("move", "Pan (middle-mouse)"),
        align="center",
        style={"padding": "4px 8px", "gap": "4px", "height": "36px"},
        background=COLORS["panel_bg"],
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )


# ---------------------------------------------------------------------------
# §6.2.2 Floating tool palette
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# §6.2.3 Overlay alignment panel
# ---------------------------------------------------------------------------

def _overlay_align_panel() -> rx.Component:
    def _field(label: str, step: float, default: float = 0, on_change=None):
        return rx.flex(
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "14px",
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
                "font_family": FONT_MONO, "font_size": "14px",
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
        id="zoom-indicator",
        style={
            "position": "absolute",
            "bottom": "8px", "right": "8px",
            "font_family": FONT_MONO, "font_size": "14px",
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
                    "font_family": FONT_MONO, "font_size": "14px", "color": COLORS["text_pri"],
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
    """Render a single enriched room dict as SVG polygon + label + DF annotation.

    CIRC rooms: boundary only — labels and DF annotations suppressed (reduces clutter).
    DIV sub-rooms: dashed boundary at 60% opacity.
    Font sizes scale with EditorState.annotation_scale via label_font_size / df_font_size.
    Stroke width scales inversely with zoom_level via EditorState.room_stroke_width.
    """
    # For DIV rooms: a clipPath containing the same polygon clips the stroke to
    # the interior only — true inset stroke effect so dashes sit on the parent
    # boundary rather than bleeding outside it.
    clip_id = "div-clip-" + room["idx"].to(str)
    return rx.fragment(
        # DIV branch: defs + clipped dashed polygon
        rx.cond(
            room["is_div"],
            rx.fragment(
                rx.el.svg.defs(
                    rx.el.svg.clip_path(
                        rx.el.polygon(points=room["vertices_str"]),
                        custom_attrs={"id": clip_id},
                    ),
                ),
                rx.el.polygon(
                    points=room["vertices_str"],
                    fill="none",
                    stroke=rx.cond(room["selected"], COLORS["room_stroke_selected"], COLORS["room_stroke_unselected"]),
                    stroke_width=EditorState.room_stroke_width,
                    stroke_dasharray="6,3",
                    opacity="0.7",
                    cursor="pointer",
                    on_click=EditorState.select_room(room["idx"]),
                    custom_attrs={"clip-path": "url(#" + clip_id + ")"},
                ),
            ),
            # Non-DIV branch: normal solid polygon
            rx.el.polygon(
                points=room["vertices_str"],
                fill=rx.cond(room["selected"], COLORS["room_fill_selected"], COLORS["room_fill_unselected"]),
                stroke=rx.cond(room["selected"], COLORS["room_stroke_selected"], COLORS["room_stroke_unselected"]),
                stroke_width=EditorState.room_stroke_width,
                cursor="pointer",
                on_click=EditorState.select_room(room["idx"]),
            ),
        ),
        # Room name label — suppressed for CIRC rooms
        rx.cond(
            ~room["is_circ"],
            rx.el.text(
                room["name"],
                x=room["label_x"],
                y=room["label_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill=rx.cond(room["selected"], COLORS["accent"], COLORS["text_pri"]),
                font_size=EditorState.label_font_size,
                font_family="DM Mono, monospace",
                style={"pointer_events": "none"},
            ),
            rx.fragment(),
        ),
        # DF annotation — suppressed for CIRC rooms
        rx.cond(
            ~room["is_circ"] & (room["df_lines"] != ""),
            rx.el.text(
                room["df_lines"],
                x=room["label_x"],
                y=room["df_label_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill=room["df_color"],
                font_size=EditorState.df_font_size,
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
    // ---------------------------------------------------------------------------
    // Pure-JS zoom/pan — bypasses Python state round-trip for smooth 60fps zoom.
    // Zoom & pan are stored in JS variables and applied directly to the DOM.
    // Python state (zoom_level, pan_x, pan_y) is synced back via a debounced call
    // after the gesture ends, so Fit/Reset buttons still work.
    // ---------------------------------------------------------------------------

    var _zoom = 1.0, _panX = 0.0, _panY = 0.0;
    var _syncTimer = null;

    function getCanvas() {
        return document.getElementById('editor-canvas');
    }

    function applyTransform() {
        var canvas = getCanvas();
        if (!canvas) return;
        canvas.style.transform = 'translate(' + _panX + 'px,' + _panY + 'px) scale(' + _zoom + ')';
        canvas.style.transformOrigin = '0 0';
        // Update zoom% indicator if present
        var ind = document.getElementById('zoom-indicator');
        if (ind) ind.textContent = Math.round(_zoom * 100) + '%';
    }

    function scheduleSync() {
        if (_syncTimer) clearTimeout(_syncTimer);
        _syncTimer = setTimeout(function() {
            if (typeof window.applyEvent === 'function') {
                window.applyEvent('editor_state.sync_zoom', {
                    data: {zoom: _zoom, pan_x: _panX, pan_y: _panY}
                });
            }
        }, 300);
    }

    // Public API — called by Python via rx.call_script for Fit/Reset
    window._archiZoom = {
        setTransform: function(zoom, panX, panY) {
            _zoom = zoom; _panX = panX; _panY = panY;
            applyTransform();
        },
        getTransform: function() { return {zoom: _zoom, panX: _panX, panY: _panY}; },
    };

    // ---------------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------------
    function dispatch(event, payload) {
        if (typeof window.applyEvent === 'function') {
            window.applyEvent(event, payload);
        }
    }

    var lastMoveTime = 0;
    var MOVE_THROTTLE_MS = 67; // ~15fps

    function isOverViewport(e) {
        var container = document.getElementById('viewport-container');
        return container && (container === e.target || container.contains(e.target));
    }

    // Converts browser client coords to SVG/image-space coords.
    // Accounts for the current zoom/pan so drawing still lands in image space.
    function getSvgCoords(svg, clientX, clientY) {
        var rect = svg.getBoundingClientRect();
        var vb = svg.viewBox.baseVal;
        if (!vb || vb.width === 0 || vb.height === 0) {
            return {x: clientX - rect.left, y: clientY - rect.top};
        }
        var scaleX = vb.width / rect.width;
        var scaleY = vb.height / rect.height;
        return {
            x: (clientX - rect.left) * scaleX + vb.x,
            y: (clientY - rect.top) * scaleY + vb.y,
        };
    }

    // ---------------------------------------------------------------------------
    // Scroll-wheel zoom + trackpad pinch (ctrlKey=true)
    // Runs entirely in JS — no Python round-trip.
    // ---------------------------------------------------------------------------
    document.addEventListener('wheel', function(e) {
        if (!isOverViewport(e)) return;
        e.preventDefault();

        var container = document.getElementById('viewport-container');
        var rect = container.getBoundingClientRect();

        // Cursor position relative to viewport container (screen pixels)
        var cx = e.clientX - rect.left;
        var cy = e.clientY - rect.top;

        // Cursor position in image space (before zoom)
        var imgX = (cx - _panX) / _zoom;
        var imgY = (cy - _panY) / _zoom;

        // Zoom factor — trackpad pinch sends ctrlKey with small deltas
        var delta = e.ctrlKey ? e.deltaY * 4 : e.deltaY;
        var factor = delta > 0 ? 0.9 : 1.1;
        var newZoom = Math.max(0.1, Math.min(20.0, _zoom * factor));

        // Adjust pan so the point under cursor stays fixed
        _panX = cx - imgX * newZoom;
        _panY = cy - imgY * newZoom;
        _zoom = newZoom;

        applyTransform();
        scheduleSync();
    }, {passive: false});

    // ---------------------------------------------------------------------------
    // Middle-mouse pan — pure JS
    // ---------------------------------------------------------------------------
    var panning = false, panStartX = 0, panStartY = 0;

    document.addEventListener('mousedown', function(e) {
        if (e.button !== 1) return;
        if (!isOverViewport(e)) return;
        e.preventDefault();
        panning = true;
        panStartX = e.clientX;
        panStartY = e.clientY;
    });

    window.addEventListener('mousemove', function(e) {
        if (!panning) return;
        _panX += e.clientX - panStartX;
        _panY += e.clientY - panStartY;
        panStartX = e.clientX;
        panStartY = e.clientY;
        applyTransform();
        scheduleSync();
    });

    window.addEventListener('mouseup', function(e) {
        if (e.button === 1) panning = false;
    });

    // ---------------------------------------------------------------------------
    // All other SVG events — click, mousemove, mousedown, mouseup
    // Re-attached via MutationObserver when Reflex re-renders the SVG.
    // ---------------------------------------------------------------------------
    function attachSvgListeners(svg) {
        svg.addEventListener('click', function(e) {
            var c = getSvgCoords(svg, e.clientX, e.clientY);
            dispatch('editor_state.handle_canvas_click', {
                data: {x: c.x, y: c.y, button: e.button, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey}
            });
        });

        svg.addEventListener('contextmenu', function(e) {
            e.preventDefault();
            var c = getSvgCoords(svg, e.clientX, e.clientY);
            dispatch('editor_state.handle_canvas_click', {
                data: {x: c.x, y: c.y, button: 2, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey}
            });
        });

        svg.addEventListener('mousemove', function(e) {
            var now = Date.now();
            if (now - lastMoveTime < MOVE_THROTTLE_MS) return;
            lastMoveTime = now;
            var c = getSvgCoords(svg, e.clientX, e.clientY);
            dispatch('editor_state.handle_mouse_move', {data: {x: c.x, y: c.y}});
        });

        svg.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return;
            var c = getSvgCoords(svg, e.clientX, e.clientY);
            dispatch('editor_state.handle_mouse_down', {data: {x: c.x, y: c.y}});
        });

        svg.addEventListener('mouseup', function(e) {
            dispatch('editor_state.handle_mouse_up', {data: {}});
        });
    }

    function setupCanvas() {
        var svg = document.getElementById('editor-svg');
        if (svg && !svg._listenersAttached) {
            svg._listenersAttached = true;
            attachSvgListeners(svg);
        }
    }

    var observer = new MutationObserver(setupCanvas);
    observer.observe(document.body, {childList: true, subtree: true});

    if (document.readyState === 'complete') setupCanvas();
    else window.addEventListener('load', setupCanvas);
})();
""")


# ---------------------------------------------------------------------------
# SVG Canvas
# ---------------------------------------------------------------------------

def _svg_canvas() -> rx.Component:
    return rx.box(
        # Background image — normal flow element, drives container height
        rx.cond(
            EditorState.current_image_b64 != "",
            rx.el.img(
                src=EditorState.current_image_b64,
                id="editor-img",
                style={
                    "display": "block",
                    "width": "100%",
                    "height": "auto",
                },
            ),
            rx.fragment(),
        ),
        # PDF overlay — use rx.el.img (native <img>) to avoid Next.js Image constraints
        rx.cond(
            EditorState.overlay_visible,
            rx.cond(
                EditorState.overlay_image_b64 != "",
                rx.el.img(
                    src=EditorState.overlay_image_b64,
                    style={
                        "position": "absolute", "top": "0", "left": "0",
                        "width": "100%", "height": "auto",
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
        # SVG overlay — absolutely positioned on top of the image
        rx.el.svg(
            # Grid dot pattern (defined in <defs>, applied via <rect>)
            rx.cond(
                EditorState.grid_visible,
                rx.fragment(
                    rx.el.svg.defs(
                        rx.el.svg.pattern(
                            rx.el.circle(
                                cx="0.5", cy="0.5", r="0.5",
                                fill="rgba(255,255,255,0.25)",
                            ),
                            id="grid-pattern",
                            custom_attrs={
                                "width": EditorState.grid_pattern_size,
                                "height": EditorState.grid_pattern_size,
                                "patternUnits": "userSpaceOnUse",
                                "x": EditorState.grid_offset_x,
                                "y": EditorState.grid_offset_y,
                            },
                        ),
                    ),
                    rx.el.rect(
                        x="0", y="0",
                        width="100%", height="100%",
                        fill="url(#grid-pattern)",
                        style={"pointer_events": "none"},
                    ),
                ),
                rx.fragment(),
            ),

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
            custom_attrs={
                "viewBox": EditorState.svg_viewbox,
                "preserveAspectRatio": "none",
            },
            style={
                "position": "absolute", "top": "0", "left": "0",
                "width": "100%", "height": "100%",
                "pointer_events": "all",
            },
        ),
        # JS bridge for coordinate conversion and zoom/pan
        _CANVAS_JS,
        id="editor-canvas",
        style={
            "position": "relative", "width": "100%",
            "margin": "auto 0",
            "transform_origin": "0 0",
        },
        background=COLORS["viewport"],
    )


# ---------------------------------------------------------------------------
# Viewport resize observer — tracks container dimensions for fit_zoom
# ---------------------------------------------------------------------------

def _viewport_resize_js() -> rx.Component:
    return rx.script("""
(function() {
    function dispatch(event, payload) {
        if (typeof window.applyEvent === 'function') {
            window.applyEvent(event, payload);
        }
    }
    function report(el) {
        dispatch('editor_state.set_viewport_size', {
            data: {w: Math.round(el.clientWidth), h: Math.round(el.clientHeight)}
        });
    }
    function setup() {
        const el = document.getElementById('viewport-container');
        if (!el) return;
        report(el);
        new ResizeObserver(function() { report(el); }).observe(el);
    }
    if (document.readyState === 'complete') setup();
    else window.addEventListener('load', setup);
})();
""")


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def _empty_state() -> rx.Component:
    """Centred Open/Create buttons shown when no project is loaded. Lives outside the transformed canvas."""
    return rx.cond(
        EditorState.current_image_b64 == "",
        rx.box(
            rx.flex(
                rx.button(
                    rx.flex(
                        rx.icon(tag="folder-open", style={"width": "80px", "height": "80px", "stroke_width": "1"}),
                        rx.text("Open Project", style={"font_family": FONT_MONO, "font_size": "18px", "margin_top": "8px"}),
                        direction="column",
                        align="center",
                    ),
                    variant="outline", size="4",
                    on_click=EditorState.open_open_project_modal,
                    style={
                        "color": COLORS["text_pri"],
                        "border_color": COLORS["panel_bdr"],
                        "cursor": "pointer",
                        "width": "180px",
                        "height": "180px",
                        "padding": "18px",
                    },
                ),
                rx.button(
                    rx.flex(
                        rx.icon(tag="folder-plus", style={"width": "80px", "height": "80px", "stroke_width": "1"}),
                        rx.text("Create Project", style={"font_family": FONT_MONO, "font_size": "18px", "margin_top": "8px"}),
                        direction="column",
                        align="center",
                    ),
                    variant="outline", size="4",
                    on_click=EditorState.open_create_project_modal,
                    style={
                        "color": COLORS["text_pri"],
                        "border_color": COLORS["panel_bdr"],
                        "cursor": "pointer",
                        "width": "180px",
                        "height": "180px",
                        "padding": "18px",
                    },
                ),
                gap="32px",
                align="center",
            ),
            style={
                "position": "absolute", "inset": "0",
                "display": "flex", "align_items": "center", "justify_content": "center",
                "z_index": "20",
            },
        ),
        rx.fragment(),
    )


def _tab_placeholder(title: str, description: str, icon_tag: str) -> rx.Component:
    """Placeholder content for tabs not yet implemented."""
    return rx.box(
        rx.flex(
            rx.icon(tag=icon_tag, style={"width": "48px", "height": "48px",
                                          "stroke_width": "1", "color": COLORS["text_dim"]}),
            rx.text(title, style={"font_family": FONT_MONO, "font_size": "18px",
                                   "color": COLORS["text_pri"], "margin_top": "12px"}),
            rx.text(description, style={"font_family": FONT_MONO, "font_size": "12px",
                                         "color": COLORS["text_dim"], "margin_top": "4px",
                                         "text_align": "center", "max_width": "400px"}),
            direction="column", align="center",
        ),
        style={
            "flex": "1",
            "display": "flex", "align_items": "center", "justify_content": "center",
        },
    )


def viewport() -> rx.Component:
    return rx.flex(
        # Pre-Simulation Checks — current HDR/AOI editor
        rx.cond(
            EditorState.active_tab == "pre_simulation",
            rx.flex(
                _top_toolbar(),
                rx.flex(
                    _svg_canvas(),
                    _overlay_align_panel(),
                    _zoom_indicator(),
                    _empty_state(),
                    _viewport_resize_js(),
                    id="viewport-container",
                    align="center",
                    justify="center",
                    style={"position": "relative", "flex": "1", "overflow": "hidden"},
                ),
                _progress_bar(),
                direction="column",
                style={"flex": "1", "overflow": "hidden"},
            ),
            rx.fragment(),
        ),
        # Model Validation
        rx.cond(
            EditorState.active_tab == "model_validation",
            _tab_placeholder(
                "Model Validation",
                "AcceleradRT preview, simulation boundary checks, and cleanup tools.",
                "shield-check",
            ),
            rx.fragment(),
        ),
        # Simulation Manager
        rx.cond(
            EditorState.active_tab == "simulation",
            _tab_placeholder(
                "Simulation Manager",
                "Connect to GCP VM, launch simulations, and stream results back to the project directory.",
                "cloud-cog",
            ),
            rx.fragment(),
        ),
        # Results Viewer
        rx.cond(
            EditorState.active_tab == "results",
            _tab_placeholder(
                "Results Viewer",
                "View HDR/TIFF results as they arrive, daylight factor analysis, and compliance reports.",
                "bar-chart-3",
            ),
            rx.fragment(),
        ),
        direction="column",
        style={"flex": "1", "overflow": "hidden"},
    )
