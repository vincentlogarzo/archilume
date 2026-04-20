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
            style={"color": COLORS["text_pri"], "flex_shrink": "0"},
        ),
        rx.text(
            title,
            style={
                **PANEL_CARD_TITLE,
                "padding": "0",
                "margin_left": "4px",
                "font_weight": "700",
            },
            color=COLORS["text_pri"],
        ),
        on_click=on_toggle,
        align="center",
        style={
            "padding": "0 8px",
            "height": "36px",
            "cursor": "pointer",
            "border_top": "1px solid",
            "border_color": COLORS["panel_bdr"],
            "background": COLORS["deep"],
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


# ---------------------------------------------------------------------------
# Visualisation (falsecolour + contour) section
# ---------------------------------------------------------------------------


_COL_HEADER_STYLE = {
    "font_family": FONT_MONO, "font_size": "10px",
    "color": COLORS["text_pri"], "text_transform": "uppercase",
    "letter_spacing": "0.06em", "font_weight": "700",
}
_ROW_LABEL_STYLE = {
    "font_family": FONT_MONO, "font_size": "10px",
    "color": COLORS["text_dim"], "text_transform": "uppercase",
    "letter_spacing": "0.05em", "font_weight": "400",
}
_CELL_INPUT_STYLE = {
    "font_family": FONT_MONO, "font_size": "11px",
    "padding": "2px 4px 2px 6px",
    "background": COLORS["panel_bg"],
    "color": COLORS["text_pri"],
    "border": f"1px solid {COLORS['panel_bdr']}",
    "border_radius": "3px",
    "width": "48px",
    "text_align": "left",
    "justify_self": "end",
}


_SCALE_TOP_HINT = (
    "Top of the DF % palette. Range 0–10 in 0.5 steps. "
    "Non-numeric input is blocked; entries snap to the nearest 0.5 on commit."
)
_DIVISIONS_HINT = (
    "Number of palette steps / contour lines. Integer 0–10. "
    "Decimals auto-round on commit; non-numeric input is blocked."
)


def _vis_col_header(label: str) -> rx.Component:
    return rx.text(label, style=_COL_HEADER_STYLE)


def _vis_num_cell(
    value, on_change, *, is_int: bool, tip: str, input_id: str,
) -> rx.Component:
    guard_kind = "int" if is_int else "decimal"
    return rx.tooltip(
        rx.el.input(
            id=input_id,
            default_value=value.to_string(),
            on_blur=on_change,
            type="number",
            step=rx.cond(is_int, "1", "0.5"),
            min="0", max="10",
            input_mode="numeric" if is_int else "decimal",
            auto_complete="off",
            custom_attrs={"data-numeric-guard": guard_kind},
            style=_CELL_INPUT_STYLE,
        ),
        content=tip,
    )


def _visualisation_body() -> rx.Component:
    btn_style = {
        "font_family": FONT_MONO, "font_size": "11px",
        "padding": "4px 10px", "cursor": "pointer",
        "display": "flex", "align_items": "center", "gap": "5px",
        "border": f"1px solid {COLORS['panel_bdr']}",
        "border_radius": "3px",
        "background": COLORS["panel_bg"],
        "_hover": {"background": COLORS["hover"]},
    }

    return rx.box(
        # Pivoted 4-col grid: Type / Palette / Scale top / Divisions
        rx.box(
            # Row 1 — column headers
            _vis_col_header("Type"),
            _vis_col_header("Palette"),
            _vis_col_header("Scale top"),
            _vis_col_header("Steps"),
            # Row 2 — Falsecolour
            rx.text("False-colour", style=_ROW_LABEL_STYLE),
            rx.tooltip(
                rx.select(
                    ["spec", "def", "pm3d", "hot", "eco", "tbo"],
                    value=EditorState.falsecolour_palette,
                    on_change=EditorState.set_falsecolour_palette,
                    size="1",
                    style={"font_family": FONT_MONO, "font_size": "11px"},
                ),
                content="Radiance falsecolor -pal palette. Default 'spec'.",
            ),
            _vis_num_cell(
                EditorState.falsecolour_scale,
                EditorState.set_falsecolour_scale,
                is_int=False, tip=_SCALE_TOP_HINT,
                input_id="vis-fc-scale",
            ),
            _vis_num_cell(
                EditorState.falsecolour_n_levels,
                EditorState.set_falsecolour_n_levels,
                is_int=True, tip=_DIVISIONS_HINT,
                input_id="vis-fc-div",
            ),
            # Row 3 — Contour lines (no palette — uses Radiance default)
            rx.text("Contour lines", style=_ROW_LABEL_STYLE),
            rx.box(),  # palette column spacer
            _vis_num_cell(
                EditorState.contour_scale,
                EditorState.set_contour_scale,
                is_int=False, tip=_SCALE_TOP_HINT,
                input_id="vis-ct-scale",
            ),
            _vis_num_cell(
                EditorState.contour_n_levels,
                EditorState.set_contour_n_levels,
                is_int=True, tip=_DIVISIONS_HINT,
                input_id="vis-ct-div",
            ),
            style={
                "display": "grid",
                "grid_template_columns": "1fr auto auto auto",
                "column_gap": "10px",
                "row_gap": "6px",
                "align_items": "center",
                "margin_top": "4px",
                "margin_bottom": "6px",
            },
        ),
        # Action row
        rx.flex(
            rx.el.button(
                rx.icon(tag="refresh-cw", size=12),
                rx.text(
                    rx.cond(EditorState.is_regenerating, "Regenerating…", "Regenerate"),
                    style={"font_family": FONT_MONO, "font_size": "11px"},
                ),
                on_click=EditorState.regenerate_visualisation_force,
                disabled=EditorState.is_regenerating,
                style=btn_style,
                color=COLORS["text_pri"],
            ),
            align="center", gap="6px",
            style={"margin_top": "6px"},
        ),
        # Progress / status line
        rx.cond(
            EditorState.regen_progress != "",
            rx.text(
                EditorState.regen_progress,
                style={
                    "font_family": FONT_MONO, "font_size": "10px",
                    "color": COLORS["text_dim"],
                    "margin_top": "4px",
                    "white_space": "nowrap", "overflow": "hidden",
                    "text_overflow": "ellipsis",
                },
            ),
            rx.fragment(),
        ),
        style={"padding": "4px 8px 6px 24px"},
    )


def visualisation_section() -> rx.Component:
    # Falsecolour + contour are DF-analysis visualisations specific to
    # daylight projects. Sunlight timeseries HDRs use tone-mapped PNG
    # siblings, so the panel is hidden in sunlight mode.
    return rx.cond(
        EditorState.is_sunlight_mode,
        rx.fragment(),
        rx.box(
            _section_header(
                "Visualisation",
                EditorState.visualisation_section_open,
                EditorState.toggle_visualisation_section,
            ),
            rx.cond(EditorState.visualisation_section_open, _visualisation_body(), rx.fragment()),
        ),
    )


