"""EditorState — single unified Reflex state for the HDR AOI Editor.

All state is in one class to avoid Reflex substate delegation issues.
Organised into sections matching the original split-state design.
"""

import logging
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TypedDict

import reflex as rx

from ..lib.debug import debug_handler, logger, trace
from ..lib.geometry import polygon_label_point

# Module-level DF image cache (numpy arrays can't be Reflex state vars)
_df_cache: dict[str, Any] = {"hdr_path": "", "image": None}


class HdrFileInfo(TypedDict):
    name: str
    hdr_path: str
    tiff_paths: list[str]
    suffix: str


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
    is_circ: bool
    is_div: bool
    vertices_str: str
    label_x: str
    label_y: str
    df_label_y: str
    selected: bool
    df_lines: str
    df_status: str
    df_color: str


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
    px: int
    py: int


class TreeNode(TypedDict):
    # type: "hdr" | "parent_room" | "child_room"
    node_type: str
    # display
    label: str
    room_type: str
    indent: str          # CSS width e.g. "16px"
    selected: bool
    is_current_hdr: bool
    collapsed: bool      # only meaningful for hdr nodes
    has_children: bool   # only meaningful for parent_room nodes
    # action payload
    hdr_name: str        # which HDR this node belongs to
    room_idx: int        # -1 for hdr nodes
    hdr_idx: int         # index into hdr_files


