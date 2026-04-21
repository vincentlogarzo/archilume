"""Modals — spec §9. Shortcuts, Open/Create project, Project Settings, Extract archive, AcceleradRT."""

import reflex as rx

from ..state import EditorState
from ..styles import COLORS, FONT_MONO


_SHORTCUTS = [
    ("↑ / ↓", "Navigate HDR files"),
    ("T", "Toggle image variant (HDR/TIFF)"),
    ("D", "Toggle draw mode"),
    ("DD", "Enter room divider mode"),
    ("E", "Toggle edit mode"),
    ("G", "Toggle pan mode"),
    ("O", "Toggle ortho / 15° snap"),
    ("Shift (hold)", "Free angle — disable 15° snap (draw mode)"),
    ("P", "Toggle DF% placement mode"),
    ("S", "Save room / confirm divider"),
    ("F", "Fit zoom to selected room"),
    ("R", "Reset zoom"),
    ("Ctrl+Z", "Undo"),
    ("Ctrl+A", "Select all rooms"),
    ("Shift+S", "Force save session"),
    ("Ctrl+R", "Rotate overlay 90°"),
    ("Esc", "Exit mode / deselect"),
    ("Delete", "Delete hovered vertex (edit mode)"),
]


def shortcuts_modal() -> rx.Component:
    rows = [
        rx.flex(
            rx.text(key, style={"font_family": FONT_MONO, "font_size": "11px",
                                 "color": COLORS["text_pri"], "width": "130px", "flex_shrink": "0"}),
            rx.text(action, style={"font_family": FONT_MONO, "font_size": "11px", "color": COLORS["text_sec"]}),
            style={"padding": "3px 0"},
        )
        for key, action in _SHORTCUTS
    ]
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Keyboard Shortcuts", style={"font_family": FONT_MONO, "font_size": "18px"}),
            rx.box(*rows, style={"max_height": "60vh", "overflow_y": "auto"}),
            rx.flex(
                rx.dialog.close(rx.button("Close", variant="outline", size="1", style={"font_family": FONT_MONO})),
                justify="end", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.shortcuts_modal_open,
        on_open_change=EditorState.close_shortcuts_modal,
    )


def _project_list_item(name: str) -> rx.Component:
    return rx.box(
        rx.text(name, style={"font_family": FONT_MONO, "font_size": "12px"}),
        style={"padding": "7px 10px", "cursor": "pointer", "border_radius": "4px"},
        color=COLORS["text_pri"],
        _hover={"background": COLORS["hover"]},
        on_click=EditorState.open_project(name),
    )


def open_project_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.flex(
                rx.dialog.title("Open Project", style={"font_family": FONT_MONO, "font_size": "18px", "margin": "0"}),
                rx.spacer(),
                rx.tooltip(
                    rx.upload(
                        rx.button(
                            rx.icon(tag="folder-open", size=14),
                            "Browse…",
                            size="1", variant="outline",
                            style={"font_family": FONT_MONO},
                        ),
                        id="open-project-archive",
                        accept={"application/zip": [".zip"]},
                        multiple=False,
                        on_drop=EditorState.upload_open_project_archive(
                            rx.upload_files(upload_id="open-project-archive")
                        ),
                        border="none",
                        padding="0",
                        style={"display": "inline-block", "min_height": "0", "height": "auto"},
                    ),
                    content="Upload a .zip of a project folder", side="left",
                ),
                align="center", style={"margin_bottom": "14px"},
            ),
            rx.box(
                rx.foreach(EditorState.available_projects, _project_list_item),
                style={
                    "border": "1px solid", "border_color": COLORS["panel_bdr"],
                    "border_radius": "6px", "overflow_y": "auto",
                    "max_height": "280px", "min_height": "80px",
                    "padding": "4px",
                },
                background=COLORS["deep"],
            ),
            rx.flex(
                rx.dialog.close(rx.button("Cancel", variant="outline", size="1", style={"font_family": FONT_MONO})),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
            style={"min_width": "320px"},
        ),
        open=EditorState.open_project_modal_open,
        on_open_change=EditorState.close_open_project_modal,
    )


