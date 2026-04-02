"""Bottom row — spec §8. Model validation, simulation manager, floor plan controls."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, PANEL_CARD, PANEL_CARD_TITLE


def _card(title: str, width: str, *children, **kw) -> rx.Component:
    return rx.box(
        rx.text(
            title,
            style={**PANEL_CARD_TITLE, "border_bottom": "1px solid"},
            color=COLORS["text_dim"],
            border_color=COLORS["panel_bdr"],
        ),
        *children,
        style={**PANEL_CARD, "width": width, "flex_shrink": "0"},
        background=COLORS["panel_bg"],
        border="1px solid", border_color=COLORS["panel_bdr"],
    )


def _action_row(icon: str, label: str, colour: str = "", on_click=None) -> rx.Component:
    c = colour or COLORS["text_dim"]
    return rx.flex(
        rx.icon(tag=icon, size=14, style={"color": c}),
        rx.text(label, style={"font_family": FONT_MONO, "font_size": "11px",
                               "color": COLORS["text_pri"], "margin_left": "6px"}),
        align="center", on_click=on_click,
        style={"padding": "4px 8px", "cursor": "pointer", "_hover": {"background": COLORS["hover"]}},
    )


def _model_validation() -> rx.Component:
    return _card(
        "Model Validation", "320px",
        _action_row("zap", "AcceleratedRT Preview", COLORS["accent"], on_click=EditorState.open_accelerad_modal),
        _action_row("scan-search", "Preview simulation boundary checks"),
        _action_row("brush", "Cleaning tools"),
        rx.box(
            rx.text("Done here before Sun Merger", style={
                "font_family": FONT_MONO, "font_size": "10px", "color": COLORS["accent2"],
            }),
            style={"background": "#eef4fe", "border_radius": "4px", "padding": "6px 8px", "margin": "6px 8px"},
        ),
    )


def _simulation_manager() -> rx.Component:
    return _card(
        "Simulation Manager", "280px",
        rx.box(
            rx.select(["Default", "Summer Solstice", "Winter Solstice", "Equinox"],
                      default_value="Default", size="1",
                      style={"font_family": FONT_MONO, "font_size": "11px"}),
            style={"padding": "6px 8px"},
        ),
        _action_row("circle-play", "Review Simulation"),
        _action_row("cloud-upload", "Connect to Cloud"),
        rx.flex(
            rx.select(["BESS", "Green Star", "NABERS", "EN 17037", "WELL"],
                      default_value="BESS", size="1",
                      style={"font_family": FONT_MONO, "font_size": "11px", "flex": "1"}),
            rx.icon_button(rx.icon(tag="heart", size=14), variant="ghost", size="1",
                           style={"color": COLORS["text_dim"]}),
            align="center", gap="4px", style={"padding": "4px 8px"},
        ),
    )


def _floor_plan_controls() -> rx.Component:
    return rx.box(
        rx.text(
            "Floor Plan Controls",
            style={**PANEL_CARD_TITLE, "border_bottom": "1px solid"},
            color=COLORS["text_dim"],
            border_color=COLORS["panel_bdr"],
        ),
        rx.box(
            rx.text("PDF Resolution", style={
                "font_family": FONT_MONO, "font_size": "9px", "text_transform": "uppercase",
                "color": COLORS["text_dim"], "margin_bottom": "4px",
            }),
            rx.radio_group(["72", "100", "150", "200", "300"], default_value="150",
                           direction="row", spacing="3", on_change=EditorState.set_overlay_dpi,
                           style={"font_family": FONT_MONO, "font_size": "11px"}),
            style={"padding": "6px 8px"},
        ),
        _action_row("rotate-ccw", "Reset Level Alignment", on_click=EditorState.reset_level_alignment),
        _action_row("layers-2", "Change AOI Level"),
        style={**PANEL_CARD, "flex": "1", "min_width": "220px"},
        background=COLORS["panel_bg"],
        border="1px solid", border_color=COLORS["panel_bdr"],
    )


def bottom_row() -> rx.Component:
    return rx.flex(
        _model_validation(), _simulation_manager(), _floor_plan_controls(),
        gap="8px",
        style={"padding": "10px", "min_height": "160px", "overflow_x": "auto"},
        background=COLORS["sidebar"],
        border_top="1px solid", border_color=COLORS["panel_bdr"],
    )
