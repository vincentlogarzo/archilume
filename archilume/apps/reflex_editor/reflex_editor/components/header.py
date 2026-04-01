"""Header bar — spec §4. 46px top bar."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_HEAD, FONT_MONO, KBD_BADGE


def _mode_badge(label: str, fg: str, bg: str, border: str, visible) -> rx.Component:
    return rx.cond(
        visible,
        rx.badge(
            label,
            style={
                "font_family": FONT_MONO,
                "font_size": "10px",
                "color": fg,
                "background": bg,
                "border": f"1px solid {border}",
                "border_radius": "3px",
                "padding": "1px 6px",
            },
        ),
        rx.fragment(),
    )


def header() -> rx.Component:
    return rx.flex(
        # Logo
        rx.text(
            "Archilume",
            style={
                "font_family": FONT_HEAD,
                "font_weight": "700",
                "font_size": "17px",
                "letter_spacing": "-0.02em",
                "color": COLORS["text_pri"],
                "white_space": "nowrap",
            },
        ),
        # Divider
        rx.box(style={
            "width": "1px", "height": "18px",
            "background": COLORS["panel_bdr"], "margin": "0 12px",
        }),
        # Workflow label
        rx.text(
            "HDR AOI Editor",
            style={"font_family": FONT_MONO, "font_size": "11px",
                    "color": COLORS["text_sec"], "white_space": "nowrap"},
        ),
        # Project badge
        rx.badge(
            rx.cond(EditorState.project, EditorState.project, "No project loaded"),
            style={
                "font_family": FONT_MONO, "font_size": "10px",
                "background": COLORS["deep"],
                "border": f"1px solid {COLORS['panel_bdr']}",
                "border_radius": "3px",
                "padding": "1px 6px",
                "margin_left": "8px",
                "color": COLORS["text_sec"],
            },
        ),
        # Mode badges
        _mode_badge("DRAW", COLORS["accent"], COLORS["btn_on"],
                     COLORS["accent"], EditorState.draw_mode),
        _mode_badge("EDIT", "#92400e", "#fef3c7",
                     COLORS["warning"], EditorState.edit_mode),
        _mode_badge("DIVIDER", "#1e40af", "#dbeafe",
                     COLORS["accent2"], EditorState.divider_mode),
        rx.spacer(),
        # Shortcuts button
        rx.button(
            rx.icon(tag="keyboard", size=14),
            rx.text("Shortcuts", style={"font_family": FONT_MONO,
                                         "font_size": "11px", "margin_left": "4px"}),
            variant="ghost",
            size="1",
            on_click=EditorState.open_shortcuts_modal,
            style={"color": COLORS["text_sec"]},
        ),
        align="center",
        style={
            "height": "46px",
            "background": COLORS["header"],
            "border_bottom": f"1px solid {COLORS['panel_bdr']}",
            "padding": "0 16px",
            "gap": "4px",
        },
    )