# ---------------------------------------------------------------------------
# External Folder Browser — server-side fallback when the native OS file
# dialog is unavailable (e.g. the backend runs headless in Docker).
# ---------------------------------------------------------------------------


def _browser_folder_row(entry) -> rx.Component:
    nav_zone = rx.flex(
        rx.cond(
            entry["is_project"],
            rx.icon(tag="folder-check", size=14, style={"color": COLORS["success"]}),
            rx.icon(tag="folder", size=14, style={"color": COLORS["text_sec"]}),
        ),
        rx.text(
            entry["name"],
            style={"font_family": FONT_MONO, "font_size": "12px",
                   "color": COLORS["text_pri"]},
        ),
        align="center", gap="8px",
        style={"flex": "1", "cursor": "pointer", "min_width": "0"},
        on_click=EditorState.external_browser_navigate(entry["path"]),
    )
    return rx.flex(
        nav_zone,
        rx.cond(
            entry["is_project"],
            rx.button(
                "Select",
                size="1",
                variant="solid",
                on_click=EditorState.external_browser_select(entry["path"]),
                style={"font_family": FONT_MONO},
            ),
            rx.fragment(),
        ),
        align="center", gap="8px",
        style={"padding": "6px 10px", "border_radius": "4px"},
        _hover={"background": COLORS["hover"]},
    )


def _browser_file_row(entry) -> rx.Component:
    return rx.flex(
        rx.flex(
            rx.icon(tag="file", size=14, style={"color": COLORS["text_sec"]}),
            rx.text(
                entry["name"],
                style={"font_family": FONT_MONO, "font_size": "12px",
                       "color": COLORS["text_pri"]},
            ),
            align="center", gap="8px",
            style={"flex": "1", "cursor": "pointer", "min_width": "0"},
            on_click=EditorState.external_browser_select(entry["path"]),
        ),
        rx.button(
            "Select",
            size="1",
            variant="solid",
            on_click=EditorState.external_browser_select(entry["path"]),
            style={"font_family": FONT_MONO},
        ),
        align="center", gap="8px",
        style={"padding": "6px 10px", "border_radius": "4px"},
        _hover={"background": COLORS["hover"]},
    )


def _browser_entry_row(entry) -> rx.Component:
    # Folder rows navigate on click and expose Select when they are an
    # archilume project (Open-Project flow only). File rows — used by the
    # settings Browse fallback — are selection-only.
    return rx.cond(
        entry["kind"] == "dir",
        _browser_folder_row(entry),
        _browser_file_row(entry),
    )


def external_browser_modal() -> rx.Component:
    is_file_mode = EditorState.external_browser_mode == "settings_file"
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(is_file_mode, "Select File", "Select Project Folder"),
                style={"font_family": FONT_MONO, "font_size": "18px", "margin": "0 0 4px 0"},
            ),
            rx.dialog.description(
                rx.cond(
                    is_file_mode,
                    "Browse the server filesystem and pick a file of the allowed type.",
                    "Browse the server filesystem. Folders containing project.toml can be selected.",
                ),
                style={"font_family": FONT_MONO, "font_size": "11px",
                       "color": COLORS["text_sec"], "margin_bottom": "10px"},
            ),
            rx.flex(
                rx.tooltip(
                    rx.icon_button(
                        rx.icon(tag="arrow-up", size=14),
                        size="1", variant="outline",
                        on_click=EditorState.external_browser_go_up,
                    ),
                    content="Parent folder", side="bottom",
                ),
                rx.text(
                    EditorState.external_browser_path,
                    style={"font_family": FONT_MONO, "font_size": "11px",
                           "color": COLORS["text_pri"], "overflow": "hidden",
                           "text_overflow": "ellipsis", "white_space": "nowrap"},
                ),
                align="center", gap="8px",
                style={"margin_bottom": "8px", "min_width": "0"},
            ),
            rx.box(
                rx.foreach(EditorState.external_browser_entries, _browser_entry_row),
                style={
                    "border": "1px solid", "border_color": COLORS["panel_bdr"],
                    "border_radius": "6px", "overflow_y": "auto",
                    "max_height": "320px", "min_height": "120px",
                    "padding": "4px",
                },
                background=COLORS["deep"],
            ),
            rx.cond(
                EditorState.external_browser_error != "",
                rx.text(
                    EditorState.external_browser_error,
                    style={"font_family": FONT_MONO, "font_size": "11px",
                           "color": COLORS["danger"], "margin_top": "8px"},
                ),
                rx.fragment(),
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button("Cancel", variant="outline", size="1",
                              style={"font_family": FONT_MONO}),
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
            style={"min_width": "480px", "max_width": "640px"},
        ),
        open=EditorState.external_browser_open,
        on_open_change=EditorState.close_external_browser,
    )


