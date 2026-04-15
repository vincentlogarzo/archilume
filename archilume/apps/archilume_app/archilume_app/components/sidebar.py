"""Left sidebar — spec §3. Fixed 52px vertical icon bar."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, SIDEBAR_DIVIDER


def _sidebar_btn(
    icon: str, tooltip: str, on_click=None, is_active=None,
) -> rx.Component:
    base_style = {
        "width": "48px", "height": "34px",
        "display": "flex", "align_items": "center", "justify_content": "center",
        "border_radius": "6px", "cursor": "pointer", "border": "none",
        "background": "transparent",
    }
    btn = rx.tooltip(
        rx.button(
            rx.icon(tag=icon, style={"width": "22px", "height": "22px", "stroke_width": "1.5"}),
            style=base_style,
            color=COLORS["text_sec"],
            _hover={"background": COLORS["hover"]},
            on_click=on_click,
        ),
        content=tooltip, side="right",
    )
    if is_active is None:
        return btn
    return rx.cond(
        is_active,
        rx.tooltip(
            rx.button(
                rx.icon(tag=icon, style={"width": "22px", "height": "22px", "stroke_width": "1.5"}),
                style=base_style,
                background=COLORS["sidebar_act"],
                color=COLORS["accent"],
                on_click=on_click,
            ),
            content=tooltip, side="right",
        ),
        btn,
    )


def _divider() -> rx.Component:
    return rx.box(
        style=SIDEBAR_DIVIDER,
        background=COLORS["panel_bdr"],
    )


def _annotation_slider() -> rx.Component:
    return rx.box(
        rx.text(
            "Aa",
            style={"font_family": FONT_MONO, "font_size": "18px",
                   "text_align": "center", "margin_bottom": "4px"},
            color=COLORS["text_dim"],
        ),
        rx.slider(
            default_value=[1.0], min=0.5, max=2.0, step=0.05,
            orientation="vertical",
            on_value_commit=EditorState.set_annotation_scale,
            style={"height": "80px"},
        ),
        style={"display": "flex", "flex_direction": "column",
               "align_items": "center", "padding": "4px 0"},
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.flex(
            _sidebar_btn("menu", "Toggle Project Browser",
                         on_click=EditorState.toggle_project_tree,
                         is_active=EditorState.project_tree_open),
            _sidebar_btn("folder-open", "Open Project",
                         on_click=EditorState.open_open_project_modal),
            _sidebar_btn("folder-plus", "Create New Project",
                         on_click=EditorState.open_create_project_modal),
            _divider(),
            _sidebar_btn("archive-restore", "Extract Archive",
                         on_click=EditorState.open_extract_modal),
            _sidebar_btn("file-bar-chart", "Export & Archive",
                         on_click=EditorState.run_export),
            _divider(),
            _sidebar_btn("crosshair", "DF% Placement [P]",
                         on_click=EditorState.toggle_df_placement,
                         is_active=EditorState.df_placement_mode),
            _sidebar_btn("pen-line", "Edit Mode [E]",
                         on_click=EditorState.toggle_edit_mode,
                         is_active=EditorState.edit_mode),
            _sidebar_btn("corner-down-right", "Ortho [O]",
                         on_click=EditorState.toggle_ortho,
                         is_active=EditorState.ortho_mode),
            _divider(),
            _annotation_slider(),
            _divider(),
            rx.spacer(),
            # Color mode toggle at the bottom
            rx.tooltip(
                rx.color_mode.button(size="1", variant="ghost"),
                content="Toggle Light / Dark Mode", side="right",
            ),
            _sidebar_btn("settings", "Project Settings",
                         on_click=EditorState.open_settings_modal),
            direction="column", align="center", gap="4px",
            style={"height": "100%", "padding": "6px 0"},
        ),
        style={
            "position": "fixed", "left": "0", "top": "0",
            "width": "52px", "height": "100vh", "z_index": "100",
        },
        background=COLORS["sidebar"],
        border_right="1px solid",
        border_color=COLORS["panel_bdr"],
    )
