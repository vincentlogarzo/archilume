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
from .components.project_tree import project_tree
from .components.right_panel import right_panel
from .components.sidebar import sidebar
from .components.viewport import viewport
from .styles import COLORS, FONT_MONO, GOOGLE_FONTS_URL, SIDEBAR_WIDTH


def index() -> rx.Component:
    return rx.box(
        # Fixed left sidebar
        sidebar(),
        # Everything else offset by sidebar width
        rx.flex(
            # Header bar
            header(),
            # Middle row: project tree + viewport + right panel
            rx.flex(
                project_tree(),
                viewport(),
                right_panel(),
                style={"flex": "1", "overflow": "hidden"},
            ),
            # Bottom row
            bottom_row(),
            direction="column",
            style={
                "margin_left": SIDEBAR_WIDTH,
                "height": "100vh",
                "width": f"calc(100vw - {SIDEBAR_WIDTH})",
                "overflow": "hidden",
            },
        ),
        # Modals (rendered at root level)
        shortcuts_modal(),
        open_project_modal(),
        create_project_modal(),
        extract_archive_modal(),
        accelerad_modal(),
        style={
            "font_family": FONT_MONO,
            "font_size": "11px",
            "color": COLORS["text_pri"],
            "background": COLORS["viewport"],
        },
    )


app = rx.App(
    style={
        "font_family": FONT_MONO,
    },
    stylesheets=[GOOGLE_FONTS_URL],
)
app.add_page(index)