# ---------------------------------------------------------------------------
# Create New Project — mode-aware, validated, drag-and-drop
# ---------------------------------------------------------------------------


# Mode dropdown items use the workflow ids declared in archilume_app/lib/project_modes.py.
# Display labels are paired here so the dropdown reads as natural English while
# the underlying state still carries the canonical id.
_MODE_OPTIONS: list[tuple[str, str]] = [
    ("sunlight", "Sunlight"),
    ("daylight", "Daylight (IESVE)"),
]


def _file_row(entry, on_remove) -> rx.Component:
    """Render one staged file row with ✓/✗ icon, filename, error, remove button."""
    return rx.flex(
        rx.cond(
            entry["ok"],
            rx.icon(tag="check", size=14, style={"color": COLORS["success"]}),
            rx.icon(tag="x", size=14, style={"color": COLORS["danger"]}),
        ),
        rx.text(
            entry["name"],
            style={"font_family": FONT_MONO, "font_size": "11px", "color": COLORS["text_pri"]},
        ),
        rx.cond(
            entry["error"] != "",
            rx.text(
                entry["error"],
                style={"font_family": FONT_MONO, "font_size": "10px",
                       "color": COLORS["danger"], "margin_left": "6px"},
            ),
            rx.fragment(),
        ),
        rx.spacer(),
        rx.icon_button(
            rx.icon(tag="x", size=12),
            variant="ghost", size="1",
            on_click=on_remove,
            style={"color": COLORS["text_dim"]},
        ),
        align="center", gap="6px",
        style={"padding": "3px 6px", "border_radius": "4px"},
    )


def _drop_zone(upload_id: str, exts_label: str, show_click_hint: bool = True) -> rx.Component:
    """Inner drop-zone visual rendered as the rx.upload child.

    ``show_click_hint`` controls whether the primary text invites a click.
    Settings fields pair this with a dedicated "Browse…" button and pass
    ``False`` so the drop zone reads as drag-and-drop only.
    """
    primary = (
        f"Drop {exts_label} here, or click to browse"
        if show_click_hint else f"Drop {exts_label} here to upload"
    )
    return rx.box(
        rx.text(
            primary,
            style={"font_family": FONT_MONO, "font_size": "11px", "color": COLORS["text_sec"], "line_height": "1.2"},
        ),
        rx.text(
            "(local + cloud-mounted folders both work)",
            style={"font_family": FONT_MONO, "font_size": "9px", "color": COLORS["text_dim"], "line_height": "1.2"},
        ),
        style={
            "border": "1px dashed", "border_radius": "6px",
            "padding": "4px 10px", "text_align": "center",
            "cursor": "pointer",
        },
        border_color=COLORS["panel_bdr"],
        background=COLORS["deep"],
    )


