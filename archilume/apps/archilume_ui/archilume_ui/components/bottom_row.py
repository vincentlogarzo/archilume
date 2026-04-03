"""Bottom row — spec §8. Model validation, simulation manager, floor plan controls, room inspector."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, KBD_BADGE, PANEL_CARD, PANEL_CARD_TITLE


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
            "Floor Plan Underlay",
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
        _action_row("layers-2", "Switch Floor Plan", on_click=EditorState.toggle_overlay),
        style={**PANEL_CARD, "flex": "1", "min_width": "220px"},
        background=COLORS["panel_bg"],
        border="1px solid", border_color=COLORS["panel_bdr"],
    )


_ROOM_TYPES = ["BED", "LIVING", "NON-RESI", "CIRC"]


def _room_inspector() -> rx.Component:
    type_buttons = []
    for rtype in _ROOM_TYPES:
        type_buttons.append(
            rx.button(
                rtype, variant="outline", size="1",
                on_click=EditorState.set_room_type(rtype),
                style={"font_family": FONT_MONO, "font_size": "10px", "padding": "2px 5px"},
                color=rx.cond(EditorState.room_type_input == rtype, COLORS["accent"], COLORS["text_sec"]),
                border_color=rx.cond(EditorState.room_type_input == rtype, COLORS["accent"], COLORS["panel_bdr"]),
                background=rx.cond(EditorState.room_type_input == rtype, COLORS["btn_on"], COLORS["deep"]),
            )
        )
    return rx.box(
        rx.text(
            "Room Inspector",
            style={**PANEL_CARD_TITLE, "border_bottom": "1px solid"},
            color=COLORS["text_dim"],
            border_color=COLORS["panel_bdr"],
        ),
        rx.flex(
            # Left col: parent + name + type
            rx.flex(
                rx.flex(
                    rx.icon_button(rx.icon(tag="chevron-left", size=12), variant="ghost", size="1",
                                   on_click=lambda: EditorState.cycle_parent(-1)),
                    rx.input(
                        value=rx.cond(EditorState.selected_parent, EditorState.selected_parent, "(None)"),
                        on_change=EditorState.set_selected_parent,
                        style={"font_family": FONT_MONO, "font_size": "11px",
                               "text_align": "center", "flex": "1"},
                        size="1",
                    ),
                    rx.icon_button(rx.icon(tag="chevron-right", size=12), variant="ghost", size="1",
                                   on_click=lambda: EditorState.cycle_parent(1)),
                    align="center", gap="2px",
                ),
                rx.input(
                    value=EditorState.room_name_input,
                    on_change=EditorState.set_room_name,
                    placeholder="Room name",
                    style={"font_family": FONT_MONO, "font_size": "11px", "margin_top": "4px"},
                    size="1",
                ),
                rx.flex(*type_buttons, gap="3px", wrap="wrap", style={"margin_top": "4px"}),
                direction="column", style={"min_width": "180px"},
            ),
            # Right col: save/delete + status
            rx.flex(
                rx.button(
                    rx.icon(tag="save", size=13),
                    rx.text("Save", style={"font_family": FONT_MONO, "font_size": "11px"}),
                    rx.text("S", style=KBD_BADGE),
                    on_click=EditorState.save_room,
                    style={"gap": "4px", "background": "#d1fae5",
                           "color": "#065f46", "border": "1px solid #059669"},
                    size="1",
                ),
                rx.button(
                    rx.icon(tag="trash-2", size=13),
                    rx.text("Delete", style={"font_family": FONT_MONO, "font_size": "11px"}),
                    on_click=EditorState.delete_room,
                    style={"gap": "4px", "background": "#fee2e2",
                           "color": "#991b1b", "border": "1px solid #dc2626"},
                    size="1",
                ),
                rx.flex(
                    rx.box(style={"width": "6px", "height": "6px", "border_radius": "50%",
                                  "background": COLORS["accent2"], "flex_shrink": "0"}),
                    rx.text(EditorState.status_message,
                            style={"font_family": FONT_MONO, "font_size": "10px", "margin_left": "4px"},
                            color=COLORS["accent2"]),
                    align="center",
                    style={"margin_top": "4px", "padding": "4px 6px", "border_radius": "4px"},
                    background=COLORS["deep"],
                ),
                direction="column", gap="4px", style={"min_width": "120px"},
            ),
            gap="14px", style={"padding": "6px 8px"},
        ),
        style={**PANEL_CARD, "flex": "1", "min_width": "320px"},
        background=COLORS["panel_bg"],
        border="1px solid", border_color=COLORS["panel_bdr"],
    )


def bottom_row() -> rx.Component:
    return rx.flex(
        _model_validation(), _simulation_manager(), _floor_plan_controls(), _room_inspector(),
        gap="8px",
        style={"padding": "14px", "min_height": "160px", "overflow_x": "auto"},
        background=COLORS["sidebar"],
        border_top="1px solid", border_color=COLORS["panel_bdr"],
    )
