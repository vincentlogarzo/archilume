"""VS Code-style collapsible accordion sections for the left panel."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PANEL_CARD_TITLE


# ---------------------------------------------------------------------------
# Reusable accordion section header
# ---------------------------------------------------------------------------

def _section_header(title: str, is_open: rx.Var[bool], on_toggle) -> rx.Component:
    return rx.flex(
        rx.icon(
            tag=rx.cond(is_open, "chevron-down", "chevron-right"),
            size=12,
            style={"color": COLORS["text_dim"], "flex_shrink": "0"},
        ),
        rx.text(
            title,
            style={
                **PANEL_CARD_TITLE,
                "padding": "0",
                "margin_left": "4px",
            },
            color=COLORS["text_dim"],
        ),
        on_click=on_toggle,
        align="center",
        style={
            "padding": "5px 8px",
            "cursor": "pointer",
            "border_top": "1px solid",
            "border_color": COLORS["panel_bdr"],
            "_hover": {"background": COLORS["hover"]},
        },
    )


# ---------------------------------------------------------------------------
# Floor Plan Underlay section
# ---------------------------------------------------------------------------

def _floor_plan_body() -> rx.Component:
    btn_style = {
        "font_family": FONT_MONO, "font_size": "11px",
        "padding": "3px 8px", "cursor": "pointer",
        "display": "flex", "align_items": "center", "gap": "5px",
        "_hover": {"background": COLORS["hover"]},
    }

    return rx.box(
        # Show / Hide / Attach Floor Plan
        rx.flex(
            rx.icon(
                tag=rx.cond(EditorState.overlay_has_pdf, "layout-panel-top", "file-up"),
                size=13,
            ),
            rx.text(
                rx.cond(
                    EditorState.overlay_has_pdf,
                    rx.cond(EditorState.overlay_visible, "Hide Floor Plan", "Show Floor Plan"),
                    "Attach Floor Plan",
                ),
                style={"font_family": FONT_MONO, "font_size": "11px", "margin_left": "5px"},
            ),
            on_click=EditorState.toggle_overlay,
            style={
                **btn_style,
                "background": rx.cond(EditorState.overlay_visible, COLORS["btn_on"], "transparent"),
            },
            color=rx.cond(EditorState.overlay_visible, COLORS["accent"], COLORS["text_dim"]),
        ),
        # DPI cycle button
        rx.tooltip(
            rx.flex(
                rx.icon(tag="image", size=13),
                rx.text(
                    "Plan Resolution: ",
                    rx.text.span(EditorState.overlay_dpi.to_string(), style={"color": COLORS["accent"]}),
                    style={"font_family": FONT_MONO, "font_size": "11px", "margin_left": "5px"},
                ),
                on_click=EditorState.cycle_overlay_dpi,
                style=btn_style,
                color=COLORS["text_dim"],
            ),
            content="Click to cycle: 72 → 100 → 150 → 200 → 300 dpi",
        ),
        # Adjust Plan Mode
        rx.flex(
            rx.icon(tag="maximize", size=13),
            rx.text("Adjust Plan Mode", style={"font_family": FONT_MONO, "font_size": "11px", "margin_left": "5px"}),
            on_click=EditorState.toggle_overlay_align,
            style={
                **btn_style,
                "background": rx.cond(EditorState.overlay_align_mode, COLORS["btn_on"], "transparent"),
            },
            color=rx.cond(EditorState.overlay_align_mode, COLORS["accent"], COLORS["text_dim"]),
        ),
        style={"padding": "2px 0", "padding_left": "16px"},
    )


def floor_plan_section() -> rx.Component:
    return rx.box(
        _section_header(
            "Floor Plan Underlay",
            EditorState.floor_plan_section_open,
            EditorState.toggle_floor_plan_section,
        ),
        rx.cond(EditorState.floor_plan_section_open, _floor_plan_body(), rx.fragment()),
    )