def _create_upload_field(
    field_id: str,
    label: str,
    accept: dict,
    multiple: bool,
    files_var,
    exts_label: str,
    upload_handler,
) -> rx.Component:
    """Create-modal upload field — drop zone + per-file ✓/✗ list.

    ``upload_handler`` is the per-field EventHandler (e.g.
    ``EditorState.upload_create_pdf``); Reflex requires the handler's
    parameter list to match the event spec exactly, so we cannot pass the
    field_id through the event — it is baked into the chosen handler.
    """
    upload_id = f"create-{field_id}"
    return rx.box(
        rx.flex(
            rx.text(label, style={
                "font_family": FONT_MONO, "font_size": "11px",
                "text_transform": "uppercase", "color": COLORS["text_dim"],
            }),
            rx.spacer(),
            rx.text("required", style={
                "font_family": FONT_MONO, "font_size": "9px",
                "color": COLORS["text_dim"], "letter_spacing": "0.06em",
            }),
            align="center", style={"margin_bottom": "4px"},
        ),
        rx.upload(
            _drop_zone(upload_id, exts_label),
            id=upload_id,
            accept=accept,
            multiple=multiple,
            on_drop=upload_handler(rx.upload_files(upload_id=upload_id)),
            border="none",
            padding="0",
            style={"width": "100%"},
        ),
        rx.foreach(
            files_var,
            lambda entry: _file_row(
                entry,
                EditorState.remove_new_project_file(field_id, entry["name"]),
            ),
        ),
        style={"margin_bottom": "10px"},
    )


def _settings_canonical_row(field_id: str, filename) -> rx.Component:
    """Settings-modal row for an existing canonical file. Shows pending-removal toggle."""
    is_pending = EditorState.settings_pending_removals.get(field_id, []).contains(filename)
    return rx.flex(
        rx.cond(
            is_pending,
            rx.icon(tag="trash-2", size=14, style={"color": COLORS["danger"]}),
            rx.icon(tag="file", size=14, style={"color": COLORS["text_sec"]}),
        ),
        rx.text(
            filename,
            style={
                "font_family": FONT_MONO, "font_size": "11px",
                "color": COLORS["text_pri"],
            },
        ),
        rx.cond(
            is_pending,
            rx.text("will be removed",
                    style={"font_family": FONT_MONO, "font_size": "10px",
                           "color": COLORS["danger"], "margin_left": "6px"}),
            rx.fragment(),
        ),
        rx.spacer(),
        rx.icon_button(
            rx.cond(is_pending, rx.icon(tag="undo-2", size=12), rx.icon(tag="x", size=12)),
            variant="ghost", size="1",
            on_click=EditorState.toggle_canonical_removal(field_id, filename),
            style={"color": COLORS["text_dim"]},
        ),
        align="center", gap="6px",
        style={"padding": "3px 6px", "border_radius": "4px"},
    )


def _settings_upload_field(
    field_id: str,
    label: str,
    accept: dict,
    multiple: bool,
    staged_files_var,
    exts_label: str,
    upload_handler,
) -> rx.Component:
    """Settings-modal upload field — shows existing canonical files + drop zone for replacements/additions.

    Pairs the drop zone with a "Browse…" button that opens a native OS file
    dialog at the field's canonical destination directory (so the user lands
    next to the existing file). Falls back to an in-app server-side browser
    when tkinter is unavailable (headless Docker backend).
    """
    upload_id = f"settings-{field_id}"
    canonical_files = EditorState.settings_canonical_files.get(field_id, [])
    return rx.box(
        rx.flex(
            rx.text(label, style={
                "font_family": FONT_MONO, "font_size": "11px",
                "text_transform": "uppercase", "color": COLORS["text_dim"],
            }),
            rx.spacer(),
            rx.button(
                rx.icon(tag="folder-open", size=12),
                rx.text("Browse\u2026", style={"font_family": FONT_MONO, "font_size": "10px"}),
                size="1",
                variant="outline",
                on_click=EditorState.pick_settings_field_file(field_id),
                style={"gap": "4px"},
            ),
            align="center", style={"margin_bottom": "4px"},
        ),
        # Existing canonical files
        rx.foreach(
            canonical_files,
            lambda fname: _settings_canonical_row(field_id, fname),
        ),
        # Drop zone for drag-and-drop (click-to-browse handled by the button above)
        rx.upload(
            _drop_zone(upload_id, f"new {exts_label}", show_click_hint=False),
            id=upload_id,
            accept=accept,
            multiple=multiple,
            on_drop=upload_handler(rx.upload_files(upload_id=upload_id)),
            border="none",
            padding="0",
            style={"width": "100%", "margin_top": "4px"},
        ),
        # Staged (not-yet-applied) replacements / additions
        rx.foreach(
            staged_files_var,
            lambda entry: _file_row(
                entry,
                EditorState.remove_settings_staged_file(field_id, entry["name"]),
            ),
        ),
        style={"margin_bottom": "10px"},
    )


