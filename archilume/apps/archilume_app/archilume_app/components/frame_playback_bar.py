"""Sunlight frame playback bar — lives inside the Room Browser next to the
currently-selected view row. Shows a scrub slider, play/pause, step buttons,
and the current frame label. Hidden for daylight projects and for single-frame
sunlight views."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO

_ROW_H = "26px"
_FONT = {"font_family": FONT_MONO, "font_size": "11px"}


def _control_btn(icon_tag: str, tooltip: str, on_click) -> rx.Component:
    return rx.tooltip(
        rx.icon_button(
            rx.icon(tag=icon_tag, size=12),
            variant="ghost", size="1",
            on_click=on_click,
            style={"color": COLORS["text_dim"], "flex_shrink": "0"},
        ),
        content=tooltip, side="bottom",
    )


def _multi_frame_row() -> rx.Component:
    return rx.flex(
        _control_btn("skip-back", "Previous frame [←]",
                     EditorState.step_frame(-1).stop_propagation),
        rx.tooltip(
            rx.icon_button(
                rx.icon(
                    tag=rx.cond(EditorState.frame_autoplay, "pause", "play"),
                    size=12,
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
            style={"flex": "1", "min_width": "60px"},
        ),
        rx.text(
            EditorState.current_frame_label,
            style={**_FONT, "color": COLORS["text_sec"],
                   "white_space": "nowrap", "flex_shrink": "0",
                   "overflow": "hidden", "text_overflow": "ellipsis",
                   "max_width": "120px"},
        ),
        rx.text(
            (EditorState.current_frame_idx + 1).to_string()
            + " / "
            + EditorState.current_view_frame_count.to_string(),
            style={**_FONT, "color": COLORS["text_dim"],
                   "flex_shrink": "0", "font_size": "10px"},
        ),
        align="center",
        gap="4px",
        style={
            "height": _ROW_H,
            "padding": "0 8px 0 24px",
            "flex_shrink": "0",
            "background": COLORS["deep"],
        },
    )


def _single_frame_row() -> rx.Component:
    return rx.flex(
        rx.text(
            EditorState.current_frame_label,
            style={**_FONT, "color": COLORS["text_sec"],
                   "white_space": "nowrap", "overflow": "hidden",
                   "text_overflow": "ellipsis", "flex": "1"},
        ),
        align="center",
        style={
            "height": _ROW_H,
            "padding": "0 8px 0 24px",
            "flex_shrink": "0",
            "background": COLORS["deep"],
        },
    )


# Ticker script: fixed 5 fps (200ms). Each tick reads the live autoplay flag
# and target FPS from a hidden DOM node's data attributes, so the script
# picks up Reflex state changes without needing to be re-rendered.
_PLAYBACK_TICKER = rx.script("""
(function() {
    if (window.__framePlaybackTickerInstalled) return;
    window.__framePlaybackTickerInstalled = true;
    window.__framePlaybackCounter = 0;
    setInterval(function() {
        var el = document.getElementById('frame-playback-ctrl');
        if (!el) return;
        if (el.dataset.autoplay !== '1') return;
        window.__framePlaybackCounter++;
        var fps = parseInt(el.dataset.fps, 10) || 5;
        var divisor = Math.max(1, Math.round(5 / fps));
        if (window.__framePlaybackCounter % divisor !== 0) return;
        var fn = window.applyEvent || (window.__reflex && window.__reflex['$/utils/state'] && window.__reflex['$/utils/state'].applyEvent);
        if (fn) fn('editor_state.advance_frame', {});
    }, 200);
})();
""")


def frame_playback_bar() -> rx.Component:
    """Render the playback strip when a sunlight view is the active selection.

    Single-frame views show only the sky-name label. Multi-frame views show
    the full play/pause + scrub + step controls. Daylight mode renders nothing.
    """
    hidden_ctrl = rx.box(
        id="frame-playback-ctrl",
        custom_attrs={
            "data-autoplay": rx.cond(EditorState.frame_autoplay, "1", "0"),
            "data-fps": EditorState.frame_playback_fps.to_string(),
        },
        style={"display": "none"},
    )
    return rx.cond(
        EditorState.is_sunlight_mode,
        rx.fragment(
            hidden_ctrl,
            _PLAYBACK_TICKER,
            rx.cond(
                EditorState.current_view_frame_count > 1,
                _multi_frame_row(),
                rx.cond(
                    EditorState.current_view_frame_count == 1,
                    _single_frame_row(),
                    rx.fragment(),
                ),
            ),
        ),
        rx.fragment(),
    )
