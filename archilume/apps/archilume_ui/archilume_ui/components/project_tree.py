"""Project tree panel — spec §5. Hierarchical room/image tree."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PROJECT_TREE_WIDTH


def _tree_header() -> rx.Component:
    return rx.flex(
        rx.text(
            "Project Browser",
            style={"font_family": FONT_MONO, "font_size": "10px",
                   "text_transform": "uppercase", "letter_spacing": "0.08em"},
            color=COLORS["text_dim"],
        ),
        rx.spacer(),
        align="center",
        style={"padding": "8px 10px"},
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )


def _render_hdr_node(hdr: dict) -> rx.Component:
    """HDR file entry."""
    return rx.flex(
        rx.icon(tag="chevron-down", size=12, color=COLORS["text_dim"]),
        rx.icon(tag="image", size=13, color=COLORS["text_sec"]),
        rx.text(
            hdr["name"],
            style={"font_family": FONT_MONO, "font_size": "11px",
                   "overflow": "hidden", "text_overflow": "ellipsis", "white_space": "nowrap"},
            color=COLORS["text_pri"],
        ),
        rx.cond(
            hdr["tiff_paths"].length() > 0,
            rx.text(
                "+" + hdr["tiff_paths"].length().to(str),
                style={"font_family": FONT_MONO, "font_size": "9px"},
                color=COLORS["text_dim"],
            ),
            rx.fragment(),
        ),
        align="center", gap="4px",
        style={"padding": "4px 10px", "cursor": "pointer"},
        _hover={"background": COLORS["hover"]},
    )


def _render_room_node(room: dict) -> rx.Component:
    """Room entry in the tree."""
    return rx.flex(
        rx.box(style={"width": "28px"}),
        rx.icon(
            tag=rx.cond(room["parent"] != "", "square", "box"),
            size=12, color=COLORS["text_sec"],
        ),
        rx.text(
            room["name"],
            style={"font_family": FONT_MONO, "font_size": "11px",
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "white_space": "nowrap", "flex": "1"},
            color=rx.cond(room["selected"], COLORS["accent"], COLORS["text_pri"]),
        ),
        rx.cond(
            room["room_type"] != "",
            rx.badge(
                room["room_type"],
                style={"font_family": FONT_MONO, "font_size": "9px", "padding": "0 4px"},
                color=COLORS["accent2"], background=COLORS["deep"],
                border="1px solid", border_color=COLORS["panel_bdr"],
            ),
            rx.fragment(),
        ),
        rx.icon(tag="eye", size=12, color=COLORS["text_dim"], style={"cursor": "pointer"}),
        rx.icon(
            tag="settings-2", size=12, color=COLORS["text_dim"],
            style={"cursor": "pointer"},
            on_click=EditorState.select_room(room["idx"]),
        ),
        align="center", gap="4px",
        style={"padding": "3px 10px", "cursor": "pointer"},
        background=rx.cond(room["selected"], COLORS["hover"], "transparent"),
        _hover={"background": COLORS["hover"]},
        on_click=EditorState.select_room(room["idx"]),
    )


def project_tree() -> rx.Component:
    return rx.cond(
        EditorState.project_tree_open,
        rx.box(
            _tree_header(),
            rx.box(
                rx.foreach(EditorState.hdr_files, _render_hdr_node),
                rx.foreach(EditorState.enriched_rooms, _render_room_node),
                style={"overflow_y": "auto", "flex": "1"},
            ),
            style={"width": PROJECT_TREE_WIDTH, "min_width": "200px",
                   "display": "flex", "flex_direction": "column"},
            background=COLORS["panel_bg"],
            border_right="1px solid", border_color=COLORS["panel_bdr"],
        ),
        rx.fragment(),
    )