# ---------------------------------------------------------------------------
# Per-mode field stacks for Create
# ---------------------------------------------------------------------------

# rx.upload accept dicts (mirror project_modes.py to keep the modal thin —
# the validators run server-side regardless).
_ACCEPT_PDF       = {"application/pdf": [".pdf"]}
_ACCEPT_GEOMETRY  = {"application/octet-stream": [".obj", ".mtl"]}
_ACCEPT_HDR       = {"application/octet-stream": [".hdr"]}
_ACCEPT_PIC       = {"application/octet-stream": [".pic", ".hdr"]}
_ACCEPT_OCT       = {"application/octet-stream": [".oct"]}
_ACCEPT_RDP       = {"text/plain": [".rdp"]}
_ACCEPT_CSV       = {"text/csv": [".csv"]}
_ACCEPT_ROOM_IESVE = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "text/csv": [".csv"],
}
_ACCEPT_AOI       = {"application/octet-stream": [".aoi"]}


def _create_fields_for_mode(mode_id: str) -> rx.Component:
    """Render the create-modal field stack for a given mode id.

    Every field is optional — users drop in whatever inputs they have and the
    editor adapts based on what is on disk after the project is created.
    """
    S = EditorState  # local alias to keep lines readable
    if mode_id == "sunlight":
        return rx.fragment(
            _create_upload_field("pdf", "PDF floor plan", _ACCEPT_PDF, False,
                                 S.staged_create_pdf, ".pdf", S.upload_create_pdf),
            _create_upload_field("geometry", "Geometry (.obj + .mtl) — for simulation",
                                 _ACCEPT_GEOMETRY, True,
                                 S.staged_create_geometry, ".obj / .mtl", S.upload_create_geometry),
            _create_upload_field("hdr_results", "HDR results — for markup",
                                 _ACCEPT_HDR, True,
                                 S.staged_create_hdr_results, ".hdr", S.upload_create_hdr_results),
            rx.text("Rooms (choose one)", style={
                "font_family": FONT_MONO, "font_size": "11px",
                "text_transform": "uppercase", "color": COLORS["text_dim"],
                "margin_top": "8px", "margin_bottom": "4px",
            }),
            _create_upload_field("room_data", "room_boundaries.csv — rows become .aoi files",
                                 _ACCEPT_CSV, False,
                                 S.staged_create_room_data, ".csv", S.upload_create_room_data),
            _create_upload_field("aoi_files", ".aoi files — pre-built room boundaries",
                                 _ACCEPT_AOI, True,
                                 S.staged_create_aoi_files, ".aoi", S.upload_create_aoi_files),
            rx.cond(
                S.create_exclusivity_error != "",
                rx.text(S.create_exclusivity_error, style={
                    "font_family": FONT_MONO, "font_size": "11px",
                    "color": COLORS["danger"], "margin_top": "4px",
                }),
                rx.fragment(),
            ),
        )
    if mode_id == "daylight":
        return rx.fragment(
            _create_upload_field("pdf", "PDF floor plan", _ACCEPT_PDF, False,
                                 S.staged_create_pdf, ".pdf", S.upload_create_pdf),
            _create_upload_field("oct", "Octree (.oct) — for simulation",
                                 _ACCEPT_OCT, False,
                                 S.staged_create_oct, ".oct", S.upload_create_oct),
            _create_upload_field("rdp", "Render params (.rdp) — for simulation",
                                 _ACCEPT_RDP, False,
                                 S.staged_create_rdp, ".rdp", S.upload_create_rdp),
            _create_upload_field("pic_results", "PIC results — for markup",
                                 _ACCEPT_PIC, True,
                                 S.staged_create_pic_results, ".pic / .hdr", S.upload_create_pic_results),
            _create_upload_field("aoi_files", ".aoi files",
                                 _ACCEPT_AOI, True,
                                 S.staged_create_aoi_files, ".aoi", S.upload_create_aoi_files),
            _create_upload_field("room_data", "IESVE room data (.xlsx / .csv)",
                                 _ACCEPT_ROOM_IESVE, False,
                                 S.staged_create_room_data, ".xlsx / .csv", S.upload_create_room_data),
        )
    return rx.fragment()


