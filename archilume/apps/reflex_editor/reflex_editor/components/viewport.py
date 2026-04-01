"""Viewport — spec §6. Canvas area with toolbar, plotly graph, and floating palettes."""

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
                           on_click=EditorState.navigate_hdr(-1)),
            rx.icon_button(rx.icon(tag="chevron-down", size=14),
                           variant="outline", size="1",
                           on_click=EditorState.navigate_hdr(1)),
            gap="2px",
        ),
        # Filename
        rx.text(
            rx.cond(
                EditorState.hdr_paths.length() > 0,
                "sample.hdr",  # TODO: derive from state
                "No images",
            ),
            style={"font_family": FONT_MONO, "font_size": "11px",
                    "color": COLORS["text_pri"], "margin_left": "8px"},
        ),
        # Variant toggle badge
        rx.button(
            rx.cond(EditorState.image_variant == "hdr", "HDR", "TIFF"),
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
            rx.cond(
                EditorState.hdr_paths.length() > 0,
                f"1 / {EditorState.hdr_paths.length()}",
                "",
            ),
            style={"font_family": FONT_MONO, "font_size": "10px",
                    "color": COLORS["text_dim"], "margin_left": "6px"},
        ),
        rx.spacer(),
        _toolbar_btn("undo", "Undo", "Ctrl+Z", on_click=EditorState.undo),
        _toolbar_btn("expand", "Fit", "F", on_click=EditorState.fit_zoom),
        _toolbar_btn("square-check", "Select All", "Ctrl+A",
                     on_click=EditorState.select_all_rooms),
        align="center",
        style={
            "background": COLORS["panel_bg"],
            "border_bottom": f"1px solid {COLORS['panel_bdr']}",
            "padding": "4px 8px",
            "gap": "4px",
        },
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
        row_style = {
            "padding": "4px 12px",
            "gap": "6px",
            "cursor": "pointer",
            "_hover": {"background": COLORS["hover"]},
        }
        if i < len(_PALETTE_TOOLS) - 1:
            row_style["border_bottom"] = f"1px solid {COLORS['panel_bdr']}"

        children = [
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
            "background": COLORS["panel_bg"],
            "border": f"1px solid {COLORS['panel_bdr']}",
            "border_radius": "8px",
            "box_shadow": "0 2px 8px rgba(0,0,0,0.08)",
            "min_width": "200px",
            "z_index": "10",
        },
    )


# ---------------------------------------------------------------------------
# §6.2.3 Overlay alignment panel
# ---------------------------------------------------------------------------

def _overlay_align_panel() -> rx.Component:
    def _field(label: str, step: float, default: float = 0):
        return rx.flex(
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "10px",
                                   "color": COLORS["text_dim"], "width": "60px"}),
            rx.input(
                type="number",
                default_value=str(default),
                step=str(step),
                style={"font_family": FONT_MONO, "font_size": "11px",
                        "width": "80px"},
                size="1",
            ),
            align="center", gap="4px",
        )

    return rx.cond(
        EditorState.overlay_align_mode,
        rx.box(
            rx.text("Overlay Alignment", style={
                "font_family": FONT_MONO, "font_size": "10px",
                "text_transform": "uppercase", "color": COLORS["text_dim"],
                "padding": "6px 8px",
                "border_bottom": f"1px solid {COLORS['panel_bdr']}",
            }),
            rx.flex(
                _field("Offset X", 1),
                _field("Offset Y", 1),
                _field("Scale X", 0.01, 1.0),
                _field("Scale Y", 0.01, 1.0),
                _field("Alpha", 0.05, 0.6),
                direction="column", gap="4px",
                style={"padding": "8px"},
            ),
            style={
                "position": "absolute",
                "top": "12px", "right": "12px",
                "background": COLORS["panel_bg"],
                "border": f"1px solid {COLORS['panel_bdr']}",
                "border_radius": "8px",
                "box_shadow": "0 2px 8px rgba(0,0,0,0.08)",
                "z_index": "10",
                "min_width": "180px",
            },
        ),
        rx.fragment(),
    )


# ---------------------------------------------------------------------------
# §6.2.4 Zoom indicator
# ---------------------------------------------------------------------------

def _zoom_indicator() -> rx.Component:
    return rx.text(
        EditorState.zoom_pct.to(str) + "%",
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


# ---------------------------------------------------------------------------
# §6.3 Progress bar
# ---------------------------------------------------------------------------

def _progress_bar() -> rx.Component:
    return rx.cond(
        EditorState.progress_visible,
        rx.box(
            rx.box(
                style={
                    "height": "100%",
                    "background": COLORS["accent"],
                    "width": EditorState.progress_pct.to(str) + "%",
                    "transition": "width 0.3s ease",
                },
            ),
            rx.text(
                EditorState.progress_msg,
                style={
                    "position": "absolute",
                    "inset": "0",
                    "display": "flex",
                    "align_items": "center",
                    "justify_content": "center",
                    "font_family": FONT_MONO,
                    "font_size": "10px",
                    "color": COLORS["text_pri"],
                },
            ),
            style={
                "position": "relative",
                "height": "18px",
                "background": COLORS["deep"],
                "border_top": f"1px solid {COLORS['panel_bdr']}",
            },
        ),
        rx.fragment(),
    )


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def viewport() -> rx.Component:
    return rx.flex(
        _top_toolbar(),
        # Canvas area
        rx.box(
            # Placeholder for plotly / interactive canvas
            rx.box(
                rx.text(
                    "Canvas — Plotly or HTML5 Canvas goes here",
                    style={"font_family": FONT_MONO, "font_size": "12px",
                            "color": COLORS["text_dim"]},
                ),
                style={
                    "width": "100%", "height": "100%",
                    "display": "flex", "align_items": "center",
                    "justify_content": "center",
                    "background": COLORS["viewport"],
                },
            ),
            _floating_palette(),
            _overlay_align_panel(),
            _zoom_indicator(),
            style={
                "position": "relative",
                "flex": "1",
                "overflow": "hidden",
            },
        ),
        _progress_bar(),
        direction="column",
        style={"flex": "1", "overflow": "hidden"},
    )
