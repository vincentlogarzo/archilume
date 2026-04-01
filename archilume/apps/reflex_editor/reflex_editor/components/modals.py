"""Modals — spec §9. Shortcuts, Open/Create project, Extract archive."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO


# ---------------------------------------------------------------------------
# §9.1 Keyboard shortcuts
# ---------------------------------------------------------------------------

_SHORTCUTS = [
    ("↑ / ↓", "Navigate HDR files"),
    ("T", "Toggle image variant (HDR/TIFF)"),
    ("D", "Toggle draw mode"),
    ("DD", "Enter room divider mode"),
    ("E", "Toggle edit mode"),
    ("Click vertex", "Select vertex for move (edit mode)"),
    ("Click canvas", "Move selected vertex to position"),
    ("Delete/Backspace", "Delete selected vertex (≥4 verts)"),
    ("O", "Toggle ortho lines"),
    ("P", "Toggle DF% placement mode"),
    ("S", "Save room / confirm divider"),
    ("F", "Fit zoom to selected room"),
    ("R", "Reset zoom"),
    ("Ctrl+Z", "Undo"),
    ("Ctrl+A", "Select all rooms"),
    ("Shift+S", "Force save session"),
    ("Ctrl+R", "Rotate overlay 90°"),
    ("Esc", "Exit mode / deselect"),
]


def shortcuts_modal() -> rx.Component:
    rows = []
    for key, action in _SHORTCUTS:
        rows.append(
            rx.flex(
                rx.text(key, style={"font_family": FONT_MONO, "font_size": "11px",
                                     "color": COLORS["text_pri"], "width": "130px",
                                     "flex_shrink": "0"}),
                rx.text(action, style={"font_family": FONT_MONO, "font_size": "11px",
                                        "color": COLORS["text_sec"]}),
                style={"padding": "3px 0"},
            )
        )

    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Keyboard Shortcuts",
                            style={"font_family": FONT_MONO, "font_size": "13px"}),
            rx.box(*rows, style={"max_height": "60vh", "overflow_y": "auto"}),
            rx.flex(
                rx.dialog.close(
                    rx.button("Close", variant="outline", size="1",
                              style={"font_family": FONT_MONO}),
                ),
                justify="end", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.shortcuts_modal_open,
        on_open_change=lambda open: rx.cond(
            open,
            EditorState.open_shortcuts_modal,
            EditorState.close_shortcuts_modal,
        ),
    )


# ---------------------------------------------------------------------------
# §9.2 Open project
# ---------------------------------------------------------------------------

def open_project_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Open Project",
                            style={"font_family": FONT_MONO, "font_size": "13px"}),
            rx.select(
                EditorState.available_projects,
                placeholder="Select a project…",
                size="2",
                style={"font_family": FONT_MONO, "width": "100%"},
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="outline", size="1",
                              style={"font_family": FONT_MONO}),
                ),
                rx.dialog.close(
                    rx.button("Open", size="1",
                              style={"font_family": FONT_MONO,
                                      "background": COLORS["accent"]}),
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.open_project_modal_open,
        on_open_change=lambda open: rx.cond(
            open,
            EditorState.open_open_project_modal,
            EditorState.close_open_project_modal,
        ),
    )


# ---------------------------------------------------------------------------
# §9.3 Create new project
# ---------------------------------------------------------------------------

def create_project_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Create New Project",
                            style={"font_family": FONT_MONO, "font_size": "13px"}),
            rx.input(
                placeholder="Project name",
                size="2",
                style={"font_family": FONT_MONO, "width": "100%"},
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="outline", size="1",
                              style={"font_family": FONT_MONO}),
                ),
                rx.dialog.close(
                    rx.button("Create", size="1",
                              style={"font_family": FONT_MONO,
                                      "background": COLORS["success"]}),
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.create_project_modal_open,
        on_open_change=lambda open: rx.cond(
            open,
            EditorState.open_create_project_modal,
            EditorState.close_create_project_modal,
        ),
    )


# ---------------------------------------------------------------------------
# §9.4 Extract archive
# ---------------------------------------------------------------------------

def extract_archive_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Extract Archive",
                            style={"font_family": FONT_MONO, "font_size": "13px"}),
            rx.select(
                [],  # TODO: populate from archive_dir/*.zip
                placeholder="Select archive…",
                size="2",
                style={"font_family": FONT_MONO, "width": "100%"},
            ),
            rx.text(
                "This will overwrite the current project AOI files and reload the session.",
                style={"font_family": FONT_MONO, "font_size": "10px",
                        "color": COLORS["danger"], "margin_top": "8px"},
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="outline", size="1",
                              style={"font_family": FONT_MONO}),
                ),
                rx.dialog.close(
                    rx.button("Extract & Reload", size="1",
                              style={"font_family": FONT_MONO,
                                      "background": COLORS["danger"],
                                      "color": "white"}),
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.extract_modal_open,
        on_open_change=lambda open: rx.cond(
            open,
            EditorState.open_extract_modal,
            EditorState.close_extract_modal,
        ),
    )


# ---------------------------------------------------------------------------
# AcceleradRT launch modal
# ---------------------------------------------------------------------------

def accelerad_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.flex(
                    rx.icon(tag="zap", size=16, style={"color": COLORS["accent"]}),
                    rx.text("AcceleradRT Preview",
                            style={"margin_left": "6px"}),
                    align="center",
                ),
                style={"font_family": FONT_MONO, "font_size": "13px"},
            ),
            # Octree file selector
            rx.box(
                rx.text("Octree File", style={
                    "font_family": FONT_MONO, "font_size": "9px",
                    "text_transform": "uppercase", "color": "#9ba6b2",
                    "margin_bottom": "4px",
                }),
                rx.select(
                    EditorState.accelerad_oct_files,
                    value=EditorState.accelerad_selected_oct,
                    on_change=EditorState.set_accelerad_oct,
                    size="2",
                    style={"font_family": FONT_MONO, "font_size": "11px",
                            "width": "100%"},
                ),
                style={"margin_bottom": "12px"},
            ),
            # Resolution inputs
            rx.flex(
                rx.box(
                    rx.text("Width (px)", style={
                        "font_family": FONT_MONO, "font_size": "9px",
                        "text_transform": "uppercase", "color": "#9ba6b2",
                        "margin_bottom": "4px",
                    }),
                    rx.input(
                        value=EditorState.accelerad_res_x.to(str),
                        on_change=EditorState.set_accelerad_res_x,
                        type="number",
                        size="2",
                        style={"font_family": FONT_MONO, "font_size": "11px",
                                "width": "100%"},
                    ),
                    style={"flex": "1"},
                ),
                rx.box(
                    rx.text("Height (px)", style={
                        "font_family": FONT_MONO, "font_size": "9px",
                        "text_transform": "uppercase", "color": "#9ba6b2",
                        "margin_bottom": "4px",
                    }),
                    rx.input(
                        value=EditorState.accelerad_res_y.to(str),
                        on_change=EditorState.set_accelerad_res_y,
                        type="number",
                        size="2",
                        style={"font_family": FONT_MONO, "font_size": "11px",
                                "width": "100%"},
                    ),
                    style={"flex": "1"},
                ),
                gap="12px",
                style={"margin_bottom": "12px"},
            ),
            # Error message
            rx.cond(
                EditorState.accelerad_error,
                rx.text(
                    EditorState.accelerad_error,
                    style={"font_family": FONT_MONO, "font_size": "10px",
                            "color": COLORS["danger"], "margin_bottom": "8px"},
                ),
                rx.fragment(),
            ),
            # Buttons
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="outline", size="2",
                              style={"font_family": FONT_MONO}),
                ),
                rx.button(
                    rx.icon(tag="zap", size=14),
                    "Launch",
                    size="2",
                    on_click=EditorState.launch_accelerad,
                    style={"font_family": FONT_MONO,
                            "background": COLORS["accent"],
                            "color": "white", "gap": "4px"},
                ),
                justify="end", gap="8px",
            ),
            style={"max_width": "480px"},
        ),
        open=EditorState.accelerad_modal_open,
        on_open_change=lambda open: rx.cond(
            open,
            EditorState.open_accelerad_modal,
            EditorState.close_accelerad_modal,
        ),
    )