def _settings_fields_for_mode(mode_id: str) -> rx.Component:
    """Render the settings-modal field stack for a given mode id."""
    S = EditorState
    if mode_id == "sunlight":
        return rx.fragment(
            _settings_upload_field("pdf", "PDF floor plan", _ACCEPT_PDF, False,
                                   S.staged_settings_pdf, ".pdf", S.upload_settings_pdf),
            _settings_upload_field("geometry", "Geometry (.obj + .mtl)",
                                   _ACCEPT_GEOMETRY, True,
                                   S.staged_settings_geometry, ".obj / .mtl", S.upload_settings_geometry),
            _settings_upload_field("hdr_results", "HDR results",
                                   _ACCEPT_HDR, True,
                                   S.staged_settings_hdr_results, ".hdr", S.upload_settings_hdr_results),
            _settings_upload_field("room_data", "room_boundaries.csv",
                                   _ACCEPT_CSV, False,
                                   S.staged_settings_room_data, ".csv", S.upload_settings_room_data),
            _settings_upload_field("aoi_files", ".aoi files",
                                   _ACCEPT_AOI, True,
                                   S.staged_settings_aoi_files, ".aoi", S.upload_settings_aoi_files),
        )
    if mode_id == "daylight":
        return rx.fragment(
            _settings_upload_field("pdf", "PDF floor plan", _ACCEPT_PDF, False,
                                   S.staged_settings_pdf, ".pdf", S.upload_settings_pdf),
            _settings_upload_field("oct", "Octree (.oct)", _ACCEPT_OCT, False,
                                   S.staged_settings_oct, ".oct", S.upload_settings_oct),
            _settings_upload_field("rdp", "Render params (.rdp)", _ACCEPT_RDP, False,
                                   S.staged_settings_rdp, ".rdp", S.upload_settings_rdp),
            _settings_upload_field("pic_results", "PIC results",
                                   _ACCEPT_PIC, True,
                                   S.staged_settings_pic_results, ".pic / .hdr", S.upload_settings_pic_results),
            _settings_upload_field("aoi_files", ".aoi files", _ACCEPT_AOI, True,
                                   S.staged_settings_aoi_files, ".aoi", S.upload_settings_aoi_files),
            _settings_upload_field("room_data", "IESVE room data (.xlsx / .csv)",
                                   _ACCEPT_ROOM_IESVE, False,
                                   S.staged_settings_room_data, ".xlsx / .csv", S.upload_settings_room_data),
        )
    return rx.fragment()


