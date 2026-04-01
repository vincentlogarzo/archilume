"""Right panel — spec §7. 220px property inspector."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO, KBD_BADGE, PANEL_CARD, PANEL_CARD_TITLE, RIGHT_PANEL_WIDTH


# ---------------------------------------------------------------------------
# §7.1 Panel cards
# ---------------------------------------------------------------------------

def _card(title: str, *children) -> rx.Component:
    return rx.box(
        rx.text(title, style=PANEL_CARD_TITLE),
        *children,
        style=PANEL_CARD,
    )


def _parent_card() -> rx.Component:
    return _card(
        "Parent Apartment",
        rx.flex(
            rx.icon_button(rx.icon(tag="chevron-left", size=14),
                           variant="ghost", size="1",
                           on_click=EditorState.cycle_parent(-1)),
            rx.input(
                value=rx.cond(EditorState.selected_parent,
                              EditorState.selected_parent, "(None)"),
                on_change=EditorState.set_selected_parent,
                style={"font_family": FONT_MONO, "font_size": "11px",
                        "text_align": "center", "flex": "1"},
                size="1",
            ),
            rx.icon_button(rx.icon(tag="chevron-right", size=14),
                           variant="ghost", size="1",
                           on_click=EditorState.cycle_parent(1)),
            align="center",
            style={"padding": "6px"},
        ),
    )


def _room_name_card() -> rx.Component:
    return _card(
        "Room Name",
        rx.box(
            rx.input(
                placeholder="e.g. BED1 → U101_BED1",
                style={"font_family": FONT_MONO, "font_size": "11px"},
                size="1",
            ),
            rx.text(
                "Preview: —",
                style={"font_family": FONT_MONO, "font_size": "10px",
                        "color": COLORS["accent2"], "margin_top": "4px"},
            ),
            style={"padding": "6px"},
        ),
    )


_ROOM_TYPES = ["BED", "LIVING", "NON-RESI", "CIRC"]


def _room_type_card() -> rx.Component:
    buttons = []
    for rtype in _ROOM_TYPES:
        buttons.append(
            rx.button(
                rtype,
                variant="outline", size="1",
                style={
                    "font_family": FONT_MONO,
                    "font_size": "10px",
                    "padding": "3px 6px",
                    "border_radius": "3px",
                    "color": COLORS["text_sec"],
                    "border_color": COLORS["panel_bdr"],
                    "background": COLORS["deep"],
                },
            )
        )
    return _card(
        "Room Type",
        rx.flex(
            *buttons,
            wrap="wrap", gap="4px",
            style={"padding": "6px"},
        ),
    )


def _actions_card() -> rx.Component:
    return _card(
        "Actions",
        rx.flex(
            # Save
            rx.button(
                rx.icon(tag="save", size=14),
                rx.text("Save", style={"font_family": FONT_MONO, "font_size": "11px"}),
                rx.text("S", style=KBD_BADGE),
                on_click=EditorState.save_room,
                style={
                    "flex": "7",
                    "background": "#d1fae5",
                    "color": "#065f46",
                    "border": "1px solid #059669",
                    "gap": "4px",
                },
                size="1",
            ),
            # Delete
            rx.button(
                rx.icon(tag="trash-2", size=14),
                rx.text("Delete", style={"font_family": FONT_MONO, "font_size": "11px"}),
                on_click=EditorState.delete_room,
                style={
                    "flex": "5",
                    "background": "#fee2e2",
                    "color": "#991b1b",
                    "border": "1px solid #dc2626",
                    "gap": "4px",
                },
                size="1",
            ),
            gap="6px",
            style={"padding": "6px"},
        ),
    )


# ---------------------------------------------------------------------------
# §7.2 Status bar
# ---------------------------------------------------------------------------

def _status_bar() -> rx.Component:
    return rx.flex(
        rx.box(style={
            "width": "6px", "height": "6px",
            "border_radius": "50%",
            "background": COLORS["accent2"],
        }),
        rx.text(
            EditorState.status_message,
            style={"font_family": FONT_MONO, "font_size": "11px",
                    "color": COLORS["accent2"], "margin_left": "6px"},
        ),
        align="center",
        style={
            "background": COLORS["deep"],
            "border": f"1px solid {COLORS['panel_bdr']}",
            "border_radius": "4px",
            "padding": "6px 8px",
            "margin_bottom": "8px",
        },
    )


# ---------------------------------------------------------------------------
# §7.3 DF% results legend
# ---------------------------------------------------------------------------

def _df_legend() -> rx.Component:
    def _row(colour: str, label: str):
        return rx.flex(
            rx.box(style={"width": "6px", "height": "6px",
                           "border_radius": "50%", "background": colour}),
            rx.text(label, style={"font_family": FONT_MONO, "font_size": "10px",
                                   "color": COLORS["text_sec"], "margin_left": "6px"}),
            align="center",
        )
    return rx.box(
        _row("#059669", "≥ threshold (pass)"),
        _row("#d97706", "< threshold (marginal)"),
        _row("#dc2626", "< 50% of threshold (fail)"),
        style={"padding": "6px 0"},
    )


# ---------------------------------------------------------------------------
# Public component
# ---------------------------------------------------------------------------

def right_panel() -> rx.Component:
    return rx.box(
        _parent_card(),
        _room_name_card(),
        _room_type_card(),
        _actions_card(),
        _status_bar(),
        _df_legend(),
        style={
            "width": RIGHT_PANEL_WIDTH,
            "min_width": "200px",
            "background": COLORS["panel_bg"],
            "border_left": f"1px solid {COLORS['panel_bdr']}",
            "padding": "8px",
            "overflow_y": "auto",
        },
    )
