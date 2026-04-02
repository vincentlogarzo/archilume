"""Header bar — spec §4. 46px top bar."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_HEAD, FONT_MONO


def _mode_badge(label: str, fg: str, bg: str, border_col: str, visible) -> rx.Component:
    return rx.cond(
        visible,
        rx.badge(
            label,
            style={"font_family": FONT_MONO, "font_size": "10px",
                   "border_radius": "3px", "padding": "1px 6px"},
            color=fg, background=bg, border="1px solid", border_color=border_col,
        ),
        rx.fragment(),
    )


def header() -> rx.Component:
    return rx.flex(
        rx.text(
            "Archilume",
            style={"font_family": FONT_HEAD, "font_weight": "700", "font_size": "17px",
                   "letter_spacing": "-0.02em", "white_space": "nowrap"},
            color=COLORS["text_pri"],
        ),
        rx.box(
            style={"width": "1px", "height": "18px", "margin": "0 12px"},
            background=COLORS["panel_bdr"],
        ),
        rx.text(
            "HDR AOI Editor",
            style={"font_family": FONT_MONO, "font_size": "11px", "white_space": "nowrap"},
            color=COLORS["text_sec"],
        ),
        rx.badge(
            rx.cond(EditorState.project, EditorState.project, "No project loaded"),
            style={"font_family": FONT_MONO, "font_size": "10px",
                   "border_radius": "3px", "padding": "1px 6px", "margin_left": "8px"},
            background=COLORS["deep"],
            border="1px solid", border_color=COLORS["panel_bdr"],
            color=COLORS["text_sec"],
        ),
        _mode_badge("DRAW", COLORS["accent"], COLORS["btn_on"], COLORS["accent"], EditorState.draw_mode),
        _mode_badge("EDIT", "#92400e", "#fef3c7", COLORS["warning"], EditorState.edit_mode),
        _mode_badge("DIVIDER", "#1e40af", "#dbeafe", COLORS["accent2"], EditorState.divider_mode),
        rx.spacer(),
        rx.cond(
            EditorState.has_multi_selection,
            rx.badge(
                EditorState.multi_selection_count.to(str) + " rooms selected",
                style={"font_family": FONT_MONO, "font_size": "10px", "padding": "1px 6px"},
                color=COLORS["accent2"], background="#eef4fe",
                border="1px solid", border_color=COLORS["accent2"],
            ),
            rx.fragment(),
        ),
        rx.button(
            rx.icon(tag="keyboard", size=14),
            rx.text("Shortcuts", style={"font_family": FONT_MONO, "font_size": "11px", "margin_left": "4px"}),
            variant="ghost", size="1", on_click=EditorState.open_shortcuts_modal,
            color=COLORS["text_sec"],
        ),
        rx.color_mode.button(size="1", variant="ghost"),
        align="center",
        style={"height": "46px", "padding": "0 16px", "gap": "4px"},
        background=COLORS["header"],
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )
