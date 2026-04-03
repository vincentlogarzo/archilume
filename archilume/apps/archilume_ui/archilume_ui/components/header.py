"""Header bar — spec §4. Top bar with logo, project name, and workflow tabs."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_HEAD, FONT_MONO


_TAB_ITEMS = [
    ("model_validation", "Model Validation", "shield-check"),
    ("pre_simulation", "Pre-Simulation Checks", "ruler"),
    ("simulation", "Simulation Manager", "cloud-cog"),
    ("results", "Results Viewer", "bar-chart-3"),
]


def _tab_btn(tab_id: str, label: str, icon_tag: str) -> rx.Component:
    is_active = EditorState.active_tab == tab_id
    return rx.button(
        rx.icon(tag=icon_tag, size=13),
        rx.text(label, style={"font_family": FONT_MONO, "font_size": "11px",
                               "margin_left": "4px"}),
        variant="ghost", size="1",
        on_click=EditorState.set_active_tab(tab_id),
        style={
            "padding": "8px 14px",
            "border_radius": "8px 8px 0 0",
            "color": rx.cond(is_active, COLORS["text_pri"], COLORS["text_dim"]),
            "background": rx.cond(is_active, COLORS["panel_bg"], "transparent"),
            "border": rx.cond(
                is_active,
                "1px solid " + COLORS["panel_bdr"],
                "1px solid transparent",
            ),
            "border_bottom": rx.cond(
                is_active,
                "1px solid " + COLORS["panel_bg"],
                "1px solid transparent",
            ),
            "margin_bottom": "-1px",
            "font_weight": rx.cond(is_active, "600", "400"),
            "cursor": "pointer",
            "transition": "all 0.15s ease",
            "position": "relative",
            "z_index": rx.cond(is_active, "2", "1"),
            "_hover": {"color": COLORS["text_pri"],
                       "background": rx.cond(is_active, COLORS["panel_bg"], COLORS["deep"])},
        },
    )


def _mode_badge(label: str, fg: str, bg: str, border_col: str, visible) -> rx.Component:
    return rx.cond(
        visible,
        rx.badge(
            label,
            style={"font_family": FONT_MONO, "font_size": "14px",
                   "border_radius": "3px", "padding": "1px 6px"},
            color=fg, background=bg, border="1px solid", border_color=border_col,
        ),
        rx.fragment(),
    )


def header() -> rx.Component:
    return rx.flex(
        # Logo + project name
        rx.el.svg(
            rx.el.circle(cx="22", cy="12", r="6", fill="#f59e0b"),
            rx.el.line(x1="22", y1="3", x2="22", y2="5", stroke="#f59e0b", stroke_width="1.5", stroke_linecap="round"),
            rx.el.line(x1="29", y1="12", x2="27", y2="12", stroke="#f59e0b", stroke_width="1.5", stroke_linecap="round"),
            rx.el.line(x1="27", y1="6", x2="25.5", y2="7.5", stroke="#f59e0b", stroke_width="1.5", stroke_linecap="round"),
            rx.el.line(x1="27", y1="18", x2="25.5", y2="16.5", stroke="#f59e0b", stroke_width="1.5", stroke_linecap="round"),
            rx.el.rect(x="4", y="8", width="16", height="22", rx="1", fill="#374151"),
            rx.el.rect(x="6", y="10", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="10.5", y="10", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.6"),
            rx.el.rect(x="15", y="10", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="6", y="14.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.6"),
            rx.el.rect(x="10.5", y="14.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="15", y="14.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.6"),
            rx.el.rect(x="6", y="19", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="10.5", y="19", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.4"),
            rx.el.rect(x="15", y="19", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="6", y="23.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.4"),
            rx.el.rect(x="10.5", y="23.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.85"),
            rx.el.rect(x="15", y="23.5", width="3", height="2.5", rx="0.4", fill="#f59e0b", opacity="0.6"),
            rx.el.rect(x="10", y="27", width="4", height="5", rx="0.5", fill=COLORS["header"]),
            custom_attrs={"viewBox": "0 0 32 32"},
            style={"width": "24px", "height": "24px", "flex_shrink": "0",
                   "align_self": "center"},
        ),
        rx.text(
            "Archilume",
            style={"font_family": FONT_HEAD, "font_weight": "700", "font_size": "18px",
                   "letter_spacing": "-0.02em", "white_space": "nowrap",
                   "align_self": "center"},
            color=COLORS["text_pri"],
        ),
        rx.text("|", style={"font_family": FONT_MONO, "font_size": "14px",
                             "margin": "0 6px", "color": COLORS["panel_bdr"],
                             "align_self": "center"}),
        rx.text(
            rx.cond(EditorState.project, EditorState.project, "No project loaded"),
            style={"font_family": FONT_MONO, "font_size": "11px", "white_space": "nowrap",
                   "align_self": "center"},
            color=COLORS["text_sec"],
        ),
        # Separator before tabs
        rx.box(style={"width": "20px", "flex_shrink": "0"}),
        # Workflow tabs
        *[_tab_btn(tid, label, icon) for tid, label, icon in _TAB_ITEMS],
        # Right side
        rx.spacer(),
        rx.flex(
            _mode_badge("DRAW", COLORS["accent"], COLORS["btn_on"], COLORS["accent"], EditorState.draw_mode),
            _mode_badge("EDIT", "#92400e", "#fef3c7", COLORS["warning"], EditorState.edit_mode),
            _mode_badge("DIVIDER", "#1e40af", "#dbeafe", COLORS["accent2"], EditorState.divider_mode),
            rx.cond(
                EditorState.has_multi_selection,
                rx.badge(
                    EditorState.multi_selection_count.to(str) + " rooms selected",
                    style={"font_family": FONT_MONO, "font_size": "14px", "padding": "1px 6px"},
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
            align="center",
            style={"gap": "4px", "align_self": "center"},
        ),
        align="end",
        style={"height": "42px", "padding": "0 12px", "gap": "6px"},
        background=COLORS["header"],
        border_bottom="1px solid", border_color=COLORS["panel_bdr"],
    )