class EditorState(rx.State):
    """Unified state for the entire editor application."""

    # =====================================================================
    # §0 — Workflow tabs
    # =====================================================================
    active_tab: str = "results"

    def set_active_tab(self, tab: str) -> None:
        self.active_tab = tab

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

    # -- View params per HDR: maps hdr_name -> [vp_x, vp_y, vh, vv]
    hdr_view_params: dict[str, list[float]] = {}

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
    df_cursor_label: str = ""

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
    viewport_width: int = 0
    viewport_height: int = 0

    # -- Grid overlay
    grid_visible: bool = False
    grid_spacing_mm: int = 50  # default 50mm = 5cm, min 5mm

    # =====================================================================
    # §12 — Mouse state
    # =====================================================================
    mouse_x: float = 0.0
    mouse_y: float = 0.0

    # =====================================================================
    # §13 — UI chrome
    # =====================================================================
    project_tree_open: bool = True
    collapsed_hdrs: list[str] = []
    shortcuts_modal_open: bool = False
    open_project_modal_open: bool = False
    create_project_modal_open: bool = False
    extract_modal_open: bool = False
    status_message: str = "Ready"
    status_colour: str = "accent2"
    _last_d_press: float = 0.0
    _UNDO_MAX: int = 50

    # =====================================================================
    # §14 — Debug
    # =====================================================================
    debug_mode: bool = os.environ.get("ARCHILUME_DEBUG", "").lower() in ("1", "true")
    debug_log: list[str] = []

    def toggle_debug_mode(self) -> None:
        """Toggle debug mode on/off. Controls backend logging and frontend overlay."""
        self.debug_mode = not self.debug_mode
        level = logging.DEBUG if self.debug_mode else logging.WARNING
        logger.setLevel(level)
        if self.debug_mode:
            # Start a fresh debug session — clear trace buffer and rotate log
            trace.clear()
            logger.debug("Debug mode ON — trace cleared, fresh session")
            self.status_message = "Debug mode ON"
        else:
            # Flush remaining trace before turning off
            trace.flush()
            self.status_message = "Debug mode OFF"
        self.status_colour = "accent2"

    def flush_debug_trace(self) -> None:
        """Write current trace buffer to debug_trace.json in the project dir."""
        trace.flush()
        if self.debug_mode:
            logger.debug(f"Trace flushed ({len(trace.entries)} entries)")

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
    def all_rooms_selected(self) -> bool:
        if not self.hdr_files:
            return False
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        hdr_idxs = [i for i, r in enumerate(self.rooms) if r.get("hdr_file") == hdr_name]
        return len(hdr_idxs) > 0 and set(hdr_idxs) == set(self.multi_selected_idxs)

    @rx.var
    def tree_nodes(self) -> list[TreeNode]:
        """Flat list of typed tree nodes for the Room Browser.

        Structure per HDR:
          [hdr row]
            [parent room row]   (rooms with no parent, or unique parent values)
              [child room row]  (rooms whose parent == parent room name)
        """
        nodes: list[TreeNode] = []
        current_hdr_name = (
            self.hdr_files[self.current_hdr_idx]["name"]
            if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files)
            else ""
        )

        for hdr_idx, hdr in enumerate(self.hdr_files):
            hdr_name = hdr["name"]
            is_current = hdr_name == current_hdr_name
            collapsed = hdr_name in self.collapsed_hdrs

            # Count rooms for this HDR
            hdr_rooms = [(i, r) for i, r in enumerate(self.rooms) if r.get("hdr_file") == hdr_name]

            nodes.append({
                "node_type": "hdr",
                "label": hdr_name,
                "room_type": "",
                "indent": "0px",
                "selected": False,
                "is_current_hdr": is_current,
                "collapsed": collapsed,
                "has_children": len(hdr_rooms) > 0,
                "hdr_name": hdr_name,
                "room_idx": -1,
                "hdr_idx": hdr_idx,
            })

            if collapsed:
                continue

            # Group: find unique parent values among this HDR's rooms
            # Parents are rooms whose own name appears as another room's parent
            parent_names = sorted({r.get("parent", "") for _, r in hdr_rooms if r.get("parent", "")})
            # Rooms that are parents themselves (no parent of their own)
            top_level = [(i, r) for i, r in hdr_rooms if not r.get("parent")]
            # Rooms that have a parent
            child_map: dict[str, list[tuple[int, dict]]] = {}
            for i, r in hdr_rooms:
                p = r.get("parent") or ""
                if p:
                    child_map.setdefault(p, []).append((i, r))

            for room_idx, room in top_level:
                room_name = room.get("name", "")
                children = child_map.get(room_name, [])
                is_selected = (
                    room_idx == self.selected_room_idx
                    or room_idx in self.multi_selected_idxs
                )
                nodes.append({
                    "node_type": "parent_room",
                    "label": room_name,
                    "room_type": room.get("room_type", ""),
                    "indent": "16px",
                    "selected": is_selected,
                    "is_current_hdr": is_current,
                    "collapsed": False,
                    "has_children": len(children) > 0,
                    "hdr_name": hdr_name,
                    "room_idx": room_idx,
                    "hdr_idx": hdr_idx,
                })
                for child_idx, child in children:
                    child_selected = (
                        child_idx == self.selected_room_idx
                        or child_idx in self.multi_selected_idxs
                    )
                    child_name = child.get("name", "")
                    child_label = child_name.removeprefix(room_name).strip("_ ") or child_name
                    nodes.append({
                        "node_type": "child_room",
                        "label": child_label,
                        "room_type": child.get("room_type", ""),
                        "indent": "32px",
                        "selected": child_selected,
                        "is_current_hdr": is_current,
                        "collapsed": False,
                        "has_children": False,
                        "hdr_name": hdr_name,
                        "room_idx": child_idx,
                        "hdr_idx": hdr_idx,
                    })

            # Orphan children (parent name not present as a top-level room)
            top_level_names = {r.get("name", "") for _, r in top_level}
            for parent_name, children in child_map.items():
                if parent_name not in top_level_names:
                    for child_idx, child in children:
                        child_selected = (
                            child_idx == self.selected_room_idx
                            or child_idx in self.multi_selected_idxs
                        )
                        child_name = child.get("name", "")
                        child_label = child_name.removeprefix(parent_name).strip("_ ") or child_name
                        nodes.append({
                            "node_type": "child_room",
                            "label": child_label,
                            "room_type": child.get("room_type", ""),
                            "indent": "16px",
                            "selected": child_selected,
                            "is_current_hdr": is_current,
                            "collapsed": False,
                            "has_children": False,
                            "hdr_name": hdr_name,
                            "room_idx": child_idx,
                            "hdr_idx": hdr_idx,
                        })

        return nodes

    def set_viewport_size(self, data: dict) -> None:
        """Called by ResizeObserver JS when the viewport container resizes."""
        self.viewport_width = int(data.get("w", 0))
        self.viewport_height = int(data.get("h", 0))

    @rx.var
    def zoom_pct(self) -> str:
        return f"{int(self.zoom_level * 100)}%"

    @rx.var
    def svg_viewbox(self) -> str:
        if self.image_width > 0 and self.image_height > 0:
            return f"0 0 {self.image_width} {self.image_height}"
        return "0 0 1000 800"

    @rx.var
    def image_aspect_ratio(self) -> str:
        """CSS aspect-ratio value, e.g. '1280 / 441'."""
        if self.image_width > 0 and self.image_height > 0:
            return f"{self.image_width} / {self.image_height}"
        return "1000 / 800"

    @rx.var
    def grid_spacing_px(self) -> float:
        """Grid spacing in image-pixel units, derived from VIEW params and grid_spacing_mm."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return 0.0
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        vp_params = self.hdr_view_params.get(hdr_name)
        if not vp_params or self.image_width <= 0:
            return 0.0
        vh = vp_params[2]  # horizontal view size in metres
        if vh <= 0:
            return 0.0
        metres_per_pixel = vh / self.image_width
        spacing_m = self.grid_spacing_mm / 1000.0
        return spacing_m / metres_per_pixel

    @rx.var
    def grid_pattern_size(self) -> str:
        s = self.grid_spacing_px
        if s <= 0:
            return "10"
        return str(round(s, 2))

    @rx.var
    def grid_offset_x(self) -> str:
        """Pattern offset so grid aligns to world origin."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return "0"
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        vp_params = self.hdr_view_params.get(hdr_name)
        if not vp_params or self.image_width <= 0:
            return "0"
        vp_x, _, vh, _ = vp_params
        metres_per_pixel = vh / self.image_width
        spacing_m = self.grid_spacing_mm / 1000.0
        # World origin (0,0) maps to pixel: img_w/2 - vp_x/mpp
        origin_px = self.image_width / 2.0 - vp_x / metres_per_pixel
        s = spacing_m / metres_per_pixel
        if s <= 0:
            return "0"
        offset = origin_px % s
        return str(round(offset, 2))

    @rx.var
    def grid_offset_y(self) -> str:
        """Pattern offset so grid aligns to world origin."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return "0"
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        vp_params = self.hdr_view_params.get(hdr_name)
        if not vp_params or self.image_height <= 0:
            return "0"
        _, vp_y, _, vv = vp_params
        metres_per_pixel = vv / self.image_height
        spacing_m = self.grid_spacing_mm / 1000.0
        origin_py = self.image_height / 2.0 + vp_y / metres_per_pixel
        s = spacing_m / metres_per_pixel
        if s <= 0:
            return "0"
        offset = origin_py % s
        return str(round(offset, 2))

    @rx.var
    def label_font_size(self) -> str:
        """Room name font size scaled by annotation_scale."""
        return str(round(10 * self.annotation_scale, 1))

    @rx.var
    def df_font_size(self) -> str:
        """DF result font size scaled by annotation_scale."""
        return str(round(8 * self.annotation_scale, 1))

    @rx.var
    def df_label_offset(self) -> str:
        """Vertical offset from label centre to DF text, scaled by annotation_scale."""
        return str(round(14 * self.annotation_scale, 1))

    @rx.var
    def room_stroke_width(self) -> str:
        """Boundary stroke width that stays visually consistent across zoom levels.

        Scales inversely with zoom_level so lines don't appear to thin out when
        zoomed in (since SVG stroke-width is in image-pixel space, not screen space).
        """
        base = 1.5
        lw = base / max(self.zoom_level, 0.01)
        return str(round(max(base * 0.5, min(base * 4.0, lw)), 2))

    @rx.var
    def enriched_rooms(self) -> list[EnrichedRoom]:
        """Rooms for current HDR enriched with SVG rendering data."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        img_w = self.image_width
        img_h = self.image_height

        # Reproject world_vertices → pixel coords using HDR VIEW parameters
        # Matches the Radiance orthographic (-vtl) projection used by the matplotlib editor:
        #   px = (world_x - vp_x) / (vh / img_w) + img_w / 2
        #   py = img_h / 2 - (world_y - vp_y) / (vv / img_h)
        vp_params = self.hdr_view_params.get(hdr_name)

        def reproject(world_verts: list, vp_x: float, vp_y: float,
                      vh: float, vv: float) -> list:
            result_v = []
            for wx, wy in world_verts:
                px = (wx - vp_x) / (vh / img_w) + img_w / 2
                py = img_h / 2 - (wy - vp_y) / (vv / img_h)
                result_v.append([px, py])
            return result_v

        result = []
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != hdr_name:
                continue
            if not room.get("visible", True):
                continue

            # Use reprojected world_vertices when view params are available
            world_verts = room.get("world_vertices", [])
            if vp_params and len(world_verts) >= 3 and img_w > 0 and img_h > 0:
                vp_x, vp_y, vh, vv = vp_params
                verts = reproject(world_verts, vp_x, vp_y, vh, vv)
            else:
                verts = room.get("vertices", [])

            if len(verts) < 3:
                continue

            is_div = "_DIV" in room.get("name", "")
            verts_str = " ".join(f"{v[0]},{v[1]}" for v in verts)

            # Label position via centroid
            lx, ly = polygon_label_point(verts)

            # DF results
            df_info = self.room_df_results.get(str(i), {})
            df_lines = df_info.get("result_lines", [])
            df_status = df_info.get("pass_status", "none")

            # DF colour: parse percentage from first result line, match matplotlib thresholds
            df_color = "#ffffff"
            if df_lines:
                _m = re.search(r'\((\d+(?:\.\d+)?)%\)', df_lines[0])
                if _m:
                    _pct = float(_m.group(1))
                    if _pct >= 90:
                        df_color = "#000000"
                    elif _pct >= 50:
                        df_color = "#E97132"
                    else:
                        df_color = "#EE0000"

            is_circ = room.get("room_type", "") == "CIRC"
            label_offset = round(14 * self.annotation_scale, 1)

            result.append({
                "idx": i,
                "name": room.get("name", ""),
                "room_type": room.get("room_type", ""),
                "parent": room.get("parent") or "",
                "is_circ": is_circ,
                "is_div": is_div,
                "vertices_str": verts_str,
                "label_x": str(lx),
                "label_y": str(ly),
                "df_label_y": str(ly + label_offset),
                "selected": i == self.selected_room_idx or i in self.multi_selected_idxs,
                "df_lines": "\n".join(df_lines) if df_lines else "",
                "df_status": df_status,
                "df_color": df_color,
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
        return [
            {
                "x": float(s[0]),
                "y": float(s[1]),
                "value": float(s[2]),
                "px": int(s[3]) if len(s) > 3 else int(round(s[0])),
                "py": int(s[4]) if len(s) > 4 else int(round(s[1])),
            }
            for s in raw
            if len(s) >= 3
        ]

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
    def image_width_str(self) -> str:
        return str(self.image_width) if self.image_width > 0 else "1280"

    @rx.var
    def image_height_str(self) -> str:
        return str(self.image_height) if self.image_height > 0 else "800"

    @rx.var
    def overlay_svg_transform(self) -> str:
        """SVG-syntax transform for the overlay image (no CSS units)."""
        t = self._get_current_overlay_transform()
        ox = t.get("offset_x", 0)
        oy = t.get("offset_y", 0)
        sx = t.get("scale_x", 1.0)
        sy = t.get("scale_y", 1.0)
        return f"translate({ox},{oy}) scale({sx},{sy})"

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

    @debug_handler
    def toggle_draw_mode(self) -> None:
        was_on = self.draw_mode
        self._clear_modes()
        self.draw_mode = not was_on
        self.status_message = "Draw mode ON — click to place vertices, S to save" if self.draw_mode else "Ready"
        self.status_colour = "accent" if self.draw_mode else "accent2"

    @debug_handler
    def toggle_edit_mode(self) -> None:
        was_on = self.edit_mode
        self._clear_modes()
        self.edit_mode = not was_on
        self.status_message = "Edit mode ON — drag vertices, right-click to delete" if self.edit_mode else "Ready"
        self.status_colour = "warning" if self.edit_mode else "accent2"

    @debug_handler
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
        if self.df_placement_mode:
            self._load_df_image_cache()
            loaded = _df_cache["image"] is not None
            self.status_message = "DF% placement ON — click to stamp values" if loaded else "DF% placement ON — HDR image could not be loaded"
        else:
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            self.df_cursor_label = ""
            self.status_message = "Ready"
        self.status_colour = "accent" if self.df_placement_mode else "accent2"

    def _load_df_image_cache(self) -> None:
        """Load and cache the DF image for the current HDR."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        hdr_path = hdr_info.get("hdr_path", "")
        # Skip if already cached for this HDR
        if _df_cache["hdr_path"] == hdr_path and _df_cache["image"] is not None:
            return
        try:
            from ..lib.df_analysis import load_df_image
            _df_cache["image"] = load_df_image(Path(hdr_path))
            _df_cache["hdr_path"] = hdr_path if _df_cache["image"] is not None else ""
        except Exception:
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""

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
            hdr_name = self.hdr_files[new_idx]["name"]
            self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]
            # Invalidate DF image cache; will reload if placement mode is active
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            if self.df_placement_mode:
                self._load_df_image_cache()

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

    def select_room_or_multi(self, idx: int, pointer: dict) -> None:
        """Click handler — multi-selects if Ctrl/Meta/Shift held, otherwise single-selects."""
        if pointer.get("ctrl_key") or pointer.get("meta_key") or pointer.get("shift_key"):
            self.select_room_multi(idx)
        else:
            self.select_room(idx)

    @debug_handler
    def select_room(self, idx: int) -> None:
        self.multi_selected_idxs = []
        self.selected_room_idx = idx
        if 0 <= idx < len(self.rooms):
            room = self.rooms[idx]
            self.room_name_input = room.get("name", "")
            self.room_type_input = room.get("room_type", "BED")
            self.selected_parent = room.get("parent", "") or ""
            # Navigate to the HDR this room belongs to
            hdr_name = room.get("hdr_file", "")
            for i, h in enumerate(self.hdr_files):
                if h["name"] == hdr_name and i != self.current_hdr_idx:
                    self.current_hdr_idx = i
                    self._rebuild_variants()
                    self.load_current_image()
                    self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]
                    break

    def room_or_stamp_click(self, idx: int, pointer: dict) -> None:
        """Polygon click handler — stamps DF% in placement mode, otherwise selects (or multi-selects) room."""
        if self.df_placement_mode:
            self._df_stamp(self.mouse_x, self.mouse_y)
        else:
            self.select_room_or_multi(idx, pointer)

    def select_room_multi(self, idx: int) -> None:
        if idx in self.multi_selected_idxs:
            self.multi_selected_idxs = [i for i in self.multi_selected_idxs if i != idx]
        else:
            self.multi_selected_idxs = self.multi_selected_idxs + [idx]


    def collapse_all_hdrs(self) -> None:
        self.collapsed_hdrs = [h["name"] for h in self.hdr_files]

    def expand_all_hdrs(self) -> None:
        self.collapsed_hdrs = []

    def toggle_hdr_collapse(self, hdr_name: str) -> None:
        if hdr_name in self.collapsed_hdrs:
            self.collapsed_hdrs = [h for h in self.collapsed_hdrs if h != hdr_name]
        else:
            self.collapsed_hdrs = self.collapsed_hdrs + [hdr_name]

    def navigate_to_hdr(self, hdr_idx: int) -> None:
        if 0 <= hdr_idx < len(self.hdr_files):
            self.current_hdr_idx = hdr_idx
            self._rebuild_variants()
            self.load_current_image()
            # Collapse all HDRs except the one just navigated to
            hdr_name = self.hdr_files[hdr_idx]["name"]
            self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]

    def select_all_rooms(self) -> None:
        if not self.hdr_files:
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        hdr_idxs = [i for i, r in enumerate(self.rooms) if r.get("hdr_file") == hdr_name]
        if set(hdr_idxs) == set(self.multi_selected_idxs):
            self.multi_selected_idxs = []
            self.selected_room_idx = -1
        else:
            self.multi_selected_idxs = hdr_idxs

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

    @debug_handler
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

    @debug_handler
    def handle_canvas_click(self, data: dict) -> None:
        """Route canvas click. data: {x, y, button, shiftKey, ctrlKey} from JS."""
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        button = int(data.get("button", 0))
        shift = bool(data.get("shiftKey", False))
        ctrl = bool(data.get("ctrlKey", False))

        self.mouse_x = x
        self.mouse_y = y

        if self.debug_mode:
            btn_name = {0: "left", 1: "middle", 2: "right"}.get(button, str(button))
            logger.debug(
                f"  canvas_click at ({x:.1f}, {y:.1f}) btn={btn_name} "
                f"shift={shift} ctrl={ctrl} | modes: draw={self.draw_mode} "
                f"edit={self.edit_mode} divider={self.divider_mode} "
                f"df_place={self.df_placement_mode} overlay_align={self.overlay_align_mode}"
            )

        if self.draw_mode:
            if button == 2:
                logger.debug(f"  → draw_mode: undo vertex (count={len(self.draw_vertices)})")
                self._drawing_undo_vertex()
            else:
                logger.debug(f"  → draw_mode: add vertex at ({x:.1f}, {y:.1f}), ortho={self.ortho_mode}")
                self._drawing_add_vertex(x, y)
        elif self.edit_mode:
            logger.debug(f"  → edit_mode: editing_click, selected_room={self.selected_room_idx}")
            self._editing_click(x, y, button, shift)
        elif self.divider_mode:
            if button == 2:
                logger.debug(f"  → divider_mode: undo point (count={len(self.divider_points)})")
                self._divider_undo_point()
            else:
                logger.debug(f"  → divider_mode: add point at ({x:.1f}, {y:.1f})")
                self._divider_add_point(x, y)
        elif self.df_placement_mode:
            if button == 2:
                logger.debug(f"  → df_placement: remove nearest stamp at ({x:.1f}, {y:.1f})")
                self._df_remove_nearest(x, y)
            else:
                logger.debug(f"  → df_placement: stamp at ({x:.1f}, {y:.1f})")
                self._df_stamp(x, y)
        elif self.overlay_align_mode:
            logger.debug(f"  → overlay_align: add align point at ({x:.1f}, {y:.1f}), points_so_far={len(self.align_points)}")
            self._add_align_point(x, y)
        else:
            # Room selection is handled by polygon on_click handlers in the SVG.
            # Only use coordinate-based selection as a fallback (clicks on empty canvas area).
            if ctrl:
                logger.debug(f"  → fallback: select_room_at({x:.1f}, {y:.1f}) multi=True")
                self._select_room_at(x, y, multi=True)
            else:
                logger.debug(f"  → fallback: select_room_at({x:.1f}, {y:.1f}) multi=False")
                self._select_room_at(x, y, multi=False)

    def handle_mouse_move(self, data: dict) -> None:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        self.mouse_x = x
        self.mouse_y = y

        if self.draw_mode and self.draw_vertices:
            self._update_draw_preview(x, y)
        elif self.edit_mode and self.dragging_vertex_idx >= 0:
            logger.debug(f"mouse_move drag: vertex_idx={self.dragging_vertex_idx} → ({x:.1f}, {y:.1f})")
            self._drag_vertex(x, y)
        elif self.df_placement_mode:
            px, py = int(round(x)), int(round(y))
            df_val_str = ""
            df_image = _df_cache["image"]
            if df_image is not None:
                from ..lib.df_analysis import read_df_at_pixel
                df_val = read_df_at_pixel(df_image, x, y)
                if df_val is not None:
                    df_val_str = f" DF: {df_val:.2f}%"
            self.df_cursor_label = f"px({px},{py}){df_val_str}"
            self.status_message = self.df_cursor_label

    @debug_handler
    def handle_mouse_down(self, data: dict) -> None:
        if not self.edit_mode:
            return
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        self._editing_start_drag(x, y)

    @debug_handler
    def handle_mouse_up(self, _data: dict) -> None:
        if self.edit_mode:
            self.dragging_vertex_idx = -1

    def sync_zoom(self, data: dict) -> None:
        """Receive zoom/pan state from JS after a gesture ends (debounced)."""
        self.zoom_level = float(data.get("zoom", self.zoom_level))
        self.pan_x = float(data.get("pan_x", self.pan_x))
        self.pan_y = float(data.get("pan_y", self.pan_y))

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        yield rx.call_script("window._archiZoom && window._archiZoom.setTransform(1.0, 0, 0);")

    def fit_zoom(self):
        """Zoom and pan so the selected room fills the viewport container.

        Transform model: translate(pan_x, pan_y) scale(zoom), origin 0 0.
        To centre image point (cx, cy) in a viewport of size (vw, vh):
            pan_x = vw/2 - cx * zoom
            pan_y = vh/2 - cy * zoom
        """
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            yield from self.reset_zoom()
            return
        room = self.rooms[self.selected_room_idx]
        verts = room.get("vertices", [])
        if not verts or self.image_width <= 0:
            yield from self.reset_zoom()
            return
        from ..lib.geometry import polygon_bbox
        min_x, min_y, max_x, max_y = polygon_bbox(verts)
        pad = 10  # small padding in image pixels so boundary stroke is visible
        bw = max_x - min_x + 2 * pad
        bh = max_y - min_y + 2 * pad
        if bw <= 0 or bh <= 0:
            yield from self.reset_zoom()
            return
        # Viewport container dimensions in screen pixels (from ResizeObserver)
        vw = self.viewport_width if self.viewport_width > 0 else self.image_width
        vh = self.viewport_height if self.viewport_height > 0 else self.image_height
        if self.image_width <= 0 or self.image_height <= 0 or vw <= 0:
            yield from self.reset_zoom()
            return
        # At zoom=1 the canvas is width=vw, height=vw*(image_height/image_width).
        # The rendered canvas height may be less than vh (letterboxed), so capping
        # effective_vh avoids over-estimating zy and leaving empty space top/bottom.
        image_scale = vw / self.image_width  # screen px per image px at zoom=1
        canvas_h_at_1 = vw * self.image_height / self.image_width
        effective_vh = min(vh, canvas_h_at_1) if canvas_h_at_1 > 0 else vh
        zx = vw / (bw * image_scale)
        zy = effective_vh / (bh * image_scale)
        self.zoom_level = min(zx, zy, 20.0)
        # Centre the bounding-box midpoint.
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        pxscale = image_scale * self.zoom_level
        self.pan_x = vw / 2 - cx * pxscale
        self.pan_y = vh / 2 - cy * pxscale
        yield rx.call_script(
            f"window._archiZoom && window._archiZoom.setTransform("
            f"{self.zoom_level}, {self.pan_x}, {self.pan_y});"
        )

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

    @debug_handler
    def save_room(self) -> None:
        if self.draw_mode and len(self.draw_vertices) >= 3:
            logger.debug(
                f"  save_room → _save_new_room: {len(self.draw_vertices)} vertices, "
                f"name_input='{self.room_name_input}', parent='{self.selected_parent}', "
                f"type='{self.room_type_input}', hdr_idx={self.current_hdr_idx}"
            )
            self._save_new_room()
        elif self.draw_mode:
            logger.debug(
                f"  save_room → SKIPPED: draw_mode but only {len(self.draw_vertices)} vertices (need ≥3)"
            )
        elif self.edit_mode and 0 <= self.selected_room_idx < len(self.rooms):
            logger.debug(
                f"  save_room → _save_edited_room: room_idx={self.selected_room_idx}, "
                f"name_input='{self.room_name_input}', type='{self.room_type_input}'"
            )
            self._save_edited_room()
        elif self.divider_mode:
            logger.debug(
                f"  save_room → _finalize_divider: {len(self.divider_points)} points, "
                f"divider_room_idx={self.divider_room_idx}"
            )
            self._finalize_divider()
        else:
            # Just save name/type of selected room
            if 0 <= self.selected_room_idx < len(self.rooms):
                logger.debug(
                    f"  save_room → _save_edited_room (name/type only): "
                    f"room_idx={self.selected_room_idx}"
                )
                self._save_edited_room()
            else:
                logger.debug(
                    f"  save_room → NOOP: no active mode, selected_room_idx={self.selected_room_idx}"
                )

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
    # GRID OVERLAY
    # =====================================================================

    def toggle_grid(self) -> None:
        self.grid_visible = not self.grid_visible

    def set_grid_spacing(self, value: str) -> None:
        try:
            v = int(float(value))
            if v < 5:
                v = 5
            self.grid_spacing_mm = v
        except (ValueError, TypeError):
            pass

    # =====================================================================
    # PDF OVERLAY
    # =====================================================================

    def toggle_overlay(self) -> None:
        self.overlay_visible = not self.overlay_visible
        logger.debug(f"[overlay] toggle_overlay: visible={self.overlay_visible}, pdf_path='{self.overlay_pdf_path}', b64_len={len(self.overlay_image_b64)}")
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
            logger.debug("[overlay] _rasterize skipped: no overlay_pdf_path")
            return
        from ..lib.image_loader import rasterize_pdf_page
        cache_dir = None
        if self.project:
            try:
                from archilume.config import get_project_paths
                cache_dir = get_project_paths(self.project).plans_dir / ".overlay_cache"
            except Exception:
                pass
        logger.debug(f"[overlay] Rasterizing: {self.overlay_pdf_path} page={self.overlay_page_idx} dpi={self.overlay_dpi}")
        b64 = rasterize_pdf_page(Path(self.overlay_pdf_path), self.overlay_page_idx, self.overlay_dpi, cache_dir=cache_dir)
        if b64:
            logger.debug(f"[overlay] Rasterized OK, b64 length={len(b64)}")
        else:
            logger.debug("[overlay] Rasterization FAILED — returned None/empty")
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
            self.status_message = "No HDR loaded"
            self.status_colour = "danger"
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        hdr_name = hdr_info["name"]
        px, py = int(round(x)), int(round(y))

        # Try to read DF% from cached image; use 0.0 if unavailable
        df_val = 0.0
        df_image = _df_cache["image"]
        if df_image is not None:
            from ..lib.df_analysis import read_df_at_pixel
            val = read_df_at_pixel(df_image, x, y)
            if val is not None:
                df_val = val

        stamps_copy = dict(self.df_stamps)
        hdr_stamps = list(stamps_copy.get(hdr_name, []))
        hdr_stamps.append([x, y, round(df_val, 2), px, py])
        stamps_copy[hdr_name] = hdr_stamps
        self.df_stamps = stamps_copy
        self.status_message = f"DF: {df_val:.2f}% at px({px},{py})"
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
        if self.debug_mode:
            trace.flush()

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
                    toml_paths = toml_data.get("paths", {})
                    image_dir_str = proj.get("image_dir") or toml_paths.get("image_dir")
                    if image_dir_str:
                        override = Path(image_dir_str)
                        if override.is_absolute() and override.exists():
                            image_dir = override
                        elif (paths.inputs_dir / override).exists():
                            image_dir = paths.inputs_dir / override
                    pdf_path_str = proj.get("pdf_path") or toml_paths.get("pdf_path")
                    if pdf_path_str:
                        pdf_p = Path(pdf_path_str)
                        if pdf_p.is_absolute() and pdf_p.exists():
                            self.overlay_pdf_path = str(pdf_p)
                        elif (paths.project_dir / pdf_p).exists():
                            self.overlay_pdf_path = str(paths.project_dir / pdf_p)
                        elif (paths.inputs_dir / pdf_p).exists():
                            self.overlay_pdf_path = str(paths.inputs_dir / pdf_p)
                except Exception:
                    pass
            self.session_path = str(paths.aoi_inputs_dir / "aoi_session.json")
            trace.set_project_path(paths.project_dir)
            from ..lib.image_loader import scan_hdr_files, read_hdr_view_params
            self.hdr_files = scan_hdr_files(image_dir)
            # Read VIEW parameters from each HDR for accurate reprojection
            vp_map: dict[str, list[float]] = {}
            for hdr_info in self.hdr_files:
                params = read_hdr_view_params(Path(hdr_info["hdr_path"]))
                if params is not None:
                    vp_map[hdr_info["name"]] = list(params)
            self.hdr_view_params = vp_map
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

    def open_projects_folder(self) -> None:
        import subprocess
        import sys
        try:
            from archilume.config import PROJECTS_DIR
            path = str(PROJECTS_DIR)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

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

    def handle_key_event(self, key: str, key_info: dict):  # type: ignore[override]
        """Route keyboard events from the Reflex on_key_down handler.

        This is the correct Reflex pattern — compiled to addEvents, not window.applyEvent.
        key_info contains: alt_key, ctrl_key, meta_key, shift_key.
        """
        # Skip modifier-only keys — they generate noise with no action
        if key in ("Shift", "Control", "Alt", "Meta"):
            return

        ctrl = key_info.get("ctrl_key", False)
        shift = key_info.get("shift_key", False)

        if self.debug_mode:
            mods = []
            if ctrl:
                mods.append("Ctrl")
            if shift:
                mods.append("Shift")
            if key_info.get("alt_key"):
                mods.append("Alt")
            mod_str = "+".join(mods + [key]) if mods else key
            logger.debug(
                f"▶ handle_key_event: key={mod_str} | modes: draw={self.draw_mode} "
                f"edit={self.edit_mode} divider={self.divider_mode} "
                f"df_place={self.df_placement_mode} overlay_align={self.overlay_align_mode} "
                f"| selected_room={self.selected_room_idx} hdr_idx={self.current_hdr_idx}"
            )

        # Skip events from inputs/textareas — Reflex handles focus isolation but
        # the tab_index=-1 on the trap div means this only fires when the div is focused;
        # in practice document-level focus means we get all keys not consumed by inputs.
        if ctrl and key.lower() == "z":
            logger.debug("  → routing to: undo()")
            self.undo()
        elif ctrl and key.lower() == "a":
            logger.debug("  → routing to: select_all_rooms()")
            self.select_all_rooms()
        elif ctrl and key.lower() == "r":
            logger.debug("  → routing to: rotate_overlay_90()")
            self.rotate_overlay_90()
        elif shift and key == "S":
            logger.debug("  → routing to: force_save()")
            self.force_save()
        elif key in ("Delete", "Backspace"):
            logger.debug("  → routing to: delete_hovered_vertex()")
            self.delete_hovered_vertex()
        elif key.lower() == "f":
            logger.debug("  → routing to: fit_zoom()")
            yield from self.fit_zoom()
        elif key.lower() == "r" and not ctrl:
            logger.debug("  → routing to: reset_zoom()")
            yield from self.reset_zoom()
        else:
            logger.debug(f"  → routing to: handle_key('{key}')")
            yield from self.handle_key(key)

    @debug_handler
    def handle_key(self, key: str) -> None:
        now = time.time()
        k = key.lower() if len(key) == 1 else key

        if k == "d":
            elapsed = now - self._last_d_press
            if elapsed < 0.4 and not self.divider_mode:
                logger.debug(f"  handle_key 'd': double-press ({elapsed:.3f}s) → divider mode ON")
                self._clear_modes()
                self.divider_mode = True
                if self.selected_room_idx >= 0:
                    self.divider_room_idx = self.selected_room_idx
                self.status_message = "Divider mode ON"
                self.status_colour = "accent2"
            else:
                logger.debug(f"  handle_key 'd': single press ({elapsed:.3f}s) → toggle_draw_mode")
                self.toggle_draw_mode()
            self._last_d_press = now
            return

        if k == "e":
            logger.debug("  handle_key 'e' → toggle_edit_mode")
            self.toggle_edit_mode()
        elif k == "o":
            logger.debug(f"  handle_key 'o' → toggle_ortho (was {self.ortho_mode})")
            self.toggle_ortho()
        elif k == "p":
            logger.debug(f"  handle_key 'p' → toggle_df_placement (was {self.df_placement_mode})")
            self.toggle_df_placement()
        elif k == "t":
            logger.debug(f"  handle_key 't' → toggle_image_variant (idx={self.current_variant_idx})")
            self.toggle_image_variant()
        elif k == "r":
            logger.debug("  handle_key 'r' → reset_zoom")
            yield from self.reset_zoom()
        elif k == "f":
            logger.debug("  handle_key 'f' → fit_zoom")
            yield from self.fit_zoom()
        elif k == "s":
            logger.debug(
                f"  handle_key 's' → save_room | draw={self.draw_mode} "
                f"edit={self.edit_mode} divider={self.divider_mode} "
                f"draw_verts={len(self.draw_vertices)} selected={self.selected_room_idx}"
            )
            self.save_room()
        elif k == "Escape":
            logger.debug(
                f"  handle_key 'Escape' → exit_mode | active modes: "
                f"draw={self.draw_mode} edit={self.edit_mode} "
                f"divider={self.divider_mode} df={self.df_placement_mode} "
                f"overlay_align={self.overlay_align_mode}"
            )
            self.exit_mode()
        elif k == "ArrowUp":
            if self.overlay_align_mode and self.overlay_visible:
                logger.debug("  handle_key 'ArrowUp' → nudge_overlay(0, -1)")
                self.nudge_overlay(0, -1)
            else:
                logger.debug(f"  handle_key 'ArrowUp' → navigate_hdr(-1) (current={self.current_hdr_idx})")
                self.navigate_hdr(-1)
        elif k == "ArrowDown":
            if self.overlay_align_mode and self.overlay_visible:
                logger.debug("  handle_key 'ArrowDown' → nudge_overlay(0, 1)")
                self.nudge_overlay(0, 1)
            else:
                logger.debug(f"  handle_key 'ArrowDown' → navigate_hdr(1) (current={self.current_hdr_idx})")
                self.navigate_hdr(1)
        elif k == "ArrowLeft":
            if self.overlay_align_mode and self.overlay_visible:
                logger.debug("  handle_key 'ArrowLeft' → nudge_overlay(-1, 0)")
                self.nudge_overlay(-1, 0)
        elif k == "ArrowRight":
            if self.overlay_align_mode and self.overlay_visible:
                logger.debug("  handle_key 'ArrowRight' → nudge_overlay(1, 0)")
                self.nudge_overlay(1, 0)
        else:
            logger.debug(f"  handle_key '{k}' → no matching action (unbound key)")
