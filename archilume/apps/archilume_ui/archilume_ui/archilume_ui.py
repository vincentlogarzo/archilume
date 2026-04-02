"""Main page — composes all layout regions from spec §1."""

import reflex as rx

from .components.bottom_row import bottom_row
from .components.header import header
from .components.modals import (
    accelerad_modal,
    create_project_modal,
    extract_archive_modal,
    open_project_modal,
    shortcuts_modal,
)
from .components.font_preview import font_preview_page
from .components.project_tree import project_tree
from .components.right_panel import right_panel
from .components.sidebar import sidebar
from .components.viewport import viewport
from .state import EditorState
from .styles import COLORS, FONT_MONO, GOOGLE_FONTS_URL, SIDEBAR_WIDTH

_FONTS_PREVIEW_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,700;1,400&"
    "family=Space+Mono:ital,wght@0,400;0,700;1,400&"
    "family=Space+Grotesk:wght@400;500;600;700&"
    "family=IBM+Plex+Sans:ital,wght@0,400;0,600;0,700;1,400&"
    "family=Geist:wght@400;500;600;700&"
    "display=swap"
)


# Global keyboard handler — captures keys not handled by input elements
_KEYBOARD_SCRIPT = rx.script("""
document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (e.ctrlKey && e.key === 'z') { e.preventDefault(); applyEvent('editor_state.undo', {}); return; }
    if (e.ctrlKey && e.key === 'a') { e.preventDefault(); applyEvent('editor_state.select_all_rooms', {}); return; }
    if (e.ctrlKey && e.key === 'r') { e.preventDefault(); applyEvent('editor_state.rotate_overlay_90', {}); return; }
    if (e.shiftKey && e.key === 'S') { e.preventDefault(); applyEvent('editor_state.force_save', {}); return; }
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); applyEvent('editor_state.delete_hovered_vertex', {}); return; }
    if (e.key.length === 1 || e.key === 'Escape' || e.key.startsWith('Arrow')) {
        applyEvent('editor_state.handle_key', {key: e.key});
    }
});
""")


def index() -> rx.Component:
    return rx.box(
        _KEYBOARD_SCRIPT,
        sidebar(),
        rx.flex(
            header(),
            rx.flex(
                project_tree(),
                viewport(),
                right_panel(),
                style={"flex": "1", "overflow": "hidden"},
            ),
            bottom_row(),
            direction="column",
            style={
                "margin_left": SIDEBAR_WIDTH, "height": "100vh",
                "width": f"calc(100vw - {SIDEBAR_WIDTH})", "overflow": "hidden",
            },
        ),
        shortcuts_modal(),
        open_project_modal(),
        create_project_modal(),
        extract_archive_modal(),
        accelerad_modal(),
        style={
            "font_family": FONT_MONO, "font_size": "13px",
            "color": COLORS["text_pri"], "background": COLORS["viewport"],
        },
    )


app = rx.App(
    style={"font_family": FONT_MONO, "font_size": "13px"},
    stylesheets=[GOOGLE_FONTS_URL, _FONTS_PREVIEW_URL],
)
app.add_page(index, on_load=EditorState.init_on_load, title="Archilume")
app.add_page(font_preview_page, route="/fonts", title="Archilume — Font Preview")
