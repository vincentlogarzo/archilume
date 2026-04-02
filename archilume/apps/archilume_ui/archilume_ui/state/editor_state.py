"""EditorState — single unified Reflex state for the HDR AOI Editor.

All state is in one class to avoid Reflex substate delegation issues.
Organised into sections matching the original split-state design.
"""

import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

import reflex as rx

from ..lib.geometry import polygon_label_point


class HdrFileInfo(TypedDict):
    name: str
    hdr_path: str
    tiff_paths: list[str]


class RoomDict(TypedDict):
    name: str
    parent: str
    room_type: str
    hdr_file: str
    vertices: list[list[float]]
    visible: bool


class EnrichedRoom(TypedDict):
    idx: int
    name: str
    room_type: str
    parent: str
    vertices_str: str
    label_x: str
    label_y: str
    df_label_y: str
    selected: bool
    df_lines: str
    df_status: str


class VertexDict(TypedDict):
    x: float
    y: float


class AlignPoint(TypedDict):
    x: float
    y: float


class VertexPoint(TypedDict):
    x: float
    y: float


class DfStamp(TypedDict):
    x: float
    y: float
    value: float


class EditorState(rx.State):
    """Unified state for the entire editor application."""

    # =====================================================================
    # §1 — Project
    # =====================================================================
    project: str = ""
    available_projects: list[str] = []
    project_mode: str = "archilume"
    session_path: str = ""

    # -- Create project form
    new_project_name: str = ""
    new_project_mode: str = "archilume"
    create_error: str = ""

    # =====================================================================
    # §2 — Image navigation
    # =====================================================================
    hdr_files: list[HdrFileInfo] = []
    current_hdr_idx: int = 0
    image_variants: list[str] = []
    current_variant_idx: int = 0

    # -- Image display
    current_image_b64: str = ""
    image_width: int = 0
    image_height: int = 0

    # =====================================================================
    # §3 — Rooms
    # =====================================================================
    rooms: list[RoomDict] = []
    selected_room_idx: int = -1
    multi_selected_idxs: list[int] = []
    selected_parent: str = ""
    room_name_input: str = ""
    room_type_input: str = "BED"

    # =====================================================================
    # §4 — Interaction modes
    # =====================================================================
    draw_mode: bool = False
    edit_mode: bool = False
    divider_mode: bool = False
    df_placement_mode: bool = False
    ortho_mode: bool = True

    # =====================================================================
    # §5 — Drawing buffer
    # =====================================================================
    draw_vertices: list[VertexDict] = []
    snap_point: dict = {}
    preview_point: dict = {}

    # =====================================================================
    # §6 — Editing
    # =====================================================================
    dragging_vertex_idx: int = -1
    hover_vertex_idx: int = -1
    hover_edge_idx: int = -1
    edit_undo_stack: list[dict] = []
    draw_undo_stack: list[dict] = []

    # =====================================================================
    # §7 — Divider
    # =====================================================================
    divider_points: list[dict] = []
    divider_room_idx: int = -1

    # =====================================================================
    # §8 — PDF overlay
    # =====================================================================
    overlay_visible: bool = False
    overlay_image_b64: str = ""
    overlay_pdf_path: str = ""
    overlay_page_idx: int = 0
    overlay_page_count: int = 0
    overlay_dpi: int = 150
    overlay_alpha: float = 0.6
    overlay_align_mode: bool = False
    overlay_transforms: dict = {}
    align_points: list[AlignPoint] = []

    # =====================================================================
    # §9 — DF% analysis
    # =====================================================================
    df_stamps: dict = {}
    room_df_results: dict = {}

    # =====================================================================
    # §10 — Export / AcceleradRT
    # =====================================================================
    progress_visible: bool = False
    progress_pct: int = 0
    progress_msg: str = ""
    available_archives: list[str] = []
    selected_archive: str = ""
    accelerad_modal_open: bool = False
    accelerad_oct_files: list[str] = []
    accelerad_selected_oct: str = ""
    accelerad_res_x: int = 900
    accelerad_res_y: int = 900
    accelerad_running: bool = False
    accelerad_error: str = ""

    # =====================================================================
    # §11 — Zoom / Pan
    # =====================================================================
    zoom_level: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    annotation_scale: float = 1.0

    # =====================================================================
    # §12 — Mouse state
    # =====================================================================
    mouse_x: float = 0.0
    mouse_y: float = 0.0

    # =====================================================================
    # §13 — UI chrome
    # =====================================================================
    project_tree_open: bool = True
    shortcuts_modal_open: bool = False
    open_project_modal_open: bool = False
    create_project_modal_open: bool = False
    extract_modal_open: bool = False
    status_message: str = "Ready"
    status_colour: str = "accent2"
    _last_d_press: float = 0.0
    _UNDO_MAX: int = 50

    # =====================================================================
    # COMPUTED VARS
    # =====================================================================

    @rx.var
    def current_hdr_name(self) -> str:
        if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files):
            return self.hdr_files[self.current_hdr_idx]["name"]
        return "No images"

    @rx.var
    def current_hdr_count(self) -> str:
        if not self.hdr_files:
            return ""
        return f"{self.current_hdr_idx + 1} / {len(self.hdr_files)}"

    @rx.var
    def current_variant_label(self) -> str:
        if not self.image_variants:
            return "—"
        idx = min(self.current_variant_idx, len(self.image_variants) - 1)
        p = self.image_variants[idx]
        if p.lower().endswith((".hdr", ".pic")):
            return "HDR"
        return "TIFF"

    @rx.var
    def resolved_room_name(self) -> str:
        if not self.room_name_input:
            return ""
        if self.selected_parent:
            return f"→ {self.selected_parent}_{self.room_name_input}"
        return f"→ {self.room_name_input}"

    @rx.var
    def has_multi_selection(self) -> bool:
        return len(self.multi_selected_idxs) > 1

    @rx.var
    def multi_selection_count(self) -> int:
        return len(self.multi_selected_idxs)

    @rx.var
    def canvas_transform(self) -> str:
        return f"scale({self.zoom_level}) translate({self.pan_x}px, {self.pan_y}px)"

    @rx.var
    def zoom_pct(self) -> str:
        return f"{int(self.zoom_level * 100)}%"

    @rx.var
    def svg_viewbox(self) -> str:
        if self.image_width > 0 and self.image_height > 0:
            return f"0 0 {self.image_width} {self.image_height}"
        return "0 0 1000 800"

    @rx.var
    def enriched_rooms(self) -> list[EnrichedRoom]:
        """Rooms for current HDR enriched with SVG rendering data."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        result = []
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != hdr_name:
                continue
            if not room.get("visible", True):
                continue
            verts = room.get("vertices", [])
            if len(verts) < 3:
                continue

            # SVG points string
            verts_str = " ".join(f"{v[0]},{v[1]}" for v in verts)

            # Label position via centroid
            lx, ly = polygon_label_point(verts)

            # DF results
            df_info = self.room_df_results.get(str(i), {})
            df_lines = df_info.get("result_lines", [])
            df_status = df_info.get("pass_status", "none")

            result.append({
                "idx": i,
                "name": room.get("name", ""),
                "room_type": room.get("room_type", ""),
                "parent": room.get("parent", ""),
                "vertices_str": verts_str,
                "label_x": str(lx),
                "label_y": str(ly),
                "df_label_y": str(ly + 14),
                "selected": i == self.selected_room_idx or i in self.multi_selected_idxs,
                "df_lines": "\n".join(df_lines) if df_lines else "",
                "df_status": df_status,
            })
        return result

    @rx.var
    def draw_points_str(self) -> str:
        if not self.draw_vertices:
            return ""
        return " ".join(f"{v['x']},{v['y']}" for v in self.draw_vertices)

    @rx.var
    def has_draw_vertices(self) -> bool:
        return len(self.draw_vertices) > 0

    @rx.var
    def last_draw_vertex(self) -> dict:
        if self.draw_vertices:
            return self.draw_vertices[-1]
        return {"x": 0.0, "y": 0.0}

    @rx.var
    def has_snap(self) -> bool:
        return bool(self.snap_point)

    @rx.var
    def has_preview(self) -> bool:
        return bool(self.preview_point)

    @rx.var
    def divider_points_str(self) -> str:
        if not self.divider_points:
            return ""
        return " ".join(f"{p['x']},{p['y']}" for p in self.divider_points)

    @rx.var
    def has_divider_points(self) -> bool:
        return len(self.divider_points) > 0

    @rx.var
    def is_dragging(self) -> bool:
        return self.dragging_vertex_idx >= 0

    @rx.var
    def current_hdr_stamps(self) -> list[DfStamp]:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        raw = self.df_stamps.get(hdr_name, [])
        return [{"x": float(s[0]), "y": float(s[1]), "value": float(s[2])} for s in raw if len(s) >= 3]

    @rx.var
    def overlay_css_transform(self) -> str:
        t = self._get_current_overlay_transform()
        ox = t.get("offset_x", 0)
        oy = t.get("offset_y", 0)
        sx = t.get("scale_x", 1.0)
        sy = t.get("scale_y", 1.0)
        rot = t.get("rotation_90", 0) * 90
        return f"translate({ox}px, {oy}px) scale({sx}, {sy}) rotate({rot}deg)"

    @rx.var
    def progress_pct_str(self) -> str:
        return f"{self.progress_pct}%"

    @rx.var
    def overlay_alpha_str(self) -> str:
        return str(self.overlay_alpha)

    @rx.var
    def selected_room_vertices(self) -> list[VertexPoint]:
        """Vertices of the selected room, for edit mode handles."""
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return []
        verts = self.rooms[self.selected_room_idx].get("vertices", [])
        return [{"x": float(v[0]), "y": float(v[1])} for v in verts]

    # =====================================================================
    # MODE TOGGLES
    # =====================================================================

    def _clear_modes(self) -> None:
        self.draw_mode = False
        self.edit_mode = False
        self.divider_mode = False
        self.df_placement_mode = False
        self.draw_vertices = []
        self.snap_point = {}
        self.preview_point = {}
        self.divider_points = []
        self.dragging_vertex_idx = -1

    def toggle_draw_mode(self) -> None:
        was_on = self.draw_mode
        self._clear_modes()
        self.draw_mode = not was_on
        self.status_message = "Draw mode ON — click to place vertices, S to save" if self.draw_mode else "Ready"
        self.status_colour = "accent" if self.draw_mode else "accent2"

    def toggle_edit_mode(self) -> None:
        was_on = self.edit_mode
        self._clear_modes()
        self.edit_mode = not was_on
        self.status_message = "Edit mode ON — drag vertices, right-click to delete" if self.edit_mode else "Ready"
        self.status_colour = "warning" if self.edit_mode else "accent2"

    def toggle_divider_mode(self) -> None:
        was_on = self.divider_mode
        self._clear_modes()
        self.divider_mode = not was_on
        if self.divider_mode and self.selected_room_idx >= 0:
            self.divider_room_idx = self.selected_room_idx
        self.status_message = "Divider mode ON — click to place cut line, S to split" if self.divider_mode else "Ready"
        self.status_colour = "accent2"

    def toggle_df_placement(self) -> None:
        was_on = self.df_placement_mode
        self._clear_modes()
        self.df_placement_mode = not was_on
        self.status_message = "DF% placement ON — click to stamp values" if self.df_placement_mode else "Ready"
        self.status_colour = "accent" if self.df_placement_mode else "accent2"

    def toggle_ortho(self) -> None:
        self.ortho_mode = not self.ortho_mode
        self.status_message = f"Ortho {'ON' if self.ortho_mode else 'OFF'}"

    def exit_mode(self) -> None:
        if self.draw_mode or self.edit_mode or self.divider_mode or self.df_placement_mode or self.overlay_align_mode:
            self._clear_modes()
            self.overlay_align_mode = False
            self.align_points = []
            self.status_message = "Ready"
            self.status_colour = "accent2"
        else:
            self.selected_room_idx = -1
            self.multi_selected_idxs = []

    # =====================================================================
    # IMAGE NAVIGATION
    # =====================================================================

    def navigate_hdr(self, direction: int) -> None:
        if not self.hdr_files:
            return
        new_idx = self.current_hdr_idx + direction
        if 0 <= new_idx < len(self.hdr_files):
            self.current_hdr_idx = new_idx
            self._rebuild_variants()
            self.load_current_image()

    def toggle_image_variant(self) -> None:
        if not self.image_variants:
            return
        self.current_variant_idx = (self.current_variant_idx + 1) % len(self.image_variants)
        self.load_current_image()

    def _rebuild_variants(self) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            self.image_variants = []
            self.current_variant_idx = 0
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        variants = [hdr_info["hdr_path"]] + hdr_info.get("tiff_paths", [])
        self.image_variants = variants
        if self.current_variant_idx >= len(variants):
            self.current_variant_idx = 0

    def load_current_image(self) -> None:
        if not self.image_variants:
            self.current_image_b64 = ""
            return
        idx = min(self.current_variant_idx, len(self.image_variants) - 1)
        path = Path(self.image_variants[idx])
        from ..lib.image_loader import get_image_dimensions, load_image_as_base64
        b64 = load_image_as_base64(path)
        if b64:
            self.current_image_b64 = b64
            w, h = get_image_dimensions(path)
            self.image_width = w
            self.image_height = h
        else:
            self.current_image_b64 = ""

    # =====================================================================
    # ROOM SELECTION
    # =====================================================================

    def select_room(self, idx: int) -> None:
        self.selected_room_idx = idx
        if 0 <= idx < len(self.rooms):
            room = self.rooms[idx]
            self.room_name_input = room.get("name", "")
            self.room_type_input = room.get("room_type", "BED")
            self.selected_parent = room.get("parent", "") or ""

    def select_room_multi(self, idx: int) -> None:
        if idx in self.multi_selected_idxs:
            self.multi_selected_idxs = [i for i in self.multi_selected_idxs if i != idx]
        else:
            self.multi_selected_idxs = self.multi_selected_idxs + [idx]

    def select_all_rooms(self) -> None:
        if not self.hdr_files:
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        self.multi_selected_idxs = [
            i for i, r in enumerate(self.rooms) if r.get("hdr_file") == hdr_name
        ]

    def set_room_name(self, value: str) -> None:
        self.room_name_input = value

    def set_room_type(self, rtype: str) -> None:
        self.room_type_input = rtype
        if self.multi_selected_idxs:
            rooms_copy = list(self.rooms)
            for idx in self.multi_selected_idxs:
                if 0 <= idx < len(rooms_copy):
                    rooms_copy[idx] = {**rooms_copy[idx], "room_type": rtype}
            self.rooms = rooms_copy
        elif 0 <= self.selected_room_idx < len(self.rooms):
            rooms_copy = list(self.rooms)
            rooms_copy[self.selected_room_idx] = {**rooms_copy[self.selected_room_idx], "room_type": rtype}
            self.rooms = rooms_copy

    def set_selected_parent(self, value: str) -> None:
        self.selected_parent = value

    def cycle_parent(self, direction: int) -> None:
        if not self.hdr_files:
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        parents = sorted(set(
            r.get("parent", "") for r in self.rooms
            if r.get("hdr_file") == hdr_name and r.get("parent")
        ))
        if not parents:
            self.selected_parent = ""
            return
        try:
            idx = parents.index(self.selected_parent)
            idx = (idx + direction) % len(parents)
        except ValueError:
            idx = 0
        self.selected_parent = parents[idx]

    def delete_room(self) -> None:
        if self.multi_selected_idxs:
            to_delete = set(self.multi_selected_idxs)
            self.rooms = [r for i, r in enumerate(self.rooms) if i not in to_delete]
            self.multi_selected_idxs = []
            self.selected_room_idx = -1
        elif 0 <= self.selected_room_idx < len(self.rooms):
            self.rooms = [r for i, r in enumerate(self.rooms) if i != self.selected_room_idx]
            self.selected_room_idx = -1
        self.status_message = "Room deleted"
        self._auto_save()

    # =====================================================================
    # CANVAS — click routing, coordinate conversion, zoom/pan
    # =====================================================================

    def handle_canvas_click(self, data: dict) -> None:
        """Route canvas click. data: {x, y, button, shiftKey, ctrlKey} from JS."""
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        button = int(data.get("button", 0))
        shift = bool(data.get("shiftKey", False))
        ctrl = bool(data.get("ctrlKey", False))

        self.mouse_x = x
        self.mouse_y = y

        if self.draw_mode:
            if button == 2:
                self._drawing_undo_vertex()
            else:
                self._drawing_add_vertex(x, y)
        elif self.edit_mode:
            self._editing_click(x, y, button, shift)
        elif self.divider_mode:
            if button == 2:
                self._divider_undo_point()
            else:
                self._divider_add_point(x, y)
        elif self.df_placement_mode:
            if button == 2:
                self._df_remove_nearest(x, y)
            else:
                self._df_stamp(x, y)
        elif self.overlay_align_mode:
            self._add_align_point(x, y)
        else:
            if ctrl:
                self._select_room_at(x, y, multi=True)
            else:
                self._select_room_at(x, y, multi=False)

    def handle_mouse_move(self, data: dict) -> None:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        self.mouse_x = x
        self.mouse_y = y

        if self.draw_mode and self.draw_vertices:
            self._update_draw_preview(x, y)
        elif self.edit_mode and self.dragging_vertex_idx >= 0:
            self._drag_vertex(x, y)

    def handle_mouse_down(self, data: dict) -> None:
        if not self.edit_mode:
            return
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        self._editing_start_drag(x, y)

    def handle_mouse_up(self, _data: dict) -> None:
        if self.edit_mode:
            self.dragging_vertex_idx = -1

    def handle_wheel(self, data: dict) -> None:
        """Scroll-wheel zoom centred on cursor, or middle-mouse pan."""
        # Middle-mouse pan (sent by JS with panDx/panDy)
        pan_dx = float(data.get("panDx", 0))
        pan_dy = float(data.get("panDy", 0))
        if pan_dx != 0 or pan_dy != 0:
            if self.zoom_level > 0:
                self.pan_x += pan_dx / self.zoom_level
                self.pan_y += pan_dy / self.zoom_level
            return

        delta = float(data.get("deltaY", 0))
        cx = float(data.get("x", 0))
        cy = float(data.get("y", 0))
        if delta == 0:
            return

        factor = 0.9 if delta > 0 else 1.1
        new_zoom = max(0.1, min(10.0, self.zoom_level * factor))

        # Adjust pan so point under cursor stays fixed
        if self.zoom_level > 0:
            self.pan_x = cx / new_zoom - cx / self.zoom_level + self.pan_x
            self.pan_y = cy / new_zoom - cy / self.zoom_level + self.pan_y

        self.zoom_level = new_zoom

    def reset_zoom(self) -> None:
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def fit_zoom(self) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            self.reset_zoom()
            return
        room = self.rooms[self.selected_room_idx]
        verts = room.get("vertices", [])
        if not verts or self.image_width <= 0:
            self.reset_zoom()
            return
        from ..lib.geometry import polygon_bbox
        min_x, min_y, max_x, max_y = polygon_bbox(verts)
        pad = 50
        bw = max_x - min_x + 2 * pad
        bh = max_y - min_y + 2 * pad
        if bw <= 0 or bh <= 0:
            self.reset_zoom()
            return
        zx = self.image_width / bw
        zy = self.image_height / bh
        self.zoom_level = min(zx, zy, 5.0)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self.pan_x = -(cx - self.image_width / (2 * self.zoom_level))
        self.pan_y = -(cy - self.image_height / (2 * self.zoom_level))

    def set_annotation_scale(self, value: list) -> None:
        if value:
            self.annotation_scale = float(value[0])

    def _select_room_at(self, x: float, y: float, multi: bool = False) -> None:
        from ..lib.geometry import point_in_polygon
        if not self.hdr_files:
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != hdr_name:
                continue
            verts = room.get("vertices", [])
            if len(verts) < 3:
                continue
            if point_in_polygon(x, y, verts):
                if multi:
                    self.select_room_multi(i)
                else:
                    self.select_room(i)
                return
        if not multi:
            self.selected_room_idx = -1
            self.multi_selected_idxs = []

    # =====================================================================
    # DRAWING MODE
    # =====================================================================

    def _drawing_add_vertex(self, x: float, y: float) -> None:
        from ..lib.geometry import ortho_constrain, point_in_polygon, snap_to_vertex
        all_verts = self._get_all_vertices_for_hdr()
        sx, sy, snapped = snap_to_vertex(x, y, all_verts, threshold=10.0)
        if snapped:
            x, y = sx, sy
        if self.ortho_mode and self.draw_vertices:
            last = self.draw_vertices[-1]
            x, y = ortho_constrain(x, y, last["x"], last["y"])
        if not self.draw_vertices and not self.selected_parent:
            self._auto_detect_parent(x, y)
        self.draw_vertices = self.draw_vertices + [{"x": x, "y": y}]
        self.snap_point = {}

    def _drawing_undo_vertex(self) -> None:
        if self.draw_vertices:
            self.draw_vertices = self.draw_vertices[:-1]

    def _update_draw_preview(self, x: float, y: float) -> None:
        from ..lib.geometry import ortho_constrain, snap_to_vertex
        all_verts = self._get_all_vertices_for_hdr()
        sx, sy, snapped = snap_to_vertex(x, y, all_verts, threshold=10.0)
        if snapped:
            self.snap_point = {"x": sx, "y": sy}
            x, y = sx, sy
        else:
            self.snap_point = {}
        if self.ortho_mode and self.draw_vertices:
            last = self.draw_vertices[-1]
            x, y = ortho_constrain(x, y, last["x"], last["y"])
        self.preview_point = {"x": x, "y": y}

    def save_room(self) -> None:
        if self.draw_mode and len(self.draw_vertices) >= 3:
            self._save_new_room()
        elif self.edit_mode and 0 <= self.selected_room_idx < len(self.rooms):
            self._save_edited_room()
        elif self.divider_mode:
            self._finalize_divider()
        else:
            # Just save name/type of selected room
            if 0 <= self.selected_room_idx < len(self.rooms):
                self._save_edited_room()

    def _save_new_room(self) -> None:
        from ..lib.geometry import make_unique_name, point_in_polygon
        vertices = [[v["x"], v["y"]] for v in self.draw_vertices]
        name = self.room_name_input.strip()
        if not name:
            name = f"ROOM_{len(self.rooms) + 1:03d}"
        if self.selected_parent:
            full_name = f"{self.selected_parent}_{name}"
        else:
            full_name = name
        existing_names = [r.get("name", "") for r in self.rooms]
        full_name = make_unique_name(full_name, existing_names)

        hdr_name = ""
        if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files):
            hdr_name = self.hdr_files[self.current_hdr_idx]["name"]

        # Containment validation
        if self.selected_parent:
            parent_room = next((r for r in self.rooms if r.get("name") == self.selected_parent), None)
            if parent_room:
                parent_verts = parent_room.get("vertices", [])
                if parent_verts:
                    outside = [v for v in vertices if not point_in_polygon(v[0], v[1], parent_verts)]
                    if outside:
                        self.status_message = f"Warning: {len(outside)} vertices outside parent boundary"

        new_room = {
            "name": full_name,
            "parent": self.selected_parent or None,
            "vertices": vertices,
            "hdr_file": hdr_name,
            "room_type": self.room_type_input or "BED",
            "visible": True,
        }
        # Push draw undo
        self.draw_undo_stack = (self.draw_undo_stack + [
            {"action": "create", "room_idx": len(self.rooms)}
        ])[-self._UNDO_MAX:]

        self.rooms = self.rooms + [new_room]
        self.draw_vertices = []
        self.snap_point = {}
        self.preview_point = {}
        self.room_name_input = ""
        self.status_message = f"Saved room: {full_name}"
        self.status_colour = "accent"
        self._auto_save()

    def _save_edited_room(self) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        rooms_copy = list(self.rooms)
        room = dict(rooms_copy[self.selected_room_idx])
        if self.room_name_input.strip():
            room["name"] = self.room_name_input.strip()
        room["room_type"] = self.room_type_input
        room["parent"] = self.selected_parent or None
        rooms_copy[self.selected_room_idx] = room
        self.rooms = rooms_copy
        self.status_message = f"Updated: {room['name']}"
        self._auto_save()

    def _auto_detect_parent(self, x: float, y: float) -> None:
        from ..lib.geometry import point_in_polygon
        if not self.hdr_files:
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        for room in self.rooms:
            if room.get("hdr_file") != hdr_name:
                continue
            if not room.get("parent"):
                verts = room.get("vertices", [])
                if len(verts) >= 3 and point_in_polygon(x, y, verts):
                    self.selected_parent = room.get("name", "")
                    return

    def _get_all_vertices_for_hdr(self) -> list[list[float]]:
        if not self.hdr_files:
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        verts: list[list[float]] = []
        for room in self.rooms:
            if room.get("hdr_file") == hdr_name:
                verts.extend(room.get("vertices", []))
        return verts

    # =====================================================================
    # EDIT MODE
    # =====================================================================

    def _editing_click(self, x: float, y: float, button: int, shift: bool) -> None:
        if button == 2:
            self._delete_vertex_at(x, y)
            return
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        room = self.rooms[self.selected_room_idx]
        verts = room.get("vertices", [])
        # Check vertex click
        for i, v in enumerate(verts):
            if math.hypot(x - v[0], y - v[1]) < 10.0:
                self._push_edit_undo()
                self.dragging_vertex_idx = i
                return
        # Check edge click → insert vertex
        from ..lib.geometry import find_nearest_edge
        edge = find_nearest_edge(x, y, verts, threshold=10.0)
        if edge is not None:
            edge_idx, nx, ny, _ = edge
            self._push_edit_undo()
            self._insert_vertex_at_edge(edge_idx, nx, ny)

    def _editing_start_drag(self, x: float, y: float) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        verts = self.rooms[self.selected_room_idx].get("vertices", [])
        for i, v in enumerate(verts):
            if math.hypot(x - v[0], y - v[1]) < 10.0:
                self._push_edit_undo()
                self.dragging_vertex_idx = i
                return

    def _drag_vertex(self, x: float, y: float) -> None:
        if self.dragging_vertex_idx < 0 or self.selected_room_idx < 0:
            return
        if self.selected_room_idx >= len(self.rooms):
            return
        room = self.rooms[self.selected_room_idx]
        verts = room.get("vertices", [])
        if self.dragging_vertex_idx >= len(verts):
            return
        if self.ortho_mode:
            from ..lib.geometry import ortho_constrain
            orig = verts[self.dragging_vertex_idx]
            x, y = ortho_constrain(x, y, orig[0], orig[1])
        new_verts = [list(v) for v in verts]
        new_verts[self.dragging_vertex_idx] = [x, y]
        rooms_copy = list(self.rooms)
        rooms_copy[self.selected_room_idx] = {**rooms_copy[self.selected_room_idx], "vertices": new_verts}
        self.rooms = rooms_copy

    def _insert_vertex_at_edge(self, edge_idx: int, x: float, y: float) -> None:
        if self.selected_room_idx < 0:
            return
        verts = [list(v) for v in self.rooms[self.selected_room_idx].get("vertices", [])]
        verts.insert(edge_idx + 1, [x, y])
        rooms_copy = list(self.rooms)
        rooms_copy[self.selected_room_idx] = {**rooms_copy[self.selected_room_idx], "vertices": verts}
        self.rooms = rooms_copy
        self.dragging_vertex_idx = edge_idx + 1

    def _delete_vertex_at(self, x: float, y: float) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        verts = self.rooms[self.selected_room_idx].get("vertices", [])
        if len(verts) <= 3:
            self.status_message = "Cannot delete: minimum 3 vertices"
            return
        best_i = -1
        best_d = 10.0
        for i, v in enumerate(verts):
            d = math.hypot(x - v[0], y - v[1])
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0:
            self._push_edit_undo()
            new_verts = [v for j, v in enumerate(verts) if j != best_i]
            rooms_copy = list(self.rooms)
            rooms_copy[self.selected_room_idx] = {**rooms_copy[self.selected_room_idx], "vertices": new_verts}
            self.rooms = rooms_copy

    def delete_hovered_vertex(self) -> None:
        if self.edit_mode and self.selected_room_idx >= 0:
            self._delete_vertex_at(self.mouse_x, self.mouse_y)

    # =====================================================================
    # UNDO
    # =====================================================================

    def _push_edit_undo(self) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        room = self.rooms[self.selected_room_idx]
        entry = {"room_idx": self.selected_room_idx, "vertices": [list(v) for v in room.get("vertices", [])]}
        self.edit_undo_stack = (self.edit_undo_stack + [entry])[-self._UNDO_MAX:]

    def undo(self) -> None:
        if self.edit_mode and self.edit_undo_stack:
            entry = self.edit_undo_stack[-1]
            self.edit_undo_stack = self.edit_undo_stack[:-1]
            idx = entry["room_idx"]
            if 0 <= idx < len(self.rooms):
                rooms_copy = list(self.rooms)
                rooms_copy[idx] = {**rooms_copy[idx], "vertices": entry["vertices"]}
                self.rooms = rooms_copy
        elif self.draw_undo_stack:
            entry = self.draw_undo_stack[-1]
            self.draw_undo_stack = self.draw_undo_stack[:-1]
            action = entry.get("action")
            if action == "create":
                idx = entry.get("room_idx", -1)
                if 0 <= idx < len(self.rooms):
                    self.rooms = [r for i, r in enumerate(self.rooms) if i != idx]
            elif action == "delete":
                room_data = entry.get("room_data")
                idx = entry.get("room_idx", len(self.rooms))
                if room_data:
                    rooms_copy = list(self.rooms)
                    rooms_copy.insert(min(idx, len(rooms_copy)), room_data)
                    self.rooms = rooms_copy

    # =====================================================================
    # DIVIDER
    # =====================================================================

    def _divider_add_point(self, x: float, y: float) -> None:
        from ..lib.geometry import ortho_constrain
        if self.selected_room_idx < 0:
            self.status_message = "Select a room first"
            return
        if self.divider_room_idx < 0:
            self.divider_room_idx = self.selected_room_idx
        if self.ortho_mode and self.divider_points:
            last = self.divider_points[-1]
            x, y = ortho_constrain(x, y, last["x"], last["y"])
        self.divider_points = self.divider_points + [{"x": x, "y": y}]

    def _divider_undo_point(self) -> None:
        if self.divider_points:
            self.divider_points = self.divider_points[:-1]

    def _finalize_divider(self) -> None:
        if len(self.divider_points) < 2 or self.divider_room_idx < 0:
            self.status_message = "Need at least 2 divider points"
            return
        if self.divider_room_idx >= len(self.rooms):
            return
        from ..lib.geometry import make_unique_name, ray_polygon_intersection, split_polygon_by_polyline
        room = self.rooms[self.divider_room_idx]
        polygon = room.get("vertices", [])
        if len(polygon) < 3:
            return
        polyline = [(p["x"], p["y"]) for p in self.divider_points]
        if len(polyline) >= 2:
            dx = polyline[0][0] - polyline[1][0]
            dy = polyline[0][1] - polyline[1][1]
            hit = ray_polygon_intersection(polyline[0], (dx, dy), polygon)
            if hit:
                polyline[0] = hit
            dx = polyline[-1][0] - polyline[-2][0]
            dy = polyline[-1][1] - polyline[-2][1]
            hit = ray_polygon_intersection(polyline[-1], (dx, dy), polygon)
            if hit:
                polyline[-1] = hit
        poly_a, poly_b = split_polygon_by_polyline(polygon, polyline)
        if poly_a is None or poly_b is None:
            self.status_message = "Division failed — try different points"
            self.divider_points = []
            return
        existing_names = [r.get("name", "") for r in self.rooms]
        base_name = room.get("name", "ROOM")
        name_a = make_unique_name(f"{base_name}_A", existing_names)
        existing_names.append(name_a)
        name_b = make_unique_name(f"{base_name}_B", existing_names)
        room_a = {"name": name_a, "parent": room.get("parent"), "vertices": poly_a,
                   "hdr_file": room.get("hdr_file", ""), "room_type": room.get("room_type", "BED"), "visible": True}
        room_b = {"name": name_b, "parent": room.get("parent"), "vertices": poly_b,
                   "hdr_file": room.get("hdr_file", ""), "room_type": room.get("room_type", "BED"), "visible": True}
        rooms_copy = list(self.rooms)
        rooms_copy[self.divider_room_idx] = room_a
        rooms_copy.insert(self.divider_room_idx + 1, room_b)
        self.rooms = rooms_copy
        self.divider_points = []
        self.divider_room_idx = -1
        self._clear_modes()
        self.status_message = f"Split into {name_a} and {name_b}"
        self.status_colour = "accent"
        self._auto_save()

    # =====================================================================
    # PDF OVERLAY
    # =====================================================================

    def toggle_overlay(self) -> None:
        self.overlay_visible = not self.overlay_visible
        if self.overlay_visible and not self.overlay_image_b64:
            self._rasterize_current_page()

    def toggle_overlay_align(self) -> None:
        self.overlay_align_mode = not self.overlay_align_mode
        self.align_points = []

    def cycle_overlay_page(self) -> None:
        if self.overlay_page_count <= 0:
            return
        self.overlay_page_idx = (self.overlay_page_idx + 1) % self.overlay_page_count
        self._rasterize_current_page()

    def set_overlay_dpi(self, dpi: str) -> None:
        try:
            self.overlay_dpi = int(dpi)
        except ValueError:
            return
        self._rasterize_current_page()

    def set_overlay_alpha(self, value: str) -> None:
        try:
            self.overlay_alpha = max(0.0, min(1.0, float(value)))
        except ValueError:
            pass

    def set_overlay_offset_x(self, value: str) -> None:
        try:
            t = dict(self._get_current_overlay_transform())
            t["offset_x"] = int(value)
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def set_overlay_offset_y(self, value: str) -> None:
        try:
            t = dict(self._get_current_overlay_transform())
            t["offset_y"] = int(value)
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def set_overlay_scale_x(self, value: str) -> None:
        try:
            t = dict(self._get_current_overlay_transform())
            t["scale_x"] = float(value)
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def set_overlay_scale_y(self, value: str) -> None:
        try:
            t = dict(self._get_current_overlay_transform())
            t["scale_y"] = float(value)
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def rotate_overlay_90(self) -> None:
        t = dict(self._get_current_overlay_transform())
        t["rotation_90"] = (t.get("rotation_90", 0) + 1) % 4
        self._set_current_overlay_transform(t)

    def reset_level_alignment(self) -> None:
        self._set_current_overlay_transform(
            {"offset_x": 0, "offset_y": 0, "scale_x": 1.0, "scale_y": 1.0, "rotation_90": 0}
        )

    def nudge_overlay(self, dx: int, dy: int) -> None:
        t = dict(self._get_current_overlay_transform())
        t["offset_x"] = t.get("offset_x", 0) + dx
        t["offset_y"] = t.get("offset_y", 0) + dy
        self._set_current_overlay_transform(t)

    def _get_current_overlay_transform(self) -> dict:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return {"offset_x": 0, "offset_y": 0, "scale_x": 1.0, "scale_y": 1.0, "rotation_90": 0}
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        return self.overlay_transforms.get(hdr_name, {
            "offset_x": 0, "offset_y": 0, "scale_x": 1.0, "scale_y": 1.0, "rotation_90": 0
        })

    def _set_current_overlay_transform(self, transform: dict) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        t = dict(self.overlay_transforms)
        t[hdr_name] = transform
        self.overlay_transforms = t

    def _rasterize_current_page(self) -> None:
        if not self.overlay_pdf_path:
            return
        from ..lib.image_loader import rasterize_pdf_page
        b64 = rasterize_pdf_page(Path(self.overlay_pdf_path), self.overlay_page_idx, self.overlay_dpi)
        self.overlay_image_b64 = b64 or ""

    def _add_align_point(self, x: float, y: float) -> None:
        self.align_points = self.align_points + [{"x": x, "y": y}]
        if len(self.align_points) == 4:
            self._compute_two_point_alignment()

    def _compute_two_point_alignment(self) -> None:
        if len(self.align_points) < 4:
            return
        pdf1, img1, pdf2, img2 = self.align_points[:4]
        pdf_dist = math.hypot(pdf2["x"] - pdf1["x"], pdf2["y"] - pdf1["y"])
        img_dist = math.hypot(img2["x"] - img1["x"], img2["y"] - img1["y"])
        if pdf_dist < 1e-6:
            self.align_points = []
            return
        scale = img_dist / pdf_dist
        t = dict(self._get_current_overlay_transform())
        t["scale_x"] = scale
        t["scale_y"] = scale
        t["offset_x"] = int(img1["x"] - pdf1["x"] * scale)
        t["offset_y"] = int(img1["y"] - pdf1["y"] * scale)
        self._set_current_overlay_transform(t)
        self.align_points = []
        self.status_message = "Alignment applied"

    # =====================================================================
    # DF% ANALYSIS
    # =====================================================================

    def _df_stamp(self, x: float, y: float) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        hdr_name = hdr_info["name"]
        from ..lib.df_analysis import load_df_image, read_df_at_pixel
        df_image = load_df_image(Path(hdr_info["hdr_path"]))
        if df_image is None:
            self.status_message = "Could not load DF image"
            self.status_colour = "danger"
            return
        df_val = read_df_at_pixel(df_image, x, y)
        if df_val is None:
            return
        stamps_copy = dict(self.df_stamps)
        hdr_stamps = list(stamps_copy.get(hdr_name, []))
        hdr_stamps.append([x, y, round(df_val, 2)])
        stamps_copy[hdr_name] = hdr_stamps
        self.df_stamps = stamps_copy
        self.status_message = f"DF: {df_val:.2f}%"
        self.status_colour = "accent"

    def _df_remove_nearest(self, x: float, y: float) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        hdr_stamps = self.df_stamps.get(hdr_name, [])
        if not hdr_stamps:
            return
        best_i, best_d = -1, 20.0
        for i, stamp in enumerate(hdr_stamps):
            d = math.hypot(x - stamp[0], y - stamp[1])
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0:
            stamps_copy = dict(self.df_stamps)
            stamps_copy[hdr_name] = [s for j, s in enumerate(hdr_stamps) if j != best_i]
            self.df_stamps = stamps_copy

    def compute_df_for_current_hdr(self) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        hdr_name = hdr_info["name"]
        from ..lib.df_analysis import compute_room_df, load_df_image
        df_image = load_df_image(Path(hdr_info["hdr_path"]))
        if df_image is None:
            return
        results = dict(self.room_df_results)
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != hdr_name:
                continue
            result = compute_room_df(df_image, room.get("vertices", []), room.get("room_type", "BED"))
            if result:
                results[str(i)] = result
        self.room_df_results = results

    # =====================================================================
    # EXPORT / ARCHIVE
    # =====================================================================

    def run_export(self) -> None:
        self.progress_visible = True
        self.progress_pct = 0
        self.progress_msg = "Starting export..."
        try:
            from archilume.config import get_project_paths
        except ImportError:
            self.progress_visible = False
            self.status_message = "Export failed: archilume not available"
            return
        if not self.project:
            self.progress_visible = False
            self.status_message = "No project loaded"
            return
        paths = get_project_paths(self.project)
        from ..lib.export_pipeline import export_report
        zip_path = export_report(
            rooms=list(self.rooms), hdr_files=list(self.hdr_files),
            image_dir=paths.image_dir, output_dir=paths.outputs_dir,
            wpd_dir=paths.wpd_dir, archive_dir=paths.archive_dir,
            project_name=self.project, df_thresholds={"BED": 0.5, "LIVING": 1.0, "NON-RESI": 2.0},
        )
        self.progress_visible = False
        if zip_path:
            self.status_message = f"Export complete: {zip_path.name}"
            self.status_colour = "accent"
        else:
            self.status_message = "Export failed"
            self.status_colour = "danger"

    def scan_archives(self) -> None:
        if not self.project:
            self.available_archives = []
            return
        try:
            from archilume.config import get_project_paths
            paths = get_project_paths(self.project)
            from ..lib.export_pipeline import list_archives
            self.available_archives = list_archives(paths.archive_dir)
        except ImportError:
            self.available_archives = []

    def set_selected_archive(self, value: str) -> None:
        self.selected_archive = value

    def extract_selected_archive(self) -> None:
        if not self.project or not self.selected_archive:
            return
        try:
            from archilume.config import get_project_paths
            paths = get_project_paths(self.project)
            from ..lib.export_pipeline import extract_archive
            if extract_archive(paths.archive_dir / self.selected_archive, paths.aoi_inputs_dir):
                self.status_message = f"Extracted: {self.selected_archive}"
                self.status_colour = "accent"
            else:
                self.status_message = "Extraction failed"
                self.status_colour = "danger"
        except ImportError:
            self.status_message = "Extract failed: archilume not available"

    # =====================================================================
    # ACCELERADRT
    # =====================================================================

    def open_accelerad_modal(self) -> None:
        try:
            from archilume import config
            project_root = config.PROJECT_ROOT
        except ImportError:
            project_root = Path(__file__).resolve().parents[5]
        oct_files: list[str] = []
        projects_dir = project_root / "projects"
        if projects_dir.exists():
            for p in projects_dir.rglob("*.oct"):
                oct_files.append(str(p))
        demo = project_root / ".devcontainer" / "accelerad_07_beta_Windows" / "demo" / "test.oct"
        if demo.exists():
            oct_files.insert(0, str(demo))
        self.accelerad_oct_files = sorted(oct_files)
        self.accelerad_selected_oct = oct_files[0] if oct_files else ""
        self.accelerad_error = ""
        self.accelerad_modal_open = True

    def close_accelerad_modal(self) -> None:
        self.accelerad_modal_open = False

    def set_accelerad_oct(self, value: str) -> None:
        self.accelerad_selected_oct = value

    def set_accelerad_res_x(self, value: str) -> None:
        try:
            self.accelerad_res_x = int(value)
        except ValueError:
            pass

    def set_accelerad_res_y(self, value: str) -> None:
        try:
            self.accelerad_res_y = int(value)
        except ValueError:
            pass

    def launch_accelerad(self) -> None:
        if not self.accelerad_selected_oct:
            self.accelerad_error = "No octree file selected."
            return
        oct_path = Path(self.accelerad_selected_oct)
        if not oct_path.exists():
            self.accelerad_error = f"File not found: {oct_path}"
            return
        try:
            from archilume import config
            exe = config.ACCELERAD_BIN_PATH / "AcceleradRT.exe"
            raypath = config.RAYPATH
        except ImportError:
            self.accelerad_error = "archilume config not available"
            return
        if not exe.exists():
            self.accelerad_error = f"AcceleradRT not found: {exe}"
            return
        env = os.environ.copy()
        env["RAYPATH"] = raypath
        cmd = [str(exe), "-x", str(self.accelerad_res_x), "-y", str(self.accelerad_res_y), "-ab", "1", str(oct_path)]
        try:
            subprocess.Popen(
                cmd, env=env,
                creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
                if sys.platform == "win32" else 0,
            )
            self.accelerad_running = True
            self.accelerad_error = ""
            self.accelerad_modal_open = False
            self.status_message = f"AcceleradRT launched: {oct_path.name}"
        except Exception as e:
            self.accelerad_error = str(e)

    # =====================================================================
    # SESSION PERSISTENCE
    # =====================================================================

    def load_session(self) -> None:
        if not self.session_path:
            return
        from ..lib.session_io import load_session
        data = load_session(Path(self.session_path))
        if data is None:
            return
        self.rooms = data.get("rooms", [])
        self.df_stamps = data.get("df_stamps", {})
        self.overlay_transforms = data.get("overlay_transforms", {})
        hdr_idx = data.get("current_hdr_idx", 0)
        if 0 <= hdr_idx < len(self.hdr_files):
            self.current_hdr_idx = hdr_idx
        self.current_variant_idx = data.get("current_variant_idx", 0)
        self.selected_parent = data.get("selected_parent", "")
        self.annotation_scale = data.get("annotation_scale", 1.0)
        self.overlay_dpi = data.get("overlay_dpi", 150)
        self.overlay_visible = data.get("overlay_visible", False)
        self.overlay_alpha = data.get("overlay_alpha", 0.6)
        pdf_path = data.get("overlay_pdf_path", "")
        if pdf_path:
            self.overlay_pdf_path = pdf_path
        self.overlay_page_idx = data.get("overlay_page_idx", 0)
        self._rebuild_variants()
        self.status_message = f"Session loaded ({len(self.rooms)} rooms)"

    def save_session(self) -> None:
        if not self.session_path:
            return
        from ..lib.session_io import build_session_dict, save_session
        data = build_session_dict(
            rooms=self.rooms, df_stamps=self.df_stamps,
            overlay_transforms=self.overlay_transforms,
            current_hdr_idx=self.current_hdr_idx, current_variant_idx=self.current_variant_idx,
            selected_parent=self.selected_parent, annotation_scale=self.annotation_scale,
            overlay_dpi=self.overlay_dpi, overlay_visible=self.overlay_visible,
            overlay_alpha=self.overlay_alpha, overlay_pdf_path=self.overlay_pdf_path,
            overlay_page_idx=self.overlay_page_idx,
        )
        save_session(Path(self.session_path), data)

    def force_save(self) -> None:
        self.save_session()
        self.status_message = "Session saved"

    def _auto_save(self) -> None:
        self.save_session()

    # =====================================================================
    # PROJECT MANAGEMENT
    # =====================================================================

    def scan_projects(self) -> None:
        try:
            from archilume.config import PROJECTS_DIR
            if PROJECTS_DIR.exists():
                self.available_projects = sorted([
                    p.name for p in PROJECTS_DIR.iterdir()
                    if p.is_dir() and (p / "project.toml").exists()
                ])
            else:
                self.available_projects = []
        except ImportError:
            self.available_projects = []

    def open_project(self, name: str) -> None:
        if not name:
            return
        self.project = name
        self._init_project_paths()
        self._rebuild_variants()
        self.load_session()
        self.load_current_image()
        self.scan_projects()
        self.open_project_modal_open = False
        self.status_message = f"Opened: {name}"
        self.status_colour = "accent"

    def set_new_project_name(self, value: str) -> None:
        self.new_project_name = value

    def set_new_project_mode(self, value: str) -> None:
        self.new_project_mode = value

    def create_project(self) -> None:
        name = self.new_project_name.strip()
        if not name:
            self.create_error = "Project name is required"
            return
        try:
            from archilume.config import get_project_paths
            paths = get_project_paths(name)
            if paths.project_dir.exists():
                self.create_error = f"Project '{name}' already exists"
                return
            paths.create_dirs()
            toml_path = paths.project_dir / "project.toml"
            toml_path.write_text(
                f'[project]\nname = "{name}"\nmode = "{self.new_project_mode}"\n',
                encoding="utf-8",
            )
            self.project = name
            self.project_mode = self.new_project_mode
            self._init_project_paths()
            self._rebuild_variants()
            self.load_session()
            self.load_current_image()
            self.scan_projects()
            self.create_project_modal_open = False
            self.create_error = ""
            self.new_project_name = ""
            self.status_message = f"Created: {name}"
            self.status_colour = "accent"
        except ImportError:
            self.create_error = "archilume config not available"
        except Exception as e:
            self.create_error = str(e)

    def _init_project_paths(self) -> None:
        if not self.project:
            return
        try:
            from archilume.config import get_project_paths
            paths = get_project_paths(self.project)
            image_dir = paths.pic_dir if self.project_mode == "iesve" else paths.image_dir
            toml_path = paths.project_dir / "project.toml"
            if toml_path.exists():
                try:
                    import tomllib
                    with open(toml_path, "rb") as f:
                        toml_data = tomllib.load(f)
                    proj = toml_data.get("project", {})
                    self.project_mode = proj.get("mode", self.project_mode)
                    if proj.get("image_dir"):
                        override = Path(proj["image_dir"])
                        if override.is_absolute() and override.exists():
                            image_dir = override
                        elif (paths.inputs_dir / override).exists():
                            image_dir = paths.inputs_dir / override
                    if proj.get("pdf_path"):
                        pdf_p = Path(proj["pdf_path"])
                        if pdf_p.is_absolute() and pdf_p.exists():
                            self.overlay_pdf_path = str(pdf_p)
                        elif (paths.inputs_dir / pdf_p).exists():
                            self.overlay_pdf_path = str(paths.inputs_dir / pdf_p)
                except Exception:
                    pass
            self.session_path = str(paths.aoi_inputs_dir / "aoi_session.json")
            from ..lib.image_loader import scan_hdr_files
            self.hdr_files = scan_hdr_files(image_dir)
            if self.overlay_pdf_path:
                from ..lib.image_loader import get_pdf_page_count
                self.overlay_page_count = get_pdf_page_count(Path(self.overlay_pdf_path))
        except ImportError:
            pass

    def init_on_load(self) -> None:
        self.scan_projects()
        if len(self.available_projects) == 1:
            self.open_project(self.available_projects[0])

    # =====================================================================
    # UI CHROME TOGGLES
    # =====================================================================

    def toggle_project_tree(self) -> None:
        self.project_tree_open = not self.project_tree_open

    def open_shortcuts_modal(self) -> None:
        self.shortcuts_modal_open = True

    def close_shortcuts_modal(self) -> None:
        self.shortcuts_modal_open = False

    def open_open_project_modal(self) -> None:
        self.scan_projects()
        self.open_project_modal_open = True

    def close_open_project_modal(self) -> None:
        self.open_project_modal_open = False

    def open_create_project_modal(self) -> None:
        self.create_project_modal_open = True

    def close_create_project_modal(self) -> None:
        self.create_project_modal_open = False

    def open_extract_modal(self) -> None:
        self.scan_archives()
        self.extract_modal_open = True

    def close_extract_modal(self) -> None:
        self.extract_modal_open = False

    # =====================================================================
    # KEYBOARD HANDLER
    # =====================================================================

    def handle_key(self, key: str) -> None:
        now = time.time()
        k = key.lower() if len(key) == 1 else key

        if k == "d":
            if now - self._last_d_press < 0.4 and not self.divider_mode:
                self._clear_modes()
                self.divider_mode = True
                if self.selected_room_idx >= 0:
                    self.divider_room_idx = self.selected_room_idx
                self.status_message = "Divider mode ON"
                self.status_colour = "accent2"
            else:
                self.toggle_draw_mode()
            self._last_d_press = now
            return

        if k == "e":
            self.toggle_edit_mode()
        elif k == "o":
            self.toggle_ortho()
        elif k == "p":
            self.toggle_df_placement()
        elif k == "t":
            self.toggle_image_variant()
        elif k == "r":
            self.reset_zoom()
        elif k == "f":
            self.fit_zoom()
        elif k == "s":
            self.save_room()
        elif k == "Escape":
            self.exit_mode()
        elif k == "ArrowUp":
            if self.overlay_align_mode and self.overlay_visible:
                self.nudge_overlay(0, -1)
            else:
                self.navigate_hdr(-1)
        elif k == "ArrowDown":
            if self.overlay_align_mode and self.overlay_visible:
                self.nudge_overlay(0, 1)
            else:
                self.navigate_hdr(1)
        elif k == "ArrowLeft":
            if self.overlay_align_mode and self.overlay_visible:
                self.nudge_overlay(-1, 0)
        elif k == "ArrowRight":
            if self.overlay_align_mode and self.overlay_visible:
                self.nudge_overlay(1, 0)
