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
        _toolbar_btn("expand", "Fit (F)", on_click=EditorState.fit_zoom),
        _toolbar_btn("zoom-in", "Reset Zoom (R)", on_click=EditorState.reset_zoom),
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
    def _field(label: str, step: str, value, on_change=None):
        return rx.flex(
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "11px",
                                   "color": COLORS["text_dim"], "width": "60px"}),
            rx.input(
                type="number",
                value=value,
                step=step,
                on_change=on_change,
                style={"font_family": FONT_MONO, "font_size": "11px", "width": "80px"},
                size="1",
            ),
            align="center", gap="4px",
        )

    return rx.cond(
        EditorState.overlay_align_mode,
        rx.box(
            rx.flex(
                rx.text("Overlay Alignment", style={
                    "font_family": FONT_MONO, "font_size": "11px",
                    "text_transform": "uppercase",
                    "color": COLORS["text_dim"],
                    "flex": "1",
                }),
                rx.icon_button(
                    rx.icon(tag="x", size=12),
                    variant="ghost", size="1",
                    on_click=EditorState.toggle_overlay_align,
                    style={"color": COLORS["text_dim"]},
                ),
                align="center", gap="4px",
                style={"padding": "6px 8px", "border_bottom": f"1px solid {COLORS['panel_bdr']}"},
            ),
            rx.flex(
                _field("Offset X", "1", EditorState.overlay_offset_x_str,
                       on_change=EditorState.set_overlay_offset_x),
                _field("Offset Y", "1", EditorState.overlay_offset_y_str,
                       on_change=EditorState.set_overlay_offset_y),
                _field("Scale", "0.01", EditorState.overlay_scale_str,
                       on_change=EditorState.set_overlay_scale),
                _field("Transp.", "0.05", EditorState.overlay_alpha_str,
                       on_change=EditorState.set_overlay_alpha),
                _field("Rotate °", "1", EditorState.overlay_rotation_deg_str,
                       on_change=EditorState.set_overlay_rotation_deg),
                direction="column", gap="4px",
                style={"padding": "8px"},
            ),
            rx.flex(
                rx.icon_button(
                    rx.icon(tag="rotate-ccw", size=12),
                    rx.text("Reset", style={"font_family": FONT_MONO, "font_size": "10px",
                                            "margin_left": "4px"}),
                    variant="ghost", size="1",
                    on_click=EditorState.reset_level_alignment,
                    style={"color": COLORS["text_dim"], "width": "100%",
                           "padding": "4px 8px", "cursor": "pointer",
                           "_hover": {"background": COLORS["hover"]}},
                ),
                style={"border_top": f"1px solid {COLORS['panel_bdr']}"},
            ),
            style={
                "position": "absolute",
                "top": "12px", "right": "12px",
                "border_radius": "8px",
                "box_shadow": "0 2px 8px rgba(0,0,0,0.08)",
                "z_index": "10",
                "min_width": "200px",
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


def _pixel_info_tooltip() -> rx.Component:
    """Floating tooltip that shows RGB values when zoomed in to pixel level."""
    return rx.el.div(
        id="pixel-info-tooltip",
        style={
            "display": "none",
            "position": "absolute",
            "pointer_events": "none",
            "z_index": "1000",
            "background": "rgba(30,30,30,0.92)",
            "color": "#fff",
            "font_family": FONT_MONO,
            "font_size": "11px",
            "padding": "4px 8px",
            "border_radius": "4px",
            "white_space": "nowrap",
            "border": "1px solid rgba(255,255,255,0.15)",
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

_TEXT_STROKE_STYLE = {
    "pointer_events": "none",
    "paint_order": "stroke",
    "stroke_linejoin": "round",
}


def _render_room(room: dict) -> rx.Component:
    """Render a single enriched room dict as SVG polygon + label + DF annotation.

    CIRC rooms: boundary only — labels and DF annotations suppressed (reduces clutter).
    DIV sub-rooms: dashed boundary at 60% opacity.
    Font sizes match the matplotlib editor hierarchy:
      - DF area result (line 0): base 8.5, coloured by percentage, stroke outline
      - DF threshold  (line 1): base 6.5, white, black stroke outline
      - Room name:               base 6.5, white (accent when selected), black stroke outline
    Stroke width scales inversely with zoom_level via EditorState.room_stroke_width.
    """
    return rx.fragment(
        rx.cond(
            room["is_div"],
            rx.el.svg.g(
                rx.el.svg.defs(
                    rx.el.svg.clip_path(
                        rx.el.polygon(points=room["vertices_str"]),
                        custom_attrs={"id": "clip-div-" + room["idx"].to(str)},
                    ),
                ),
                rx.el.polygon(
                    points=room["vertices_str"],
                    fill="none",
                    stroke=rx.cond(room["selected"], COLORS["room_stroke_selected"], COLORS["room_stroke_unselected"]),
                    stroke_width=EditorState.room_stroke_width,
                    stroke_dasharray="6,3",
                    opacity="0.7",
                    cursor=rx.cond(EditorState.df_placement_mode, "crosshair", "pointer"),
                    on_click=lambda e: EditorState.room_or_stamp_click(room["idx"], e),
                    custom_attrs={"clip-path": "url(#clip-div-" + room["idx"].to(str) + ")"},
                ),
            ),
            # Non-DIV branch: normal solid polygon
            rx.el.polygon(
                points=room["vertices_str"],
                fill=rx.cond(room["selected"], COLORS["room_fill_selected"], COLORS["room_fill_unselected"]),
                stroke=rx.cond(room["selected"], COLORS["room_stroke_selected"], COLORS["room_stroke_unselected"]),
                stroke_width=EditorState.room_stroke_width,
                cursor=rx.cond(EditorState.df_placement_mode, "crosshair", "pointer"),
                on_click=EditorState.room_or_stamp_click(room["idx"]),
            ),
        ),
        # DF line 0: area result (larger font, coloured by percentage) — suppressed for CIRC
        rx.cond(
            ~room["is_circ"] & room["has_df"] & (room["df_line_0"] != ""),
            rx.el.text(
                room["df_line_0"],
                x=room["label_x"],
                y=room["df_line_0_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill=room["df_line_0_color"],
                font_size=EditorState.df_area_font_size,
                font_weight=room["df_line_0_weight"],
                font_family="DM Mono, monospace",
                stroke=room["df_line_0_stroke"],
                stroke_width=room["df_line_0_stroke_w"],
                style=_TEXT_STROKE_STYLE,
            ),
            rx.fragment(),
        ),
        # DF line 1: threshold (smaller font, always white, black stroke) — suppressed for CIRC
        rx.cond(
            ~room["is_circ"] & room["has_df"] & (room["df_line_1"] != ""),
            rx.el.text(
                room["df_line_1"],
                x=room["label_x"],
                y=room["df_line_1_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill="white",
                font_size=EditorState.label_font_size,
                font_weight="normal",
                font_family="DM Mono, monospace",
                stroke="black",
                stroke_width=EditorState.label_stroke_width,
                style=_TEXT_STROKE_STYLE,
            ),
            rx.fragment(),
        ),
        # Room name label — suppressed for CIRC rooms
        rx.cond(
            ~room["is_circ"],
            rx.el.text(
                room["name"],
                x=room["label_x"],
                y=room["name_y"],
                text_anchor="middle",
                dominant_baseline="middle",
                fill=rx.cond(room["selected"], COLORS["accent"], "white"),
                font_size=EditorState.label_font_size,
                font_weight="normal",
                font_family="DM Mono, monospace",
                stroke="black",
                stroke_width=EditorState.label_stroke_width,
                style=_TEXT_STROKE_STYLE,
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
    """Render a DF% stamp dot + label (matching matplotlib editor style)."""
    return rx.fragment(
        # Cyan dot at stamped pixel
        rx.el.circle(
            cx=stamp["x"].to(str),
            cy=stamp["y"].to(str),
            r="4",
            fill=COLORS["df_stamp"],
        ),
        # Background rect for readability
        rx.el.rect(
            x=stamp["x"].to(str),
            y=(stamp["y"] - 16).to(str),
            width="80",
            height="22",
            rx="3",
            fill="#222222",
            opacity="0.8",
            style={"pointer_events": "none"},
        ),
        # DF value + pixel coords label
        rx.el.text(
            "DF:" + stamp["value"].to(str) + "% px(" + stamp["px"].to(str) + "," + stamp["py"].to(str) + ")",
            x=(stamp["x"] + 4).to(str),
            y=(stamp["y"] - 5).to(str),
            fill="white",
            font_size="8",
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
            var fn = window.applyEvent || window.__reflex?.['$/utils/state']?.applyEvent;
            if (typeof fn === 'function') fn('editor_state.sync_zoom', {
                data: {zoom: _zoom, pan_x: _panX, pan_y: _panY}
            });
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
        var fn = window.applyEvent || window.__reflex?.['$/utils/state']?.applyEvent;
        if (typeof fn === 'function') fn(event, payload);
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
    // Overlay scale — Ctrl+scroll in Adjust Plan Mode scales the PDF underlay
    // around its centre.  Pure JS for 60fps; debounce-syncs to Python.
    // ---------------------------------------------------------------------------
    var _overlaySyncTimer = null;

    function getOverlayImg() {
        // The overlay <img> has opacity < 1 and is not the editor-img
        var imgs = document.querySelectorAll('#viewport-container img:not(#editor-img)');
        for (var i = 0; i < imgs.length; i++) {
            if (parseFloat(window.getComputedStyle(imgs[i]).opacity) < 1) return imgs[i];
        }
        return null;
    }

    function parseOverlayTransform(img) {
        // Try inline style first (set by us after first scroll), then computed matrix
        var raw = img.style.transform || '';
        var t = {ox: 0, oy: 0, sx: 1, sy: 1, rot: 0};
        if (raw) {
            var m;
            m = raw.match(/translate\(\s*([-\d.]+)px\s*,\s*([-\d.]+)px\s*\)/);
            if (m) { t.ox = parseFloat(m[1]); t.oy = parseFloat(m[2]); }
            m = raw.match(/scale\(\s*([-\d.]+)\s*(?:,\s*([-\d.]+))?\s*\)/);
            if (m) { t.sx = parseFloat(m[1]); t.sy = m[2] !== undefined ? parseFloat(m[2]) : t.sx; }
            m = raw.match(/rotate\(\s*([-\d.]+)deg\s*\)/);
            if (m) { t.rot = parseFloat(m[1]); }
        } else {
            // Parse from computed matrix(a, b, c, d, tx, ty)
            var cs = window.getComputedStyle(img).transform;
            var mm = cs && cs.match(/matrix\(\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*,\s*([-\d.e]+)\s*\)/);
            if (mm) {
                t.sx = parseFloat(mm[1]);
                t.sy = parseFloat(mm[4]);
                t.ox = parseFloat(mm[5]);
                t.oy = parseFloat(mm[6]);
            }
        }
        return t;
    }

    function applyOverlayTransform(img, t) {
        img.style.transform = 'translate(' + t.ox + 'px, ' + t.oy + 'px) scale(' + t.sx + ', ' + t.sy + ') rotate(' + t.rot + 'deg)';
    }

    function scheduleOverlaySync(t) {
        if (_overlaySyncTimer) clearTimeout(_overlaySyncTimer);
        _overlaySyncTimer = setTimeout(function() {
            dispatch('editor_state.sync_overlay_transform', {
                data: {
                    offset_x: Math.round(t.ox),
                    offset_y: Math.round(t.oy),
                    scale_x: Math.round(t.sx * 1000000) / 1000000,
                    scale_y: Math.round(t.sy * 1000000) / 1000000,
                }
            });
            // Clear inline override after a short delay so the Reflex CSS
            // class (updated by the state sync) takes back control.
            setTimeout(function() {
                var img = getOverlayImg();
                if (img) img.style.transform = '';
            }, 350);
        }, 250);
    }

    // ---------------------------------------------------------------------------
    // Scroll-wheel zoom + trackpad pinch (ctrlKey=true)
    // Runs entirely in JS — no Python round-trip.
    // ---------------------------------------------------------------------------
    document.addEventListener('wheel', function(e) {
        if (!isOverViewport(e)) return;
        e.preventDefault();

        var container = document.getElementById('viewport-container');

        // Ctrl+scroll in Adjust Plan Mode → scale overlay, not canvas
        if (e.ctrlKey && container && container.dataset.overlayAlign === 'true') {
            var overlayImg = getOverlayImg();
            if (overlayImg) {
                var t = parseOverlayTransform(overlayImg);
                var factor = e.deltaY > 0 ? 0.95 : 1.05;
                var newS = t.sx * factor;
                // Scale around centre: adjust offset so centre stays fixed
                var rect = container.getBoundingClientRect();
                var halfW = rect.width / 2;
                var halfH = rect.height / 2;
                t.ox = t.ox + halfW * (t.sx - newS);
                t.oy = t.oy + halfH * (t.sy - newS);
                t.sx = newS;
                t.sy = newS;
                applyOverlayTransform(overlayImg, t);
                scheduleOverlaySync(t);
                return;
            }
        }

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
        var newZoom = Math.max(0.1, Math.min(200.0, _zoom * factor));

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
    // Pixel inspector — shows RGB values when zoomed in to pixel level
    // ---------------------------------------------------------------------------
    var _pixelCanvas = null;
    var _pixelCtx = null;
    var _pixelImgLoaded = false;
    var _pixelImgSrc = '';
    var PIXEL_ZOOM_THRESHOLD = 15.0;

    function ensurePixelCanvas() {
        var img = document.getElementById('editor-img');
        if (!img || !img.naturalWidth) { _pixelImgLoaded = false; return null; }
        if (_pixelCanvas && _pixelImgSrc === img.src && _pixelImgLoaded) return _pixelCtx;
        _pixelCanvas = document.createElement('canvas');
        _pixelCanvas.width = img.naturalWidth;
        _pixelCanvas.height = img.naturalHeight;
        _pixelCtx = _pixelCanvas.getContext('2d', {willReadFrequently: true});
        _pixelCtx.drawImage(img, 0, 0);
        _pixelImgSrc = img.src;
        _pixelImgLoaded = true;
        return _pixelCtx;
    }

    document.addEventListener('mousemove', function(e) {
        var tip = document.getElementById('pixel-info-tooltip');
        if (!tip) return;
        if (_zoom < PIXEL_ZOOM_THRESHOLD) { tip.style.display = 'none'; return; }
        var container = document.getElementById('viewport-container');
        if (!container || !container.contains(e.target)) { tip.style.display = 'none'; return; }

        var rect = container.getBoundingClientRect();
        var cx = e.clientX - rect.left;
        var cy = e.clientY - rect.top;
        var imgX = Math.floor((cx - _panX) / _zoom);
        var imgY = Math.floor((cy - _panY) / _zoom);

        var ctx = ensurePixelCanvas();
        if (!ctx) { tip.style.display = 'none'; return; }
        if (imgX < 0 || imgY < 0 || imgX >= _pixelCanvas.width || imgY >= _pixelCanvas.height) {
            tip.style.display = 'none'; return;
        }

        var px = ctx.getImageData(imgX, imgY, 1, 1).data;
        tip.textContent = 'R:' + px[0] + ' G:' + px[1] + ' B:' + px[2] + '  [' + imgX + ',' + imgY + ']';
        tip.style.display = 'block';
        tip.style.left = (cx + 16) + 'px';
        tip.style.top = (cy - 28) + 'px';
    });

    // Hide tooltip when leaving the viewport
    document.addEventListener('mouseleave', function() {
        var tip = document.getElementById('pixel-info-tooltip');
        if (tip) tip.style.display = 'none';
    });

    // Invalidate pixel canvas when image changes
    var _imgObserver = new MutationObserver(function() { _pixelImgLoaded = false; });
    (function watchImg() {
        var img = document.getElementById('editor-img');
        if (img) _imgObserver.observe(img, {attributes: true, attributeFilter: ['src']});
        else setTimeout(watchImg, 500);
    })();

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
                    "image_rendering": "pixelated",
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

            # DF cursor tag — follows mouse when placement mode is active
            rx.cond(
                EditorState.df_cursor_label != "",
                rx.fragment(
                    rx.el.rect(
                        x=(EditorState.mouse_x + 12).to(str),
                        y=(EditorState.mouse_y - 20).to(str),
                        width="120",
                        height="18",
                        rx="3",
                        fill="#222222",
                        opacity="0.85",
                        style={"pointer_events": "none"},
                    ),
                    rx.el.text(
                        EditorState.df_cursor_label,
                        x=(EditorState.mouse_x + 16).to(str),
                        y=(EditorState.mouse_y - 8).to(str),
                        fill="white",
                        font_size="10",
                        font_family="DM Mono, monospace",
                        dominant_baseline="middle",
                        style={"pointer_events": "none"},
                    ),
                ),
                rx.fragment(),
            ),

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
        var fn = window.applyEvent || window.__reflex?.['$/utils/state']?.applyEvent;
        if (typeof fn === 'function') fn(event, payload);
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
    """Centred Open/Create buttons shown in Results Viewer when no image is loaded."""
    return rx.cond(
        EditorState.current_image_b64 == "",
        _empty_state_buttons(),
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


def _tab_with_no_project_gate(placeholder: rx.Component) -> rx.Component:
    """Wraps a tab placeholder: shows Open/Create project buttons when no project is loaded."""
    return rx.cond(
        EditorState.project == "",
        rx.box(
            _empty_state_buttons(),
            style={"flex": "1", "position": "relative", "overflow": "hidden"},
        ),
        placeholder,
    )


def _empty_state_buttons() -> rx.Component:
    """Centred Open/Create buttons — reusable across all tabs."""
    return rx.box(
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
    )


def viewport() -> rx.Component:
    return rx.flex(
        # Pre-Simulation Checks — room boundary editing (no HDR viewing)
        rx.cond(
            EditorState.active_tab == "pre_simulation",
            _tab_with_no_project_gate(
                _tab_placeholder(
                    "Pre-Simulation Checks",
                    "Room boundary editing, AOI setup, and simulation preparation tools.",
                    "ruler",
                ),
            ),
            rx.fragment(),
        ),
        # Simulation Manager
        rx.cond(
            EditorState.active_tab == "simulation",
            _tab_with_no_project_gate(
                _tab_placeholder(
                    "Simulation Manager",
                    "Connect to GCP VM, launch simulations, and stream results back to the project directory.",
                    "cloud-cog",
                ),
            ),
            rx.fragment(),
        ),
        # Results Viewer — HDR/AOI editor
        rx.cond(
            EditorState.active_tab == "results",
            rx.flex(
                _top_toolbar(),
                rx.flex(
                    _svg_canvas(),
                    _overlay_align_panel(),
                    _zoom_indicator(),
                    _pixel_info_tooltip(),
                    _empty_state(),
                    _viewport_resize_js(),
                    id="viewport-container",
                    align="center",
                    justify="center",
                    data_overlay_align=rx.cond(
                        EditorState.overlay_align_mode & EditorState.overlay_visible,
                        "true", "false",
                    ),
                    style={"position": "relative", "flex": "1", "overflow": "hidden"},
                ),
                _progress_bar(),
                direction="column",
                style={"flex": "1", "overflow": "hidden"},
            ),
            rx.fragment(),
        ),
        direction="column",
        style={"flex": "1", "overflow": "hidden"},
    )