def create_project_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Create New Project",
                            style={"font_family": FONT_MONO, "font_size": "18px"}),

            # Project name
            rx.box(
                rx.text("Project name", style={
                    "font_family": FONT_MONO, "font_size": "11px",
                    "text_transform": "uppercase", "color": COLORS["text_dim"],
                    "margin_bottom": "4px",
                }),
                rx.input(
                    placeholder="my-project",
                    on_change=EditorState.set_new_project_name,
                    size="2",
                    style={"font_family": FONT_MONO, "width": "100%"},
                ),
                style={"margin_bottom": "12px"},
            ),

            # Mode selector
            rx.box(
                rx.text("Workflow mode (locked once created)", style={
                    "font_family": FONT_MONO, "font_size": "11px",
                    "text_transform": "uppercase", "color": COLORS["text_dim"],
                    "margin_bottom": "4px",
                }),
                rx.select(
                    [mode_id for mode_id, _ in _MODE_OPTIONS],
                    default_value="sunlight",
                    value=EditorState.new_project_mode,
                    on_change=EditorState.set_new_project_mode,
                    size="2",
                    style={"font_family": FONT_MONO, "width": "100%"},
                ),
                style={"margin_bottom": "12px"},
            ),

            # Mode-conditional fields
            rx.cond(EditorState.new_project_mode == "sunlight",
                    _create_fields_for_mode("sunlight"), rx.fragment()),
            rx.cond(EditorState.new_project_mode == "daylight",
                    _create_fields_for_mode("daylight"), rx.fragment()),

            # Whole-form error summary
            rx.cond(
                EditorState.create_error != "",
                rx.text(EditorState.create_error, style={
                    "font_family": FONT_MONO, "font_size": "12px",
                    "color": COLORS["danger"], "margin_top": "8px",
                }),
                rx.fragment(),
            ),

            rx.flex(
                rx.dialog.close(rx.button("Cancel", variant="outline", size="1",
                                          style={"font_family": FONT_MONO})),
                rx.button(
                    "Create",
                    size="1",
                    on_click=EditorState.create_project,
                    disabled=~EditorState.create_form_is_valid,
                    style={"font_family": FONT_MONO, "background": COLORS["success"]},
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),

            style={"max_width": "560px", "max_height": "85vh", "overflow_y": "auto"},
        ),
        open=EditorState.create_project_modal_open,
        on_open_change=EditorState.close_create_project_modal,
    )


def project_settings_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.flex(
                    rx.icon(tag="settings", size=16, style={"color": COLORS["accent"]}),
                    rx.text("Project Settings", style={"margin_left": "6px"}),
                    align="center",
                ),
                style={"font_family": FONT_MONO, "font_size": "18px"},
            ),
            rx.text(
                EditorState.project,
                style={"font_family": FONT_MONO, "font_size": "12px",
                       "color": COLORS["text_sec"], "margin_bottom": "10px"},
            ),
            rx.text(
                "Add or replace project inputs. Required inputs cannot be removed without a replacement.",
                style={"font_family": FONT_MONO, "font_size": "11px",
                       "color": COLORS["text_dim"], "margin_bottom": "10px"},
            ),

            # Mode-conditional fields based on the current project's mode (immutable)
            rx.cond(EditorState.project_mode == "sunlight",
                    _settings_fields_for_mode("sunlight"), rx.fragment()),
            rx.cond(EditorState.project_mode == "daylight",
                    _settings_fields_for_mode("daylight"), rx.fragment()),

            rx.cond(
                EditorState.settings_error != "",
                rx.text(EditorState.settings_error, style={
                    "font_family": FONT_MONO, "font_size": "12px",
                    "color": COLORS["danger"], "margin_top": "8px",
                }),
                rx.fragment(),
            ),

            rx.flex(
                rx.dialog.close(rx.button("Cancel", variant="outline", size="1",
                                          style={"font_family": FONT_MONO})),
                rx.button(
                    "Apply",
                    size="1",
                    on_click=EditorState.apply_settings,
                    disabled=~EditorState.settings_form_is_valid,
                    style={"font_family": FONT_MONO, "background": COLORS["accent"], "color": "white"},
                ),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),

            style={"max_width": "560px", "max_height": "85vh", "overflow_y": "auto"},
        ),
        open=EditorState.settings_modal_open,
        on_open_change=EditorState.close_settings_modal,
    )


