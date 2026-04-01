"""EditorState — central Reflex state for the HDR AOI Editor (spec §10)."""

import os
import subprocess
import sys
from pathlib import Path

import reflex as rx


class EditorState(rx.State):
    """Server-side state mirroring spec §10.2."""

    # -- Project ----------------------------------------------------------
    project: str = ""
    available_projects: list[str] = []

    # -- Image navigation -------------------------------------------------
    hdr_paths: list[str] = []
    current_hdr_index: int = 0
    image_variant: str = "hdr"  # "hdr" | "tiff"
    show_image: bool = True

    # -- Rooms ------------------------------------------------------------
    rooms: list[dict] = []
    selected_room_idx: int = -1  # -1 = none
    multi_selected_room_idxs: list[int] = []
    selected_parent: str = ""

    # -- Drawing / interaction modes --------------------------------------
    draw_mode: bool = False
    edit_mode: bool = False
    divider_mode: bool = False
    df_placement_mode: bool = False
    ortho_lines: bool = True

    # -- Drawing buffers --------------------------------------------------
    draw_vertices: list[dict] = []  # [{x, y}, ...]
    divider_points: list[dict] = []

    # -- Overlay / floor plan ---------------------------------------------
    overlay_visible: bool = False
    overlay_align_mode: bool = False
    overlay_transforms: dict = {}  # per-HDR {offset_x, offset_y, scale_x, scale_y, alpha}
    overlay_page: int = 0

    # -- Annotation -------------------------------------------------------
    annotation_scale: float = 1.0

    # -- Undo -------------------------------------------------------------
    undo_stack: list[dict] = []

    # -- DF% results ------------------------------------------------------
    df_results: dict = {}

    # -- UI chrome --------------------------------------------------------
    project_tree_open: bool = True
    shortcuts_modal_open: bool = False
    open_project_modal_open: bool = False
    create_project_modal_open: bool = False
    extract_modal_open: bool = False
    status_message: str = "Ready"
    status_colour: str = "accent2"  # accent2 | accent | danger
    progress_visible: bool = False
    progress_pct: int = 0
    progress_msg: str = ""

    # -- Grid -------------------------------------------------------------
    grid_spacing: int = 50
    grid_visible: bool = True

    # -- Zoom -------------------------------------------------------------
    zoom_pct: int = 100

    # -- AcceleradRT preview ----------------------------------------------
    accelerad_modal_open: bool = False
    accelerad_oct_files: list[str] = []
    accelerad_selected_oct: str = ""
    accelerad_res_x: int = 900
    accelerad_res_y: int = 900
    accelerad_running: bool = False
    accelerad_error: str = ""

    # =====================================================================
    # Event handlers (stubs — implement logic later)
    # =====================================================================

    def navigate_hdr(self, direction: int):
        """Move to next/previous HDR image."""
        new_idx = self.current_hdr_index + direction
        if 0 <= new_idx < len(self.hdr_paths):
            self.current_hdr_index = new_idx

    def toggle_image_variant(self):
        self.image_variant = "tiff" if self.image_variant == "hdr" else "hdr"

    def toggle_draw_mode(self):
        self.draw_mode = not self.draw_mode
        self.edit_mode = False
        self.divider_mode = False
        self.df_placement_mode = False

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.draw_mode = False
        self.divider_mode = False
        self.df_placement_mode = False

    def toggle_divider_mode(self):
        self.divider_mode = not self.divider_mode
        self.draw_mode = False
        self.edit_mode = False
        self.df_placement_mode = False

    def toggle_df_placement(self):
        self.df_placement_mode = not self.df_placement_mode
        self.draw_mode = False
        self.edit_mode = False
        self.divider_mode = False

    def toggle_ortho(self):
        self.ortho_lines = not self.ortho_lines

    def toggle_overlay(self):
        self.overlay_visible = not self.overlay_visible

    def toggle_overlay_align(self):
        self.overlay_align_mode = not self.overlay_align_mode

    def toggle_show_image(self):
        self.show_image = not self.show_image

    def toggle_project_tree(self):
        self.project_tree_open = not self.project_tree_open

    def set_annotation_scale(self, value: list):
        if value:
            self.annotation_scale = float(value[0])

    def set_selected_parent(self, value: str):
        self.selected_parent = value

    def cycle_parent(self, direction: int):
        """Cycle through parent apartments. Stub."""

    def select_room(self, idx: int):
        self.selected_room_idx = idx

    def save_room(self):
        """Save current room (draw, divider, or edit). Stub."""

    def delete_room(self):
        """Delete selected room. Stub."""

    def undo(self):
        """Pop undo stack. Stub."""

    def reset_zoom(self):
        self.zoom_pct = 100

    def fit_zoom(self):
        """Fit zoom to selected room. Stub."""

    def select_all_rooms(self):
        """Select all rooms for current HDR. Stub."""

    def canvas_click(self, click_data: dict):
        """Handle canvas click in current mode. Stub."""

    # -- Project management -----------------------------------------------

    def open_project(self, name: str):
        """Load project by name. Stub."""
        self.project = name

    def create_project(self, name: str):
        """Create new project. Stub."""
        self.project = name

    def extract_archive(self, archive_name: str):
        """Extract archive into project. Stub."""

    # -- Modals -----------------------------------------------------------

    def open_shortcuts_modal(self):
        self.shortcuts_modal_open = True

    def close_shortcuts_modal(self):
        self.shortcuts_modal_open = False

    def open_open_project_modal(self):
        self.open_project_modal_open = True

    def close_open_project_modal(self):
        self.open_project_modal_open = False

    def open_create_project_modal(self):
        self.create_project_modal_open = True

    def close_create_project_modal(self):
        self.create_project_modal_open = False

    def open_extract_modal(self):
        self.extract_modal_open = True

    def close_extract_modal(self):
        self.extract_modal_open = False

    # -- AcceleradRT handlers ---------------------------------------------

    def open_accelerad_modal(self):
        """Scan for .oct files and open the launch modal."""
        project_root = Path(__file__).resolve().parents[4]
        oct_files = []
        projects_dir = project_root / "projects"
        if projects_dir.exists():
            for oct_path in projects_dir.rglob("*.oct"):
                oct_files.append(str(oct_path))
        # Also include the bundled demo
        demo_oct = project_root / ".devcontainer" / "accelerad_07_beta_Windows" / "demo" / "test.oct"
        if demo_oct.exists():
            oct_files.insert(0, str(demo_oct))
        self.accelerad_oct_files = sorted(oct_files)
        self.accelerad_selected_oct = oct_files[0] if oct_files else ""
        self.accelerad_error = ""
        self.accelerad_modal_open = True

    def close_accelerad_modal(self):
        self.accelerad_modal_open = False

    def set_accelerad_oct(self, value: str):
        self.accelerad_selected_oct = value

    def set_accelerad_res_x(self, value: str):
        try:
            self.accelerad_res_x = int(value)
        except ValueError:
            pass

    def set_accelerad_res_y(self, value: str):
        try:
            self.accelerad_res_y = int(value)
        except ValueError:
            pass

    def launch_accelerad(self):
        """Launch AcceleradRT as a detached subprocess.

        Mirrors archilume/apps/octree_viewer.py using config paths.
        """
        if not self.accelerad_selected_oct:
            self.accelerad_error = "No octree file selected."
            return

        oct_path = Path(self.accelerad_selected_oct)
        if not oct_path.exists():
            self.accelerad_error = f"File not found: {oct_path}"
            return

        from archilume import config

        exe = config.ACCELERAD_BIN_PATH / "AcceleradRT.exe"
        if not exe.exists():
            self.accelerad_error = f"AcceleradRT not found: {exe}"
            return

        env = os.environ.copy()
        env["RAYPATH"] = config.RAYPATH

        cmd = [
            str(exe),
            "-x", str(self.accelerad_res_x),
            "-y", str(self.accelerad_res_y),
            "-ab", "1",
            str(oct_path),
        ]

        try:
            subprocess.Popen(
                cmd,
                env=env,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                if sys.platform == "win32" else 0,
            )
            self.accelerad_running = True
            self.accelerad_error = ""
            self.accelerad_modal_open = False
            self.status_message = f"AcceleradRT launched: {oct_path.name}"
        except Exception as e:
            self.accelerad_error = str(e)

    # -- Keyboard handler -------------------------------------------------

    def handle_key(self, key: str):
        """Route keyboard shortcut to correct action. Stub."""
        keymap = {
            "d": self.toggle_draw_mode,
            "e": self.toggle_edit_mode,
            "o": self.toggle_ortho,
            "p": self.toggle_df_placement,
            "t": self.toggle_image_variant,
            "r": self.reset_zoom,
            "f": self.fit_zoom,
        }
        action = keymap.get(key.lower())
        if action:
            action()
