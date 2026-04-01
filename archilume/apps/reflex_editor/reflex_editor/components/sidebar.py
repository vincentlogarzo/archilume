"""Left sidebar — spec §3. Fixed 52px vertical icon bar."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, SIDEBAR_DIVIDER


def _sidebar_btn(
    icon: str,
    tooltip: str,
    on_click=None,
    is_active=None,
) -> rx.Component:
    """Single sidebar icon button with tooltip."""
    base_style = {
        "width": "48px",
        "height": "38px",
        "display": "flex",
        "align_items": "center",
        "justify_content": "center",
        "border_radius": "6px",
        "cursor": "pointer",
        "border": "none",
        "background": "transparent",
        "color": COLORS["text_sec"],
        "_hover": {"background": COLORS["hover"]},
    }
    btn = rx.tooltip(
        rx.button(
            rx.icon(tag=icon, size=20),
            style=base_style,
            on_click=on_click,
        ),
        content=tooltip,
        side="right",
    )
    return rx.cond(
        is_active,
        rx.tooltip(
            rx.button(
                rx.icon(tag=icon, size=20),
                style={
                    **base_style,
                    "background": COLORS["sidebar_act"],
                    "color": COLORS["accent"],
                },
                on_click=on_click,
            ),
            content=tooltip,
            side="right",
        ),
        btn,
    ) if is_active is not None else btn


def _divider() -> rx.Component:
    return rx.box(style=SIDEBAR_DIVIDER)


def _annotation_slider() -> rx.Component:
    return rx.box(
        rx.text(
            "Aa",
            style={
                "font_family": FONT_MONO,
                "font_size": "9px",
                "color": COLORS["text_dim"],
                "text_align": "center",
                "margin_bottom": "4px",
            },
        ),
        rx.slider(
            default_value=[1.0],
            min=0.5,
            max=2.0,
            step=0.05,
            orientation="vertical",
            on_value_commit=EditorState.set_annotation_scale,
            style={"height": "80px"},
        ),
        style={
            "display": "flex",
            "flex_direction": "column",
            "align_items": "center",
            "padding": "4px 0",
        },
    )


def sidebar() -> rx.Component:
    """Full left sidebar."""
    return rx.box(
        rx.flex(
            # -- Navigation group --
            _sidebar_btn("menu", "Toggle Project Browser",
                         on_click=EditorState.toggle_project_tree,
                         is_active=EditorState.project_tree_open),
            _sidebar_btn("folder-open", "Open Project",
                         on_click=EditorState.open_open_project_modal),
            _sidebar_btn("folder-plus", "Create New Project",
                         on_click=EditorState.open_create_project_modal),
            _divider(),
            # -- Archive group --
            _sidebar_btn("archive-restore", "Extract Archive",
                         on_click=EditorState.open_extract_modal),
            _sidebar_btn("file-bar-chart", "Export & Archive"),
            _divider(),
            # -- Floor plan group --
            _sidebar_btn("layout-panel-top", "Floor Plan: OFF",
                         on_click=EditorState.toggle_overlay,
                         is_active=EditorState.overlay_visible),
            _sidebar_btn("refresh-cw", "Change Floor Plan Page"),
            _sidebar_btn("maximize", "Resize Plan Mode: OFF",
                         on_click=EditorState.toggle_overlay_align,
                         is_active=EditorState.overlay_align_mode),
            _divider(),
            # -- Image / view group --
            _sidebar_btn("layers", "Toggle Image Layers [T]",
                         on_click=EditorState.toggle_show_image,
                         is_active=EditorState.show_image),
            _sidebar_btn("zoom-in", "Reset Zoom [R]",
                         on_click=EditorState.reset_zoom),
            _divider(),
            # -- Drawing tools --
            _sidebar_btn("crosshair", "DF% Placement: OFF [P]",
                         on_click=EditorState.toggle_df_placement,
                         is_active=EditorState.df_placement_mode),
            _sidebar_btn("pen-line", "Boundary Edit Mode: OFF [E]",
                         on_click=EditorState.toggle_edit_mode,
                         is_active=EditorState.edit_mode),
            _sidebar_btn("corner-down-right", "Ortho Lines: ON [O]",
                         on_click=EditorState.toggle_ortho,
                         is_active=EditorState.ortho_lines),
            _divider(),
            # -- Annotation slider --
            _annotation_slider(),
            _divider(),
            # -- Spacer --
            rx.spacer(),
            # -- Bottom group --
            _sidebar_btn("clock-3", "History"),
            _sidebar_btn("settings-2", "Settings"),
            direction="column",
            align="center",
            style={"height": "100%", "padding": "6px 0"},
        ),
        style={
            "position": "fixed",
            "left": "0",
            "top": "0",
            "width": "52px",
            "height": "100vh",
            "background": COLORS["sidebar"],
            "border_right": f"1px solid {COLORS['panel_bdr']}",
            "z_index": "100",
        },
    )