def extract_archive_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Extract Archive", style={"font_family": FONT_MONO, "font_size": "18px"}),
            rx.select(
                EditorState.available_archives, placeholder="Select archive…",
                on_change=EditorState.set_selected_archive, size="2",
                style={"font_family": FONT_MONO, "width": "100%"},
            ),
            rx.text(
                "This will overwrite the current project AOI files and reload the session.",
                style={"font_family": FONT_MONO, "font_size": "14px", "color": COLORS["danger"], "margin_top": "8px"},
            ),
            rx.flex(
                rx.dialog.close(rx.button("Cancel", variant="outline", size="1", style={"font_family": FONT_MONO})),
                rx.button("Extract & Reload", size="1", on_click=EditorState.extract_selected_archive,
                          style={"font_family": FONT_MONO, "background": COLORS["danger"], "color": "white"}),
                justify="end", gap="8px", style={"margin_top": "12px"},
            ),
        ),
        open=EditorState.extract_modal_open,
        on_open_change=EditorState.close_extract_modal,
    )


def accelerad_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.flex(
                    rx.icon(tag="zap", size=16, style={"color": COLORS["accent"]}),
                    rx.text("AcceleradRT Preview", style={"margin_left": "6px"}),
                    align="center",
                ),
                style={"font_family": FONT_MONO, "font_size": "18px"},
            ),
            rx.box(
                rx.text("Octree File", style={
                    "font_family": FONT_MONO, "font_size": "18px", "text_transform": "uppercase",
                    "color": COLORS["text_dim"], "margin_bottom": "4px",
                }),
                rx.select(
                    EditorState.accelerad_oct_files, value=EditorState.accelerad_selected_oct,
                    on_change=EditorState.set_accelerad_oct, size="2",
                    style={"font_family": FONT_MONO, "font_size": "11px", "width": "100%"},
                ),
                style={"margin_bottom": "12px"},
            ),
            rx.flex(
                rx.box(
                    rx.text("Width (px)", style={
                        "font_family": FONT_MONO, "font_size": "18px", "text_transform": "uppercase",
                        "color": COLORS["text_dim"], "margin_bottom": "4px",
                    }),
                    rx.input(value=EditorState.accelerad_res_x.to(str), on_change=EditorState.set_accelerad_res_x,
                             type="number", size="2",
                             style={"font_family": FONT_MONO, "font_size": "11px", "width": "100%"}),
                    style={"flex": "1"},
                ),
                rx.box(
                    rx.text("Height (px)", style={
                        "font_family": FONT_MONO, "font_size": "18px", "text_transform": "uppercase",
                        "color": COLORS["text_dim"], "margin_bottom": "4px",
                    }),
                    rx.input(value=EditorState.accelerad_res_y.to(str), on_change=EditorState.set_accelerad_res_y,
                             type="number", size="2",
                             style={"font_family": FONT_MONO, "font_size": "11px", "width": "100%"}),
                    style={"flex": "1"},
                ),
                gap="12px", style={"margin_bottom": "12px"},
            ),
            rx.cond(
                EditorState.accelerad_error != "",
                rx.text(EditorState.accelerad_error, style={
                    "font_family": FONT_MONO, "font_size": "14px", "color": COLORS["danger"], "margin_bottom": "8px",
                }),
                rx.fragment(),
            ),
            rx.flex(
                rx.dialog.close(rx.button("Cancel", variant="outline", size="2", style={"font_family": FONT_MONO})),
                rx.button(rx.icon(tag="zap", size=14), "Launch", size="2", on_click=EditorState.launch_accelerad,
                          style={"font_family": FONT_MONO, "background": COLORS["accent"], "color": "white", "gap": "4px"}),
                justify="end", gap="8px",
            ),
            style={"max_width": "480px"},
        ),
        open=EditorState.accelerad_modal_open,
        on_open_change=EditorState.close_accelerad_modal,
    )
