"""Project tree panel — spec §5. Collapsible 260px left panel."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PANEL_CARD_TITLE, PROJECT_TREE_WIDTH


def project_tree() -> rx.Component:
    """Conditionally rendered project browser panel."""
    return rx.cond(
        EditorState.project_tree_open,
        rx.box(
            # Header row
            rx.flex(
                rx.text("Project Browser", style=PANEL_CARD_TITLE),
                rx.spacer(),
                rx.icon_button(
                    rx.icon(tag="unfold-horizontal", size=14),
                    variant="ghost", size="1",
                    style={"color": COLORS["text_dim"]},
                ),
                rx.icon_button(
                    rx.icon(tag="fold-horizontal", size=14),
                    variant="ghost", size="1",
                    style={"color": COLORS["text_dim"]},
                ),
                align="center",
                style={"padding": "6px 8px",
                        "border_bottom": f"1px solid {COLORS['panel_bdr']}"},
            ),
            # Tree body — placeholder
            rx.box(
                rx.text(
                    "No project loaded",
                    style={
                        "font_family": FONT_MONO,
                        "font_size": "11px",
                        "color": COLORS["text_dim"],
                        "padding": "16px",
                        "text_align": "center",
                    },
                ),
                style={"flex": "1", "overflow_y": "auto"},
            ),
            # Footer — AOI level indicator
            rx.flex(
                rx.icon(tag="layers-2", size=14,
                        style={"color": COLORS["text_dim"]}),
                rx.text("Level: —",
                        style={"font_family": FONT_MONO, "font_size": "10px",
                                "color": COLORS["text_dim"], "margin_left": "4px"}),
                rx.spacer(),
                rx.button(
                    "Change",
                    variant="outline", size="1",
                    style={"font_family": FONT_MONO, "font_size": "10px",
                            "color": COLORS["accent2"],
                            "border_color": COLORS["panel_bdr"]},
                ),
                align="center",
                style={"padding": "6px 8px",
                        "border_top": f"1px solid {COLORS['panel_bdr']}"},
            ),
            style={
                "width": PROJECT_TREE_WIDTH,
                "min_width": "240px",
                "max_width": "300px",
                "background": COLORS["panel_bg"],
                "border_right": f"1px solid {COLORS['panel_bdr']}",
                "display": "flex",
                "flex_direction": "column",
            },
        ),
        rx.fragment(),
    )
