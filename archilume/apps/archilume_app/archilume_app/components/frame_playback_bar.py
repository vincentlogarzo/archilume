"""Sunlight frame playback bar — floats as a centred overlay near the bottom
of the canvas. Shows a scrub slider, play/pause, step buttons, fps input, and
the current frame label. Hidden for daylight projects; single-frame sunlight
views show only the sky-name label.

Autoplay runs as a server-side background task on ``EditorState`` — see
``autoplay_frames_loop`` in ``state/editor_state.py``. There is no client-side
ticker."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO

_ROW_H = "28px"
_FONT = {"font_family": FONT_MONO, "font_size": "12px"}

_OVERLAY_BG = rx.color_mode_cond(
    light="rgba(255, 255, 255, 0.60)",
    dark="rgba(30, 33, 41, 0.60)",
)

_FPS_OPTIONS = ["1", "2", "5", "10", "15", "24", "30"]


def _control_btn(icon_tag: str, tooltip: str, on_click) -> rx.Component:
    return rx.tooltip(
        rx.icon_button(
            rx.icon(tag=icon_tag, size=13),
            variant="ghost", size="1",
            on_click=on_click,
            style={"color": COLORS["text_dim"], "flex_shrink": "0"},
        ),
        content=tooltip, side="bottom",
    )


def _fps_input() -> rx.Component:
    return rx.tooltip(
        rx.flex(
            rx.select(
                _FPS_OPTIONS,
                value=EditorState.frame_playback_fps.to_string(),
                on_change=EditorState.set_frame_fps,
                size="1",
                style={
                    "flex_shrink": "0",
                    "font_family": FONT_MONO, "font_size": "11px",
                },
            ),
            rx.text(
                "fps",
                style={**_FONT, "color": COLORS["text_dim"],
                       "font_size": "11px", "flex_shrink": "0"},
            ),
            align="center", gap="4px",
            style={"flex_shrink": "0"},
        ),
        content="Playback speed (fps)", side="bottom",
    )


def _multi_frame_row() -> rx.Component:
    return rx.flex(
        _control_btn("skip-back", "Previous frame [←]",
                     EditorState.step_frame(-1).stop_propagation),
        rx.tooltip(
            rx.icon_button(
                rx.icon(
                    tag=rx.cond(EditorState.frame_autoplay, "pause", "play"),
                    size=13,
                ),
                variant="ghost", size="1",
                on_click=EditorState.toggle_frame_autoplay.stop_propagation,
                style={"color": COLORS["accent"], "flex_shrink": "0"},
            ),
            content="Play/pause [space]", side="bottom",
        ),
        _control_btn("skip-forward", "Next frame [→]",
                     EditorState.step_frame(1).stop_propagation),
        rx.slider(
            min=0,
            max=EditorState.current_view_frame_count - 1,
            value=[EditorState.current_frame_idx],
            on_change=lambda v: EditorState.set_frame_idx(v[0]),
            size="1",
            style={"flex": "1", "min_width": "120px"},
        ),
        rx.text(
            EditorState.current_frame_label,
            style={**_FONT, "color": COLORS["text_sec"],
                   "white_space": "nowrap", "flex_shrink": "0",
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "max_width": "160px"},
        ),
        rx.text(
            (EditorState.current_frame_idx + 1).to_string()
            + " / "
            + EditorState.current_view_frame_count.to_string(),
            style={**_FONT, "color": COLORS["text_dim"],
                   "flex_shrink": "0", "font_size": "12px"},
        ),
        _fps_input(),
        align="center",
        gap="6px",
        style={
            "height": _ROW_H,
            "padding": "0 12px",
            "flex_shrink": "0",
        },
    )


def _single_frame_row() -> rx.Component:
    return rx.flex(
        rx.text(
            EditorState.current_frame_label,
            style={**_FONT, "color": COLORS["text_sec"],
                   "white_space": "nowrap", "overflow": "hidden",
                   "text_overflow": "ellipsis", "flex": "1",
                   "text_align": "center"},
        ),
        align="center",
        justify="center",
        style={
            "height": _ROW_H,
            "padding": "0 12px",
            "flex_shrink": "0",
        },
    )


def frame_playback_bar() -> rx.Component:
    """Render the playback strip when a sunlight view is the active selection.

    Single-frame views show only the sky-name label. Multi-frame views show
    the full play/pause + scrub + step + fps controls. Daylight mode renders
    nothing. Autoplay is driven by a background event handler on EditorState,
    so no client-side ticker is needed.
    """
    return rx.cond(
        EditorState.is_sunlight_mode,
        rx.box(
            rx.cond(
                EditorState.current_view_frame_count > 1,
                _multi_frame_row(),
                rx.cond(
                    EditorState.current_view_frame_count == 1,
                    _single_frame_row(),
                    rx.fragment(),
                ),
            ),
            style={
                "position": "absolute",
                "bottom": "20px",
                "left": "50%",
                "transform": "translateX(-50%)",
                "z_index": "4",
                "background": _OVERLAY_BG,
                "backdrop_filter": "blur(8px)",
                "-webkit-backdrop-filter": "blur(8px)",
                "border": "1px solid",
                "border_color": COLORS["panel_bdr"],
                "border_radius": "8px",
                "box_shadow": "0 2px 10px rgba(0,0,0,0.25)",
                "min_width": "700px",
                "max_width": "1200px",
                "width": "70%",
                "padding": "3px 10px",
                "pointer_events": "auto",
            },
        ),
        rx.fragment(),
    )
