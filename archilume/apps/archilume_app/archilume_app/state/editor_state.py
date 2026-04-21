"""EditorState — single unified Reflex state for the HDR AOI Editor.

All state is in one class to avoid Reflex substate delegation issues.
Organised into sections matching the original split-state design.
"""

import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional, TypedDict
from urllib.parse import quote

import pandas as pd
import reflex as rx

from archilume.config import get_project_paths

from ..lib.debug import (
    debug_handler,
    logger,
    new_correlation_id,
    trace,
    with_correlation_id,
)
from ..lib.geometry import (
    max_inscribed_rect,
    max_inscribed_rect_aspect,
    polygon_bbox,
    polygon_label_point,
)
from ..lib import project_modes

# Module-level DF image cache (numpy arrays can't be Reflex state vars)
_df_cache: dict[str, Any] = {"hdr_path": "", "image": None}

# PDF overlay "Plan Resolution" cycle. Compressed-PNG disk cache keeps even the
# 400 DPI variant cheap, so 72/100 (visibly soft on high-DPI displays) were
# dropped and 400 was added for extreme-zoom inspection.
_DPI_STEPS: tuple[int, ...] = (150, 200, 300, 400)
_DEFAULT_OVERLAY_DPI: int = 200


def _overlay_cache_dir(project: str) -> Optional[Path]:
    """Filesystem path of the per-project PDF overlay PNG cache.

    Lives under ``projects/<project>/inputs/plans/.overlay_cache/`` — keeps
    cache artefacts project-bound (moves with archive/restore, deleted with
    the project). Served by a FastAPI sub-app at
    ``/overlay_cache/{project}/{filename}``. Returns None when *project* is
    empty (no project is active — no cache location is defined).
    """
    if not project:
        return None
    return get_project_paths(project).plans_dir / ".overlay_cache"


def _backend_base_url() -> str:
    """Absolute base URL of the Reflex FastAPI backend.

    Mirrors the precedence used in ``rxconfig.py`` so the browser fetches
    ``/overlay_cache/...`` from the backend port (8000 in dev) instead of
    the frontend port (3000). On a reverse-proxied production origin this
    prefix resolves to the same host and remains correct.
    """
    return os.environ.get(
        "REFLEX_API_URL",
        os.environ.get("API_URL", "http://localhost:8000"),
    )


def _snap_scale_top(value: str) -> "float | None":
    """Parse, clamp to [0, 10], and snap to nearest 0.5. Returns None if non-numeric."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    v = max(0.0, min(10.0, v))
    return round(round(v * 2) / 2, 1)


def _snap_scale_divisions(value: str) -> "int | None":
    """Parse, round to nearest integer, clamp to [0, 10]. Returns None if non-numeric."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(10, v))


class _StagedUploadBytes:
    """Tiny container used by project-create/settings upload handlers to pass
    already-read upload bytes into the synchronous staging helper."""

    __slots__ = ("name", "data")

    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self.data = data


class HdrFileInfo(TypedDict):
    name: str
    hdr_path: str
    tiff_paths: list[str]
    suffix: str
    legend_map: dict[str, str]


class FrameDict(TypedDict):
    hdr_path: str
    png_path: str
    sky_name: str
    hdr_stem: str
    frame_label: str


class ViewGroupDict(TypedDict):
    view_name: str       # display label, trimmed of common octree prefix
    view_prefix: str     # full prefix used to match HDR stems (includes octree_base)
    frames: list[FrameDict]


def _stem_to_view_map(view_groups: list) -> dict[str, str]:
    """Flatten view_groups → {hdr_stem: view_name}. Empty for daylight."""
    return {
        frame["hdr_stem"]: vg["view_name"]
        for vg in view_groups
        for frame in vg["frames"]
    }


def _select_level_prefetch_targets(
    project_mode: str,
    view_groups: list,
    current_view_idx: int,
    hdr_files: list,
    current_hdr_idx: int,
    current_variant_idx: int,
) -> list[Path]:
    """Resolve +/-1 adjacent-level image Paths for background LRU warm.

    Sunlight: frame-0 PNG sibling of each neighbour view (what
    ``load_current_image`` reads for variant 0). Daylight: the neighbour's
    current-variant TIFF if populated, else its raw HDR.

    Clamped to valid index range; returns an empty list when no neighbours
    qualify (e.g. first/last level, or no images loaded).
    """
    targets: list[Path] = []
    if project_mode == "sunlight" and view_groups:
        total = len(view_groups)
        for delta in (-1, 1):
            idx = current_view_idx + delta
            if 0 <= idx < total:
                frames = view_groups[idx].get("frames") or []
                if frames:
                    png = frames[0].get("png_path") or ""
                    if png:
                        targets.append(Path(png))
        return targets
    if hdr_files:
        total = len(hdr_files)
        for delta in (-1, 1):
            idx = current_hdr_idx + delta
            if 0 <= idx < total:
                info = hdr_files[idx]
                variants = list(info.get("tiff_paths") or [])
                if variants:
                    v = min(max(0, current_variant_idx), len(variants) - 1)
                    targets.append(Path(variants[v]))
                else:
                    hdr_path = info.get("hdr_path")
                    if hdr_path:
                        targets.append(Path(hdr_path))
    return targets


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
    # Per-line DF annotation fields
    df_line_0: str           # Area result, e.g. "DF avg: 1.23%"
    df_line_0_y: str         # Y position
    df_line_0_color: str     # Coloured by percentage threshold
    df_line_0_weight: str    # "bold" when black (pass), else "normal"
    df_line_0_stroke: str    # "white" for black text, "black" otherwise
    df_line_0_stroke_w: str  # Stroke width
    df_line_1: str           # Threshold, e.g. "Above 0.5%: 85%"
    df_line_1_y: str         # Y position
    name_y: str              # Room name Y (below DF lines, or at label_y if no DF)
    room_df_fs: str          # Per-room adaptive font size for DF area line
    room_lbl_fs: str         # Per-room adaptive font size for threshold + name
    room_stroke_w: str       # Per-room stroke width (scales with room_lbl_fs)
    has_df: bool             # Whether DF results exist
    selected: bool
    df_status: str
    show_labels: bool        # Whether labels fit within the room polygon
    # HTML overlay fields (percentage-based positioning)
    label_x_pct: str         # left position as percentage string
    df_line_0_y_pct: str     # top position as percentage
    df_line_1_y_pct: str
    name_y_pct: str
    room_df_fs_pct: str      # font-size as percentage of container width
    room_lbl_fs_pct: str
    clip_polygon_css: str    # CSS clip-path polygon string
    df_line_0_text_stroke: str  # e.g. "1.2px white"
    lbl_text_stroke: str
    bbox_left_pct: str
    bbox_top_pct: str
    bbox_w_pct: str
    bbox_h_pct: str
    # Fraction fields for stacked area annotation (numerator / denominator)
    df_area_num: str      # compliant area, e.g. "0.00"
    df_area_den: str      # total area, e.g. "1.71"
    df_area_pct: str      # percentage suffix, e.g. "(0%)"


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
    tooltip: str         # full name shown on hover; empty = no tooltip
    room_type: str
    indent: str          # CSS width e.g. "16px"
    selected: bool
    is_current_hdr: bool
    collapsed: bool      # only meaningful for hdr nodes
    has_children: bool   # only meaningful for parent_room nodes
    # tree connector — computed once at build time, single source of truth
    connector: str       # "T" = more siblings below, "L" = last sibling, "none" = hdr row
    parent_continues: str   # "1" when this child's parent is not the last sibling (vertical passes alongside), else "0"
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
    is_project_loading: bool = False

    # -- Create project form
    new_project_name: str = ""
    new_project_mode: str = "sunlight"
    create_error: str = ""
    # Per-file staging for Create New Project. field_id -> list of entries where
    # each entry has keys: path (str), name (str), ok (bool), error (str).
    new_project_staged: dict[str, list[dict]] = {}
    new_project_staging_dir: str = ""

    # -- Project settings modal (post-create edits)
    settings_modal_open: bool = False
    settings_error: str = ""
    settings_staged: dict[str, list[dict]] = {}
    settings_staging_dir: str = ""
    # Filenames the user has marked for removal from canonical dirs, keyed by
    # field_id. Only deleted when apply_settings runs AND integrity check
    # confirms the field still has at least one file afterwards.
    settings_pending_removals: dict[str, list[str]] = {}

    # =====================================================================
    # §2 — Image navigation
    # =====================================================================
    hdr_files: list[HdrFileInfo] = []
    current_hdr_idx: int = 0
    image_variants: list[str] = []
    current_variant_idx: int = 0

    # Sunlight-only: views grouped across timesteps. Empty for daylight mode.
    view_groups: list[ViewGroupDict] = []
    current_view_idx: int = 0
    current_frame_idx: int = 0
    frame_autoplay: bool = False
    frame_playback_fps: int = 5

    # -- Image display
    current_image_b64: str = ""
    current_legend_b64: str = ""
    legend_pinned: bool = False
    legend_hovered: bool = False
    image_width: int = 0
    image_height: int = 0

    # -- View params per HDR: maps hdr_name -> [vp_x, vp_y, vh, vv, img_w, img_h]
    hdr_view_params: dict[str, list[float]] = {}

    # -- Falsecolour / contour visualisation settings (per-project, persisted in
    #    aoi_session.json). User-tunable; trigger regeneration on change.
    falsecolour_scale: float = 4.0
    falsecolour_n_levels: int = 10
    falsecolour_palette: str = "spec"
    contour_scale: float = 2.0
    contour_n_levels: int = 4
    last_generated: dict = {}  # {"falsecolour": {scale,n_levels}, "contour": {...}}
    is_regenerating: bool = False
    regen_progress: str = ""

    # =====================================================================
    # §3 — Rooms
    # =====================================================================
    rooms: list[RoomDict] = []
    selected_room_idx: int = -1
    multi_selected_idxs: list[int] = []
    selected_parent: str = ""
    room_name_input: str = ""
    room_type_input: str = "NONE"

    # =====================================================================
    # §4 — Interaction modes
    # =====================================================================
    draw_mode: bool = False
    edit_mode: bool = False
    divider_mode: bool = False
    df_placement_mode: bool = False
    pan_mode: bool = False
    ortho_mode: bool = True
    shift_held: bool = False

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
    # Unified undo/redo stacks (replaces old edit_undo_stack + draw_undo_stack)
    _undo_stack: list[dict] = []
    _redo_stack: list[dict] = []
    _last_undo_push_time: float = 0.0
    # Overlay-scoped undo (only active in overlay_align_mode)
    _overlay_undo_stack: list[dict] = []
    _overlay_session_start: dict = {}

    # =====================================================================
    # §7 — Divider
    # =====================================================================
    divider_points: list[dict] = []
    divider_preview_point: dict = {}  # cursor position for preview line; ortho-constrained
    divider_room_idx: int = -1
    divider_room_name: str = ""  # name of target room at mode entry — re-resolves index after undo shifts

    # =====================================================================
    # §7b — Context menu
    # =====================================================================
    context_menu_visible: bool = False
    context_menu_x: float = 0.0   # viewport-relative px for rendering
    context_menu_y: float = 0.0
    context_menu_canvas_x: float = 0.0  # canvas-space coords for room hit-test
    context_menu_canvas_y: float = 0.0
    context_menu_room_idx: int = -1

    # =====================================================================
    # §8 — PDF overlay
    # =====================================================================
    overlay_visible: bool = False
    overlay_image_url: str = ""
    overlay_pdf_path: str = ""
    overlay_page_idx: int = 0
    overlay_page_count: int = 0
    overlay_dpi: int = _DEFAULT_OVERLAY_DPI
    overlay_alpha: float = 0.6
    overlay_align_mode: bool = False
    overlay_transforms: dict = {}
    align_points: list[AlignPoint] = []
    overlay_img_width: int = 0
    overlay_img_height: int = 0
    _arrow_last_time: float = 0.0
    _arrow_last_dir: str = ""
    _arrow_repeat_count: int = 0
    _overlay_dragging: bool = False
    _overlay_drag_start_x: float = 0.0
    _overlay_drag_start_y: float = 0.0
    _overlay_drag_start_ox: float = 0.0
    _overlay_drag_start_oy: float = 0.0
    _overlay_prefetch_token: int = 0  # cancellation epoch for background DPI prefetch
    _level_prefetch_token: int = 0  # cancellation epoch for adjacent-level PNG warm
    _legacy_overlay_pending: bool = False
    _session_load_ok: bool = False  # guards auto-save; True only after a successful load

    # =====================================================================
    # §9 — DF% analysis
    # =====================================================================
    df_stamps: dict = {}
    room_df_results: dict = {}
    df_cursor_label: str = ""   # "px(x,y) DF: x.xx%" — shown in status bar
    df_cursor_df: str = ""      # "DF: x.xx%" — cursor overlay line 1

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
    room_browser_section_open: bool = True
    floor_plan_section_open: bool = True
    visualisation_section_open: bool = True
    collapsed_hdrs: list[str] = []
    shortcuts_modal_open: bool = False
    open_project_modal_open: bool = False
    create_project_modal_open: bool = False
    extract_modal_open: bool = False
    # Server-side folder browser — fallback for the "Browse…" button in
    # Open Project and for per-field Browse in Project Settings when the
    # backend cannot spawn a native OS file dialog (headless Docker, no X11).
    external_browser_open: bool = False
    external_browser_path: str = ""
    external_browser_entries: list[dict[str, Any]] = []
    external_browser_error: str = ""
    # "project"      → pick a folder that contains project.toml (Open Project)
    # "settings_file"→ pick a file matching allowed extensions (Settings Browse)
    external_browser_mode: str = "project"
    external_browser_target_field: str = ""
    external_browser_allowed_extensions: list[str] = []
    external_browser_multiple: bool = False
    status_message: str = "Ready"
    status_colour: str = "accent2"
    _last_d_press: float = 0.0
    _UNDO_MAX: int = 100

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

        Daylight structure (one HDR per view):
          [hdr row]
            [parent room row]
              [child room row]

        Sunlight structure (timeseries — one header per view, rooms shared
        across all frames of the view):
          [view row]
            [parent room row]
              [child room row]
        """
        if self.project_mode == "sunlight" and self.view_groups:
            return self._sunlight_tree_nodes()

        nodes: list[TreeNode] = []
        current_hdr_name = (
            self.hdr_files[self.current_hdr_idx]["name"]
            if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files)
            else ""
        )

        for hdr_idx in range(len(self.hdr_files) - 1, -1, -1):
            hdr = self.hdr_files[hdr_idx]
            hdr_name = hdr["name"]
            is_current = hdr_name == current_hdr_name
            collapsed = hdr_name in self.collapsed_hdrs

            # Count rooms for this HDR
            hdr_rooms = [(i, r) for i, r in enumerate(self.rooms) if r.get("hdr_file") == hdr_name]

            nodes.append({
                "node_type": "hdr",
                "label": hdr_name,
                "tooltip": "",
                "room_type": "",
                "indent": "0px",
                "selected": False,
                "is_current_hdr": is_current,
                "collapsed": collapsed,
                "has_children": len(hdr_rooms) > 0,
                "connector": "none",
                "parent_continues": "0",
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

            for top_pos, (room_idx, room) in enumerate(top_level):
                room_name = room.get("name", "")
                children = child_map.get(room_name, [])
                is_selected = (
                    room_idx == self.selected_room_idx
                    or room_idx in self.multi_selected_idxs
                )
                is_last_top = (top_pos == len(top_level) - 1)
                parent_connector = "L" if is_last_top else "T"
                nodes.append({
                    "node_type": "parent_room",
                    "label": room_name,
                    "tooltip": "",
                    "room_type": room.get("room_type", "") or "NONE",
                    "indent": "16px",
                    "selected": is_selected,
                    "is_current_hdr": is_current,
                    "collapsed": False,
                    "has_children": len(children) > 0,
                    "connector": parent_connector,
                    "parent_continues": "0",
                    "hdr_name": hdr_name,
                    "room_idx": room_idx,
                    "hdr_idx": hdr_idx,
                })
                for child_pos, (child_idx, child) in enumerate(children):
                    child_selected = (
                        child_idx == self.selected_room_idx
                        or child_idx in self.multi_selected_idxs
                    )
                    child_name = child.get("name", "")
                    child_label = child_name.removeprefix(room_name).strip("_ ") or child_name
                    is_last_child = (child_pos == len(children) - 1)
                    nodes.append({
                        "node_type": "child_room",
                        "label": child_label,
                        "tooltip": "",
                        "room_type": child.get("room_type", "") or "NONE",
                        "indent": "32px",
                        "selected": child_selected,
                        "is_current_hdr": is_current,
                        "collapsed": False,
                        "has_children": False,
                        "connector": "L" if is_last_child else "T",
                        "parent_continues": ("1" if not is_last_top else "0"),
                        "hdr_name": hdr_name,
                        "room_idx": child_idx,
                        "hdr_idx": hdr_idx,
                    })

            # Safety net: post-validation orphans (parent name not present as
            # a real top-level room). Render as parent_room so orphans never
            # display with child styling. Layers 1-2 should prevent reaching
            # this path with well-formed AOI inputs.
            top_level_names = {r.get("name", "") for _, r in top_level}
            orphan_groups = [(p, c) for p, c in child_map.items() if p not in top_level_names]
            for group_pos, (_parent_name, children) in enumerate(orphan_groups):
                is_last_group = (group_pos == len(orphan_groups) - 1)
                for child_pos, (child_idx, child) in enumerate(children):
                    child_selected = (
                        child_idx == self.selected_room_idx
                        or child_idx in self.multi_selected_idxs
                    )
                    is_last_child = (child_pos == len(children) - 1 and is_last_group)
                    nodes.append({
                        "node_type": "parent_room",
                        "label": child.get("name", ""),
                        "tooltip": "",
                        "room_type": child.get("room_type", "") or "NONE",
                        "indent": "16px",
                        "selected": child_selected,
                        "is_current_hdr": is_current,
                        "collapsed": False,
                        "has_children": False,
                        "connector": "L" if is_last_child else "T",
                        "parent_continues": "0",
                        "hdr_name": hdr_name,
                        "room_idx": child_idx,
                        "hdr_idx": hdr_idx,
                    })

        return nodes

    def _sunlight_tree_nodes(self) -> list[TreeNode]:
        """Sunlight variant of tree_nodes: one header per view (level). Rooms
        are keyed to ``view_name`` so they share across all timestep frames.
        ``hdr_idx`` on view rows is the view_groups index (consumed by
        ``navigate_to_view``)."""
        nodes: list[TreeNode] = []
        current_view_name = ""
        if 0 <= self.current_view_idx < len(self.view_groups):
            current_view_name = self.view_groups[self.current_view_idx]["view_name"]

        for view_idx in range(len(self.view_groups) - 1, -1, -1):
            vg = self.view_groups[view_idx]
            view_name = vg["view_name"]
            view_prefix = vg.get("view_prefix", view_name)
            is_current = view_name == current_view_name
            collapsed = view_name in self.collapsed_hdrs

            view_rooms = [(i, r) for i, r in enumerate(self.rooms) if r.get("hdr_file") == view_name]

            nodes.append({
                "node_type": "hdr",
                "label": view_name,
                "tooltip": view_prefix,
                "room_type": "",
                "indent": "0px",
                "selected": False,
                "is_current_hdr": is_current,
                "collapsed": collapsed,
                "has_children": len(view_rooms) > 0,
                "connector": "none",
                "parent_continues": "0",
                "hdr_name": view_name,
                "room_idx": -1,
                "hdr_idx": view_idx,
            })

            if collapsed:
                continue

            top_level = [(i, r) for i, r in view_rooms if not r.get("parent")]
            child_map: dict[str, list[tuple[int, dict]]] = {}
            for i, r in view_rooms:
                p = r.get("parent") or ""
                if p:
                    child_map.setdefault(p, []).append((i, r))

            for top_pos, (room_idx, room) in enumerate(top_level):
                room_name = room.get("name", "")
                children = child_map.get(room_name, [])
                is_selected = (
                    room_idx == self.selected_room_idx
                    or room_idx in self.multi_selected_idxs
                )
                is_last_top = (top_pos == len(top_level) - 1)
                parent_connector = "L" if is_last_top else "T"
                nodes.append({
                    "node_type": "parent_room",
                    "label": room_name,
                    "tooltip": "",
                    "room_type": room.get("room_type", "") or "NONE",
                    "indent": "16px",
                    "selected": is_selected,
                    "is_current_hdr": is_current,
                    "collapsed": False,
                    "has_children": len(children) > 0,
                    "connector": parent_connector,
                    "parent_continues": "0",
                    "hdr_name": view_name,
                    "room_idx": room_idx,
                    "hdr_idx": view_idx,
                })
                for child_pos, (child_idx, child) in enumerate(children):
                    child_selected = (
                        child_idx == self.selected_room_idx
                        or child_idx in self.multi_selected_idxs
                    )
                    child_name = child.get("name", "")
                    child_label = child_name.removeprefix(room_name).strip("_ ") or child_name
                    is_last_child = (child_pos == len(children) - 1)
                    nodes.append({
                        "node_type": "child_room",
                        "label": child_label,
                        "tooltip": "",
                        "room_type": child.get("room_type", "") or "NONE",
                        "indent": "32px",
                        "selected": child_selected,
                        "is_current_hdr": is_current,
                        "collapsed": False,
                        "has_children": False,
                        "connector": "L" if is_last_child else "T",
                        "parent_continues": ("1" if not is_last_top else "0"),
                        "hdr_name": view_name,
                        "room_idx": child_idx,
                        "hdr_idx": view_idx,
                    })

            # Safety net (see tree_nodes comment above).
            top_level_names = {r.get("name", "") for _, r in top_level}
            orphan_groups = [(p, c) for p, c in child_map.items() if p not in top_level_names]
            for group_pos, (_parent_name, children) in enumerate(orphan_groups):
                is_last_group = (group_pos == len(orphan_groups) - 1)
                for child_pos, (child_idx, child) in enumerate(children):
                    child_selected = (
                        child_idx == self.selected_room_idx
                        or child_idx in self.multi_selected_idxs
                    )
                    is_last_child = (child_pos == len(children) - 1 and is_last_group)
                    nodes.append({
                        "node_type": "parent_room",
                        "label": child.get("name", ""),
                        "tooltip": "",
                        "room_type": child.get("room_type", "") or "NONE",
                        "indent": "16px",
                        "selected": child_selected,
                        "is_current_hdr": is_current,
                        "collapsed": False,
                        "has_children": False,
                        "connector": "L" if is_last_child else "T",
                        "parent_continues": "0",
                        "hdr_name": view_name,
                        "room_idx": child_idx,
                        "hdr_idx": view_idx,
                    })

        return nodes

    @rx.var
    def current_view_frame_count(self) -> int:
        if not self.view_groups:
            return 0
        if not (0 <= self.current_view_idx < len(self.view_groups)):
            return 0
        return len(self.view_groups[self.current_view_idx]["frames"])

    @rx.var
    def current_frame_label(self) -> str:
        if not self.view_groups:
            return ""
        if not (0 <= self.current_view_idx < len(self.view_groups)):
            return ""
        frames = self.view_groups[self.current_view_idx]["frames"]
        if not frames:
            return ""
        idx = max(0, min(self.current_frame_idx, len(frames) - 1))
        return frames[idx]["frame_label"]

    @rx.var
    def current_view_name(self) -> str:
        if not self.view_groups:
            return ""
        if not (0 <= self.current_view_idx < len(self.view_groups)):
            return ""
        return self.view_groups[self.current_view_idx]["view_name"]

    @rx.var
    def is_sunlight_mode(self) -> bool:
        return self.project_mode == "sunlight" and bool(self.view_groups)

    def set_viewport_size(self, data: dict) -> None:
        """Called by ResizeObserver JS when the viewport container resizes."""
        self.viewport_width = int(data.get("w", 0))
        self.viewport_height = int(data.get("h", 0))
        if self._legacy_overlay_pending and self.viewport_width > 0:
            self._migrate_legacy_overlay_transforms()

    @rx.var
    def zoom_pct(self) -> str:
        return f"{int(self.zoom_level * 100)}%"

    @rx.var
    def svg_viewbox(self) -> str:
        if self.image_width > 0 and self.image_height > 0:
            return f"0 0 {self.image_width} {self.image_height}"
        return "0 0 1000 800"

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
        vp_x, _, vh, _, *_rest = vp_params
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
        _, vp_y, _, vv, *_rest = vp_params
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
        """Room name + threshold font size (base 6.5), scaled by annotation_scale and inversely by zoom."""
        fs = 6.5 * self.annotation_scale / max(self.zoom_level, 0.01)
        return str(round(max(2.0, min(30.0, fs)), 1))

    @rx.var
    def df_stamp_font_size(self) -> str:
        """DF stamp label font size, scaled by annotation_scale and inversely by zoom."""
        fs = 2.5 * self.annotation_scale / max(self.zoom_level, 0.01)
        return str(round(max(1.0, min(10.0, fs)), 1))

    @rx.var
    def df_stamp_bg_width(self) -> str:
        """DF stamp background rect width."""
        w = 27.5 * self.annotation_scale / max(self.zoom_level, 0.01)
        return str(round(max(8.0, min(110.0, w)), 1))

    def _df_fs_val(self) -> float:
        """Internal helper: clamped DF stamp font size as a number."""
        return max(1.0, min(10.0, 2.5 * self.annotation_scale / max(self.zoom_level, 0.01)))

    @rx.var
    def df_stamp_bg_height(self) -> str:
        """DF stamp background rect height (single line). ~2x font size."""
        return str(round(self._df_fs_val() * 2.0, 1))

    @rx.var
    def df_stamp_bg_height_f(self) -> float:
        """DF stamp background rect height as float for SVG coordinate arithmetic."""
        return round(self._df_fs_val() * 2.0, 2)

    @rx.var
    def df_stamp_bg_half_f(self) -> float:
        """Half the background rect height — used for vertically centering text."""
        return round(self._df_fs_val(), 2)

    @rx.var
    def df_stamp_icon_half(self) -> float:
        """Half icon size — used to center the icon on a point via translate."""
        return round(max(2.0, min(16.0, self._df_fs_val() * 2.0)) / 2.0, 2)

    @rx.var
    def df_stamp_icon_scale(self) -> str:
        """Scale factor mapping 24×24 lucide viewBox into image-pixel units."""
        return str(round(max(2.0, min(16.0, self._df_fs_val() * 2.0)) / 24.0, 4))

    @rx.var
    def df_stamp_x_pad(self) -> float:
        """Horizontal padding from stamp x to text. ~0.6x font size."""
        return round(self._df_fs_val() * 0.6, 1)

    @rx.var
    def room_stroke_width(self) -> str:
        """Boundary stroke width that stays visually consistent across zoom levels.

        Scales inversely with zoom_level so lines don't appear to thin out when
        zoomed in (since SVG stroke-width is in image-pixel space, not screen space).
        """
        base = 1.5
        lw = base / max(self.zoom_level, 0.01)
        return str(round(max(base * 0.5, min(base * 2.5, lw)), 2))

    @rx.var
    def child_room_stroke_width(self) -> str:
        """Half the parent stroke width for child/division rooms."""
        base = 1.5
        lw = base / max(self.zoom_level, 0.01)
        parent_w = max(base * 0.5, min(base * 2.5, lw))
        return str(round(parent_w * 0.5, 2))

    @rx.var
    def divider_vertex_radius(self) -> str:
        """Radius for divider mode vertex indicators — slightly larger than boundary stroke."""
        base = 1.5
        lw = base / max(self.zoom_level, 0.01)
        stroke_w = max(base * 0.5, min(base * 2.5, lw))
        return str(round(stroke_w * 1.2, 2))

    @rx.var
    def edit_vertex_radius(self) -> str:
        """Radius for edit-mode vertex handles — diameter = 3x boundary stroke width."""
        base = 1.5
        lw = base / max(self.zoom_level, 0.01)
        stroke_w = max(base * 0.5, min(base * 2.5, lw))
        return str(round(stroke_w * 1.5, 2))

    @rx.var
    def snap_rect_x(self) -> str:
        """Top-left x of the 9×9 snap indicator square."""
        return str(self.snap_point.get("x", 0) - 4.5)

    @rx.var
    def snap_rect_y(self) -> str:
        """Top-left y of the 9×9 snap indicator square."""
        return str(self.snap_point.get("y", 0) - 4.5)

    @rx.var
    def enriched_rooms(self) -> list[EnrichedRoom]:
        """Rooms for current HDR enriched with SVG rendering data."""
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        room_key = self._current_level_key() or hdr_name
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
        intermediates = []   # pass-1 data per room
        per_room_fs = []     # max font size per visible parent room
        per_room_fs_child = []  # max font size per visible child room
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != room_key:
                continue
            if not room.get("visible", True):
                continue

            # Use reprojected world_vertices when view params are available
            world_verts = room.get("world_vertices", [])
            if vp_params and len(world_verts) >= 3 and img_w > 0 and img_h > 0:
                vp_x, vp_y, vh, vv, *_rest = vp_params
                verts = reproject(world_verts, vp_x, vp_y, vh, vv)
            else:
                verts = room.get("vertices", [])

            if len(verts) < 3:
                continue

            is_div = bool(room.get("parent"))
            verts_str = " ".join(f"{v[0]},{v[1]}" for v in verts)

            # Label position via centroid
            lx, ly = polygon_label_point(verts)

            # DF results
            df_info = self.room_df_results.get(str(i), {})
            df_lines_raw = df_info.get("result_lines", [])
            df_status = df_info.get("pass_status", "none")
            has_df = len(df_lines_raw) > 0
            _area_num = df_info.get("area_num", "")
            _area_den = df_info.get("area_den", "")
            _area_pct = df_info.get("area_pct", "")

            # DF colour from pct_above (numeric), matching matplotlib thresholds
            pct_above = df_info.get("pct_above")
            scale = self.annotation_scale
            # Base font size in image-pixel units — zoom-independent.
            # The inscribed-rect fit factor sizes text to fill the room.
            _df_fs = 8.5 * scale
            _stroke_bold = str(round(_df_fs * 0.06, 2))
            _stroke_norm = str(round(_df_fs * 0.12, 2))
            if pct_above is not None and has_df:
                if pct_above >= 90:
                    line_0_color = "#000000"
                    line_0_weight = "bold"
                    line_0_stroke = "white"
                    line_0_stroke_w = _stroke_bold
                elif pct_above >= 50:
                    line_0_color = "#E97132"
                    line_0_weight = "normal"
                    line_0_stroke = "black"
                    line_0_stroke_w = _stroke_norm
                else:
                    line_0_color = "#EE0000"
                    line_0_weight = "normal"
                    line_0_stroke = "black"
                    line_0_stroke_w = _stroke_norm
            else:
                line_0_color = "#ffffff"
                line_0_weight = "normal"
                line_0_stroke = "black"
                line_0_stroke_w = _stroke_norm

            # ---- Pass 1: compute max font size per room ----
            LBL_RATIO = 0.75
            GAP_01 = 0.6                # gap after line 0 (tighter)
            GAP_12 = LBL_RATIO * 0.5    # gap after line 1 (tighter)

            if has_df and len(df_lines_raw) >= 2:
                stack_mult = 1.0 + GAP_01 + LBL_RATIO + GAP_12 + LBL_RATIO
            elif has_df:
                stack_mult = 1.0 + GAP_12 + LBL_RATIO
            else:
                stack_mult = LBL_RATIO

            # When fraction is rendered (stacked num/den), visual width is
            # narrower than the flat text.  Estimate from the layout:
            #   fraction_col + gap + "m²" + gap + pct
            if _area_num:
                _frac_w = max(len(_area_num), len(_area_den))
                chars_0 = _frac_w + 1 + 2 + 1 + len(_area_pct)
            else:
                chars_0 = len(df_lines_raw[0]) if has_df else 0
            chars_1 = len(df_lines_raw[1]) if len(df_lines_raw) >= 2 else 0
            chars_name = len(room.get("name", ""))
            CHAR_W = 0.65  # DM Mono + special chars + bold safety
            STROKE_PAD = 0.12  # -webkit-text-stroke extends visual bbox
            width_mult = max(
                chars_0 * CHAR_W,
                chars_1 * CHAR_W * LBL_RATIO,
                chars_name * CHAR_W * LBL_RATIO,
                0.01,
            ) + STROKE_PAD  # add stroke margin (in F units)
            stack_mult_padded = stack_mult + STROKE_PAD

            is_circ = room.get("room_type", "") == "CIRC"

            # Aspect-aware inscribed rect — checks corners & edge midpoints
            # so concave polygons don't permit overflow.
            half_w, half_h = max_inscribed_rect_aspect(
                lx, ly, width_mult, stack_mult_padded, verts,
            )
            avail_w = half_w * 2 * 0.95
            avail_h = half_h * 2 * 0.95

            fs_from_h = avail_h / stack_mult_padded if stack_mult_padded > 0 else 999
            fs_from_w = avail_w / width_mult if width_mult > 0 else 999
            # Empirically calibrated: CHAR_W/STROKE_PAD slightly over-estimate visual
            # footprint, so auto-fit under-sizes by ~10%.
            FIT_FACTOR = 1.1
            max_fs = min(fs_from_h, fs_from_w) * scale * FIT_FACTOR

            # Stash intermediate data for pass 2
            intermediates.append({
                "i": i, "room": room, "verts": verts, "verts_str": verts_str,
                "lx": lx, "ly": ly, "is_div": is_div, "is_circ": is_circ,
                "has_df": has_df, "df_lines_raw": df_lines_raw,
                "df_status": df_status, "pct_above": pct_above,
                "line_0_color": line_0_color, "line_0_weight": line_0_weight,
                "line_0_stroke": line_0_stroke, "line_0_stroke_w": line_0_stroke_w,
                "stack_mult": stack_mult, "max_fs": max_fs,
                "width_mult": width_mult, "stack_mult_padded": stack_mult_padded,
                "area_num": _area_num, "area_den": _area_den, "area_pct": _area_pct,
            })
            # Two-tier font sizing: parent rooms and child (div) rooms get
            # independent uniform sizes so small children don't shrink
            # parent annotations.
            if not is_circ:
                if is_div:
                    per_room_fs_child.append(max_fs)
                else:
                    per_room_fs.append(max_fs)

        # ---- Uniform font sizes per tier ----
        uniform_fs_parent = min(per_room_fs) if per_room_fs else 0.0
        uniform_fs_child = min(per_room_fs_child) if per_room_fs_child else uniform_fs_parent

        # ---- Pass 2: build result dicts using uniform font size ----
        LBL_RATIO = 0.75
        GAP_01 = 0.6
        GAP_12 = LBL_RATIO * 0.5

        for info in intermediates:
            i = info["i"]
            room = info["room"]
            verts = info["verts"]
            lx, ly = info["lx"], info["ly"]
            has_df = info["has_df"]
            df_lines_raw = info["df_lines_raw"]

            _tier_fs = uniform_fs_child if info["is_div"] else uniform_fs_parent
            _df_fs_fit = _tier_fs
            _lbl_fs_fit = _df_fs_fit * LBL_RATIO
            show_labels = (
                _df_fs_fit >= 1.0
                and not info["is_circ"]
                and _tier_fs <= info["max_fs"] + 1e-6
            )

            room_df_fs = str(round(_df_fs_fit, 2))
            room_lbl_fs = str(round(_lbl_fs_fit, 2))
            room_step = _df_fs_fit * GAP_01
            room_nstep = _df_fs_fit * GAP_12
            room_stroke_w = str(round(_lbl_fs_fit * 0.12, 2))

            # Y positions: vertically centre text stack on label anchor
            if has_df and len(df_lines_raw) >= 2:
                total_h = _df_fs_fit + room_step + _lbl_fs_fit + room_nstep + _lbl_fs_fit
            elif has_df:
                total_h = _df_fs_fit + room_nstep + _lbl_fs_fit
            else:
                total_h = _lbl_fs_fit
            top_y = ly - total_h / 2

            if has_df and len(df_lines_raw) >= 2:
                df_line_0_y = top_y + _df_fs_fit / 2
                df_line_1_y = df_line_0_y + room_step + _lbl_fs_fit / 2
                name_y_val = df_line_1_y + room_nstep + _lbl_fs_fit / 2
            elif has_df:
                df_line_0_y = top_y + _df_fs_fit / 2
                df_line_1_y = df_line_0_y
                name_y_val = df_line_0_y + room_nstep + _lbl_fs_fit / 2
            else:
                df_line_0_y = ly
                df_line_1_y = ly
                name_y_val = ly

            # Annotation bounding box (image-pixel space, centred on lx,ly)
            _bbox_w = info["width_mult"] * _df_fs_fit
            _bbox_h = info["stack_mult_padded"] * _df_fs_fit
            _bbox_left_pct = str(round((lx - _bbox_w / 2) / img_w * 100, 4)) if img_w > 0 else "0"
            _bbox_top_pct = str(round((ly - _bbox_h / 2) / img_h * 100, 4)) if img_h > 0 else "0"
            _bbox_w_pct = str(round(_bbox_w / img_w * 100, 4)) if img_w > 0 else "0"
            _bbox_h_pct = str(round(_bbox_h / img_h * 100, 4)) if img_h > 0 else "0"

            # HTML overlay: percentage-based positioning & font sizes
            _lx_pct = str(round(lx / img_w * 100, 4)) if img_w > 0 else "0"
            _dl0y_pct = str(round(df_line_0_y / img_h * 100, 4)) if img_h > 0 else "0"
            _dl1y_pct = str(round(df_line_1_y / img_h * 100, 4)) if img_h > 0 else "0"
            _ny_pct = str(round(name_y_val / img_h * 100, 4)) if img_h > 0 else "0"
            _df_fs_pct = str(round(_df_fs_fit / img_w * 100, 4)) if img_w > 0 else "0"
            _lbl_fs_pct = str(round(_lbl_fs_fit / img_w * 100, 4)) if img_w > 0 else "0"

            # CSS clip-path polygon (percentage coords)
            if img_w > 0 and img_h > 0 and len(verts) >= 3:
                _clip_parts = ", ".join(
                    f"{round(v[0] / img_w * 100, 4)}% {round(v[1] / img_h * 100, 4)}%"
                    for v in verts
                )
                _clip_css = f"polygon({_clip_parts})"
            else:
                _clip_css = "none"

            # Text stroke for outline
            _df_stroke_w = round(_df_fs_fit * 0.12, 2)
            _lbl_stroke_w = round(_lbl_fs_fit * 0.12, 2)
            line_0_stroke = info["line_0_stroke"]
            _df_text_stroke = f"{_df_stroke_w}px {line_0_stroke}"
            _lbl_text_stroke = f"{_lbl_stroke_w}px black"

            result.append({
                "idx": i,
                "name": room.get("name", ""),
                "room_type": room.get("room_type", "") or "NONE",
                "parent": room.get("parent") or "",
                "is_circ": info["is_circ"],
                "is_div": info["is_div"],
                "vertices_str": info["verts_str"],
                "label_x": str(lx),
                "label_y": str(ly),
                "df_line_0": df_lines_raw[0] if has_df else "",
                "df_line_0_y": str(df_line_0_y),
                "df_line_0_color": info["line_0_color"],
                "df_line_0_weight": info["line_0_weight"],
                "df_line_0_stroke": line_0_stroke,
                "df_line_0_stroke_w": info["line_0_stroke_w"],
                "df_line_1": df_lines_raw[1] if len(df_lines_raw) >= 2 else "",
                "df_line_1_y": str(df_line_1_y),
                "name_y": str(name_y_val),
                "room_df_fs": room_df_fs,
                "room_lbl_fs": room_lbl_fs,
                "room_stroke_w": room_stroke_w,
                "has_df": has_df,
                "show_labels": show_labels,
                "selected": i == self.selected_room_idx or i in self.multi_selected_idxs,
                "df_status": info["df_status"],
                # HTML overlay fields
                "label_x_pct": _lx_pct,
                "df_line_0_y_pct": _dl0y_pct,
                "df_line_1_y_pct": _dl1y_pct,
                "name_y_pct": _ny_pct,
                "room_df_fs_pct": _df_fs_pct,
                "room_lbl_fs_pct": _lbl_fs_pct,
                "clip_polygon_css": _clip_css,
                "df_line_0_text_stroke": _df_text_stroke,
                "lbl_text_stroke": _lbl_text_stroke,
                "bbox_left_pct": _bbox_left_pct,
                "bbox_top_pct": _bbox_top_pct,
                "bbox_w_pct": _bbox_w_pct,
                "bbox_h_pct": _bbox_h_pct,
                "df_area_num": info.get("area_num", ""),
                "df_area_den": info.get("area_den", ""),
                "df_area_pct": info.get("area_pct", ""),
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
    def first_draw_vertex(self) -> dict:
        if self.draw_vertices:
            return self.draw_vertices[0]
        return {"x": 0.0, "y": 0.0}

    @rx.var
    def can_close_polygon(self) -> bool:
        return len(self.draw_vertices) >= 3

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
    def has_divider_preview(self) -> bool:
        return bool(self.divider_points) and bool(self.divider_preview_point)

    @rx.var
    def divider_preview_line_str(self) -> str:
        """Polyline from last placed divider point to current cursor (ortho-aware)."""
        if not self.divider_points or not self.divider_preview_point:
            return ""
        last = self.divider_points[-1]
        p = self.divider_preview_point
        return f"{last['x']},{last['y']} {p['x']},{p['y']}"

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
    def canvas_css_transform(self) -> str:
        """CSS transform for #editor-canvas, driven by zoom/pan state.

        Exposed via a data-transform attribute + MutationObserver so the
        transform survives Reflex re-renders. Normal scroll/pan gestures
        update JS local vars directly; this computed var reflects the last
        synced value (or explicit setTransform calls from fit/reset).
        """
        return f"translate({self.pan_x}px, {self.pan_y}px) scale({self.zoom_level})"

    @rx.var
    def canvas_fit_scale(self) -> float:
        """Screen px per image px at zoom=1, fit-to-contain inside viewport.

        S = min(vw/iw, vh/ih). Canvas is sized iw*S × ih*S so any image
        aspect — landscape, portrait, square — fully fits the viewport.
        For landscape images where vw/iw <= vh/ih, S collapses to vw/iw
        (the previous width-locked behaviour).
        """
        if self.image_width <= 0 or self.image_height <= 0:
            return 1.0
        vw = self.viewport_width if self.viewport_width > 0 else self.image_width
        vh = self.viewport_height if self.viewport_height > 0 else self.image_height
        return min(vw / self.image_width, vh / self.image_height)

    @rx.var
    def canvas_width_css(self) -> str:
        if self.image_width <= 0 or self.image_height <= 0:
            return "100%"
        return f"{self.image_width * self.canvas_fit_scale}px"

    @rx.var
    def canvas_height_css(self) -> str:
        if self.image_width <= 0 or self.image_height <= 0:
            return "auto"
        return f"{self.image_height * self.canvas_fit_scale}px"

    @rx.var
    def overlay_css_transform(self) -> str:
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        if self.viewport_width <= 0 or self.image_width <= 0:
            return "translate(0px, 0px) scale(1, 1) rotate(0deg)"
        t = self._get_current_overlay_transform()
        iw = self.image_width
        ih = self.image_height or 1
        s = self.canvas_fit_scale
        cw = iw * s   # canvas width in CSS px (= vw for landscape)
        ch = ih * s   # canvas height in CSS px
        sx = t.get("scale_x", 1.0)
        sy = t.get("scale_y", 1.0)
        # Centring term: with transform-origin top-left, scaled PDF top-left stays at (0,0).
        # Translate the scaled PDF so its centre coincides with HDR centre, then apply
        # the user-controlled offset (offset_x/y are fractions of canvas dimensions,
        # measured as displacement of PDF centre from HDR centre).
        pdf_aspect = (self.overlay_img_height / self.overlay_img_width) if self.overlay_img_width > 0 else (ih / iw)
        cx = cw * (1.0 - sx) / 2.0
        cy = (ch - cw * pdf_aspect * sy) / 2.0
        ox = cx + t.get("offset_x", 0) * cw
        oy = cy + t.get("offset_y", 0) * ch
        rot = (t.get("rotation_90", 0) % 4) * 90
        return f"translate({ox}px, {oy}px) scale({sx}, {sy}) rotate({rot}deg)"

    @rx.var
    def overlay_params_json(self) -> str:
        """JSON-encoded fractional transform params for JS-side resize interpolation.

        JS reads these from a data attribute to recompute pixel transforms
        synchronously on viewport resize, avoiding the Python round-trip lag.
        """
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps
        t = self._get_current_overlay_transform()
        iw = self.image_width
        ih = self.image_height or 1
        if self.overlay_img_width > 0:
            pdf_aspect = self.overlay_img_height / self.overlay_img_width
        else:
            pdf_aspect = ih / max(iw, 1)
        return json.dumps({
            "offset_x": t.get("offset_x", 0),
            "offset_y": t.get("offset_y", 0),
            "scale_x": t.get("scale_x", 1.0),
            "scale_y": t.get("scale_y", 1.0),
            "rotation_90": t.get("rotation_90", 0),
            "iw": iw,
            "ih": ih,
            "pdf_aspect": pdf_aspect,
        })

    @rx.var
    def progress_pct_str(self) -> str:
        return f"{self.progress_pct}%"

    @rx.var
    def overlay_has_pdf(self) -> bool:
        return bool(self.overlay_pdf_path)

    @rx.var
    def overlay_alpha_str(self) -> str:
        return str(self.overlay_alpha)

    @rx.var
    def overlay_transparency_str(self) -> str:
        """Current transparency as a fraction 0–1 (0 = opaque, 1 = fully transparent)."""
        return str(round(1.0 - self.overlay_alpha, 2))

    @rx.var
    def overlay_svg_transform(self) -> str:
        """SVG-syntax transform for the overlay image (no CSS units)."""
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        t = self._get_current_overlay_transform()
        iw = self.image_width or 1
        ih = self.image_height or 1
        sx = t.get("scale_x", 1.0)
        sy = t.get("scale_y", 1.0)
        # PDF rendered to fill HDR width (= iw) at scale 1.
        pdf_aspect = (self.overlay_img_height / self.overlay_img_width) if self.overlay_img_width > 0 else (ih / iw)
        cx = iw * (1.0 - sx) / 2.0
        cy = (ih - iw * pdf_aspect * sy) / 2.0
        ox = cx + t.get("offset_x", 0) * iw
        oy = cy + t.get("offset_y", 0) * ih
        return f"translate({ox},{oy}) scale({sx},{sy})"

    @rx.var
    def overlay_offset_x_str(self) -> str:
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        iw = self.image_width
        if iw <= 0:
            return "0"
        return str(round(self._get_current_overlay_transform().get("offset_x", 0) * iw))

    @rx.var
    def overlay_offset_y_str(self) -> str:
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        ih = self.image_height
        if ih <= 0:
            return "0"
        return str(round(self._get_current_overlay_transform().get("offset_y", 0) * ih))

    @rx.var
    def overlay_scale_str(self) -> str:
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        return str(self._get_current_overlay_transform().get("scale_x", 1.0))

    @rx.var
    def overlay_rotation_deg_str(self) -> str:
        """Current rotation in degrees (0/90/180/270) as a string for the input field."""
        _ = self.overlay_transforms, self.current_view_idx, self.current_hdr_idx  # declare deps for Reflex tracking
        rot90 = self._get_current_overlay_transform().get("rotation_90", 0)
        return str((rot90 % 4) * 90)

    @rx.var
    def selected_room_vertices(self) -> list[VertexPoint]:
        """Vertices of the selected room, for edit mode handles."""
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return []
        verts = self.rooms[self.selected_room_idx].get("vertices", [])
        return [{"x": float(v[0]), "y": float(v[1])} for v in verts]

    @rx.var
    def divider_room_vertices(self) -> list[VertexPoint]:
        """Pixel-space vertices of the room being divided, for non-draggable snap indicators."""
        if not self.divider_mode or self.divider_room_idx < 0 or self.divider_room_idx >= len(self.rooms):
            return []
        verts = self._room_pixel_vertices(self.rooms[self.divider_room_idx])
        return [{"x": float(v[0]), "y": float(v[1])} for v in verts]

    # =====================================================================
    # MODE TOGGLES
    # =====================================================================

    def _clear_modes(self) -> None:
        self._finalize_vertex_edit_undo()
        self.draw_mode = False
        self.edit_mode = False
        self.divider_mode = False
        self.df_placement_mode = False
        self.pan_mode = False
        self.draw_vertices = []
        self.snap_point = {}
        self.preview_point = {}
        self.divider_points = []
        self.divider_preview_point = {}
        self.divider_room_idx = -1
        self.divider_room_name = ""
        self.dragging_vertex_idx = -1

    @debug_handler
    def toggle_draw_mode(self) -> None:
        was_on = self.draw_mode
        self._clear_modes()
        self.draw_mode = not was_on
        if self.draw_mode:
            self.room_name_input = ""  # Force ROOM_NNN auto-naming for drawn rooms
            self.selected_parent = ""  # Draw mode creates parent rooms; clear stale parent
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
    def toggle_divider_mode(self):
        was_on = self.divider_mode
        self._clear_modes()
        self.divider_mode = not was_on
        if self.divider_mode and self.selected_room_idx >= 0:
            self.divider_room_idx = self.selected_room_idx
            self.divider_room_name = self.rooms[self.selected_room_idx].get("name", "")
            yield from self.fit_zoom()
        self.status_message = "Divider mode — click to place cut line, S to split, Esc to cancel" if self.divider_mode else "Ready"
        self.status_colour = "accent2"

    def toggle_df_placement(self) -> None:
        was_on = self.df_placement_mode
        self._clear_modes()
        self.df_placement_mode = not was_on
        if self.df_placement_mode:
            self.overlay_align_mode = False
            self._load_df_image_cache()
            loaded = _df_cache["image"] is not None
            self.status_message = "DF% placement ON — click to stamp values" if loaded else "DF% placement ON — HDR image could not be loaded"
        else:
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            self.df_cursor_label = ""
            self.df_cursor_df = ""
            self.status_message = "Ready"
        self.status_colour = "accent" if self.df_placement_mode else "accent2"

    @debug_handler
    def toggle_pan_mode(self) -> None:
        was_on = self.pan_mode
        self._clear_modes()
        self.pan_mode = not was_on
        self.status_message = "Pan mode ON — click-drag to pan" if self.pan_mode else "Ready"
        self.status_colour = "accent" if self.pan_mode else "accent2"

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
        self.context_menu_visible = False
        if self.draw_mode or self.edit_mode or self.divider_mode or self.df_placement_mode or self.pan_mode or self.overlay_align_mode:
            was_df = self.df_placement_mode
            self._clear_modes()
            self.overlay_align_mode = False
            self.align_points = []
            if was_df:
                _df_cache["image"] = None
                _df_cache["hdr_path"] = ""
                self.df_cursor_label = ""
                self.df_cursor_df = ""
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
            old_hdr_idx = self.current_hdr_idx
            old_variant_idx = self.current_variant_idx
            self.current_hdr_idx = new_idx
            self._rebuild_variants()
            self.load_current_image()
            hdr_name = self.hdr_files[new_idx]["name"]
            self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]
            # Invalidate DF image cache; recompute will reload on next call
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            if self.df_placement_mode:
                self._load_df_image_cache()
            self._recompute_df()
            self._push_undo({
                "action": "hdr_navigate",
                "desc": f"Navigate to {hdr_name}",
                "before": {"hdr_idx": old_hdr_idx, "variant_idx": old_variant_idx},
                "after": {"hdr_idx": new_idx, "variant_idx": self.current_variant_idx},
            })

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
        variants = list(hdr_info.get("tiff_paths", []))
        self.image_variants = variants
        if self.current_variant_idx >= len(variants):
            self.current_variant_idx = 0

    def load_current_image(self) -> None:
        from ..lib.image_loader import (
            get_image_dimensions,
            load_frame_png_as_base64,
            load_image_as_base64,
        )
        # Sunlight: read the {stem}.png sibling written by the renderer.
        if (self.project_mode == "sunlight" and self.hdr_files
                and 0 <= self.current_hdr_idx < len(self.hdr_files)
                and self.current_variant_idx == 0):
            hdr_path = Path(self.hdr_files[self.current_hdr_idx]["hdr_path"])
            b64 = load_frame_png_as_base64(hdr_path)
            if b64:
                self.current_image_b64 = b64
                png_path = hdr_path.parent / f"{hdr_path.stem}.png"
                w, h = get_image_dimensions(png_path)
                self.image_width = w
                self.image_height = h
                self._update_legend()
                return

        if not self.image_variants:
            self.current_image_b64 = ""
            self.current_legend_b64 = ""
            return
        idx = min(self.current_variant_idx, len(self.image_variants) - 1)
        path = Path(self.image_variants[idx])
        b64 = load_image_as_base64(path)
        if b64:
            self.current_image_b64 = b64
            w, h = get_image_dimensions(path)
            self.image_width = w
            self.image_height = h
        else:
            self.current_image_b64 = ""
        self._update_legend()

    def _update_legend(self) -> None:
        """Load the legend PNG matching the current image variant, or clear."""
        self.current_legend_b64 = ""
        if not self.image_variants or not self.hdr_files:
            return
        idx = min(self.current_variant_idx, len(self.image_variants) - 1)
        variant_path = Path(self.image_variants[idx])
        if variant_path.suffix.lower() in (".hdr", ".pic"):
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        legend_map: dict = hdr_info.get("legend_map", {})
        if not legend_map:
            return
        hdr_stem = hdr_info["name"]
        variant_stem = variant_path.stem
        suffix = variant_stem[len(hdr_stem) + 1:] if variant_stem.startswith(hdr_stem + "_") else variant_stem
        for key, legend_path in legend_map.items():
            if key in suffix:
                from ..lib.image_loader import load_image_as_base64
                b64 = load_image_as_base64(Path(legend_path))
                if b64:
                    self.current_legend_b64 = b64
                return

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
            self.room_type_input = room.get("room_type", "NONE") or "NONE"
            self.selected_parent = room.get("parent", "") or ""
            # Navigate to the HDR/view this room belongs to
            hdr_name = room.get("hdr_file", "")
            if self.project_mode == "sunlight" and self.view_groups:
                for vi, vg in enumerate(self.view_groups):
                    if vg["view_name"] == hdr_name and vi != self.current_view_idx:
                        self._goto_frame(vi, 0)
                        self.collapsed_hdrs = [v["view_name"] for v in self.view_groups if v["view_name"] != hdr_name]
                        break
                return
            for i, h in enumerate(self.hdr_files):
                if h["name"] == hdr_name and i != self.current_hdr_idx:
                    self.current_hdr_idx = i
                    self._rebuild_variants()
                    self.load_current_image()
                    self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]
                    # Invalidate DF cache; reload if placement mode is active
                    _df_cache["image"] = None
                    _df_cache["hdr_path"] = ""
                    if self.df_placement_mode:
                        self._load_df_image_cache()
                    break

    def room_or_stamp_click(self, idx: int, pointer: dict) -> None:
        """Polygon click handler — stamps DF% in placement mode, otherwise selects (or multi-selects) room.

        pointer is a Reflex pointer event dict containing client_x/client_y (screen pixels)
        and optionally x/y SVG coords set by the JS click handler.  We prefer SVG coords from
        the pointer dict so the stamp position matches the exact click — falling back to the
        last mouse_move position only if SVG coords are not present.
        """
        # Dismiss context menu on any polygon click
        self.context_menu_visible = False
        if self.df_placement_mode:
            # Prefer SVG-space coords forwarded in the pointer dict by the JS click handler;
            # fall back to last mouse_move state if not available.
            cx = pointer.get("x") if pointer.get("x") is not None else self.mouse_x
            cy = pointer.get("y") if pointer.get("y") is not None else self.mouse_y
            self._df_stamp(float(cx), float(cy))
        else:
            self.select_room_or_multi(idx, pointer)

    def select_room_multi(self, idx: int) -> None:
        if idx in self.multi_selected_idxs:
            self.multi_selected_idxs = [i for i in self.multi_selected_idxs if i != idx]
        else:
            self.multi_selected_idxs = self.multi_selected_idxs + [idx]


    def collapse_all_hdrs(self) -> None:
        if self.project_mode == "sunlight" and self.view_groups:
            self.collapsed_hdrs = [v["view_name"] for v in self.view_groups]
        else:
            self.collapsed_hdrs = [h["name"] for h in self.hdr_files]

    def expand_all_hdrs(self) -> None:
        self.collapsed_hdrs = []

    def toggle_hdr_collapse(self, hdr_name: str) -> None:
        if hdr_name in self.collapsed_hdrs:
            self.collapsed_hdrs = [h for h in self.collapsed_hdrs if h != hdr_name]
        else:
            self.collapsed_hdrs = self.collapsed_hdrs + [hdr_name]

    # =====================================================================
    # SUNLIGHT VIEW NAVIGATION (timeseries frame cycling)
    # =====================================================================

    def _current_room_hdr_key(self) -> str:
        """Return the value to store in ``room['hdr_file']`` for the current
        selection. Sunlight rooms key to the *view name* so one room set
        applies across every timestep frame; daylight rooms stay keyed to the
        per-HDR stem (one HDR per view)."""
        if self.project_mode == "sunlight" and self.view_groups:
            vi = max(0, min(self.current_view_idx, len(self.view_groups) - 1))
            return self.view_groups[vi]["view_name"]
        if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files):
            return self.hdr_files[self.current_hdr_idx]["name"]
        return ""

    def _resolve_room_hdr_key(self, hdr_stem: str) -> str:
        """Map an HDR stem (e.g. seeded from an AOI lookup) to the key used on
        rooms. In sunlight mode, collapse the per-frame stem to its view name
        so the room applies to every timestep frame of that view."""
        if self.project_mode == "sunlight" and self.view_groups:
            for vg in self.view_groups:
                for frame in vg["frames"]:
                    if frame["hdr_stem"] == hdr_stem:
                        return vg["view_name"]
        return hdr_stem

    def _migrate_sunlight_room_keys(self) -> None:
        """Rewrite existing rooms so ``hdr_file`` holds the view name (level),
        not a per-frame HDR stem. Idempotent — rooms already keyed to view
        names are left alone."""
        if not self.view_groups:
            return
        stem_to_view = _stem_to_view_map(self.view_groups)
        view_names = {vg["view_name"] for vg in self.view_groups}
        changed = False
        new_rooms: list[RoomDict] = []
        for room in self.rooms:
            key = room.get("hdr_file", "")
            if key in view_names or not key:
                new_rooms.append(room)
                continue
            mapped = stem_to_view.get(key)
            if mapped and mapped != key:
                updated = dict(room)
                updated["hdr_file"] = mapped
                new_rooms.append(updated)  # type: ignore[arg-type]
                changed = True
            else:
                new_rooms.append(room)
        if changed:
            self.rooms = new_rooms

    def _goto_frame(self, view_idx: int, frame_idx: int) -> None:
        """Resolve (view_idx, frame_idx) into ``current_hdr_idx`` and refresh
        the displayed image. Invalidates DF caches the same way
        ``navigate_to_hdr`` does."""
        if not self.view_groups:
            return
        view_idx = max(0, min(view_idx, len(self.view_groups) - 1))
        frames = self.view_groups[view_idx]["frames"]
        if not frames:
            return
        frame_idx = max(0, min(frame_idx, len(frames) - 1))
        target_stem = frames[frame_idx]["hdr_stem"]
        for i, h in enumerate(self.hdr_files):
            if h["name"] == target_stem:
                self.current_hdr_idx = i
                break
        self.current_view_idx = view_idx
        self.current_frame_idx = frame_idx
        self._rebuild_variants()
        self.load_current_image()
        _df_cache["image"] = None
        _df_cache["hdr_path"] = ""
        if self.df_placement_mode:
            self._load_df_image_cache()
        self._restore_overlay_page_for_current_level()

    def navigate_to_view(self, view_idx: int):
        """Click handler for a sunlight view (level) header."""
        if not self.view_groups:
            return None
        if not (0 <= view_idx < len(self.view_groups)):
            return None
        # Toggle collapse to mirror existing navigate_to_hdr behaviour
        view_name = self.view_groups[view_idx]["view_name"]
        self.toggle_hdr_collapse(view_name)
        self._goto_frame(view_idx, 0)
        # Auto-play multi-frame views; stay paused on single-frame views
        frame_count = len(self.view_groups[view_idx]["frames"])
        self.frame_autoplay = frame_count > 1
        return EditorState.prefetch_level_window

    def navigate_level(self, direction: int):
        """Arrow-key / toolbar chevron handler — move between levels in sunlight,
        between HDRs in daylight. ``direction`` is +1 (next) or -1 (previous).

        Collapses all other levels/HDRs and expands the target, mirroring the
        daylight ``navigate_hdr`` behaviour."""
        if self.is_sunlight_mode:
            if not self.view_groups:
                return None
            new_idx = self.current_view_idx + direction
            if not (0 <= new_idx < len(self.view_groups)):
                return None
            target_name = self.view_groups[new_idx]["view_name"]
            self.collapsed_hdrs = [
                vg["view_name"] for vg in self.view_groups if vg["view_name"] != target_name
            ]
            self._goto_frame(new_idx, 0)
            frame_count = len(self.view_groups[new_idx]["frames"])
            self.frame_autoplay = frame_count > 1
        else:
            self.navigate_hdr(direction)
        return EditorState.prefetch_level_window

    def set_frame_idx(self, idx: int) -> None:
        """Scrub-slider handler. ``idx`` may arrive as str from the slider."""
        try:
            i = int(idx)
        except (TypeError, ValueError):
            return
        self._goto_frame(self.current_view_idx, i)

    def step_frame(self, delta: int) -> None:
        """Arrow-key handler — step one frame forward/back, wrapping."""
        if not self.view_groups:
            return
        frames = self.view_groups[self.current_view_idx]["frames"]
        if not frames:
            return
        new_idx = (self.current_frame_idx + delta) % len(frames)
        self._goto_frame(self.current_view_idx, new_idx)

    def advance_frame(self) -> None:
        """Autoplay tick — advance one frame with wrap-around."""
        if not self.frame_autoplay:
            return
        self.step_frame(1)

    def toggle_frame_autoplay(self) -> None:
        if not self.view_groups:
            return
        frames = self.view_groups[self.current_view_idx]["frames"]
        if len(frames) <= 1:
            self.frame_autoplay = False
            return
        self.frame_autoplay = not self.frame_autoplay

    def set_frame_fps(self, fps: int) -> None:
        try:
            v = int(fps)
        except (TypeError, ValueError):
            return
        self.frame_playback_fps = max(1, min(30, v))

    def navigate_to_hdr(self, hdr_idx: int):
        # Sunlight: tree rows carry the view_groups index in ``hdr_idx`` —
        # route to the view-level navigator so frame state stays coherent.
        if self.project_mode == "sunlight" and self.view_groups:
            self.navigate_to_view(hdr_idx)
            return EditorState.prefetch_level_window
        if 0 <= hdr_idx < len(self.hdr_files):
            old_hdr_idx = self.current_hdr_idx
            old_variant_idx = self.current_variant_idx
            hdr_name = self.hdr_files[hdr_idx]["name"]
            self.current_hdr_idx = hdr_idx
            self._rebuild_variants()
            self.load_current_image()
            # Invalidate DF cache; reload if placement mode is active
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            if self.df_placement_mode:
                self._load_df_image_cache()
            # Toggle collapse for the clicked HDR
            self.toggle_hdr_collapse(hdr_name)
            if old_hdr_idx != hdr_idx:
                self._push_undo({
                    "action": "hdr_navigate",
                    "desc": f"Navigate to {hdr_name}",
                    "before": {"hdr_idx": old_hdr_idx, "variant_idx": old_variant_idx},
                    "after": {"hdr_idx": hdr_idx, "variant_idx": self.current_variant_idx},
                })
            return EditorState.prefetch_level_window
        return None

    def select_all_rooms(self) -> None:
        if self.project_mode == "sunlight" and self.view_groups:
            if not (0 <= self.current_view_idx < len(self.view_groups)):
                return
            key = self.view_groups[self.current_view_idx]["view_name"]
        else:
            if not self.hdr_files:
                return
            key = self.hdr_files[self.current_hdr_idx]["name"]
        hdr_idxs = [i for i, r in enumerate(self.rooms) if r.get("hdr_file") == key]
        if set(hdr_idxs) == set(self.multi_selected_idxs):
            self.multi_selected_idxs = []
            self.selected_room_idx = -1
        else:
            self.multi_selected_idxs = hdr_idxs

    def set_room_name(self, value: str) -> None:
        self.room_name_input = value

    def set_room_type(self, rtype: str) -> None:
        self.room_type_input = rtype
        affected = list(self.multi_selected_idxs) if self.multi_selected_idxs else (
            [self.selected_room_idx] if 0 <= self.selected_room_idx < len(self.rooms) else []
        )
        affected = [i for i in affected if 0 <= i < len(self.rooms)]
        if not affected:
            return
        before_changes = [{"idx": i, "room_name": self.rooms[i].get("name", ""), "room_type": self.rooms[i].get("room_type", "NONE")} for i in affected]
        rooms_copy = list(self.rooms)
        for idx in affected:
            rooms_copy[idx] = {**rooms_copy[idx], "room_type": rtype}
        self.rooms = rooms_copy
        after_changes = [{"idx": i, "room_name": self.rooms[i].get("name", ""), "room_type": rtype} for i in affected]
        self._push_undo({
            "action": "room_type",
            "desc": f"Set room type to {rtype}",
            "before": {"changes": before_changes},
            "after": {"changes": after_changes},
        })
        self._auto_save()
        self._recompute_df()

    _ROOM_TYPE_CYCLE = ["NONE", "BED", "LIVING", "NON-RESI", "CIRC"]

    def cycle_room_type(self, room_idx: int) -> None:
        """Cycle the room type for a room (or all selected rooms in bulk)."""
        if not (0 <= room_idx < len(self.rooms)):
            return
        current = self.rooms[room_idx].get("room_type", "NONE") or "NONE"
        try:
            next_type = self._ROOM_TYPE_CYCLE[
                (self._ROOM_TYPE_CYCLE.index(current) + 1) % len(self._ROOM_TYPE_CYCLE)
            ]
        except ValueError:
            next_type = self._ROOM_TYPE_CYCLE[0]
        affected = list(self.multi_selected_idxs) if self.multi_selected_idxs else [room_idx]
        affected = [i for i in affected if 0 <= i < len(self.rooms)]
        before_changes = [{"idx": i, "room_name": self.rooms[i].get("name", ""), "room_type": self.rooms[i].get("room_type", "NONE")} for i in affected]
        rooms_copy = list(self.rooms)
        for idx in affected:
            rooms_copy[idx] = {**rooms_copy[idx], "room_type": next_type}
        self.rooms = rooms_copy
        after_changes = [{"idx": i, "room_name": self.rooms[i].get("name", ""), "room_type": next_type} for i in affected]
        self._push_undo({
            "action": "room_type",
            "desc": f"Cycle room type to {next_type}",
            "before": {"changes": before_changes},
            "after": {"changes": after_changes},
        })
        self.room_type_input = next_type
        self._auto_save()
        self._recompute_df()

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

    def _collect_children(self, indices: set[int]) -> set[int]:
        """Expand a set of room indices to include children of any parent rooms."""
        expanded = set(indices)
        for i in list(expanded):
            if 0 <= i < len(self.rooms) and not self.rooms[i].get("parent"):
                parent_name = self.rooms[i].get("name", "")
                if parent_name:
                    for j, r in enumerate(self.rooms):
                        if r.get("parent") == parent_name:
                            expanded.add(j)
        return expanded

    @debug_handler
    def delete_room(self) -> None:
        deleted_top_names: list[str] = []
        if self.multi_selected_idxs:
            to_delete = self._collect_children(set(self.multi_selected_idxs))
            undo_rooms = [
                {"idx": i, "data": dict(self.rooms[i])}
                for i in sorted(to_delete)
                if 0 <= i < len(self.rooms)
            ]
            deleted_top_names = [
                self.rooms[i].get("name", "")
                for i in to_delete
                if 0 <= i < len(self.rooms) and self.rooms[i].get("parent") is None
            ]
            self._push_undo({
                "action": "room_delete",
                "desc": f"Delete {len(undo_rooms)} room(s)",
                "before": {"rooms": undo_rooms},
                "after": {},
            })
            self.rooms = [r for i, r in enumerate(self.rooms) if i not in to_delete]
            self.multi_selected_idxs = []
            self.selected_room_idx = -1
        elif 0 <= self.selected_room_idx < len(self.rooms):
            to_delete = self._collect_children({self.selected_room_idx})
            undo_rooms = [
                {"idx": i, "data": dict(self.rooms[i])}
                for i in sorted(to_delete)
                if 0 <= i < len(self.rooms)
            ]
            deleted_top_names = [
                self.rooms[i].get("name", "")
                for i in to_delete
                if 0 <= i < len(self.rooms) and self.rooms[i].get("parent") is None
            ]
            room_name = self.rooms[self.selected_room_idx].get("name", "?")
            child_count = len(to_delete) - 1
            desc = f"Delete room {room_name}"
            if child_count > 0:
                desc += f" + {child_count} child room(s)"
            self._push_undo({
                "action": "room_delete",
                "desc": desc,
                "before": {"rooms": undo_rooms},
                "after": {},
            })
            self.rooms = [r for i, r in enumerate(self.rooms) if i not in to_delete]
            self.selected_room_idx = -1
        for name in deleted_top_names:
            self._delete_aoi_for_room(name)
        self.status_message = "Room deleted"
        self._auto_save()
        self._recompute_df()

    # =====================================================================
    # CANVAS — click routing, coordinate conversion, zoom/pan
    # =====================================================================

    @debug_handler
    def handle_canvas_click(self, data: dict) -> None:
        """Route canvas click. data: {x, y, button, shiftKey, ctrlKey, zoom, pan_x, pan_y[, viewport_x, viewport_y]} from JS."""
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        button = int(data.get("button", 0))
        shift = bool(data.get("shiftKey", False))
        ctrl = bool(data.get("ctrlKey", False))
        self.shift_held = shift
        viewport_x = float(data.get("viewport_x", x))
        viewport_y = float(data.get("viewport_y", y))

        # Sync zoom/pan from JS immediately — avoids stale zoom_level for
        # inverse-zoom stamp sizing (the debounced sync_zoom may lag).
        # No clamp: JS wheel handler already clamps at 1.0 for user scroll;
        # only programmatic Fit PDF sets sub-1.0, which must be preserved.
        if "zoom" in data:
            self.zoom_level = float(data["zoom"])
        if "pan_x" in data:
            self.pan_x = float(data["pan_x"])
        if "pan_y" in data:
            self.pan_y = float(data["pan_y"])

        self.mouse_x = x
        self.mouse_y = y

        btn_name = {0: "left", 1: "middle", 2: "right"}.get(button, str(button))
        logger.info(
            f"[DFDIAG] canvas_click at ({x:.1f}, {y:.1f}) btn={btn_name} "
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
            # Dismiss any open context menu on left-click
            if button != 2 and self.context_menu_visible:
                self.context_menu_visible = False
            if button == 2:
                logger.debug(f"  → normal: show_context_menu at canvas=({x:.1f},{y:.1f}) viewport=({viewport_x:.1f},{viewport_y:.1f})")
                self.show_context_menu(x, y, viewport_x, viewport_y)
            elif ctrl:
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
        self.shift_held = bool(data.get("shiftKey", False))

        # Overlay drag is handled entirely by the JS capture-phase listener in
        # viewport.py (stopImmediatePropagation prevents on_mouse_move firing).
        # sync_overlay_transform() is the canonical Python write path (called on drag end).
        # _overlay_dragging and _overlay_drag_start_* are retained for handle_mouse_down/up.

        if self.draw_mode and self.draw_vertices:
            self._update_draw_preview(x, y)
        elif self.divider_mode and self.divider_points:
            self._update_divider_preview(x, y)
        elif self.divider_mode and not self.divider_points:
            self._update_divider_snap(x, y)
        elif self.edit_mode and self.dragging_vertex_idx >= 0:
            logger.debug(f"mouse_move drag: vertex_idx={self.dragging_vertex_idx} → ({x:.1f}, {y:.1f})")
            self._drag_vertex(x, y)
        elif self.df_placement_mode:
            px, py = int(round(x)), int(round(y))
            df_val = None
            df_val_str = ""
            df_image = _df_cache["image"]
            if df_image is not None:
                from ..lib.df_analysis import read_df_at_pixel
                df_val = read_df_at_pixel(df_image, x, y)
                if df_val is not None:
                    df_val_str = f" {df_val:.2f}% DF"
            self.df_cursor_df = f"{df_val:.2f}% DF" if df_val is not None else ""
            self.df_cursor_label = f"px({px},{py}){df_val_str}"
            self.status_message = self.df_cursor_label

    @debug_handler
    def handle_mouse_down(self, data: dict) -> None:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        if self.overlay_align_mode and self.overlay_visible:
            t = self._get_current_overlay_transform()
            self._overlay_dragging = True
            self._overlay_drag_start_x = x
            self._overlay_drag_start_y = y
            self._overlay_drag_start_ox = float(t.get("offset_x", 0))
            self._overlay_drag_start_oy = float(t.get("offset_y", 0))
            return
        if not self.edit_mode:
            return
        self._editing_start_drag(x, y)

    @debug_handler
    def handle_mouse_up(self, data: dict) -> None:
        if self._overlay_dragging:
            self._overlay_dragging = False
            return
        if self.edit_mode:
            self.dragging_vertex_idx = -1

    def sync_zoom(self, data: dict) -> None:
        """Receive zoom/pan state from JS after a gesture ends (debounced).

        No 1.0 clamp — JS wheel handler already clamps user scroll at 1.0;
        only the programmatic Fit PDF path produces sub-1.0 zoom and that
        value must persist so the canvas transform binding stays in sync.
        """
        self.zoom_level = float(data.get("zoom", self.zoom_level))
        self.pan_x = float(data.get("pan_x", self.pan_x))
        self.pan_y = float(data.get("pan_y", self.pan_y))
        # Complete deferred legacy overlay migration now that viewport_width is known
        if self._legacy_overlay_pending and self.viewport_width > 0:
            self._migrate_legacy_overlay_transforms()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        yield rx.call_script("window._archiZoom && window._archiZoom.setTransform(1.0, 0, 0);")

    def fit_zoom(self):
        """Zoom/pan so the selected room's bounding rect maximally fills the viewport.

        Transform model: translate(pan_x, pan_y) scale(zoom), origin 0 0.
        The canvas (width:100%, height:auto) is CSS-centred vertically via
        margin:auto.  CSS transforms don't alter layout, so at any zoom the
        visible clip region is the viewport (vw × vh), not the zoom-1 canvas.

        Zoom is computed so the room bbox fills the constraining dimension
        (width or height) of the viewport edge-to-edge, with small proportional
        padding.  Pan centres the bbox midpoint in the viewport.
        """
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            yield from self.reset_zoom()
            return
        room = self.rooms[self.selected_room_idx]
        verts = self._room_pixel_vertices(room)
        if len(verts) < 3 or self.image_width <= 0:
            yield from self.reset_zoom()
            return

        min_x, min_y, max_x, max_y = polygon_bbox(verts)
        raw_w = max_x - min_x
        raw_h = max_y - min_y
        if raw_w <= 0 or raw_h <= 0:
            yield from self.reset_zoom()
            return

        # Proportional padding — 5% of each dimension, min 2px
        pad_x = max(raw_w * 0.05, 2.0)
        pad_y = max(raw_h * 0.05, 2.0)
        bw = raw_w + 2 * pad_x
        bh = raw_h + 2 * pad_y

        # Viewport dimensions (screen pixels)
        vw = self.viewport_width if self.viewport_width > 0 else self.image_width
        vh = self.viewport_height if self.viewport_height > 0 else self.image_height
        if vw <= 0 or vh <= 0:
            yield from self.reset_zoom()
            return

        # Fit-to-contain image scale — min(vw/iw, vh/ih) — aspect-agnostic.
        # For landscape images this collapses to vw/iw (the previous value).
        image_scale = min(vw / self.image_width, vh / self.image_height)

        # Zoom: maximise room in viewport.  Use vw and vh directly — the
        # viewport is the clip boundary at any zoom, not the zoom-1 canvas.
        zx = vw / (bw * image_scale)
        zy = vh / (bh * image_scale)
        self.zoom_level = min(zx, zy, 200.0)
        self.zoom_level = max(self.zoom_level, 1.0)

        # Centre room bbox midpoint in viewport, accounting for the fact that
        # the canvas is explicitly sized to iw*S × ih*S and centred in the
        # viewport flex container on both axes.
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        pxscale = image_scale * self.zoom_level
        canvas_w_at_1 = self.image_width * image_scale
        canvas_h_at_1 = self.image_height * image_scale
        canvas_offset_left = (vw - canvas_w_at_1) / 2
        canvas_offset_top = (vh - canvas_h_at_1) / 2
        self.pan_x = vw / 2 - canvas_offset_left - cx * pxscale
        self.pan_y = vh / 2 - canvas_offset_top - cy * pxscale

        yield rx.call_script(
            f"window._archiZoom && window._archiZoom.setTransform("
            f"{self.zoom_level}, {self.pan_x}, {self.pan_y});"
        )

    def fit_to_overlay(self):
        """Zoom/pan so the entire PDF underlay fills the viewport."""
        if not self.overlay_pdf_path or self.image_width <= 0 or self.overlay_img_width <= 0:
            yield from self.reset_zoom()
            return

        t = self._get_current_overlay_transform()
        iw = self.image_width
        ih = self.image_height or 1
        sx = t.get("scale_x", 1.0)
        sy = t.get("scale_y", 1.0)
        pdf_aspect = self.overlay_img_height / self.overlay_img_width

        # PDF bbox in SVG image-pixel coords (mirrors overlay_svg_transform).
        # The PDF <img> has width:100% (= iw at zoom-1) before its own CSS
        # scale is applied, so its native extent is iw × (iw * pdf_aspect).
        # The overlay_svg_transform translates then scales from top-left, so:
        #   top-left  = (ox, oy)
        #   bot-right = (ox + iw*sx, oy + iw*pdf_aspect*sy)
        cx_term = iw * (1.0 - sx) / 2.0
        cy_term = (ih - iw * pdf_aspect * sy) / 2.0
        ox = cx_term + t.get("offset_x", 0) * iw
        oy = cy_term + t.get("offset_y", 0) * ih
        pdf_w = iw * sx
        pdf_h = iw * pdf_aspect * sy

        # Combine HDR extent (0,0)→(iw,ih) with PDF extent to get full union bbox
        min_x = min(0.0, ox)
        min_y = min(0.0, oy)
        max_x = max(float(iw), ox + pdf_w)
        max_y = max(float(ih), oy + pdf_h)

        bbox_w = max_x - min_x
        bbox_h = max_y - min_y
        pad_x = max(bbox_w * 0.03, 2.0)
        pad_y = max(bbox_h * 0.03, 2.0)
        bw = bbox_w + 2 * pad_x
        bh = bbox_h + 2 * pad_y

        vw = self.viewport_width if self.viewport_width > 0 else iw
        vh = self.viewport_height if self.viewport_height > 0 else ih
        if vw <= 0 or vh <= 0:
            yield from self.reset_zoom()
            return

        # Fit-to-contain image scale — aspect-agnostic.
        image_scale = min(vw / iw, vh / ih)
        zx = vw / (bw * image_scale)
        zy = vh / (bh * image_scale)
        self.zoom_level = min(zx, zy, 200.0)
        self.zoom_level = max(self.zoom_level, 0.1)

        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        pxscale = image_scale * self.zoom_level
        canvas_w_at_1 = iw * image_scale
        canvas_h_at_1 = ih * image_scale
        canvas_offset_left = (vw - canvas_w_at_1) / 2
        canvas_offset_top = (vh - canvas_h_at_1) / 2
        self.pan_x = vw / 2 - canvas_offset_left - mid_x * pxscale
        self.pan_y = vh / 2 - canvas_offset_top - mid_y * pxscale

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
        from ..lib.geometry import (
            angular_snap_constrain,
            clamp_point_outside_polygon,
            ortho_closure_corner,
            point_in_polygon,
            snap_to_vertex,
        )

        # Close-polygon: snap to first vertex when ≥3 vertices placed
        if len(self.draw_vertices) >= 3:
            first = self.draw_vertices[0]
            if math.hypot(x - first["x"], y - first["y"]) < 15.0:
                # Insert intermediate ortho corner so all closing edges are 90°
                if self.ortho_mode:
                    last = self.draw_vertices[-1]
                    prev = self.draw_vertices[-2]
                    corner = ortho_closure_corner(
                        last["x"], last["y"], first["x"], first["y"], prev["x"], prev["y"],
                    )
                    if corner is not None:
                        self.draw_vertices = self.draw_vertices + [{"x": corner[0], "y": corner[1]}]
                self._save_new_room()
                return

        # Snap to existing room vertices
        all_verts = self._get_all_vertices_for_hdr()
        sx, sy, snapped = snap_to_vertex(x, y, all_verts, threshold=10.0)
        if snapped:
            x, y = sx, sy

        # Angular / ortho constraint (draw mode: 15° snap unless Shift held)
        if self.ortho_mode and self.draw_vertices and not self.shift_held:
            last = self.draw_vertices[-1]
            x, y = angular_snap_constrain(x, y, last["x"], last["y"])

        # Parent-room overlap prevention (only when drawing a new parent room)
        if not self.selected_parent:
            parent_polys = self._get_parent_room_polygons_for_hdr()
            if not self.draw_vertices:
                # First vertex: reject if inside existing parent room
                for poly in parent_polys:
                    if point_in_polygon(x, y, poly):
                        self.status_message = (
                            "Cannot draw inside an existing room — "
                            "use DD (room divider) to subdivide"
                        )
                        self.status_colour = "warning"
                        return
            else:
                # Subsequent vertices: clamp to boundary if inside a parent
                for poly in parent_polys:
                    x, y, _ = clamp_point_outside_polygon(x, y, poly)

        self.draw_vertices = self.draw_vertices + [{"x": x, "y": y}]
        self.snap_point = {}

    def _drawing_undo_vertex(self) -> None:
        if self.draw_vertices:
            self.draw_vertices = self.draw_vertices[:-1]

    def _update_draw_preview(self, x: float, y: float) -> None:
        from ..lib.geometry import angular_snap_constrain, clamp_point_outside_polygon, ortho_closure_corner, snap_to_vertex

        # Close-polygon snap: prioritise first vertex when ≥3 placed
        if len(self.draw_vertices) >= 3:
            first = self.draw_vertices[0]
            if math.hypot(x - first["x"], y - first["y"]) < 15.0:
                self.snap_point = {"x": first["x"], "y": first["y"]}
                if self.ortho_mode:
                    last = self.draw_vertices[-1]
                    prev = self.draw_vertices[-2]
                    corner = ortho_closure_corner(
                        last["x"], last["y"], first["x"], first["y"], prev["x"], prev["y"],
                    )
                    if corner is not None:
                        self.preview_point = {"x": corner[0], "y": corner[1]}
                        return
                self.preview_point = {"x": first["x"], "y": first["y"]}
                return

        # Normal snap to existing room vertices
        all_verts = self._get_all_vertices_for_hdr()
        sx, sy, snapped = snap_to_vertex(x, y, all_verts, threshold=10.0)
        if snapped:
            self.snap_point = {"x": sx, "y": sy}
            x, y = sx, sy
        else:
            self.snap_point = {}

        # Angular / ortho constraint (draw mode: 15° snap unless Shift held)
        if self.ortho_mode and self.draw_vertices and not self.shift_held:
            last = self.draw_vertices[-1]
            x, y = angular_snap_constrain(x, y, last["x"], last["y"])

        # Clamp preview outside parent rooms (when drawing a new parent)
        if not self.selected_parent and self.draw_vertices:
            parent_polys = self._get_parent_room_polygons_for_hdr()
            for poly in parent_polys:
                x, y, _ = clamp_point_outside_polygon(x, y, poly)

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

    # ---- Drawn-room .aoi writeback (sunlight only) -----------------------
    #
    # Contract: top-level rooms (``parent is None``) persist as v2 ``.aoi``
    # files in ``aoi_inputs_dir`` *and* in ``aoi_session.json``. Child rooms
    # (``parent`` set) persist in the session only. This matches the upload
    # path — seeded parent rooms come from ``.aoi`` files; children drawn on
    # top are session-only.
    def _aoi_inputs_dir_for_writeback(self) -> Optional[Path]:
        if self.project_mode != "sunlight" or not self.project:
            return None
        try:
            from archilume.config import get_project_paths
            return get_project_paths(self.project).aoi_inputs_dir
        except Exception:
            return None

    def _resolve_room_world_vertices(self, room: dict) -> Optional[list[list[float]]]:
        """Return the room's world vertices in metres, projecting from pixel
        vertices if necessary. Returns None when the HDR view params are
        unavailable."""
        world = room.get("world_vertices")
        if world:
            return [[float(x), float(y)] for x, y in world]
        pixel_verts = room.get("vertices") or []
        if len(pixel_verts) < 3:
            return None
        hdr_key = room.get("hdr_file", "")
        vp = self.hdr_view_params.get(hdr_key) if self.hdr_view_params else None
        if not vp or len(vp) < 6:
            return None
        return self._project_pixels_to_world(pixel_verts, vp[0], vp[1], vp[2], vp[3], vp[4], vp[5])

    def _resolve_room_ffl_m(self, room: dict) -> Optional[float]:
        """FFL in metres for a drawn room. Derived from the room's HDR name —
        ``plan_ffl_<mm>`` → ``mm / 1000``. Returns None when no HDR is bound."""
        import re
        if "ffl" in room:
            try:
                return float(room["ffl"])
            except (TypeError, ValueError):
                pass
        hdr_key = room.get("hdr_file", "") or ""
        m = re.search(r"plan_ffl_(-?\d+)", hdr_key)
        if not m:
            return None
        return int(m.group(1)) / 1000.0

    def _write_aoi_for_room(self, room: dict) -> None:
        """Write a v2 ``.aoi`` for a top-level sunlight room. No-op otherwise."""
        if room.get("parent") is not None:
            return
        dest_dir = self._aoi_inputs_dir_for_writeback()
        if dest_dir is None:
            return
        world = self._resolve_room_world_vertices(room)
        ffl = self._resolve_room_ffl_m(room)
        if world is None or ffl is None:
            logger.debug(
                "[aoi_writeback] skipping %r — world_vertices=%s ffl=%s",
                room.get("name"), world is not None, ffl,
            )
            return
        from ..lib import aoi_io
        try:
            aoi_io.write_v2_aoi(dest_dir, room.get("name", ""), ffl, world)
        except Exception as e:
            logger.warning("[aoi_writeback] write failed for %r: %s", room.get("name"), e)

    def _delete_aoi_for_room(self, name: str) -> None:
        dest_dir = self._aoi_inputs_dir_for_writeback()
        if dest_dir is None or not name:
            return
        from ..lib import aoi_io
        try:
            aoi_io.delete_aoi(dest_dir, name)
        except Exception as e:
            logger.warning("[aoi_writeback] delete failed for %r: %s", name, e)

    def _rename_aoi_for_room(self, old_name: str, new_name: str) -> None:
        dest_dir = self._aoi_inputs_dir_for_writeback()
        if dest_dir is None or not old_name or not new_name or old_name == new_name:
            return
        from ..lib import aoi_io
        try:
            aoi_io.rename_aoi(dest_dir, old_name, new_name)
        except Exception as e:
            logger.warning("[aoi_writeback] rename failed %r -> %r: %s", old_name, new_name, e)

    def _save_new_room(self) -> None:
        from ..lib.geometry import make_unique_name, next_room_number, point_in_polygon, polygons_overlap
        vertices = [[v["x"], v["y"]] for v in self.draw_vertices]
        name = self.room_name_input.strip()
        if not name:
            existing_names_list = [r.get("name", "") for r in self.rooms]
            next_num = next_room_number(existing_names_list)
            name = f"ROOM_{next_num:03d}"
        existing_names = [r.get("name", "") for r in self.rooms]
        full_name = make_unique_name(name, existing_names)

        hdr_name = ""
        if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files):
            hdr_name = self.hdr_files[self.current_hdr_idx]["name"]

        # Overlap validation: new parent room must not overlap existing parents
        if not self.selected_parent:
            parent_polys = self._get_parent_room_polygons_for_hdr()
            for poly in parent_polys:
                if polygons_overlap(vertices, poly):
                    self.status_message = (
                        "Room overlaps an existing room — "
                        "adjust vertices or use DD to subdivide"
                    )
                    self.status_colour = "warning"
                    return

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
            "hdr_file": self._current_room_hdr_key() or hdr_name,
            "room_type": self.room_type_input or "NONE",
            "visible": True,
        }
        self.rooms = self.rooms + [new_room]
        self._write_aoi_for_room(new_room)
        self.draw_vertices = []
        self.snap_point = {}
        self.preview_point = {}
        self.room_name_input = ""
        self.status_message = f"Saved room: {full_name}"
        self.status_colour = "accent"
        self._auto_save()
        self._recompute_df()

    def _save_edited_room(self) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        rooms_copy = list(self.rooms)
        room = dict(rooms_copy[self.selected_room_idx])
        old_name = room.get("name", "") or ""
        old_parent = room.get("parent")
        if self.room_name_input.strip():
            room["name"] = self.room_name_input.strip()
        room["room_type"] = self.room_type_input
        room["parent"] = self.selected_parent or None
        rooms_copy[self.selected_room_idx] = room
        self.rooms = rooms_copy
        new_name = room.get("name", "") or ""
        new_parent = room.get("parent")
        was_top = old_parent is None
        is_top = new_parent is None
        if was_top and is_top:
            if old_name != new_name:
                self._rename_aoi_for_room(old_name, new_name)
            self._write_aoi_for_room(room)
        elif was_top and not is_top:
            self._delete_aoi_for_room(old_name)
        elif not was_top and is_top:
            self._write_aoi_for_room(room)
        self.status_message = f"Updated: {room['name']}"
        self._auto_save()
        self._recompute_df()

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

    def _get_parent_room_polygons_for_hdr(self) -> list[list[list[float]]]:
        """Get vertex lists of all parent rooms (no parent) for current HDR."""
        if not self.hdr_files:
            return []
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        result: list[list[list[float]]] = []
        for room in self.rooms:
            if room.get("hdr_file") == hdr_name and not room.get("parent"):
                verts = room.get("vertices", [])
                if len(verts) >= 3:
                    result.append(verts)
        return result

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

    # ------------------------------------------------------------------
    # Unified undo/redo infrastructure
    # ------------------------------------------------------------------

    def _push_undo(self, entry: dict) -> None:
        """Push an undo entry onto the unified stack; clear redo stack."""
        now = time.time()
        # Coalesce rapid same-type entries (hdr_navigate)
        if (
            self._undo_stack
            and entry["action"] in ("hdr_navigate",)
            and self._undo_stack[-1]["action"] == entry["action"]
            and now - self._last_undo_push_time < 0.5
        ):
            top = dict(self._undo_stack[-1])
            top["after"] = entry["after"]
            self._undo_stack = self._undo_stack[:-1] + [top]
        else:
            self._undo_stack = (self._undo_stack + [entry])[-self._UNDO_MAX:]
        self._redo_stack = []
        self._last_undo_push_time = now

    def _push_overlay_undo(self, entry: dict) -> None:
        """Push to the overlay-scoped undo stack (only used in overlay_align_mode)."""
        now = time.time()
        if (
            self._overlay_undo_stack
            and self._overlay_undo_stack[-1]["action"] == entry["action"]
            and now - self._last_undo_push_time < 0.5
        ):
            top = dict(self._overlay_undo_stack[-1])
            top["after"] = entry["after"]
            self._overlay_undo_stack = self._overlay_undo_stack[:-1] + [top]
        else:
            self._overlay_undo_stack = (self._overlay_undo_stack + [entry])[-self._UNDO_MAX:]
        self._last_undo_push_time = now

    def _push_edit_undo(self) -> None:
        if self.selected_room_idx < 0 or self.selected_room_idx >= len(self.rooms):
            return
        self._finalize_vertex_edit_undo()
        room = self.rooms[self.selected_room_idx]
        self._push_undo({
            "action": "vertex_edit",
            "desc": f"Edit vertices of {room.get('name', '?')}",
            "before": {
                "room_idx": self.selected_room_idx,
                "room_name": room.get("name", ""),
                "vertices": [list(v) for v in room.get("vertices", [])],
            },
            "after": {},
        })

    def _finalize_vertex_edit_undo(self) -> None:
        """Fill in the ``after`` vertices for the most recent vertex_edit entry if empty."""
        if not self._undo_stack:
            return
        top = self._undo_stack[-1]
        if top["action"] == "vertex_edit" and not top.get("after"):
            room_name = top["before"].get("room_name", "")
            idx = top["before"]["room_idx"]
            if room_name:
                idx = next((i for i, r in enumerate(self.rooms) if r.get("name") == room_name), idx)
            if 0 <= idx < len(self.rooms):
                updated_top = dict(top)
                updated_top["after"] = {
                    "room_idx": idx,
                    "room_name": room_name,
                    "vertices": [list(v) for v in self.rooms[idx].get("vertices", [])],
                }
                self._undo_stack = self._undo_stack[:-1] + [updated_top]

    def undo(self) -> None:
        # Overlay-align mode: use scoped overlay stack
        if self.overlay_align_mode:
            self._undo_overlay()
            return
        self._finalize_vertex_edit_undo()
        if not self._undo_stack:
            self.status_message = "Nothing to undo"
            return
        entry = self._undo_stack[-1]
        self._undo_stack = self._undo_stack[:-1]
        self._apply_undo(entry)
        self._redo_stack = (self._redo_stack + [entry])[-self._UNDO_MAX:]
        self._auto_save()
        self._recompute_df()

    def redo(self) -> None:
        # Overlay-align mode: no redo for overlay (keep it simple)
        if self.overlay_align_mode:
            self.status_message = "Redo not available in adjust-plan mode"
            return
        if not self._redo_stack:
            self.status_message = "Nothing to redo"
            return
        entry = self._redo_stack[-1]
        self._redo_stack = self._redo_stack[:-1]
        self._apply_redo(entry)
        self._undo_stack = (self._undo_stack + [entry])[-self._UNDO_MAX:]
        self._auto_save()
        self._recompute_df()

    def _apply_undo(self, entry: dict) -> None:
        action = entry["action"]
        before = entry.get("before", {})
        after = entry.get("after", {})
        if action == "vertex_edit":
            self._restore_vertices(before)
            self.status_message = "Vertex edit undone"
        elif action == "room_delete":
            self._undo_room_delete(before)
        elif action == "room_divide":
            self._restore_rooms_snapshot(before)
            self.status_message = "Division undone"
            self.status_colour = "accent2"
        elif action == "room_type":
            self._restore_room_types(before)
            self.status_message = "Room type change undone"
        elif action == "df_stamp_add":
            self._remove_df_stamp(after)
            self.status_message = "DF stamp undone"
        elif action == "df_stamp_remove":
            self._insert_df_stamp(before)
            self.status_message = "DF stamp removal undone"
        elif action == "hdr_navigate":
            self._apply_hdr_navigate(before)

    def _apply_redo(self, entry: dict) -> None:
        action = entry["action"]
        before = entry.get("before", {})
        after = entry.get("after", {})
        if action == "vertex_edit":
            self._restore_vertices(after)
            self.status_message = "Vertex edit redone"
        elif action == "room_delete":
            self._redo_room_delete(before)
        elif action == "room_divide":
            self._restore_rooms_snapshot(after)
            self.status_message = "Division redone"
        elif action == "room_type":
            self._restore_room_types(after)
            self.status_message = "Room type change redone"
        elif action == "df_stamp_add":
            self._insert_df_stamp(after)
            self.status_message = "DF stamp redone"
        elif action == "df_stamp_remove":
            self._remove_df_stamp(before)
            self.status_message = "DF stamp removal redone"
        elif action == "hdr_navigate":
            self._apply_hdr_navigate(after)

    # -- Individual restore handlers --

    def _restore_vertices(self, data: dict) -> None:
        room_name = data.get("room_name", "")
        idx = data.get("room_idx", -1)
        if room_name:
            idx = next((i for i, r in enumerate(self.rooms) if r.get("name") == room_name), idx)
        if 0 <= idx < len(self.rooms):
            rooms_copy = list(self.rooms)
            rooms_copy[idx] = {**rooms_copy[idx], "vertices": data["vertices"]}
            self.rooms = rooms_copy

    def _undo_room_delete(self, before: dict) -> None:
        rooms_copy = list(self.rooms)
        for room_info in before.get("rooms", []):
            idx = room_info["idx"]
            data = room_info["data"]
            rooms_copy.insert(min(idx, len(rooms_copy)), data)
        self.rooms = rooms_copy
        self.selected_room_idx = -1
        self.status_message = "Room deletion undone"

    def _redo_room_delete(self, before: dict) -> None:
        indices = sorted([r["idx"] for r in before.get("rooms", [])], reverse=True)
        rooms_copy = list(self.rooms)
        for idx in indices:
            if 0 <= idx < len(rooms_copy):
                del rooms_copy[idx]
        self.rooms = rooms_copy
        self.selected_room_idx = -1
        self.status_message = "Room deletion redone"

    def _restore_rooms_snapshot(self, data: dict) -> None:
        self.rooms = data["rooms_snapshot"]
        self.selected_room_idx = -1

    def _restore_room_types(self, data: dict) -> None:
        rooms_copy = list(self.rooms)
        for change in data.get("changes", []):
            room_name = change.get("room_name", "")
            idx = change["idx"]
            if room_name:
                idx = next((i for i, r in enumerate(self.rooms) if r.get("name") == room_name), idx)
            if 0 <= idx < len(rooms_copy):
                rooms_copy[idx] = {**rooms_copy[idx], "room_type": change["room_type"]}
        self.rooms = rooms_copy

    def _remove_df_stamp(self, data: dict) -> None:
        hdr = data["hdr_name"]
        idx = data["stamp_idx"]
        stamps = dict(self.df_stamps)
        hdr_stamps = list(stamps.get(hdr, []))
        if 0 <= idx < len(hdr_stamps):
            del hdr_stamps[idx]
        stamps[hdr] = hdr_stamps
        self.df_stamps = stamps

    def _insert_df_stamp(self, data: dict) -> None:
        hdr = data["hdr_name"]
        idx = data["stamp_idx"]
        stamp = data["stamp"]
        stamps = dict(self.df_stamps)
        hdr_stamps = list(stamps.get(hdr, []))
        hdr_stamps.insert(min(idx, len(hdr_stamps)), stamp)
        stamps[hdr] = hdr_stamps
        self.df_stamps = stamps

    def _apply_hdr_navigate(self, data: dict) -> None:
        idx = data["hdr_idx"]
        if 0 <= idx < len(self.hdr_files):
            self.current_hdr_idx = idx
            self.current_variant_idx = data.get("variant_idx", 0)
            self._rebuild_variants()
            self.load_current_image()
            hdr_name = self.hdr_files[idx]["name"]
            self.collapsed_hdrs = [h["name"] for h in self.hdr_files if h["name"] != hdr_name]
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            if self.df_placement_mode:
                self._load_df_image_cache()
            self._recompute_df()
            self.status_message = f"Navigated to {hdr_name}"

    def _undo_overlay(self) -> None:
        """Undo within overlay-align mode (scoped stack)."""
        if not self._overlay_undo_stack:
            # Restore session start baseline
            if self._overlay_session_start:
                key = self._overlay_session_start.get("level_key", "")
                transform = self._overlay_session_start.get("transform")
                if key:
                    t = dict(self.overlay_transforms)
                    if transform is None:
                        t.pop(key, None)
                    else:
                        t[key] = transform
                    self.overlay_transforms = t
                    self._auto_save()
                self.status_message = "Overlay restored to session start"
            else:
                self.status_message = "Nothing to undo"
            return
        entry = self._overlay_undo_stack[-1]
        self._overlay_undo_stack = self._overlay_undo_stack[:-1]
        before = entry.get("before", {})
        key = before.get("level_key", "")
        transform = before.get("transform")
        if key:
            t = dict(self.overlay_transforms)
            if transform is None:
                t.pop(key, None)
            else:
                t[key] = transform
            self.overlay_transforms = t
        # Handle overlay props restore
        if "dpi" in before:
            dpi_changed = self.overlay_dpi != before.get("dpi", self.overlay_dpi)
            page_changed = self.overlay_page_idx != before.get("page_idx", self.overlay_page_idx)
            self.overlay_dpi = before.get("dpi", self.overlay_dpi)
            self.overlay_alpha = before.get("alpha", self.overlay_alpha)
            self.overlay_page_idx = before.get("page_idx", self.overlay_page_idx)
            # Sync the restored page_idx back into the per-level transform so that
            # navigating away and returning restores the correct (undone) page.
            if page_changed:
                level_key = self._current_level_key()
                if level_key and level_key in self.overlay_transforms:
                    t = dict(self.overlay_transforms)
                    entry_t = dict(t[level_key])
                    entry_t["page_idx"] = self.overlay_page_idx
                    t[level_key] = entry_t
                    self.overlay_transforms = t
            if dpi_changed or page_changed:
                self._rasterize_current_page()
        self._auto_save()
        self.status_message = "Overlay change undone"

    # =====================================================================
    # DIVIDER
    # =====================================================================

    def _room_pixel_vertices(self, room: dict) -> list[list[float]]:
        """Return room vertices in current-HDR pixel space.

        Mirrors the reprojection logic in `enriched_rooms`: when ``world_vertices``
        and view params exist, reproject to pixel coords; otherwise fall back to the
        stored ``vertices`` list. Without this, the divider overlay uses stale
        coords and renders offset from the polygon boundary.
        """
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return room.get("vertices", [])
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        img_w = self.image_width
        img_h = self.image_height
        vp_params = self.hdr_view_params.get(hdr_name)
        world_verts = room.get("world_vertices", [])
        if vp_params and len(world_verts) >= 3 and img_w > 0 and img_h > 0:
            vp_x, vp_y, vh, vv, *_rest = vp_params
            return [
                [(wx - vp_x) / (vh / img_w) + img_w / 2,
                 img_h / 2 - (wy - vp_y) / (vv / img_h)]
                for wx, wy in world_verts
            ]
        return room.get("vertices", [])

    def _get_divider_room_vertices(self) -> list[list[float]]:
        """Return pixel-space vertices of the room being divided (current HDR)."""
        idx = self.divider_room_idx
        if 0 <= idx < len(self.rooms):
            return self._room_pixel_vertices(self.rooms[idx])
        return []

    def _update_divider_snap(self, x: float, y: float) -> None:
        """Update snap highlight when hovering near a room boundary vertex (first point only)."""
        from ..lib.geometry import snap_to_vertex
        room_verts = self._get_divider_room_vertices()
        sx, sy, snapped = snap_to_vertex(x, y, room_verts, threshold=12.0)
        if snapped:
            self.snap_point = {"x": sx, "y": sy}
        else:
            self.snap_point = {}

    def _update_divider_preview(self, x: float, y: float) -> None:
        """Preview line from last placed divider point to cursor. Honours ortho mode."""
        from ..lib.geometry import ortho_constrain
        if not self.divider_points:
            self.divider_preview_point = {}
            return
        last = self.divider_points[-1]
        if self.ortho_mode:
            x, y = ortho_constrain(x, y, last["x"], last["y"])
        self.divider_preview_point = {"x": x, "y": y}

    def _divider_add_point(self, x: float, y: float) -> None:
        from ..lib.geometry import (
            nearest_point_on_edge,
            ortho_constrain,
            point_in_polygon,
            snap_to_vertex,
        )
        if self.selected_room_idx < 0:
            self.status_message = "Select a room first"
            return
        if self.divider_room_idx < 0:
            self.divider_room_idx = self.selected_room_idx
            self.divider_room_name = self.rooms[self.selected_room_idx].get("name", "") if 0 <= self.selected_room_idx < len(self.rooms) else ""
        # Snap to room boundary vertices on first point (no ortho constraint yet)
        if not self.divider_points:
            room_verts = self._get_divider_room_vertices()
            sx, sy, snapped = snap_to_vertex(x, y, room_verts, threshold=12.0)
            if snapped:
                x, y = sx, sy
        elif self.ortho_mode:
            last = self.divider_points[-1]
            x, y = ortho_constrain(x, y, last["x"], last["y"])

        # Clamp clicks outside the parent onto the nearest edge; auto-finalize
        # on the 2nd-or-later point so the division stays fully inside the parent.
        parent_verts = self._get_divider_room_vertices()
        if parent_verts and not point_in_polygon(x, y, parent_verts):
            best: tuple[float, float, float] | None = None
            n = len(parent_verts)
            for i in range(n):
                x1, y1 = parent_verts[i]
                x2, y2 = parent_verts[(i + 1) % n]
                nx, ny, d = nearest_point_on_edge(x, y, x1, y1, x2, y2)
                if best is None or d < best[2]:
                    best = (nx, ny, d)
            if best is not None:
                x, y = best[0], best[1]
                self.divider_points = self.divider_points + [{"x": x, "y": y}]
                self.snap_point = {}
                self.divider_preview_point = {}
                if len(self.divider_points) >= 2:
                    self._finalize_divider()
                return

        self.divider_points = self.divider_points + [{"x": x, "y": y}]
        self.snap_point = {}
        self.divider_preview_point = {}

    def _divider_undo_point(self) -> None:
        if self.divider_points:
            self.divider_points = self.divider_points[:-1]

    @staticmethod
    def _poly_area(verts: list) -> float:
        """Shoelace formula — returns absolute area of a polygon."""
        n = len(verts)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            x1, y1 = verts[i][0], verts[i][1]
            x2, y2 = verts[(i + 1) % n][0], verts[(i + 1) % n][1]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def _finalize_divider(self) -> None:
        if len(self.divider_points) < 2 or self.divider_room_idx < 0:
            self.status_message = "Need at least 2 divider points"
            return
        # Re-resolve index by name in case undo/delete shifted the rooms list
        if self.divider_room_name:
            resolved = next((i for i, r in enumerate(self.rooms) if r.get("name") == self.divider_room_name), self.divider_room_idx)
            self.divider_room_idx = resolved
        if self.divider_room_idx >= len(self.rooms):
            return
        from ..lib.geometry import make_unique_name, ray_polygon_intersection, split_polygon_by_polyline
        room = self.rooms[self.divider_room_idx]
        # Work in current-HDR pixel space so the divider polyline (from click coords)
        # matches the polygon. Saved child gets both pixel vertices and world_vertices
        # so render reprojection stays consistent across HDR switches.
        polygon = self._room_pixel_vertices(room)
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
            self.divider_preview_point = {}
            return

        # Snapshot rooms before mutation for undo
        snapshot_before = [dict(r, vertices=[list(v) for v in r["vertices"]]) for r in self.rooms]

        # Parent room stays intact — only the smaller polygon becomes a CIRC child.
        # Deleting the child leaves the parent's full boundary / area unchanged.
        area_a = self._poly_area(poly_a)
        area_b = self._poly_area(poly_b)
        child_poly_px = poly_a if area_a <= area_b else poly_b

        # Reverse-project pixel-space child polygon back to world coords so it
        # reprojects correctly when the HDR view changes.
        hdr_name = room.get("hdr_file", "")
        vp_params = self.hdr_view_params.get(hdr_name)
        img_w = self.image_width
        img_h = self.image_height
        child_poly_world: list[list[float]] = []
        if vp_params and img_w > 0 and img_h > 0:
            vp_x, vp_y, vh, vv, *_rest = vp_params
            for px, py in child_poly_px:
                wx = (px - img_w / 2) * (vh / img_w) + vp_x
                wy = (img_h / 2 - py) * (vv / img_h) + vp_y
                child_poly_world.append([wx, wy])

        # Re-project child world coords to HDR-native pixel space so stored
        # vertices are consistent with parent rooms (which use vp[4]/vp[5]).
        # child_poly_px may be in display-pixel space when viewing a non-HDR
        # variant; this ensures the DF mask subtraction always aligns.
        if child_poly_world and vp_params and len(vp_params) >= 6:
            _native_w, _native_h = vp_params[4], vp_params[5]
            if _native_w > 0 and _native_h > 0:
                child_poly_px = [
                    [(wx - vp_x) / (vh / _native_w) + _native_w / 2,
                     _native_h / 2 - (wy - vp_y) / (vv / _native_h)]
                    for wx, wy in child_poly_world
                ]

        # Parent chain: child references original room name (or its parent if nested)
        original_name = room.get("name", "ROOM")
        original_parent = room.get("parent")
        division_parent = original_name if not original_parent else original_parent

        existing_names = [r.get("name", "") for r in self.rooms]
        child_name = make_unique_name(f"{original_name}_DIV", existing_names)
        child_room: dict = {
            "name": child_name,
            "parent": division_parent,
            "vertices": child_poly_px,
            "hdr_file": self._current_room_hdr_key() or hdr_name,
            "room_type": "CIRC",
            "visible": True,
        }
        if child_poly_world:
            child_room["world_vertices"] = child_poly_world
        rooms_copy = list(self.rooms)
        rooms_copy.insert(self.divider_room_idx + 1, child_room)
        self.rooms = rooms_copy
        snapshot_after = [dict(r, vertices=[list(v) for v in r["vertices"]]) for r in self.rooms]
        self._push_undo({
            "action": "room_divide",
            "desc": f"Divide room {original_name}",
            "before": {"rooms_snapshot": snapshot_before},
            "after": {"rooms_snapshot": snapshot_after},
        })
        self.divider_points = []
        self.divider_preview_point = {}
        self.divider_room_idx = -1
        self._clear_modes()
        self.status_message = f"Inserted CIRC child {child_name} inside {original_name}"
        self.status_colour = "accent"
        self._auto_save()
        self._recompute_df()

    # =====================================================================
    # CONTEXT MENU
    # =====================================================================

    @rx.var
    def context_menu_x_px(self) -> str:
        return f"{int(self.context_menu_x)}px"

    @rx.var
    def context_menu_y_px(self) -> str:
        return f"{int(self.context_menu_y)}px"

    def show_context_menu(self, canvas_x: float, canvas_y: float, viewport_x: float, viewport_y: float) -> None:
        """Show context menu at viewport position, performing a room hit-test at canvas position."""
        from ..lib.geometry import point_in_polygon
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"] if self.hdr_files else ""
        hit_idx = -1
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file", "") != hdr_name:
                continue
            verts = room.get("vertices", [])
            if len(verts) >= 3 and point_in_polygon(canvas_x, canvas_y, verts):
                hit_idx = i
                break
        if hit_idx >= 0:
            self.context_menu_room_idx = hit_idx
            self.context_menu_x = viewport_x
            self.context_menu_y = viewport_y
            self.context_menu_canvas_x = canvas_x
            self.context_menu_canvas_y = canvas_y
            self.context_menu_visible = True
            # Also select the room
            self.select_room(hit_idx)
        else:
            # No room hit — show reinstate-from-AOI option
            self.context_menu_room_idx = -1
            self.context_menu_x = viewport_x
            self.context_menu_y = viewport_y
            self.context_menu_canvas_x = canvas_x
            self.context_menu_canvas_y = canvas_y
            self.context_menu_visible = True

    @rx.var
    def context_menu_has_room(self) -> bool:
        """True when the context menu targets an existing room (show Delete);
        False when targeting empty space (show Reinstate from AOI)."""
        return self.context_menu_room_idx >= 0

    def dismiss_context_menu(self) -> None:
        self.context_menu_visible = False

    def context_menu_delete(self) -> None:
        """Delete the room targeted by the context menu."""
        if self.context_menu_room_idx >= 0:
            self.selected_room_idx = self.context_menu_room_idx
            self.multi_selected_idxs = []
        self.context_menu_visible = False
        self.delete_room()

    @staticmethod
    def _parse_level_aoi(path: Path) -> tuple[str, str, list[list[float]]] | None:
        """Parse a level-suffixed AOI file (e.g. L200002B_L2.aoi).

        Returns (zone_name, ffl_string, world_vertices) or None on failure.
        """
        import re
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None
        if len(lines) < 6:
            return None
        # Line 1: "AOI Points File: L200002B L2"
        m_zone = re.match(r"AOI Points File:\s*(\S+)", lines[0])
        if not m_zone:
            return None
        zone_name = m_zone.group(1)
        # Line 2: "ASSOCIATED VIEW FILE: plan_ffl_14300.vp"
        m_view = re.search(r"plan_ffl_(\d+)", lines[1])
        if not m_view:
            return None
        ffl_str = m_view.group(1)
        # Line 5: "NO. PERIMETER POINTS N: ..."
        m_pts = re.search(r"POINTS\s+(\d+)", lines[4])
        if not m_pts:
            return None
        n_pts = int(m_pts.group(1))
        if len(lines) < 5 + n_pts:
            return None
        verts: list[list[float]] = []
        for line in lines[5 : 5 + n_pts]:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    verts.append([float(parts[0]), float(parts[1])])
                except ValueError:
                    return None
        if len(verts) < 3:
            return None
        return (zone_name, ffl_str, verts)


    @staticmethod
    def _parse_base_aoi(path: Path) -> tuple[str, str, list[list[float]]] | None:
        """Parse a base-format AOI file. Returns (zone_name, level_code, world_vertices)."""
        import re
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return None
        if len(lines) < 4:
            return None
        m_zone = re.match(r"ZONE\s+(\S+)\s+(\S+)", lines[1])
        if not m_zone:
            return None
        zone_name, level_code = m_zone.group(1), m_zone.group(2)
        m_pts = re.search(r"POINTS\s+(\d+)", lines[2])
        if not m_pts:
            return None
        n_pts = int(m_pts.group(1))
        if len(lines) < 3 + n_pts:
            return None
        verts: list[list[float]] = []
        for line in lines[3 : 3 + n_pts]:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    verts.append([float(parts[0]), float(parts[1])])
                except ValueError:
                    return None
        if len(verts) < 3:
            return None
        return (zone_name, level_code, verts)

    @staticmethod
    def _build_level_ffl_map(aoi_inputs_dir: Path) -> dict[str, str]:
        """Build level_code->ffl_string map from outputs/aoi/ _L*.aoi files."""
        import re
        outputs_aoi = aoi_inputs_dir.parent.parent / "outputs" / "aoi"
        level_map: dict[str, str] = {}
        if not outputs_aoi.exists():
            return level_map
        for p in outputs_aoi.glob("*_L*.aoi"):
            try:
                top_lines = p.read_text(encoding="utf-8").splitlines()[:2]
            except Exception:
                continue
            if len(top_lines) < 2:
                continue
            m_view = re.search(r"plan_ffl_(\d+)", top_lines[1])
            if not m_view:
                continue
            m_level = re.search(r"_([Ll]\d+)\.aoi$", p.name)
            if m_level:
                level_map[m_level.group(1).upper()] = m_view.group(1)
        return level_map

    @staticmethod
    def _project_world_to_pixels(
        world_verts: list[list[float]],
        vp_x: float, vp_y: float, vh: float, vv: float,
        img_w: float, img_h: float,
    ) -> list[list[float]]:
        """World (metres) -> pixel coords via Radiance -vtl inverse projection."""
        return [
            [(wx - vp_x) / (vh / img_w) + img_w / 2,
             img_h / 2 - (wy - vp_y) / (vv / img_h)]
            for wx, wy in world_verts
        ]

    @staticmethod
    def _project_pixels_to_world(
        pixel_verts: list[list[float]],
        vp_x: float, vp_y: float, vh: float, vv: float,
        img_w: float, img_h: float,
    ) -> list[list[float]]:
        """Pixel coords -> world (metres). Inverse of :meth:`_project_world_to_pixels`."""
        return [
            [(px - img_w / 2) * (vh / img_w) + vp_x,
             vp_y - (py - img_h / 2) * (vv / img_h)]
            for px, py in pixel_verts
        ]

    def _seed_rooms_from_modern_aoi(self, aoi_dir: Path) -> int:
        """Seed ``self.rooms`` from modern ``.aoi`` files.

        Supports three header variants:

        * **v2 minimal** — ``AoI Points File : X,Y positions`` / ``FFL z height(m):`` /
          ``POINTS N`` / world-only ``x y`` rows. Filestem is the room name;
          parent is always ``None`` (child relationships live only in
          ``aoi_session.json``). Pixels are projected client-side via the
          HDR's view params, matched by FFL.
        * **v1 input** — ``PARENT:`` / ``CHILD:`` / ``FFL z height(m):`` /
          ``CENTRAL x,y:`` / ``NO. PERIMETER POINTS N:`` with world-only rows.
          Kept for read-only back-compat with pre-migration projects.
        * **v1 processed** — ``ASSOCIATED VIEW FILE:`` on line[1] with
          ``x y pixel_x pixel_y`` data rows (produced by
          ``ViewGenerator.create_aoi_files(coordinate_map)``).
        """
        import re
        seeded = 0

        # Built once: ffl_mm -> (hdr_entry, vp) — used to map an .aoi FFL to
        # its matching HDR so the stored pixel verts line up with the HDR the
        # room will render over.
        ffl_mm_to_entry: dict[int, tuple[dict, list[float]]] = {}
        for entry in self.hdr_files:
            m = re.search(r"plan_ffl_(\d+)", entry["name"])
            vp = self.hdr_view_params.get(entry["name"]) if self.hdr_view_params else None
            if m and vp and len(vp) >= 6:
                ffl_mm_to_entry.setdefault(int(m.group(1)), (entry, vp))

        for aoi_path in sorted(aoi_dir.glob("*.aoi")):
            if aoi_path.stem == "aoi_session":
                continue
            try:
                lines = [l.strip() for l in aoi_path.read_text(encoding="utf-8").splitlines()]
            except Exception:
                continue
            if len(lines) < 4:
                continue
            if not re.match(r"AO?I Points File\s*:", lines[0], re.IGNORECASE):
                continue

            # ---- Detect format + locate data-start sentinel ----
            ffl: float | None = None
            vertex_start: int | None = None
            is_v1_processed = False
            for i, ln in enumerate(lines):
                upper = ln.upper()
                if ln.startswith("FFL z height(m):"):
                    try:
                        ffl = float(ln.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif upper.startswith("ASSOCIATED VIEW FILE:"):
                    is_v1_processed = True
                elif upper.startswith("POINTS ") or upper.startswith("NO. PERIMETER POINTS"):
                    vertex_start = i + 1
                    break
            if ffl is None or vertex_start is None:
                continue

            # ---- v1 processed: world + pixel columns in data rows ----
            if is_v1_processed:
                m_view = re.search(r"plan_ffl_(\d+)", lines[1])
                if not m_view:
                    continue
                ffl_pat = re.compile(r"plan_ffl_" + m_view.group(1) + r"(?!\d)")
                hdr_name = next(
                    (entry["name"] for entry in self.hdr_files if ffl_pat.search(entry["name"])),
                    None,
                )
                if hdr_name is None:
                    continue
                pixel_verts: list[list[float]] = []
                world_verts: list[list[float]] = []
                for ln in lines[vertex_start:]:
                    parts = ln.split()
                    if len(parts) >= 4:
                        try:
                            world_verts.append([float(parts[0]), float(parts[1])])
                            pixel_verts.append([float(parts[2]), float(parts[3])])
                        except ValueError:
                            continue
                if len(pixel_verts) < 3:
                    continue
                m_name = re.match(r"AOI Points File:\s*(.+)", lines[0])
                display_name = m_name.group(1).strip() if m_name else aoi_path.stem
                self.rooms.append({
                    "name": display_name,
                    "parent": None,
                    "vertices": pixel_verts,
                    "world_vertices": world_verts,
                    "ffl": ffl,
                    "hdr_file": self._resolve_room_hdr_key(hdr_name),
                    "visible": True,
                })
                seeded += 1
                continue

            # ---- v1 input (PARENT/CHILD) and v2 minimal: world-only rows ----
            world_verts = []
            for ln in lines[vertex_start:]:
                parts = ln.split()
                if len(parts) >= 2:
                    try:
                        world_verts.append([float(parts[0]), float(parts[1])])
                    except ValueError:
                        continue
            if len(world_verts) < 3:
                continue

            cached = ffl_mm_to_entry.get(int(round(ffl * 1000)))
            if cached is None:
                continue
            entry, vp = cached
            pixel_verts = self._project_world_to_pixels(
                world_verts, vp[0], vp[1], vp[2], vp[3], vp[4], vp[5],
            )

            # Room name: always the filestem. Parent/child relationships are
            # managed in-app and persisted to aoi_session.json — never
            # reconstructed from .aoi header lines (even in v1 files).
            self.rooms.append({
                "name": aoi_path.stem,
                "parent": None,
                "vertices": pixel_verts,
                "world_vertices": world_verts,
                "ffl": ffl,
                "hdr_file": self._resolve_room_hdr_key(entry["name"]),
                "visible": True,
            })
            seeded += 1
        self._validate_room_hierarchy()
        return seeded

    def _seed_rooms_from_iesve_aoi(self, aoi_dir: Path) -> int:
        """Seed ``self.rooms`` from IESVE ``.aoi`` files (world X/Y only).

        FFL per zone is looked up in the converted ``room_boundaries.csv`` when
        available. Rooms are projected into the first HDR matching their FFL
        (or level-code prefix) using ``hdr_view_params``.
        """
        import re
        if not self.hdr_files or not self.hdr_view_params:
            return 0

        ffl_lookup: dict[str, float] = {}
        # Try any xlsx/csv file in aoi_dir whose columns match the IESVE room-data
        # schema. Some projects keep the original xlsx, others have it
        # misnamed as .csv; we accept either and sniff the format.
        def _try_load_room_data(path: Path) -> dict[str, float]:
            try:
                try:
                    df = pd.read_excel(path)
                except Exception:
                    try:
                        df = pd.read_csv(path, encoding="utf-8")
                    except (UnicodeDecodeError, pd.errors.ParserError):
                        df = pd.read_csv(path, encoding="cp1252")
                if "Space ID" in df.columns and "Min. Height (m) (Real)" in df.columns:
                    return dict(zip(
                        df["Space ID"].astype(str),
                        df["Min. Height (m) (Real)"].astype(float),
                    ))
            except Exception as exc:
                logger.debug("IESVE FFL candidate %s unreadable: %s", path.name, exc)
            return {}

        for cand in sorted(aoi_dir.glob("*.xlsx")) + sorted(aoi_dir.glob("*.csv")):
            ffl_lookup = _try_load_room_data(cand)
            if ffl_lookup:
                break

        ffl_mm_to_entry: dict[int, tuple[dict, list[float]]] = {}
        for entry in self.hdr_files:
            m = re.search(r"plan_ffl_(\d+)", entry["name"])
            vp = self.hdr_view_params.get(entry["name"])
            if m and vp and len(vp) >= 6:
                ffl_mm_to_entry.setdefault(int(m.group(1)), (entry, vp))

        use_ffl_filter = bool(ffl_mm_to_entry)
        level_cache: dict[str, tuple[dict, list[float]]] = {}
        if not use_ffl_filter:
            for entry in self.hdr_files:
                m_lvl = re.match(r"^(L\d+)", entry["name"], re.IGNORECASE)
                vp = self.hdr_view_params.get(entry["name"])
                if m_lvl and vp and len(vp) >= 6:
                    level_cache.setdefault(m_lvl.group(1).upper(), (entry, vp))

        seeded = 0
        for aoi_path in sorted(aoi_dir.glob("*.aoi")):
            if aoi_path.stem == "aoi_session":
                continue
            parsed = self._parse_base_aoi(aoi_path)
            if parsed is None:
                continue
            space_id, level_code, world_verts = parsed
            ffl = ffl_lookup.get(space_id, 0.0)
            if use_ffl_filter:
                cached = ffl_mm_to_entry.get(int(round(ffl * 1000)))
            else:
                cached = level_cache.get(level_code.upper())
            if cached is None:
                continue
            entry, vp = cached
            pixel_verts = self._project_world_to_pixels(
                world_verts, vp[0], vp[1], vp[2], vp[3], vp[4], vp[5],
            )
            self.rooms.append({
                "name": f"{space_id} {level_code}".strip(),
                "parent": None,
                "vertices": pixel_verts,
                "world_vertices": world_verts,
                "ffl": ffl,
                "hdr_file": self._resolve_room_hdr_key(entry["name"]),
                "visible": True,
            })
            seeded += 1
        self._validate_room_hierarchy()
        return seeded

    def _validate_room_hierarchy(self) -> None:
        """Enforce: a room is a child only when its ``parent`` names a real
        top-level sibling (same ``hdr_file``, no parent of its own) AND every
        child vertex sits inside that parent's polygon. Violations are demoted
        to ``parent = None`` so they render top-level. Idempotent.

        A room with ``parent`` set to ``None`` or ``""`` is treated as
        top-level (the codebase uses both sentinels interchangeably — e.g. the
        divider tool at :3309 vs zone-click at :3885).
        """
        from ..lib.geometry import point_in_polygon, polygon_centroid
        by_hdr: dict[str, list[int]] = {}
        for idx, room in enumerate(self.rooms):
            by_hdr.setdefault(room.get("hdr_file", ""), []).append(idx)
        for hdr_key, idxs in by_hdr.items():
            name_to_idx = {
                self.rooms[i].get("name", ""): i
                for i in idxs
                if not self.rooms[i].get("parent")
            }
            for i in idxs:
                room = self.rooms[i]
                parent_name = room.get("parent")
                if not parent_name:
                    continue
                parent_idx = name_to_idx.get(parent_name)
                if parent_idx is None:
                    logger.warning(
                        "[hierarchy] demoting %r — parent %r not found in %r",
                        room.get("name"), parent_name, hdr_key,
                    )
                    room["parent"] = None
                    continue
                parent_verts = self.rooms[parent_idx].get("vertices") or []
                child_verts = room.get("vertices") or []
                if len(parent_verts) < 3 or len(child_verts) < 3:
                    logger.warning(
                        "[hierarchy] demoting %r — insufficient vertices for containment test",
                        room.get("name"),
                    )
                    room["parent"] = None
                    continue
                # Probe the child's interior (centroid) rather than every
                # vertex. Divider-produced children share edges with the
                # parent, so boundary-coincident vertices would fail the
                # strict ray-cast containment test.
                cx, cy = polygon_centroid(child_verts)
                if not point_in_polygon(cx, cy, parent_verts):
                    logger.warning(
                        "[hierarchy] demoting %r — centroid outside parent %r",
                        room.get("name"), parent_name,
                    )
                    room["parent"] = None

    def _maybe_seed_from_aoi_files(self) -> int:
        """If the current project has ``.aoi`` files but no session yet, seed
        ``self.rooms`` from them and return the count. Callers should invoke
        ``save_session()`` afterwards so the seeded rooms persist.
        """
        if not self.project:
            return 0
        try:
            from archilume.config import get_project_paths
            aoi_dir = get_project_paths(self.project).aoi_inputs_dir
        except Exception:
            return 0
        if not aoi_dir.exists():
            return 0
        aoi_files = [p for p in aoi_dir.glob("*.aoi") if p.stem != "aoi_session"]
        if not aoi_files:
            return 0
        # IESVE files carry a ``ZONE {space_id} {level_code}`` line on line 1;
        # v2 sunlight files share the ``AoI Points File :`` header but have no
        # ZONE line. Use ZONE presence as the discriminator.
        is_iesve = False
        try:
            head = aoi_files[0].read_text(encoding="utf-8").splitlines()[:5]
            if any(l.lstrip().upper().startswith("ZONE ") for l in head):
                is_iesve = True
        except Exception:
            pass
        if is_iesve:
            return self._seed_rooms_from_iesve_aoi(aoi_dir)
        return self._seed_rooms_from_modern_aoi(aoi_dir)

    def reinstate_room_from_aoi(self) -> None:
        """Reinstate a deleted room by finding the AOI file that contains the clicked location."""
        import re
        from ..lib.geometry import point_in_polygon

        self.context_menu_visible = False

        # Current HDR info
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            self.status_message = "No HDR loaded"
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        vp_params = self.hdr_view_params.get(hdr_name)
        if not vp_params:
            self.status_message = "No view params for current HDR"
            return

        vp_x, vp_y, vh, vv, *_rest = vp_params
        img_w = self.image_width
        img_h = self.image_height
        if img_w <= 0 or img_h <= 0:
            self.status_message = "Image not loaded"
            return

        # Convert click pixel coords to world coords
        px = self.context_menu_canvas_x
        py = self.context_menu_canvas_y
        wx = (px - img_w / 2) * (vh / img_w) + vp_x
        wy = (img_h / 2 - py) * (vv / img_h) + vp_y

        # Extract FFL from current HDR name (e.g. "527DP_plan_ffl_14300" → "14300")
        m_ffl = re.search(r"ffl_(\d+)", hdr_name)
        if not m_ffl:
            self.status_message = "Cannot determine floor level from HDR name"
            return
        current_ffl = m_ffl.group(1)

        from archilume.config import get_project_paths
        aoi_dir = get_project_paths(self.project).aoi_inputs_dir
        if not aoi_dir.exists():
            self.status_message = "AOI directory not found"
            return

        existing_names = {r.get("name", "") for r in self.rooms if r.get("hdr_file") == hdr_name}
        match_zone: str | None = None
        match_verts: list[list[float]] = []

        # Strategy 1: level-suffixed AOI files in inputs/aoi/
        for aoi_path in sorted(aoi_dir.glob("*_L*.aoi")):
            parsed = self._parse_level_aoi(aoi_path)
            if parsed is None:
                continue
            zone_name, ffl_str, world_verts = parsed
            if ffl_str != current_ffl:
                continue
            if zone_name in existing_names:
                continue
            if point_in_polygon(wx, wy, world_verts):
                match_zone = zone_name
                match_verts = world_verts
                break

        # Strategy 2: base-format AOI files with level->FFL map from outputs/
        if match_zone is None:
            level_ffl_map = self._build_level_ffl_map(aoi_dir)
            for aoi_path in sorted(aoi_dir.glob("*.aoi")):
                if "_L" in aoi_path.stem or aoi_path.stem == "aoi_session":
                    continue
                parsed_base = self._parse_base_aoi(aoi_path)
                if parsed_base is None:
                    continue
                zone_name, level_code, world_verts = parsed_base
                mapped_ffl = level_ffl_map.get(level_code.upper())
                if mapped_ffl != current_ffl:
                    continue
                if zone_name in existing_names:
                    continue
                if point_in_polygon(wx, wy, world_verts):
                    match_zone = zone_name
                    match_verts = world_verts
                    break

        if match_zone is None:
            self.status_message = "No matching AOI file found at this location"
            return

        # Project world vertices to pixel space
        pixel_verts = self._project_world_to_pixels(
            match_verts, vp_x, vp_y, vh, vv, img_w, img_h,
        )

        new_room: dict = {
            "name": match_zone,
            "parent": "",
            "room_type": "NONE",
            "hdr_file": self._current_room_hdr_key() or hdr_name,
            "vertices": pixel_verts,
            "world_vertices": match_verts,
            "visible": True,
        }
        new_idx = len(self.rooms)
        self.rooms = self.rooms + [new_room]
        self.selected_room_idx = new_idx
        self.multi_selected_idxs = []
        self.status_message = f"Reinstated room {match_zone} from AOI"
        self._auto_save()
        self._recompute_df()

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

    # ------------------------------------------------------------------
    # § Legend popout
    # ------------------------------------------------------------------
    def toggle_legend_pin(self) -> None:
        self.legend_pinned = not self.legend_pinned

    def set_legend_hovered(self, v: bool) -> None:
        self.legend_hovered = v

    def toggle_overlay(self):
        if not self.overlay_pdf_path:
            self._pick_pdf_via_dialog()
        else:
            self.overlay_visible = not self.overlay_visible
            logger.debug(f"[overlay] toggle_overlay: visible={self.overlay_visible}, pdf_path='{self.overlay_pdf_path}', url='{self.overlay_image_url}'")
            if self.overlay_visible and not self.overlay_image_url:
                self._rasterize_current_page()
            if self.overlay_visible:
                self._ensure_default_transform()
            self._auto_save()
        # Warm the disk cache for other DPI variants in the background so
        # cycling "Plan Resolution" is instant. Safe to call unconditionally:
        # the prefetch task bails if pdf_path or project is empty.
        if self.overlay_pdf_path:
            return EditorState.prefetch_overlay_dpi_cache

    def _pick_pdf_via_dialog(self) -> None:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select Floor Plan PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        root.destroy()
        if not path:
            return
        self.overlay_pdf_path = path
        from ..lib.image_loader import get_pdf_page_count
        self.overlay_page_count = get_pdf_page_count(Path(path))
        self.overlay_page_idx = 0
        self.overlay_image_url = ""
        self._save_pdf_path_to_toml(path)
        self._rasterize_current_page()
        if self.overlay_image_url:
            self.overlay_visible = True
            self.status_message = f"Floor plan attached ({self.overlay_page_count} page(s))"
            self.status_colour = "accent"
        else:
            self.status_message = "Failed to rasterize PDF"
            self.status_colour = "danger"

    def _save_pdf_path_to_toml(self, path: str) -> None:
        if not self.project:
            return
        try:
            from archilume.config import get_project_paths
            import tomllib
            project_paths = get_project_paths(self.project)
            toml_path = project_paths.project_dir / "project.toml"
            data: dict = {}
            if toml_path.exists():
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
            # Store relative to inputs_dir; fall back to absolute only when PDF
            # lives outside the project.
            pdf_p = Path(path)
            try:
                rel = pdf_p.resolve().relative_to(project_paths.inputs_dir.resolve())
                stored = str(rel).replace("\\", "/")
            except ValueError:
                stored = str(pdf_p)
            data.setdefault("paths", {})["pdf_path"] = stored
            # Migrate: drop legacy [project].pdf_path if present
            if isinstance(data.get("project"), dict):
                data["project"].pop("pdf_path", None)
            # Write TOML manually (no tomli_w dependency)
            lines = []
            for section, values in data.items():
                lines.append(f"[{section}]")
                for k, v in values.items():
                    if isinstance(v, str):
                        lines.append(f'{k} = "{v}"')
                    else:
                        lines.append(f"{k} = {v}")
                lines.append("")
            toml_path.write_text("\n".join(lines), encoding="utf-8")
            logger.debug(f"[overlay] Saved pdf_path to {toml_path}")
        except Exception as e:
            logger.debug(f"[overlay] Failed to save pdf_path to toml: {e}")

    def toggle_overlay_align(self) -> None:
        # DF placement relies on canvas clicks which overlay-align blocks at the JS level,
        # so force it off to avoid silently broken state.
        if self.df_placement_mode:
            self.df_placement_mode = False
            _df_cache["image"] = None
            _df_cache["hdr_path"] = ""
            self.df_cursor_label = ""
            self.df_cursor_df = ""
        entering = not self.overlay_align_mode
        self.overlay_align_mode = not self.overlay_align_mode
        self.align_points = []
        if entering:
            # Snapshot current overlay state as the committed baseline
            key = self._current_level_key()
            transform = dict(self.overlay_transforms.get(key, {})) if key and key in self.overlay_transforms else None
            self._overlay_session_start = {"level_key": key, "transform": transform}
            self._overlay_undo_stack = []
            # In sunlight mode, auto-inherit from below on first entry to adjust-plan
            # for this level (no stored transform yet) so the user doesn't have to
            # manually click "Inherit from Below" every time.
            if self.is_sunlight_mode and key and key not in self.overlay_transforms:
                self.inherit_from_level_below()
        else:
            # Exiting: commit final position, clear overlay undo stack
            self._overlay_undo_stack = []
            self._overlay_session_start = {}

    def cycle_overlay_page(self):
        if self.overlay_page_count <= 0:
            return
        old_page = self.overlay_page_idx
        self.overlay_page_idx = (self.overlay_page_idx + 1) % self.overlay_page_count
        if self.overlay_align_mode:
            self._push_overlay_undo({
                "action": "overlay_props",
                "desc": "Change overlay page",
                "before": {"page_idx": old_page, "dpi": self.overlay_dpi, "alpha": self.overlay_alpha},
                "after": {"page_idx": self.overlay_page_idx, "dpi": self.overlay_dpi, "alpha": self.overlay_alpha},
            })
        # Persist new page into the per-level transform so navigating away and back
        # restores the correct page for this level (fixes cross-level page mutation).
        key = self._current_level_key()
        if key:
            t = dict(self._get_current_overlay_transform())
            t["page_idx"] = self.overlay_page_idx
            t.setdefault("is_manual", True)
            outer = dict(self.overlay_transforms)
            outer[key] = t
            self.overlay_transforms = outer
            self._auto_save()
        self._rasterize_current_page()
        if self.overlay_pdf_path:
            return EditorState.prefetch_overlay_dpi_cache

    def set_overlay_dpi(self, dpi: str) -> None:
        try:
            self.overlay_dpi = int(dpi)
        except ValueError:
            return
        self._rasterize_current_page()

    def cycle_overlay_dpi(self) -> None:
        old_dpi = self.overlay_dpi
        try:
            idx = _DPI_STEPS.index(self.overlay_dpi)
        except ValueError:
            # Legacy sessions may hold a retired DPI (e.g. 72 or 100).
            # Snap to the default and start cycling from there.
            self.overlay_dpi = _DEFAULT_OVERLAY_DPI
            idx = _DPI_STEPS.index(_DEFAULT_OVERLAY_DPI)
        self.overlay_dpi = _DPI_STEPS[(idx + 1) % len(_DPI_STEPS)]
        if self.overlay_align_mode:
            self._push_overlay_undo({
                "action": "overlay_props",
                "desc": "Change overlay DPI",
                "before": {"dpi": old_dpi, "alpha": self.overlay_alpha, "page_idx": self.overlay_page_idx},
                "after": {"dpi": self.overlay_dpi, "alpha": self.overlay_alpha, "page_idx": self.overlay_page_idx},
            })
        self._rasterize_current_page()

    def set_overlay_alpha(self, value: str) -> None:
        try:
            self.overlay_alpha = max(0.0, min(1.0, float(value)))
            self._auto_save()
        except ValueError:
            pass

    # =====================================================================
    # FALSECOLOUR / CONTOUR VISUALISATION SETTINGS
    # =====================================================================

    def _sync_vis_input(self, input_id: str, display: "float | int") -> rx.event.EventSpec:
        """Return a client-side script that forces the DOM input's value to match
        the snapped state. Needed because rx.el.input uses default_value= (honoured
        only on mount); server-side state updates don't propagate to the DOM
        otherwise, so the user sees their raw typed value persist."""
        return rx.call_script(
            f"var el=document.getElementById('{input_id}');"
            f"if(el) el.value='{display}';"
        )

    def set_falsecolour_scale(self, value: float):
        snapped = _snap_scale_top(value)
        if snapped is not None:
            self.falsecolour_scale = snapped
            self._auto_save()
        return self._sync_vis_input("vis-fc-scale", self.falsecolour_scale)

    def set_falsecolour_n_levels(self, value: float):
        snapped = _snap_scale_divisions(value)
        if snapped is not None:
            self.falsecolour_n_levels = snapped
            self._auto_save()
        return self._sync_vis_input("vis-fc-div", self.falsecolour_n_levels)

    def set_falsecolour_palette(self, value: str) -> None:
        if value not in ("spec", "def", "pm3d", "hot", "eco", "tbo"):
            return
        self.falsecolour_palette = value
        self._auto_save()

    def set_contour_scale(self, value: float):
        snapped = _snap_scale_top(value)
        if snapped is not None:
            self.contour_scale = snapped
            self._auto_save()
        return self._sync_vis_input("vis-ct-scale", self.contour_scale)

    def set_contour_n_levels(self, value: float):
        snapped = _snap_scale_divisions(value)
        if snapped is not None:
            self.contour_n_levels = snapped
            self._auto_save()
        return self._sync_vis_input("vis-ct-div", self.contour_n_levels)

    def _current_image_dir(self) -> "Path | None":
        if not self.hdr_files:
            return None
        return Path(self.hdr_files[0]["hdr_path"]).parent

    def regenerate_visualisation_force(self):
        """UI entry point for the explicit "Regenerate" button.

        1. Defensively re-snap all four state values (idempotent if the blur
           handlers already ran, but catches the edge case where the user clicks
           Regenerate mid-type without losing input focus first).
        2. Force every input's DOM value to match the snapped state, so the UI
           visibly confirms the correction before any Radiance work runs.
        3. Chain to the background event with force=True so all PNGs are rebuilt
           regardless of the last_generated cache.
        """
        # Re-snap — each helper is None-safe and returns the snapped value or None.
        for attr, snapper in (
            ("falsecolour_scale",    _snap_scale_top),
            ("falsecolour_n_levels", _snap_scale_divisions),
            ("contour_scale",        _snap_scale_top),
            ("contour_n_levels",     _snap_scale_divisions),
        ):
            snapped = snapper(str(getattr(self, attr)))
            if snapped is not None:
                setattr(self, attr, snapped)
        self._auto_save()

        sync_js = (
            "var set=function(id,v){var el=document.getElementById(id); if(el) el.value=v;};"
            f"set('vis-fc-scale','{self.falsecolour_scale}');"
            f"set('vis-fc-div','{self.falsecolour_n_levels}');"
            f"set('vis-ct-scale','{self.contour_scale}');"
            f"set('vis-ct-div','{self.contour_n_levels}');"
        )
        return [rx.call_script(sync_js), EditorState.regenerate_visualisation_bg(True)]

    @rx.event(background=True)
    async def regenerate_visualisation_bg(self, force: bool = False):
        """Regenerate stale falsecolour + contour PNGs for the current project.

        Runs Radiance commands in a background thread so the UI stays responsive.
        If ``force`` is True, ignores cache and regenerates every HDR for both
        streams (used by the explicit "Regenerate" button).

        Sunlight projects skip this step entirely — the SunlightAccessWorkflow
        emits a ``{stem}.png`` sibling next to every HDR at render time, so
        there is nothing for the app to regenerate.
        """
        import asyncio
        from ..lib import visualisation_manager as vm
        from ..lib.image_loader import clear_cache, scan_hdr_files

        async with self:
            mode = self.project_mode
        if mode == "sunlight":
            return

        if not vm.radiance_available():
            # Emit a visible log so the skip shows up in container stdout —
            # the transient status message alone is easy to miss, and silent
            # skips break the export overlay phase (which needs the PNGs).
            try:
                from archilume import config as _ar_config
                _rad_bin = _ar_config.RADIANCE_BIN_PATH
            except Exception:
                _rad_bin = "<unknown>"
            logger.warning(
                "Radiance CLI not found at %s — falsecolour/contour PNGs "
                "cannot be regenerated. Annotated overlay export will skip "
                "any missing base PNGs.", _rad_bin,
            )
            async with self:
                self.status_message = "Radiance CLI not found — skipping visualisation generation"
                self.status_colour = "accent2"
            return

        # Snapshot inputs under the state lock.
        async with self:
            if self.is_regenerating:
                return  # already running
            image_dir = self._current_image_dir()
            if image_dir is None:
                return
            hdr_files = list(self.hdr_files)
            fc_settings = {
                "scale": self.falsecolour_scale,
                "n_levels": self.falsecolour_n_levels,
                "palette": self.falsecolour_palette,
            }
            ct_settings = {"scale": self.contour_scale,    "n_levels": self.contour_n_levels}
            self.is_regenerating = True
            self.regen_progress = ""

        # Determine work per stream (snapshot copies — no state access here).
        # Existence-only gating on the non-force path: regen is only driven by
        # a missing PNG. Force=True (Regenerate button) still rebuilds every
        # HDR and invalidates both legends.
        if force:
            fc_stale = [Path(h["hdr_path"]) for h in hdr_files]
            ct_stale = [Path(h["hdr_path"]) for h in hdr_files]
            fc_force_legend = True
            ct_force_legend = True
        else:
            fc_stale = vm.detect_stale("falsecolour", hdr_files, image_dir)
            ct_stale = vm.detect_stale("contour",    hdr_files, image_dir)
            fc_force_legend = False
            ct_force_legend = False

        if not fc_stale and not ct_stale:
            async with self:
                self.is_regenerating = False
                self.regen_progress = ""
                # Ensure last_generated reflects current settings even when nothing changed.
                self.last_generated = {"falsecolour": fc_settings, "contour": ct_settings}
                self._auto_save()
            return

        if fc_force_legend:
            vm.invalidate_legend("falsecolour", image_dir)
        if ct_force_legend:
            vm.invalidate_legend("contour", image_dir)

        # Process each stream sequentially. Falsecolour first so the user sees
        # the recoloured plate before the contour overlay catches up.
        for stream, stale, settings in (
            ("falsecolour", fc_stale, fc_settings),
            ("contour",    ct_stale, ct_settings),
        ):
            total = len(stale)
            for i, hdr in enumerate(stale, 1):
                async with self:
                    self.regen_progress = f"Regenerating {stream} {i}/{total}: {hdr.stem}"
                try:
                    await asyncio.to_thread(
                        vm.regenerate_one, stream, hdr, image_dir, settings,
                    )
                except Exception as e:
                    logger.exception("regenerate_one failed for %s/%s", stream, hdr.stem)
                    async with self:
                        self.regen_progress = f"Error on {hdr.stem}: {e}"

        # Refresh the variant list + clear the image cache so new PNGs surface.
        clear_cache()
        new_hdr_files = scan_hdr_files(image_dir)
        async with self:
            self.hdr_files = new_hdr_files
            self.last_generated = {"falsecolour": fc_settings, "contour": ct_settings}
            self.is_regenerating = False
            self.regen_progress = ""
            self.status_message = "Visualisation regenerated"
            self.status_colour = "accent"
            self._rebuild_variants()
            self.load_current_image()
            self._auto_save()

    def set_overlay_transparency_fraction(self, value: str) -> None:
        """Set transparency as a fraction 0–1 (0 = opaque, 1 = fully transparent)."""
        try:
            v = round(max(0.0, min(1.0, float(value))) * 20) / 20  # snap to 0.05 increments
            self.overlay_alpha = round(1.0 - v, 2)
            self._auto_save()
        except ValueError:
            pass

    def set_overlay_transparency(self, value: list[float]) -> None:
        """Slider on_value_commit passes list[float]; value 0–95 (transparency %) → opacity = 1 - v/100."""
        v = value[0] if value else 40
        self.overlay_alpha = max(0.05, min(1.0, 1.0 - v / 100))
        self._auto_save()

    def set_overlay_transparency_int(self, value: str) -> None:
        """Number input: value 0–100 (transparency %) → opacity = 1 - v/100."""
        try:
            v = max(0, min(100, int(value)))
            self.overlay_alpha = max(0.0, min(1.0, 1.0 - v / 100))
            self._auto_save()
        except ValueError:
            pass

    def set_overlay_offset_x(self, value: str) -> None:
        try:
            iw = self.image_width
            if iw <= 0:
                return
            t = dict(self._get_current_overlay_transform())
            t["offset_x"] = int(value) / iw
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def set_overlay_offset_y(self, value: str) -> None:
        try:
            ih = self.image_height
            if ih <= 0:
                return
            t = dict(self._get_current_overlay_transform())
            t["offset_y"] = int(value) / ih
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

    def set_overlay_scale(self, value: str) -> None:
        try:
            s = float(value)
            t = dict(self._get_current_overlay_transform())
            t["scale_x"] = s
            t["scale_y"] = s
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def rotate_overlay_90(self) -> None:
        t = dict(self._get_current_overlay_transform())
        t["rotation_90"] = (t.get("rotation_90", 0) + 90) % 360
        self._set_current_overlay_transform(t)

    def set_overlay_rotation_deg(self, value: str) -> None:
        try:
            t = dict(self._get_current_overlay_transform())
            t["rotation_90"] = int(value) % 360
            self._set_current_overlay_transform(t)
        except ValueError:
            pass

    def _centred_default_transform(self) -> dict:
        """Default transform: PDF centre coincident with HDR centre.

        offset_x / offset_y are fractions of HDR image dimensions, measured as the
        displacement of the PDF centre from the HDR centre. (0, 0) → centred.
        """
        return {"offset_x": 0.0, "offset_y": 0.0, "scale_x": 1.0, "scale_y": 1.0, "rotation_90": 0}

    def inherit_from_level_below(self) -> None:
        """Copy the overlay transform from the level immediately below onto this level.

        Sunlight view_generator uses shared view extents across levels, so a transform
        aligned on one level applies 1:1 to any other level. If no lower level exists
        or it has no stored transform, fall back to the centred default.

        Size/scale/opacity/rotation are inherited verbatim. The PDF page is advanced
        by one (page_below + 1) so each floor level shows the next plan sheet.
        """
        current_key = self._current_level_key()
        if not current_key:
            return
        below_key = self._level_below_key()
        below_t = self.overlay_transforms.get(below_key) if below_key else None
        if below_t:
            logger.debug("[overlay-inherit] %s <- %s", current_key, below_key)
            # Copy geometry (scale/offset/rotation) but NOT page_idx or is_manual.
            new_t = {k: v for k, v in below_t.items() if k not in ("is_manual", "page_idx")}
            # Advance the PDF page by one relative to the level below so each floor
            # shows the next plan sheet (expected: page_below + 1).
            below_page = int(below_t.get("page_idx", self.overlay_page_idx))
            if self.overlay_page_count > 0:
                new_page = (below_page + 1) % self.overlay_page_count
            else:
                new_page = below_page
            new_t["page_idx"] = new_page
            self.overlay_page_idx = new_page
            self._set_current_overlay_transform(new_t)
            if self.overlay_visible and self.overlay_pdf_path:
                self._rasterize_current_page()
        else:
            logger.debug(
                "[overlay-inherit] %s: no lower level with transform — reset to centred",
                current_key,
            )
            self._set_current_overlay_transform(self._centred_default_transform())

    def _restore_overlay_page_for_current_level(self) -> None:
        """Restore or infer the PDF page for the current level so each level displays
        its own page.

        Prevents cross-level page mutation (``overlay_page_idx`` was a shared global)
        and auto-inherits ``page_below + 1`` on first visit so the user doesn't need
        to open Adjust Plan. A stored transform that predates the ``page_idx`` field
        (legacy session data) is treated the same as a first visit — otherwise the
        stale transform would swallow the restore branch and leave ``overlay_page_idx``
        leaking from the previous level.
        """
        level_key = self._current_level_key()
        if not (level_key and self.overlay_pdf_path and self.overlay_page_count > 0):
            return
        stored_page = None
        if level_key in self.overlay_transforms:
            stored_page = self.overlay_transforms[level_key].get("page_idx")
        new_page = int(stored_page) if stored_page is not None else self._infer_default_page_for_current_level()
        if new_page != self.overlay_page_idx:
            self.overlay_page_idx = new_page
            if self.overlay_visible:
                self._rasterize_current_page()

    def _infer_default_page_for_current_level(self) -> int:
        """Compute the default PDF page for the current level without storing a transform.

        In sunlight mode, looks up the level immediately below and returns
        ``page_below + 1`` (modulo page_count) so each floor shows the next
        plan sheet automatically.  If no lower level with a stored page exists,
        returns 0.  Used by ``_goto_frame`` to set ``overlay_page_idx`` on
        first navigation to a level that has no stored transform yet.
        """
        if self.overlay_page_count <= 0:
            return 0
        below_key = self._level_below_key()
        if below_key:
            below_t = self.overlay_transforms.get(below_key)
            if below_t is not None:
                below_page = int(below_t.get("page_idx", 0))
                return (below_page + 1) % self.overlay_page_count
        return 0

    def _ensure_default_transform(self) -> None:
        """Store a centred default transform for the current level if none exists yet."""
        key = self._current_level_key()
        if not key:
            return
        if key not in self.overlay_transforms:
            self._set_current_overlay_transform(self._centred_default_transform())

    def _arrow_accel(self, direction: str) -> int:
        """Return the nudge step in CSS pixels for one arrow-key press.

        Single tap = 5 px (visible at any viewport size). Holding the key
        escalates to 15 px then 40 px so bulk alignment is quick. Previous
        tuning (1/5/20 px) was invisible on wide viewports — a 1 px shift
        on a 2248 px canvas is a 0.04 % translation, below perception.
        """
        now = time.time()
        elapsed = now - self._arrow_last_time
        if direction == self._arrow_last_dir and elapsed < 0.15:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_count = 1
        self._arrow_last_time = now
        self._arrow_last_dir = direction
        if self._arrow_repeat_count >= 10:
            step = 40
        elif self._arrow_repeat_count >= 4:
            step = 15
        else:
            step = 5
        logger.debug(
            f"[accel] dir={direction} elapsed={elapsed*1000:.0f}ms "
            f"count={self._arrow_repeat_count} step={step}"
        )
        return step

    def nudge_overlay(self, dx: int, dy: int) -> None:
        logger.debug(
            f"[nudge] dx={dx} dy={dy} vw={self.viewport_width} "
            f"hdr_idx={self.current_hdr_idx} hdr_count={len(self.hdr_files)} "
            f"align={self.overlay_align_mode} vis={self.overlay_visible}"
        )
        if self.viewport_width <= 0:
            logger.debug("[nudge] ABORT: viewport_width <= 0")
            return
        s = self.canvas_fit_scale
        cw = self.image_width * s
        ch = self.image_height * s
        if cw <= 0 or ch <= 0:
            return
        t = dict(self._get_current_overlay_transform())
        t["offset_x"] = t.get("offset_x", 0.0) + dx / cw
        t["offset_y"] = t.get("offset_y", 0.0) + dy / ch
        self._set_current_overlay_transform(t)

    def sync_overlay_transform(self, data: dict) -> None:
        """Debounced sync from JS after Ctrl+scroll overlay scaling or drag.

        JS sends absolute CSS pixel translate (centring + offset baked in). Subtract
        the centring term to recover offset-from-centre, then convert to fractions
        of HDR image dimensions.
        """
        if self.viewport_width <= 0 or self.image_width <= 0:
            return
        iw = self.image_width
        ih = self.image_height or 1
        s = self.canvas_fit_scale
        cw = iw * s
        ch = ih * s
        if cw <= 0 or ch <= 0:
            return
        t = dict(self._get_current_overlay_transform())
        sx = data.get("scale_x", t.get("scale_x", 1.0))
        sy = data.get("scale_y", t.get("scale_y", 1.0))
        pdf_aspect = (self.overlay_img_height / self.overlay_img_width) if self.overlay_img_width > 0 else (ih / iw)
        cx = cw * (1.0 - sx) / 2.0
        cy = (ch - cw * pdf_aspect * sy) / 2.0
        if "offset_x" in data:
            t["offset_x"] = (data["offset_x"] - cx) / cw
        if "offset_y" in data:
            t["offset_y"] = (data["offset_y"] - cy) / ch
        t["scale_x"] = sx
        t["scale_y"] = sy
        self._set_current_overlay_transform(t)

    def _current_level_key(self) -> str:
        """Transform storage key for the currently-displayed HDR — the level label.

        Sunlight: view_groups[current_view_idx]["view_name"] (e.g. ``ffl_103180``)
        so all timestep frames of a level share one transform slot.
        Daylight (view_groups empty): hdr_files[current_hdr_idx]["name"] — each
        HDR is effectively its own view.
        """
        if self.view_groups and 0 <= self.current_view_idx < len(self.view_groups):
            return self.view_groups[self.current_view_idx]["view_name"]
        if self.hdr_files and 0 <= self.current_hdr_idx < len(self.hdr_files):
            return self.hdr_files[self.current_hdr_idx]["name"]
        return ""

    def _level_below_key(self) -> str:
        """Return the level key immediately below the current one by ``ffl_NNNNNN`` elevation.

        Works for both modes: sunlight keys are view_names (``ffl_NNNNNN``), daylight
        keys are HDR stems that embed ``ffl_NNNNNN``. Returns "" if the current key
        lacks an ffl token or no lower level exists.
        """
        current = self._current_level_key()
        if not current:
            return ""
        m = re.search(r"ffl_(\d+)", current)
        if not m:
            return ""
        current_z = int(m.group(1))
        if self.view_groups:
            candidates = [vg["view_name"] for vg in self.view_groups]
        else:
            candidates = [h["name"] for h in self.hdr_files]
        below_z = -1
        below_key = ""
        for key in candidates:
            mm = re.search(r"ffl_(\d+)", key)
            if not mm:
                continue
            z = int(mm.group(1))
            if z < current_z and z > below_z:
                below_z = z
                below_key = key
        return below_key

    def _get_current_overlay_transform(self) -> dict:
        key = self._current_level_key()
        if key and key in self.overlay_transforms:
            return self.overlay_transforms[key]
        return self._centred_default_transform()

    def _set_current_overlay_transform(self, transform: dict) -> None:
        key = self._current_level_key()
        if not key:
            return
        stored = dict(transform)
        stored["is_manual"] = True
        # Persist the current page index so each level remembers its own PDF page.
        # This prevents cross-level mutation: navigating to another level restores
        # that level's own page rather than inheriting the global overlay_page_idx.
        if "page_idx" not in stored:
            stored["page_idx"] = self.overlay_page_idx
        logger.debug(
            "[overlay-set] level=%s ox=%.6f oy=%.6f sx=%.4f sy=%.4f rot=%s page=%d vw=%d iw=%d ih=%d pw=%d ph=%d",
            key, stored.get("offset_x", 0), stored.get("offset_y", 0),
            stored.get("scale_x", 1), stored.get("scale_y", 1),
            stored.get("rotation_90", 0), stored.get("page_idx", 0),
            self.viewport_width, self.image_width, self.image_height,
            self.overlay_img_width, self.overlay_img_height,
        )
        # Push to overlay-scoped undo stack if in adjust-plan mode
        if self.overlay_align_mode:
            old_transform = dict(self.overlay_transforms[key]) if key in self.overlay_transforms else None
            self._push_overlay_undo({
                "action": "overlay_transform",
                "desc": "Overlay transform change",
                "before": {"level_key": key, "transform": old_transform},
                "after": {"level_key": key, "transform": dict(stored)},
            })
        t = dict(self.overlay_transforms)
        t[key] = stored
        self.overlay_transforms = t
        self._auto_save()

    def _rasterize_current_page(self) -> None:
        if not self.overlay_pdf_path:
            logger.debug("[overlay] _rasterize skipped: no overlay_pdf_path")
            return
        pdf_path = Path(self.overlay_pdf_path)
        if not pdf_path.exists():
            logger.warning("[overlay] PDF missing: %s — clearing overlay state", pdf_path)
            self.status_message = f"Floor plan not found: {pdf_path.name} — select a new PDF"
            self.status_colour = "danger"
            self.overlay_image_url = ""
            self.overlay_img_width = 0
            self.overlay_img_height = 0
            self.overlay_pdf_path = ""
            self.overlay_page_count = 0
            self.overlay_page_idx = 0
            return
        from ..lib.image_loader import rasterize_pdf_page
        cache_dir = _overlay_cache_dir(self.project)
        if cache_dir is None:
            logger.debug("[overlay] _rasterize skipped: no active project")
            return
        logger.debug(f"[overlay] Rasterizing: {self.overlay_pdf_path} page={self.overlay_page_idx} dpi={self.overlay_dpi}")
        cache_path, pw, ph = rasterize_pdf_page(pdf_path, self.overlay_page_idx, self.overlay_dpi, cache_dir=cache_dir)
        if cache_path:
            logger.debug(f"[overlay] Rasterized OK, path={cache_path}")
        else:
            logger.debug("[overlay] Rasterization FAILED — returned None/empty")
        # URL is served by the FastAPI /overlay_cache/{project}/{filename}
        # route on the backend port. Both segments percent-encoded to handle
        # spaces and other reserved characters in project or file names.
        if cache_path:
            url = f"/overlay_cache/{quote(self.project)}/{quote(cache_path.name)}"
            self.overlay_image_url = f"{_backend_base_url()}{url}"
        else:
            self.overlay_image_url = ""
        self.overlay_img_width = pw
        self.overlay_img_height = ph

    @rx.event(background=True)
    async def prefetch_overlay_dpi_cache(self):
        """Warm the PNG disk cache for every (page, dpi) combination.

        Runs PyMuPDF rasterisation on worker threads so the Reflex event loop
        stays responsive. Processes combinations in priority order:

        1. Current page at non-current DPIs (user likely to cycle DPI)
        2. Neighbouring pages at current DPI (user likely to page next/prev)
        3. All remaining pages × DPIs

        Between iterations we re-check the snapshot under the state lock and
        abort if the user opened a different PDF (token bumped) — a page or
        DPI change is *not* grounds to abort, since the point of prefetch is
        to cover those navigations in advance. Cache hits skip rasterisation.
        """
        import asyncio
        from ..lib.image_loader import rasterize_pdf_page_to_cache

        async with self:
            if not self.overlay_pdf_path:
                return
            cache_dir = _overlay_cache_dir(self.project)
            if cache_dir is None:
                return
            pdf_path = Path(self.overlay_pdf_path)
            current_page = self.overlay_page_idx
            current_dpi = self.overlay_dpi
            page_count = self.overlay_page_count or 1
            self._overlay_prefetch_token += 1
            my_token = self._overlay_prefetch_token
            pdf_path_str = self.overlay_pdf_path

        # Priority-ordered (page, dpi) queue. A page's distance from
        # current_page is the primary sort key so pages nearer the user's
        # current position warm first; DPI tiebreaker puts current_dpi last
        # (it is already rendered synchronously on demand).
        combos: list[tuple[int, int]] = []
        # Tier 1: current page, non-current DPIs first
        for dpi in _DPI_STEPS:
            if dpi != current_dpi:
                combos.append((current_page, dpi))
        combos.append((current_page, current_dpi))
        # Tier 2+: all other pages, ordered by distance to current_page
        other_pages = sorted(
            (p for p in range(page_count) if p != current_page),
            key=lambda p: abs(p - current_page),
        )
        for page in other_pages:
            # current_dpi first for fast page navigation at the active zoom
            combos.append((page, current_dpi))
            for dpi in _DPI_STEPS:
                if dpi != current_dpi:
                    combos.append((page, dpi))

        logger.debug(
            "[overlay] prefetch started: %d combos (%d pages × %d dpis)",
            len(combos), page_count, len(_DPI_STEPS),
        )

        for page, dpi in combos:
            async with self:
                if (
                    self._overlay_prefetch_token != my_token
                    or self.overlay_pdf_path != pdf_path_str
                ):
                    logger.debug("[overlay] prefetch superseded — aborting")
                    return
            try:
                await asyncio.to_thread(
                    rasterize_pdf_page_to_cache, pdf_path, page, dpi, cache_dir,
                )
            except Exception as exc:
                logger.debug(
                    "[overlay] prefetch page=%d dpi=%d failed: %r", page, dpi, exc,
                )

        logger.debug("[overlay] prefetch complete: all %d combos warmed", len(combos))

    @rx.event(background=True)
    async def prefetch_level_window(self):
        """Warm the image LRU for the +/-1 adjacent levels so flicking between
        level-above and level-below is served from memory.

        Mirrors ``prefetch_overlay_dpi_cache``: token-based supersede,
        ``asyncio.to_thread`` to keep the event loop responsive, and a
        per-target abort check so rapid keyboard flicks do not back up stale
        work. Picks targets by mode:

        * Sunlight: neighbours in ``view_groups`` -> frame-0 PNG sibling
          (``load_current_image`` reads that PNG for variant 0).
        * Daylight: neighbours in ``hdr_files`` -> ``tiff_paths[variant]`` if
          present, else the HDR itself (what ``_rebuild_variants`` plus
          ``load_current_image`` will load on navigate).

        Target list is bounded to at most two Paths, safely within the
        ``_image_cache`` capacity (60).
        """
        import asyncio
        from ..lib.image_loader import load_image_as_base64

        async with self:
            self._level_prefetch_token += 1
            my_token = self._level_prefetch_token
            targets = _select_level_prefetch_targets(
                self.project_mode,
                list(self.view_groups),
                self.current_view_idx,
                list(self.hdr_files),
                self.current_hdr_idx,
                self.current_variant_idx,
            )

        if not targets:
            return

        logger.debug("[level] prefetch started: %d targets", len(targets))

        for path in targets:
            async with self:
                if self._level_prefetch_token != my_token:
                    logger.debug("[level] prefetch superseded — aborting")
                    return
            try:
                await asyncio.to_thread(load_image_as_base64, path)
            except Exception as exc:
                logger.debug("[level] prefetch %s failed: %r", path, exc)

        logger.debug("[level] prefetch complete: %d targets warmed", len(targets))

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
        # Input coords are SVG user units (= HDR image intrinsic pixels). Solve so
        # PDF point pdf1 lands on img point img1 under: img = c + offset*dim + scale*pdf,
        # where c is the centring term (so offset is displacement of PDF centre from HDR centre).
        iw = self.image_width or 1
        ih = self.image_height or 1
        pdf_aspect = (self.overlay_img_height / self.overlay_img_width) if self.overlay_img_width > 0 else (ih / iw)
        cx = iw * (1.0 - scale) / 2.0
        cy = (ih - iw * pdf_aspect * scale) / 2.0
        t["offset_x"] = (img1["x"] - cx - pdf1["x"] * scale) / iw
        t["offset_y"] = (img1["y"] - cy - pdf1["y"] * scale) / ih
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
        stamp_data = [x, y, round(df_val, 2), px, py]
        hdr_stamps.append(stamp_data)
        stamps_copy[hdr_name] = hdr_stamps
        self.df_stamps = stamps_copy
        self._push_undo({
            "action": "df_stamp_add",
            "desc": f"Place DF stamp ({df_val:.2f}%)",
            "before": {},
            "after": {"hdr_name": hdr_name, "stamp_idx": len(hdr_stamps) - 1, "stamp": stamp_data},
        })
        self.status_message = f"{df_val:.2f}% DF at px({px},{py})"
        self.status_colour = "accent"

    def _df_remove_nearest(self, x: float, y: float) -> None:
        logger.info(f"[DFDIAG] _df_remove_nearest ENTER click=({x:.1f},{y:.1f}) zoom={self.zoom_level:.3f}")
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            logger.info(f"[DFDIAG]   → abort: no hdr_files or bad idx ({self.current_hdr_idx}/{len(self.hdr_files)})")
            return
        hdr_name = self.hdr_files[self.current_hdr_idx]["name"]
        hdr_stamps = self.df_stamps.get(hdr_name, [])
        logger.info(f"[DFDIAG]   hdr_name={hdr_name!r}  stamps_keys={list(self.df_stamps.keys())}  count={len(hdr_stamps)}")
        if not hdr_stamps:
            logger.info(f"[DFDIAG]   → abort: no stamps under key {hdr_name!r}")
            return
        threshold = 20.0 / max(self.zoom_level, 0.01)
        best_i, best_d = -1, threshold
        all_dists = []
        for i, stamp in enumerate(hdr_stamps):
            d = math.hypot(x - stamp[0], y - stamp[1])
            all_dists.append(f"{i}:{d:.2f}")
            if d < best_d:
                best_d = d
                best_i = i
        logger.info(f"[DFDIAG]   threshold={threshold:.2f}  dists=[{', '.join(all_dists)}]  best_i={best_i}  best_d={best_d:.2f}")
        if best_i >= 0:
            removed_stamp = list(hdr_stamps[best_i])
            self._push_undo({
                "action": "df_stamp_remove",
                "desc": "Remove DF stamp",
                "before": {"hdr_name": hdr_name, "stamp_idx": best_i, "stamp": removed_stamp},
                "after": {},
            })
            stamps_copy = dict(self.df_stamps)
            stamps_copy[hdr_name] = [s for j, s in enumerate(hdr_stamps) if j != best_i]
            self.df_stamps = stamps_copy

    def compute_df_for_current_hdr(self) -> None:
        if not self.hdr_files or self.current_hdr_idx >= len(self.hdr_files):
            return
        hdr_info = self.hdr_files[self.current_hdr_idx]
        hdr_path = hdr_info["hdr_path"]
        hdr_name = hdr_info["name"]
        from ..lib.df_analysis import compute_room_df, load_df_image

        # Use module-level cache — HDR image load is expensive (subprocess + disk I/O)
        if _df_cache.get("hdr_path") == hdr_path and _df_cache.get("image") is not None:
            df_image = _df_cache["image"]
        else:
            df_image = load_df_image(Path(hdr_path))
            _df_cache["image"] = df_image
            _df_cache["hdr_path"] = hdr_path if df_image is not None else ""

        if df_image is None:
            return

        # Compute real-world area per pixel from Radiance orthographic view params.
        # Use image dims stored alongside the view params (read from the HDR header)
        # so this is independent of self.image_width/height which may not be set yet.
        area_per_pixel_m2 = 0.0
        vp_params = self.hdr_view_params.get(hdr_name)
        if vp_params and len(vp_params) >= 6:
            _vp_x, _vp_y, vh, vv, _iw, _ih = vp_params[:6]
            if _iw > 0 and _ih > 0:
                area_per_pixel_m2 = (vh / _iw) * (vv / _ih)

        # Helper: reproject world_vertices to HDR-native pixel space so all
        # masks are in the same coordinate system as df_image.  Falls back to
        # stored vertices when world_vertices or view params are unavailable.
        def _hdr_native_verts(room: dict) -> list[list[float]]:
            wv = room.get("world_vertices", [])
            if vp_params and len(wv) >= 3 and _iw > 0 and _ih > 0:
                _vp_x_l, _vp_y_l, _vh_l, _vv_l = vp_params[:4]
                return [
                    [( wx - _vp_x_l) / (_vh_l / _iw) + _iw / 2,
                     _ih / 2 - (wy - _vp_y_l) / (_vv_l / _ih)]
                    for wx, wy in wv
                ]
            return room.get("vertices", [])

        # Build parent -> child vertex map so parent DF excludes divided areas
        child_verts_by_parent: dict[str, list[list[list[float]]]] = {}
        for room in self.rooms:
            if room.get("hdr_file") != hdr_name:
                continue
            parent_name = room.get("parent")
            if parent_name:
                child_verts_by_parent.setdefault(parent_name, []).append(
                    _hdr_native_verts(room)
                )

        results = {}
        for i, room in enumerate(self.rooms):
            if room.get("hdr_file") != hdr_name:
                continue
            room_name = room.get("name", "")
            result = compute_room_df(
                df_image,
                _hdr_native_verts(room),
                room.get("room_type", "NONE") or "NONE",
                area_per_pixel_m2=area_per_pixel_m2,
                exclude_polygons=child_verts_by_parent.get(room_name),
            )
            if result:
                results[str(i)] = result
        self.room_df_results = results

    def _recompute_df(self) -> None:
        """Clear stale results and recompute DF for rooms on current HDR."""
        self.room_df_results = {}
        self.compute_df_for_current_hdr()

    # =====================================================================
    # EXPORT / ARCHIVE
    # =====================================================================

    @rx.event(background=True)
    async def run_export(self):
        """Export DF results + archive inputs/outputs on a background thread.

        Mirrors :meth:`regenerate_visualisation_bg` — worker thread runs the
        blocking export while this coroutine polls a shared progress dict and
        flushes ``progress_pct`` / ``progress_msg`` back to the UI.
        """
        import asyncio

        async with self:
            if not self.project:
                self.status_message = "No project loaded"
                self.status_colour = "danger"
                return
            project_name = self.project
            rooms = list(self.rooms)
            hdr_files = list(self.hdr_files)
            view_params = dict(self.hdr_view_params)
            self.progress_visible = True
            self.progress_pct = 0
            self.progress_msg = "Starting export..."

        try:
            from archilume.config import get_project_paths
        except ImportError:
            async with self:
                self.progress_visible = False
                self.status_message = "Export failed: archilume not available"
                self.status_colour = "danger"
            return

        from ..lib.export_pipeline import export_report
        paths = get_project_paths(project_name)

        progress: dict = {"pct": 0, "msg": "Starting export..."}

        def _on_progress(pct: int, msg: str) -> None:
            progress["pct"] = pct
            progress["msg"] = msg

        worker = asyncio.create_task(asyncio.to_thread(
            export_report,
            rooms=rooms,
            hdr_files=hdr_files,
            hdr_view_params=view_params,
            image_dir=paths.image_dir,
            wpd_dir=paths.wpd_dir,
            archive_dir=paths.archive_dir,
            outputs_dir=paths.outputs_dir,
            inputs_dir=paths.inputs_dir,
            project_name=project_name,
            iesve_mode=False,
            on_progress=_on_progress,
        ))

        last_pct, last_msg = -1, ""
        while not worker.done():
            await asyncio.sleep(0.15)
            pct, msg = progress["pct"], progress["msg"]
            if pct != last_pct or msg != last_msg:
                last_pct, last_msg = pct, msg
                async with self:
                    self.progress_pct = pct
                    self.progress_msg = msg

        try:
            zip_path = await worker
        except Exception as exc:
            logger.exception("Export failed")
            async with self:
                self.progress_visible = False
                self.status_message = f"Export failed: {exc}"
                self.status_colour = "danger"
            return

        async with self:
            self.progress_pct = 100
            self.progress_msg = "Export complete."
            if zip_path:
                self.status_message = f"Export complete: {zip_path.name}"
                self.status_colour = "accent"
            else:
                self.status_message = "Export failed"
                self.status_colour = "danger"

        await asyncio.sleep(1.2)
        async with self:
            self.progress_visible = False

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
            # Archives contain `inputs/...` + `outputs/...` relative to the
            # project root, so extract there to restore both trees in place.
            if extract_archive(paths.archive_dir / self.selected_archive, paths.project_dir):
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

    def _load_session_core(self) -> None:
        """Load session JSON and restore state, but skip rasterization and DF compute.

        Used by _open_project_progressive to defer heavy work until after the
        UI has rendered the main image.
        """
        if not self.session_path:
            return
        from ..lib.session_io import load_session
        data = load_session(Path(self.session_path))
        if data is None:
            session_file = Path(self.session_path)
            if session_file.exists():
                logger.warning("[session] Failed to parse %s — auto-save blocked until next successful load", session_file)
                self._session_load_ok = False
                return
            # No session file yet — clear any stale cross-project state first
            # (self.rooms etc. are not reset by open_project), then seed rooms
            # from any .aoi files present so first-open of a project created
            # from staged AOI inputs isn't empty.
            self.rooms = []
            self.df_stamps = {}
            self.overlay_transforms = {}
            self._session_load_ok = True
            seeded = self._maybe_seed_from_aoi_files()
            if seeded > 0:
                logger.info("[session-load] seeded %d rooms from .aoi files", seeded)
                self.save_session()
                self.status_message = f"Seeded {seeded} rooms from .aoi files"
            return
        self.rooms = data.get("rooms", [])
        self._validate_room_hierarchy()
        self.df_stamps = data.get("df_stamps", {})
        self.overlay_transforms = data.get("overlay_transforms", {})
        _tv = data.get("transform_version", 0)
        _needs_legacy_migration = _tv < 3 and bool(self.overlay_transforms)
        _needs_level_migration = _tv < 5 and bool(self.overlay_transforms)
        hdr_idx = data.get("current_hdr_idx", 0)
        if 0 <= hdr_idx < len(self.hdr_files):
            self.current_hdr_idx = hdr_idx
        self.current_variant_idx = data.get("current_variant_idx", 0)
        self.selected_parent = data.get("selected_parent", "")
        self.annotation_scale = data.get("annotation_scale", 1.0)
        self.overlay_dpi = data.get("overlay_dpi", _DEFAULT_OVERLAY_DPI)
        self.overlay_visible = data.get("overlay_visible", False)
        self.overlay_alpha = data.get("overlay_alpha", 0.6)
        self.overlay_page_idx = data.get("overlay_page_idx", 0)
        self.overlay_img_width = data.get("overlay_img_width", 0)
        self.overlay_img_height = data.get("overlay_img_height", 0)
        self._restore_visualisation_settings(data)
        self._rebuild_variants()
        if _needs_legacy_migration:
            self._migrate_legacy_overlay_transforms()
        if _needs_level_migration:
            self._migrate_overlay_keys_to_level()
        self._session_load_ok = True
        logger.info(
            "[session-load] transforms=%s pw=%d ph=%d tv=%s vis=%s",
            {k: {kk: round(vv, 6) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in self.overlay_transforms.items()},
            self.overlay_img_width, self.overlay_img_height,
            data.get("transform_version", "?"), self.overlay_visible,
        )
        self.status_message = f"Session loaded ({len(self.rooms)} rooms)"

    def _restore_visualisation_settings(self, data: dict) -> None:
        fc = data.get("falsecolour_settings") or {}
        ct = data.get("contour_settings") or {}
        self.falsecolour_scale    = float(fc.get("scale", 4.0))
        self.falsecolour_n_levels = int(fc.get("n_levels", 10))
        pal = str(fc.get("palette", "spec"))
        self.falsecolour_palette  = pal if pal in ("spec", "def", "pm3d", "hot", "eco", "tbo") else "spec"
        self.contour_scale        = float(ct.get("scale", 2.0))
        self.contour_n_levels     = int(ct.get("n_levels", 4))
        self.last_generated       = data.get("last_generated") or {}

    def load_session(self) -> None:
        if not self.session_path:
            return
        from ..lib.session_io import load_session
        data = load_session(Path(self.session_path))
        if data is None:
            session_file = Path(self.session_path)
            if session_file.exists():
                # File exists but couldn't be parsed — do NOT allow auto-save to
                # overwrite the on-disk session with empty/stale in-memory state.
                logger.warning("[session] Failed to parse %s — auto-save blocked until next successful load", session_file)
                self._session_load_ok = False
                return
            # New project, no session file yet — clear any stale cross-project
            # state first (self.rooms etc. are not reset by open_project), then
            # seed rooms from any .aoi files present, and persist so subsequent
            # opens take the normal path.
            self.rooms = []
            self.df_stamps = {}
            self.overlay_transforms = {}
            self._session_load_ok = True
            seeded = self._maybe_seed_from_aoi_files()
            if seeded > 0:
                logger.info("[session-load] seeded %d rooms from .aoi files", seeded)
                self.save_session()
                self.status_message = f"Seeded {seeded} rooms from .aoi files"
            return
        self.rooms = data.get("rooms", [])
        self._validate_room_hierarchy()
        self.df_stamps = data.get("df_stamps", {})
        self.overlay_transforms = data.get("overlay_transforms", {})
        _tv = data.get("transform_version", 0)
        _needs_legacy_migration = _tv < 3 and bool(self.overlay_transforms)
        _needs_level_migration = _tv < 5 and bool(self.overlay_transforms)
        hdr_idx = data.get("current_hdr_idx", 0)
        if 0 <= hdr_idx < len(self.hdr_files):
            self.current_hdr_idx = hdr_idx
        self.current_variant_idx = data.get("current_variant_idx", 0)
        self.selected_parent = data.get("selected_parent", "")
        self.annotation_scale = data.get("annotation_scale", 1.0)
        self.overlay_dpi = data.get("overlay_dpi", _DEFAULT_OVERLAY_DPI)
        self.overlay_visible = data.get("overlay_visible", False)
        self.overlay_alpha = data.get("overlay_alpha", 0.6)
        self.overlay_page_idx = data.get("overlay_page_idx", 0)
        # Restore cached PDF intrinsic dimensions so overlay_css_transform can
        # compute the correct centring term before rasterization completes.
        self.overlay_img_width = data.get("overlay_img_width", 0)
        self.overlay_img_height = data.get("overlay_img_height", 0)
        self._restore_visualisation_settings(data)
        self._rebuild_variants()
        # Migrate legacy pixel offsets AFTER _rebuild_variants sets image_width.
        if _needs_legacy_migration:
            self._migrate_legacy_overlay_transforms()
        if _needs_level_migration:
            self._migrate_overlay_keys_to_level()
        self._session_load_ok = True
        logger.info(
            "[session-load] transforms=%s pw=%d ph=%d tv=%s vis=%s",
            {k: {kk: round(vv, 6) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in self.overlay_transforms.items()},
            self.overlay_img_width, self.overlay_img_height,
            data.get("transform_version", "?"), self.overlay_visible,
        )
        self.status_message = f"Session loaded ({len(self.rooms)} rooms)"
        if self.overlay_visible and self.overlay_pdf_path and not self.overlay_image_url:
            self._rasterize_current_page()
        self._recompute_df()

    def save_session(self) -> None:
        if not self.session_path:
            return
        from ..lib.session_io import build_session_dict, save_session
        # Write tv=5 (level-keyed, v4 numerics) when all transforms are safe.
        # Only keep tv=1 if genuinely un-migrated legacy transforms remain,
        # so next load re-attempts migration with correct viewport dimensions.
        if not self._legacy_overlay_pending:
            tv = 5
        elif self.overlay_transforms and all(
            t.get("is_manual") for t in self.overlay_transforms.values()
        ):
            tv = 5  # all transforms set by user — safe even if migration was pending
        else:
            tv = 1
        data = build_session_dict(
            rooms=self.rooms, df_stamps=self.df_stamps,
            overlay_transforms=self.overlay_transforms,
            current_hdr_idx=self.current_hdr_idx, current_variant_idx=self.current_variant_idx,
            selected_parent=self.selected_parent, annotation_scale=self.annotation_scale,
            overlay_dpi=self.overlay_dpi, overlay_visible=self.overlay_visible,
            overlay_alpha=self.overlay_alpha,
            overlay_page_idx=self.overlay_page_idx, transform_version=tv,
            overlay_img_width=self.overlay_img_width,
            overlay_img_height=self.overlay_img_height,
            falsecolour_settings={
                "scale": self.falsecolour_scale,
                "n_levels": self.falsecolour_n_levels,
                "palette": self.falsecolour_palette,
            },
            contour_settings={"scale": self.contour_scale, "n_levels": self.contour_n_levels},
            last_generated=dict(self.last_generated),
        )
        save_session(Path(self.session_path), data)

    def force_save(self) -> None:
        self.save_session()
        self.status_message = "Session saved"

    def restart_app(self) -> None:
        """Spawn a detached relaunch of the Archilume app, then kill this process.

        Uses the same ``examples/launch_archilume_app.py`` entry point so the new
        instance runs the full kill-stale-backends → reflex run flow. The current
        Python process exits half a second later so the Reflex response flushes
        to the client before the socket closes.
        """
        import threading
        try:
            self.save_session()
        except Exception:
            pass
        try:
            repo_root = Path(__file__).resolve().parents[5]
            launch_script = repo_root / "examples" / "launch_archilume_app.py"
            if not launch_script.exists():
                self.status_message = f"Restart failed — launch script not found: {launch_script}"
                return
            kwargs: dict = {"close_fds": True}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([sys.executable, str(launch_script)], **kwargs)
            self.status_message = "Restarting Archilume app…"
            self.status_colour = "accent2"
            # Give the response a moment to flush, then kill this process.
            # The detached relaunch will clear the backend port and start fresh.
            threading.Timer(0.6, lambda: os._exit(0)).start()
        except Exception as e:
            self.status_message = f"Restart failed: {e}"

    def _auto_save(self) -> None:
        if not self._session_load_ok:
            logger.debug("[session] auto-save skipped — no successful load yet")
            return
        self.save_session()
        if self.debug_mode:
            trace.flush()

    def _migrate_overlay_keys_to_level(self) -> None:
        """Collapse per-HDR-stem overlay_transforms into per-level entries.

        Before v5, keys were HDR filename stems (e.g. ``SS_0621_1500``), which in
        sunlight mode produced one slot per timestep frame — 125 independent
        underlay placements per level. v5 keys by level name (view_groups[*]
        .view_name), so all frames of a level share one slot.

        For each level, prefer the stem whose transform has ``is_manual=True``
        (the user's last edit); fall back to the first stem with any transform.
        Daylight sessions (view_groups empty) are untouched — hdr stems already
        act as per-view keys there.
        """
        if not self.overlay_transforms or not self.view_groups:
            return
        stem_to_view = _stem_to_view_map(self.view_groups)
        view_names = {vg["view_name"] for vg in self.view_groups}
        by_level: dict[str, list[dict]] = {}
        passthrough: dict[str, dict] = {}
        for old_key, t in self.overlay_transforms.items():
            if old_key in view_names:
                # Already a level key (idempotent re-run).
                passthrough[old_key] = t
                continue
            level = stem_to_view.get(old_key)
            if level is None:
                # Orphaned stem — not in any current view. Preserve it so we
                # don't silently drop user edits when view_groups change.
                passthrough[old_key] = t
                continue
            by_level.setdefault(level, []).append(t)
        migrated = dict(passthrough)
        for level, entries in by_level.items():
            chosen = next((t for t in entries if t.get("is_manual")), entries[0])
            migrated[level] = chosen
        self.overlay_transforms = migrated
        logger.info("[session-load] migrated overlay_transforms to per-level keys (v5): %d entries", len(migrated))

    def _migrate_legacy_overlay_transforms(self) -> None:
        """Convert legacy offsets to centre-relative image-fraction offsets (v4).

        v1: absolute CSS pixels → image fractions (heuristic: abs > 5)
        v2: viewport-width fractions → image fractions
        v3: top-left-relative image fractions → centre-relative image fractions (v4)
        v4 (current): fractions of HDR image dimensions, displacement of PDF centre
            from HDR centre.
        """
        iw = self.image_width
        ih = self.image_height
        vw = self.viewport_width
        from_version = getattr(self, "_legacy_overlay_from_version", 0)
        # v3→v4 also needs PDF intrinsic dimensions to compute the centring shift.
        needs_pdf = from_version >= 3 or from_version == 0
        pw = self.overlay_img_width
        ph = self.overlay_img_height
        if not iw or not ih or not vw or (needs_pdf and (not pw or not ph)):
            self._legacy_overlay_pending = True
            return
        pdf_aspect = (ph / pw) if (pw and ph) else (ih / iw)
        pdf_h_frac = pdf_aspect * (iw / ih)  # rendered PDF height as fraction of HDR height
        migrated = {}
        for hdr_name, t in self.overlay_transforms.items():
            if t.get("is_manual"):
                # Already v4 — user set this transform manually; never re-migrate.
                migrated[hdr_name] = t
                continue
            t2 = dict(t)
            ox = t.get("offset_x", 0)
            oy = t.get("offset_y", 0)
            sx = t.get("scale_x", 1.0)
            sy = t.get("scale_y", 1.0)
            if from_version < 3:
                if abs(ox) > 5 or abs(oy) > 5:
                    # v1: absolute CSS pixels → image fractions
                    ox = ox / iw
                    oy = oy / ih
                else:
                    # v2: viewport-width fractions → image fractions
                    ox = ox * vw / iw
                    oy = oy * iw / ih
            # v3 → v4: top-left-relative → centre-relative
            t2["offset_x"] = ox + (sx - 1.0) / 2.0
            t2["offset_y"] = oy + (pdf_h_frac * sy - 1.0) / 2.0
            migrated[hdr_name] = t2
        self.overlay_transforms = migrated
        self._legacy_overlay_pending = False
        self._legacy_overlay_from_version = 4

    # =====================================================================
    # PROJECT MANAGEMENT
    # =====================================================================

    # Backend-only scan caches. Scans over a Docker bind-mount (Windows host →
    # Linux container via 9p/virtiofs) are 5–50 ms per syscall; without caching
    # every interaction that opens the modal or progresses project load would
    # walk ``projects/`` again.
    _scan_projects_last: float = 0.0
    _scan_projects_ttl: float = 5.0

    def scan_projects(self, force: bool = False) -> None:
        if not force and (time.time() - self._scan_projects_last) < self._scan_projects_ttl:
            return
        try:
            from archilume.config import PROJECTS_DIR
            if PROJECTS_DIR.exists():
                # Use os.scandir for fewer filesystem calls (is_dir() is free
                # from the directory entry on most OSes — important for Docker
                # bind-mounts where each syscall adds latency).
                with os.scandir(PROJECTS_DIR) as it:
                    self.available_projects = sorted([
                        e.name for e in it
                        if e.is_dir(follow_symlinks=False)
                        and (Path(e.path) / "project.toml").exists()
                    ])
            else:
                self.available_projects = []
            self._scan_projects_last = time.time()
        except ImportError:
            self.available_projects = []

    def open_project(self, name: str):
        """Switch projects by forcing a full page reload with ``?project=NAME``.

        The fresh page load constructs a pristine ``EditorState`` — guaranteed
        zero residue from the outgoing project. All post-reload work
        (``_init_project_paths``, ``load_session``, visualisation regen,
        overlay prefetch, level-window prefetch) runs through
        ``init_on_load`` → ``_open_project_progressive`` exactly as on first
        launch. Persists the outgoing session first so no edits are lost.
        """
        if not name:
            return None
        try:
            self.save_session()
        except Exception:
            logger.exception("[open_project] save_session failed for outgoing project")
        from urllib.parse import quote
        return rx.redirect(f"/?project={quote(name, safe='')}", is_external=True)

    def _open_project_progressive(self, name: str):
        """Open a project with progressive UI updates via yield.

        Used by init_on_load so the UI becomes interactive before heavy
        compute (PDF rasterization, DF analysis) finishes.
        """
        if not name:
            return
        self.is_project_loading = True
        self.save_session()
        self.project = name
        self.status_message = f"Loading {name}..."
        self.status_colour = "accent"

        # Phase 1: paths + file scan (~100ms)
        self._init_project_paths()
        self._rebuild_variants()
        yield

        # Phase 2: session restore (JSON parse, no heavy compute)
        self._load_session_core()
        self.collapse_all_hdrs()
        yield

        # Phase 3: load main image — app feels "ready" after this
        self.load_current_image()
        self.open_project_modal_open = False
        self.is_project_loading = False
        self.status_message = f"Opened: {name}"
        yield

        # Phase 4: deferred heavy compute
        if self.overlay_visible and self.overlay_pdf_path and not self.overlay_image_url:
            self._rasterize_current_page()
            yield
        self._recompute_df()

        # Phase 4b: warm the PDF overlay cache for every (page, dpi) in the
        # background so navigating levels or cycling DPI is cache-served.
        if self.overlay_pdf_path:
            yield EditorState.prefetch_overlay_dpi_cache

        # Warm adjacent-level PNGs so +1/-1 flicks hit the in-memory LRU.
        yield EditorState.prefetch_level_window

        # Phase 5: detect & regenerate any missing/stale falsecolour or contour
        # PNGs in the background. UI is fully interactive at this point.
        yield EditorState.regenerate_visualisation_bg(False)

    def set_new_project_name(self, value: str) -> None:
        self.new_project_name = value

    # set_new_project_mode defined below (purges stale staged files on switch).

    def create_project(self) -> None:
        """Scaffold the project, move staged files into canonical locations, and
        write ``project.toml``. Atomic: on any failure the partially-created
        project dir is rolled back so the user can retry without cleanup.
        """
        import shutil

        name = self.new_project_name.strip()
        if not name:
            self.create_error = "Project name is required"
            return

        try:
            from archilume.config import get_project_paths
        except ImportError:
            self.create_error = "archilume config not available"
            return

        paths = get_project_paths(name)
        if paths.project_dir.exists():
            self.create_error = f"Project '{name}' already exists"
            return

        mode_id = self.new_project_mode
        if mode_id not in project_modes.MODES:
            self.create_error = f"Unknown mode: {mode_id}"
            return

        missing = project_modes.missing_required(mode_id, self.new_project_staged)
        if missing:
            self.create_error = f"Missing: {', '.join(missing)}"
            return

        invalid_combos = project_modes.invalid_combinations(mode_id, self.new_project_staged)
        if invalid_combos:
            self.create_error = invalid_combos[0]
            return

        # Reject if any staged file failed validation.
        invalid = [
            e.get("name", "?")
            for entries in self.new_project_staged.values()
            for e in entries
            if not e.get("ok")
        ]
        if invalid:
            self.create_error = f"Fix invalid files: {', '.join(invalid)}"
            return

        try:
            # Create only project roots. Per-field directories (aoi/, plans/,
            # pic/, image/, …) are made on-demand by their writers — a field
            # with no staged files never creates its dir. This keeps the
            # project layout scoped to the mode's declared fields.
            paths.project_dir.mkdir(parents=True, exist_ok=True)
            paths.inputs_dir.mkdir(parents=True, exist_ok=True)
            paths.archive_dir.mkdir(parents=True, exist_ok=True)
            self._move_staged_into_project(paths, mode_id, self.new_project_staged)
            self._maybe_convert_iesve_room_data(paths)
            self._maybe_convert_sunlight_csv_to_aoi(paths, mode_id)
            self._write_project_toml(name, mode_id, paths)
        except Exception as e:
            shutil.rmtree(paths.project_dir, ignore_errors=True)
            logger.exception("create_project failed")
            self.create_error = f"Create failed: {e}"
            return

        self._cleanup_create_staging_dir()
        self.new_project_staged = {}
        self.create_error = ""
        self.new_project_name = ""

        self.project = name
        self.project_mode = mode_id
        self._init_project_paths()
        self._rebuild_variants()
        self.load_session()
        self.load_current_image()
        self.scan_projects()
        self.create_project_modal_open = False
        self.status_message = f"Created: {name}"
        self.status_colour = "accent"

    def _move_staged_into_project(
        self, paths, mode_id: str, staged: dict[str, list[dict]],
    ) -> None:
        """Move every valid staged file to its canonical destination directory."""
        import shutil

        for field_id, entries in staged.items():
            field = project_modes.field_by_id(mode_id, field_id)
            if field is None:
                continue
            dest_dir = getattr(paths, field.dest_attr, None)
            if dest_dir is None:
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                if not entry.get("ok"):
                    continue
                src = entry.get("path") or ""
                if not src:
                    continue
                shutil.move(src, dest_dir / Path(src).name)

    def _maybe_convert_iesve_room_data(self, paths) -> None:
        """If an ``iesve_room_data.xlsx`` landed in ``aoi_inputs_dir``, convert
        it to the canonical ``room_boundaries.csv``."""
        paths.aoi_inputs_dir.mkdir(parents=True, exist_ok=True)
        xlsx_candidates = sorted(paths.aoi_inputs_dir.glob("*.xlsx"))
        if not xlsx_candidates:
            return
        try:
            from archilume.utils import iesve_aoi_to_room_boundaries_csv
        except ImportError:
            logger.warning("iesve_aoi_to_room_boundaries_csv unavailable; skipping conversion")
            return
        for xlsx in xlsx_candidates:
            try:
                iesve_aoi_to_room_boundaries_csv(
                    xlsx, paths.aoi_inputs_dir / "room_boundaries.csv",
                )
            except Exception as e:
                logger.warning("xlsx conversion failed for %s: %s", xlsx, e)

    def _maybe_convert_sunlight_csv_to_aoi(self, paths, mode_id: str) -> None:
        """Sunlight mode: convert ``room_boundaries.csv`` in ``aoi_inputs_dir``
        to v2 ``.aoi`` files so the downstream seeder picks them up as if the
        user had uploaded ``.aoi`` files directly.

        Skips silently when the CSV is absent or any ``.aoi`` already exists.
        Exclusivity at staging time (``project_modes.invalid_combinations``)
        prevents both-supplied scenarios; the existing-.aoi check here is a
        defensive fallback when projects are created outside the UI.
        """
        if mode_id != "sunlight":
            return
        csv_path = paths.aoi_inputs_dir / "room_boundaries.csv"
        if not csv_path.exists():
            return
        if any(paths.aoi_inputs_dir.glob("*.aoi")):
            logger.info(
                "[sunlight_csv] .aoi files already present in %s; skipping CSV conversion",
                paths.aoi_inputs_dir,
            )
            return
        from ..lib.sunlight_csv import SunlightCsvError, convert_csv_to_aoi_files
        try:
            written = convert_csv_to_aoi_files(csv_path, paths.aoi_inputs_dir)
        except SunlightCsvError as e:
            logger.warning("room_boundaries.csv conversion failed: %s", e)
            return
        logger.info("[sunlight_csv] generated %d .aoi files from %s", len(written), csv_path.name)

    def _write_project_toml(self, name: str, mode_id: str, paths) -> None:
        """Write ``project.toml`` referencing only the files present for this mode."""

        paths.project_dir.mkdir(parents=True, exist_ok=True)
        toml_path = paths.project_dir / "project.toml"
        lines = [
            "[project]",
            f'name = "{name}"',
            f'mode = "{mode_id}"',
            "",
            "[paths]",
        ]
        mode = project_modes.MODES[mode_id]
        for f in mode.fields:
            dest_dir = getattr(paths, f.dest_attr, None)
            if dest_dir is None or not dest_dir.exists():
                continue
            hits: list[str] = []
            for ext in f.allowed_extensions:
                hits.extend(sorted(str(p.relative_to(paths.project_dir)).replace("\\", "/")
                                   for p in dest_dir.glob(f"*{ext}")))
            if not hits:
                continue
            if f.multiple:
                lines.append(f'{f.id} = {hits!r}')
            else:
                lines.append(f'{f.id} = "{hits[0]}"')
        toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # =====================================================================
    # APPLY SETTINGS
    # =====================================================================

    def apply_settings(self) -> None:
        """Apply staged replacements / additions and confirmed removals to the
        current project. Overwrites canonical files in place. Refuses to run if
        a required field would be left empty.
        """
        import shutil

        if not self.project:
            self.settings_error = "No project loaded"
            return
        paths = self._current_project_paths()
        if paths is None:
            self.settings_error = "Could not resolve project paths"
            return

        invalid = [
            e.get("name", "?")
            for entries in self.settings_staged.values()
            for e in entries
            if not e.get("ok")
        ]
        if invalid:
            self.settings_error = f"Fix invalid files: {', '.join(invalid)}"
            return

        violated = self._settings_required_field_violations(paths)
        if violated:
            self.settings_error = f"Cannot remove required inputs: {', '.join(violated)}"
            return

        try:
            # 1. Apply confirmed removals.
            for field_id, removals in self.settings_pending_removals.items():
                field = project_modes.field_by_id(self.project_mode, field_id)
                if field is None:
                    continue
                dest_dir = getattr(paths, field.dest_attr, None)
                if dest_dir is None or not dest_dir.exists():
                    continue
                for fname in removals:
                    (dest_dir / fname).unlink(missing_ok=True)

            # 2. Move staged files in (overwriting in place).
            self._move_staged_into_project(paths, self.project_mode, self.settings_staged)

            # 3. Re-run xlsx -> csv conversion in case room data was replaced.
            self._maybe_convert_iesve_room_data(paths)

            # 4. Sunlight only: regenerate .aoi files when a new CSV was staged.
            self._maybe_convert_sunlight_csv_to_aoi(paths, self.project_mode)

            # 5. Rewrite project.toml so paths reflect the new canonical set.
            self._write_project_toml(self.project, self.project_mode, paths)
        except Exception as e:
            logger.exception("apply_settings failed")
            self.settings_error = f"Apply failed: {e}"
            return

        self._cleanup_settings_staging_dir()
        self.settings_staged = {}
        self.settings_pending_removals = {}
        self.settings_error = ""
        self.settings_modal_open = False

        # Reload session & current image so the editor picks up new files.
        self._init_project_paths()
        self._rebuild_variants()
        self.load_session()
        self.load_current_image()
        self.status_message = "Project inputs updated"
        self.status_colour = "accent"

    def _init_project_paths(self) -> None:
        if not self.project:
            return
        self.overlay_pdf_path = ""
        self.overlay_image_url = ""
        self.overlay_visible = False
        self.overlay_page_idx = 0
        self.overlay_page_count = 0
        self.overlay_img_width = 0
        self.overlay_img_height = 0
        try:
            from archilume.config import get_project_paths
            from ..lib import project_migration
            # Upgrade legacy project.toml ("archilume"/"hdr"/"iesve") to the
            # new four-mode taxonomy in place. Idempotent — no-op if already new.
            migrated = project_migration.migrate_project_toml(self.project)
            if migrated is not None:
                self.project_mode = migrated
                self.status_message = f"Migrated project mode → {migrated}"
                self.status_colour = "accent2"
            paths = get_project_paths(self.project)
            # For daylight projects, prefer the user-supplied .pic directory when
            # it actually contains images (markup flow). Fall back to
            # outputs/image/ for sunlight and for daylight-sim projects that
            # haven't rendered yet. A project.toml override below wins over both.
            image_dir = paths.image_dir
            if self.project_mode == "daylight" and paths.pic_dir.exists():
                if any(paths.pic_dir.glob("*.pic")) or any(paths.pic_dir.glob("*.hdr")):
                    image_dir = paths.pic_dir
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
                        else:
                            logger.warning("[overlay] persisted pdf_path not found: %s", pdf_path_str)
                            self.status_message = f"Saved floor plan not found: {pdf_path_str}"
                            self.status_colour = "accent2"
                        # Populate page count so prefetch knows how many pages
                        # to warm in the background.
                        if self.overlay_pdf_path:
                            from ..lib.image_loader import get_pdf_page_count
                            self.overlay_page_count = get_pdf_page_count(Path(self.overlay_pdf_path))
                except Exception:
                    pass
            self.session_path = str(paths.aoi_inputs_dir / "aoi_session.json")
            trace.set_project_path(paths.project_dir)
            from ..lib.image_loader import scan_hdr_files, read_hdr_view_params, scan_sunlight_view_groups
            self.hdr_files = scan_hdr_files(image_dir)
            # Read VIEW parameters from each HDR for accurate reprojection
            vp_map: dict[str, list[float]] = {}
            for hdr_info in self.hdr_files:
                params = read_hdr_view_params(Path(hdr_info["hdr_path"]))
                if params is not None:
                    vp_map[hdr_info["name"]] = list(params)
            self.hdr_view_params = vp_map

            # Sunlight: group HDRs into per-view timeseries; migrate room
            # hdr_file keys from per-frame stems to the view label so rooms
            # apply across every timestep of that view.
            self.view_groups = []
            self.current_view_idx = 0
            self.current_frame_idx = 0
            if self.project_mode == "sunlight":
                sky_stems: list[str] = []
                if paths.sky_dir.exists():
                    sky_stems = [p.stem for p in paths.sky_dir.glob("*.sky")]
                self.view_groups = scan_sunlight_view_groups(image_dir, sky_stems)
                if self.view_groups:
                    missing_pngs = [
                        Path(frame["hdr_path"])
                        for group in self.view_groups
                        for frame in group["frames"]
                        if not Path(frame["png_path"]).exists()
                    ]
                    if missing_pngs:
                        from archilume.post.hdr_to_png import convert_hdrs_to_pngs
                        print(
                            f"[archilume-app] {len(missing_pngs)} sunlight frames missing "
                            f".png siblings — regenerating from HDR..."
                        )
                        convert_hdrs_to_pngs(missing_pngs)
                    self._migrate_sunlight_room_keys()
                    first_frame = self.view_groups[0]["frames"][0]
                    for i, h in enumerate(self.hdr_files):
                        if h["name"] == first_frame["hdr_stem"]:
                            self.current_hdr_idx = i
                            break
            if self.overlay_pdf_path:
                from ..lib.image_loader import get_pdf_page_count
                self.overlay_page_count = get_pdf_page_count(Path(self.overlay_pdf_path))
        except ImportError:
            pass

    def init_on_load(self):
        self.scan_projects(force=True)
        yield

        # Clear process-scoped caches on every boot (including project-switch
        # reloads). image_loader caches are path-keyed and live in the server
        # process — without this, same-filename assets across projects could
        # collide. _df_cache is a single-entry singleton on this module.
        from ..lib.image_loader import clear_cache as clear_image_loader_caches
        clear_image_loader_caches()
        _df_cache["image"] = None
        _df_cache["hdr_path"] = ""

        # Project target: URL query (?project=NAME) takes precedence over the
        # env var so the reload-based switch in open_project lands on the right
        # project. Falls back to ARCHILUME_INITIAL_PROJECT, then to auto-open
        # when there is exactly one project available.
        try:
            query_params = dict(self.router.url.query_parameters)
        except Exception:
            query_params = {}
        query_project = str(query_params.get("project", "")).strip()
        initial = query_project or os.environ.get("ARCHILUME_INITIAL_PROJECT", "").strip()
        if initial and initial in self.available_projects:
            yield from self._open_project_progressive(initial)
        elif len(self.available_projects) == 1:
            yield from self._open_project_progressive(self.available_projects[0])

    # =====================================================================
    # UI CHROME TOGGLES
    # =====================================================================

    def toggle_project_tree(self) -> None:
        self.project_tree_open = not self.project_tree_open

    def toggle_floor_plan_section(self) -> None:
        self.floor_plan_section_open = not self.floor_plan_section_open

    def toggle_visualisation_section(self) -> None:
        self.visualisation_section_open = not self.visualisation_section_open

    def toggle_room_browser_section(self) -> None:
        self.room_browser_section_open = not self.room_browser_section_open




    def open_shortcuts_modal(self) -> None:
        self.shortcuts_modal_open = True

    def close_shortcuts_modal(self) -> None:
        self.shortcuts_modal_open = False

    def open_open_project_modal(self) -> None:
        self.scan_projects(force=True)
        self.open_project_modal_open = True

    async def upload_open_project_archive(self, files: list[rx.UploadFile]):
        """Browser-side Browse for Open Project: user uploads a ``.zip`` of a
        project folder, the backend extracts it into ``PROJECTS_DIR`` and
        opens it.

        The zip is expected to contain either ``project.toml`` at the root or
        a single top-level directory that contains ``project.toml`` (the
        common "zip a folder" shape). The extracted project is named after
        its top-level directory (or the zip stem when the toml is at the
        root), with a ``-N`` suffix appended if the name already exists.
        """
        import shutil
        import tempfile
        import zipfile

        if not files:
            return None
        upload = files[0]
        try:
            raw_name = Path(upload.name).name
        except Exception:
            raw_name = "upload.zip"
        if Path(raw_name).suffix.lower() != ".zip":
            return rx.toast.error("Browse expects a .zip archive of a project folder")

        try:
            from archilume.config import PROJECTS_DIR
        except ImportError:
            return rx.toast.error("Projects directory not configured")
        projects_dir = Path(PROJECTS_DIR).resolve()
        projects_dir.mkdir(parents=True, exist_ok=True)

        try:
            data = await upload.read()
        except Exception as exc:
            return rx.toast.error(f"Failed to read upload: {exc}")

        tmp_root = Path(tempfile.mkdtemp(prefix="archilume-open-"))
        zip_path = tmp_root / raw_name
        extract_dir = tmp_root / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            zip_path.write_bytes(data)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                return rx.toast.error("Not a valid zip archive")

            # Find project.toml — either at the extract root or one level deep
            # in a single top-level folder (the common "zip a folder" shape).
            if (extract_dir / "project.toml").exists():
                source_dir = extract_dir
                default_name = Path(raw_name).stem
            else:
                top_entries = [p for p in extract_dir.iterdir() if p.is_dir()]
                source_dir = next(
                    (p for p in top_entries if (p / "project.toml").exists()),
                    None,
                )
                if source_dir is None:
                    return rx.toast.error(
                        "Archive does not contain a project.toml at its root"
                    )
                default_name = source_dir.name

            base = default_name or "project"
            name = base
            suffix = 1
            while (projects_dir / name).exists():
                name = f"{base}-{suffix}"
                suffix += 1
            dest = projects_dir / name
            try:
                shutil.copytree(source_dir, dest)
            except OSError as exc:
                return rx.toast.error(f"Failed to import project: {exc}")
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

        self.open_project_modal_open = False
        self.scan_projects(force=True)
        return [
            self.open_project(name),
            rx.toast.success(f"Imported project '{name}'"),
        ]

    def pick_and_add_external_project(self):
        """Pick a project folder and link it into PROJECTS_DIR.

        Tries the native OS folder dialog first. When that is unavailable
        (headless Docker backend, no display) falls back to an in-browser
        server-side folder browser modal that navigates the container
        filesystem. Either way the selection is validated (must contain
        ``project.toml``) and, if outside PROJECTS_DIR, linked in via a
        directory junction (Windows) or symlink (POSIX).
        """
        try:
            import tkinter as tk
            from tkinter import filedialog
        except (ImportError, ModuleNotFoundError):
            return self.open_external_browser()

        try:
            from archilume.config import HOST_PROJECTS_DIR
        except ImportError:
            return rx.toast.error("Projects directory not configured")

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            picked = filedialog.askdirectory(
                title="Select archilume project folder",
                initialdir=HOST_PROJECTS_DIR,
            )
            root.destroy()
        except tk.TclError:
            return self.open_external_browser()

        if not picked:
            return None

        return self._link_external_project(Path(picked).resolve())

    def _link_external_project(self, picked_path: Path):
        """Validate ``picked_path`` and link it into PROJECTS_DIR, then open.

        Shared by the native tkinter picker and the server-side browser
        fallback. Returns a toast event on failure, or ``None`` on success
        after opening the project.
        """
        try:
            from archilume.config import PROJECTS_DIR
        except ImportError:
            return rx.toast.error("Projects directory not configured")

        if not picked_path.is_dir():
            return rx.toast.error("Not a folder")
        if not (picked_path / "project.toml").exists():
            return rx.toast.error("Not a valid archilume project — missing project.toml")

        projects_dir = Path(PROJECTS_DIR).resolve()
        try:
            picked_path.relative_to(projects_dir)
            name = picked_path.name
        except ValueError:
            projects_dir.mkdir(parents=True, exist_ok=True)
            base = picked_path.name
            name = base
            suffix = 1
            while (projects_dir / name).exists():
                name = f"{base}-{suffix}"
                suffix += 1
            link_path = projects_dir / name
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(link_path), str(picked_path)],
                        capture_output=True, text=True,
                    )
                    if result.returncode != 0:
                        return rx.toast.error(
                            f"Failed to link project: {result.stderr.strip() or result.stdout.strip()}"
                        )
                else:
                    os.symlink(picked_path, link_path, target_is_directory=True)
            except OSError as exc:
                return rx.toast.error(f"Failed to link project: {exc}")

        self.scan_projects(force=True)
        return self.open_project(name)

    # --- server-side folder browser (fallback for headless backends) -------

    def _scan_browser_dir(self, path: Path) -> list[dict[str, Any]]:
        """List directory entries of ``path`` for the server-side browser.

        In ``project`` mode returns sub-directories only, flagging those that
        contain ``project.toml``. In ``settings_file`` mode also returns files
        whose suffix is in ``external_browser_allowed_extensions``.
        """
        entries: list[dict[str, Any]] = []
        file_mode = self.external_browser_mode == "settings_file"
        allowed = {ext.lower() for ext in self.external_browser_allowed_extensions}
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        child = Path(e.path)
                        if e.is_dir(follow_symlinks=False):
                            is_project = (child / "project.toml").exists()
                            entries.append({
                                "name": e.name,
                                "path": str(child),
                                "kind": "dir",
                                "is_project": is_project,
                            })
                        elif file_mode and e.is_file(follow_symlinks=False):
                            if Path(e.name).suffix.lower() in allowed:
                                entries.append({
                                    "name": e.name,
                                    "path": str(child),
                                    "kind": "file",
                                    "is_project": False,
                                })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError) as exc:
            self.external_browser_error = f"Cannot read directory: {exc}"
            return []
        self.external_browser_error = ""
        # Directories first, projects above plain dirs, then files; alpha within groups.
        def _key(x: dict[str, Any]) -> tuple:
            kind_rank = 0 if x["kind"] == "dir" else 1
            proj_rank = 0 if x.get("is_project") else 1
            return (kind_rank, proj_rank, x["name"].lower())
        entries.sort(key=_key)
        return entries

    def open_external_browser(self) -> None:
        try:
            from archilume.config import HOST_PROJECTS_DIR
        except ImportError:
            self.external_browser_error = "Projects directory not configured"
            HOST_PROJECTS_DIR = str(Path.cwd())
        start = Path(HOST_PROJECTS_DIR)
        if not start.exists() or not start.is_dir():
            start = Path("/") if sys.platform != "win32" else Path(start.anchor or "C:\\")
        self.open_project_modal_open = False
        # Reset file-mode metadata so a leftover settings Browse doesn't
        # leak file listings into the Open-Project dialog.
        self.external_browser_mode = "project"
        self.external_browser_target_field = ""
        self.external_browser_allowed_extensions = []
        self.external_browser_multiple = False
        self.external_browser_path = str(start)
        self.external_browser_entries = self._scan_browser_dir(start)
        self.external_browser_open = True

    def close_external_browser(self) -> None:
        self.external_browser_open = False

    def external_browser_navigate(self, path: str) -> None:
        target = Path(path)
        if not target.is_dir():
            self.external_browser_error = "Not a directory"
            return
        self.external_browser_path = str(target)
        self.external_browser_entries = self._scan_browser_dir(target)

    def external_browser_go_up(self) -> None:
        current = Path(self.external_browser_path) if self.external_browser_path else Path("/")
        parent = current.parent
        if parent == current:
            return
        self.external_browser_path = str(parent)
        self.external_browser_entries = self._scan_browser_dir(parent)

    def external_browser_select(self, path: str):
        if self.external_browser_mode == "settings_file":
            return self._select_settings_browser_file(Path(path).resolve())
        result = self._link_external_project(Path(path).resolve())
        if result is None:
            self.external_browser_open = False
        return result

    def _select_settings_browser_file(self, picked: Path):
        """Stage a file picked from the server-side browser into the active
        settings field, then close the browser. The settings modal remains
        open underneath, showing the staged file in its ✓/✗ row list."""
        field_id = self.external_browser_target_field
        if not field_id:
            self.external_browser_error = "No target field set"
            return None
        if not picked.is_file():
            self.external_browser_error = "Not a file"
            return None
        try:
            data = picked.read_bytes()
        except OSError as exc:
            self.external_browser_error = f"Cannot read file: {exc}"
            return None
        self._stage_uploaded_files(
            field_id,
            [_StagedUploadBytes(name=picked.name, data=data)],
            target="settings",
        )
        self.external_browser_open = False
        return None

    def close_open_project_modal(self) -> None:
        self.open_project_modal_open = False

    def open_create_project_modal(self) -> None:
        import tempfile
        self._cleanup_create_staging_dir()
        self.new_project_staging_dir = tempfile.mkdtemp(prefix="archilume-new-")
        self.new_project_staged = {}
        self.create_error = ""
        self.create_project_modal_open = True

    def close_create_project_modal(self) -> None:
        self._cleanup_create_staging_dir()
        self.new_project_staged = {}
        self.create_error = ""
        self.new_project_name = ""
        self.create_project_modal_open = False

    def _cleanup_create_staging_dir(self) -> None:
        import shutil
        if self.new_project_staging_dir:
            shutil.rmtree(self.new_project_staging_dir, ignore_errors=True)
        self.new_project_staging_dir = ""

    # =====================================================================
    # CREATE PROJECT — per-file upload handling
    # =====================================================================

    def _stage_uploaded_files(
        self,
        field_id: str,
        upload_files: list,
        target: str,
    ) -> None:
        """Shared helper: move Reflex-uploaded files into the active staging
        dir, validate each, and record entries in the matching staged dict.

        ``target`` is either ``"create"`` or ``"settings"``.
        """
        import shutil

        if target == "create":
            staging_dir = self.new_project_staging_dir
            staged = dict(self.new_project_staged)
            mode_id = self.new_project_mode
        else:
            staging_dir = self.settings_staging_dir
            staged = dict(self.settings_staged)
            mode_id = self.project_mode

        if not staging_dir:
            return
        field = project_modes.field_by_id(mode_id, field_id)
        if field is None:
            return

        existing = list(staged.get(field_id, []))
        staging_path = Path(staging_dir)
        staging_path.mkdir(parents=True, exist_ok=True)

        # Single-document fields (e.g. PDF, room_boundaries.csv) must never
        # accumulate more than one file. A fresh drop replaces whatever was
        # staged before — the old staged copy is unlinked so it doesn't leak.
        if not field.multiple and upload_files:
            for prior in existing:
                p = prior.get("path") or ""
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass
            existing = []
            # Honour only the LAST upload in the batch. rx.upload with
            # multiple=False shouldn't deliver >1 file, but guard anyway.
            upload_files = upload_files[-1:]
            # In settings mode, a single-doc drop implies replacing the
            # existing canonical file; mark every canonical entry in this
            # field for removal so apply_settings doesn't leave duplicates.
            if target == "settings":
                paths = self._current_project_paths()
                if paths is not None:
                    dest_dir = getattr(paths, field.dest_attr, None)
                    if dest_dir is not None and dest_dir.exists():
                        pending = dict(self.settings_pending_removals)
                        marks = list(pending.get(field_id, []))
                        for ext_ in field.allowed_extensions:
                            for p in dest_dir.glob(f"*{ext_}"):
                                if p.name not in marks:
                                    marks.append(p.name)
                        if marks:
                            pending[field_id] = marks
                            self.settings_pending_removals = pending

        for upload in upload_files:
            try:
                raw_name = Path(upload.name).name
            except Exception:
                raw_name = "upload.bin"
            ext = Path(raw_name).suffix.lower()
            if ext not in field.allowed_extensions:
                existing.append({
                    "path": "",
                    "name": raw_name,
                    "ok": False,
                    "error": f"Unsupported extension {ext or '(none)'}",
                })
                continue

            dest = staging_path / raw_name
            # Avoid collisions if user uploads files with the same name twice.
            counter = 1
            while dest.exists():
                stem, ext_ = Path(raw_name).stem, Path(raw_name).suffix
                dest = staging_path / f"{stem}__{counter}{ext_}"
                counter += 1
            try:
                dest.write_bytes(upload.data)
            except Exception as e:
                existing.append({
                    "path": "",
                    "name": raw_name,
                    "ok": False,
                    "error": f"Upload failed: {e}",
                })
                continue

            ok, msg = field.validator(dest)
            if not ok:
                # Keep the file on disk so the user sees the failed row, but
                # mark as invalid. Removed when they click the row's X.
                pass
            existing.append({
                "path": str(dest),
                "name": dest.name,
                "ok": bool(ok),
                "error": "" if ok else msg,
            })

        staged[field_id] = existing
        if target == "create":
            self.new_project_staged = staged
        else:
            self.settings_staged = staged

    async def _read_and_stage(
        self, files: list[rx.UploadFile], field_id: str, target: str,
    ) -> None:
        """Common path for create and settings uploads.

        ``target`` is either ``"create"`` or ``"settings"``. Called from thin
        per-field wrappers below — Reflex's event-handler validator requires
        handler signatures to match the event payload exactly, so we can't
        parameterise the field id directly on the upload event. The wrappers
        bake the field id in and delegate here.
        """
        read_files = []
        for f in files:
            try:
                data = await f.read()
                read_files.append(_StagedUploadBytes(name=f.name, data=data))
            except Exception as e:
                logger.warning("upload read failed for %s: %s", getattr(f, "name", "?"), e)
        self._stage_uploaded_files(field_id, read_files, target)

    # --- Create flow: one handler per field_id ---------------------------
    async def upload_create_pdf(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "pdf", "create")
    async def upload_create_geometry(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "geometry", "create")
    async def upload_create_hdr_results(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "hdr_results", "create")
    async def upload_create_pic_results(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "pic_results", "create")
    async def upload_create_oct(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "oct", "create")
    async def upload_create_rdp(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "rdp", "create")
    async def upload_create_room_data(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "room_data", "create")
    async def upload_create_aoi_files(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "aoi_files", "create")

    # --- Settings flow: one handler per field_id -------------------------
    async def upload_settings_pdf(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "pdf", "settings")
    async def upload_settings_geometry(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "geometry", "settings")
    async def upload_settings_hdr_results(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "hdr_results", "settings")
    async def upload_settings_pic_results(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "pic_results", "settings")
    async def upload_settings_oct(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "oct", "settings")
    async def upload_settings_rdp(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "rdp", "settings")
    async def upload_settings_room_data(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "room_data", "settings")
    async def upload_settings_aoi_files(self, files: list[rx.UploadFile]) -> None:
        await self._read_and_stage(files, "aoi_files", "settings")

    # --- Settings "Browse…" button -----------------------------------------
    # Opens a native OS file picker at the field's canonical destination dir
    # so the user lands where the existing file already lives. Falls back to
    # the server-side in-browser file picker when tkinter is unavailable
    # (e.g. headless Docker backend).
    def pick_settings_field_file(self, field_id: str):
        field = project_modes.field_by_id(self.project_mode, field_id)
        if field is None:
            return rx.toast.error(f"Unknown field: {field_id}")
        paths = self._current_project_paths()
        initial_dir: Optional[Path] = None
        if paths is not None:
            candidate = getattr(paths, field.dest_attr, None)
            if candidate is not None and candidate.exists():
                initial_dir = candidate
        if initial_dir is None:
            try:
                from archilume.config import PROJECTS_DIR
                initial_dir = Path(PROJECTS_DIR)
            except ImportError:
                initial_dir = Path.cwd()

        try:
            import tkinter as tk
            from tkinter import filedialog
        except (ImportError, ModuleNotFoundError):
            return self.open_settings_file_browser(field_id, initial_dir)

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            filetypes = [
                (f"{ext.lstrip('.').upper()} files", f"*{ext}")
                for ext in field.allowed_extensions
            ]
            filetypes.append(("All files", "*.*"))
            if field.multiple:
                picked = filedialog.askopenfilenames(
                    title=f"Select {field.label}",
                    filetypes=filetypes,
                    initialdir=str(initial_dir),
                )
                picked_paths = [Path(p) for p in (picked or ())]
            else:
                picked = filedialog.askopenfilename(
                    title=f"Select {field.label}",
                    filetypes=filetypes,
                    initialdir=str(initial_dir),
                )
                picked_paths = [Path(picked)] if picked else []
            root.destroy()
        except tk.TclError:
            return self.open_settings_file_browser(field_id, initial_dir)

        if not picked_paths:
            return None

        staged: list[_StagedUploadBytes] = []
        for p in picked_paths:
            try:
                staged.append(_StagedUploadBytes(name=p.name, data=p.read_bytes()))
            except OSError as exc:
                logger.warning("settings pick read failed for %s: %s", p, exc)
        if staged:
            self._stage_uploaded_files(field_id, staged, target="settings")
        return None

    def open_settings_file_browser(self, field_id: str, initial_dir: Optional[Path] = None):
        """Fallback server-side file picker for the settings Browse button.
        Starts at the field's canonical destination dir so the user lands
        next to the existing file."""
        field = project_modes.field_by_id(self.project_mode, field_id)
        if field is None:
            return rx.toast.error(f"Unknown field: {field_id}")
        if initial_dir is None:
            paths = self._current_project_paths()
            if paths is not None:
                candidate = getattr(paths, field.dest_attr, None)
                if candidate is not None and candidate.exists():
                    initial_dir = candidate
        if initial_dir is None or not initial_dir.exists():
            try:
                from archilume.config import PROJECTS_DIR
                initial_dir = Path(PROJECTS_DIR)
            except ImportError:
                initial_dir = Path.cwd()
        self.external_browser_mode = "settings_file"
        self.external_browser_target_field = field_id
        self.external_browser_allowed_extensions = list(field.allowed_extensions)
        self.external_browser_multiple = field.multiple
        self.external_browser_path = str(initial_dir)
        self.external_browser_entries = self._scan_browser_dir(initial_dir)
        self.external_browser_open = True
        return None

    def remove_new_project_file(self, field_id: str, filename: str) -> None:
        self._remove_staged_file(field_id, filename, target="create")

    def _remove_staged_file(self, field_id: str, filename: str, target: str) -> None:
        if target == "create":
            staged = dict(self.new_project_staged)
        else:
            staged = dict(self.settings_staged)
        entries = list(staged.get(field_id, []))
        kept = []
        for entry in entries:
            if entry.get("name") == filename:
                path = entry.get("path") or ""
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                continue
            kept.append(entry)
        if kept:
            staged[field_id] = kept
        else:
            staged.pop(field_id, None)
        if target == "create":
            self.new_project_staged = staged
        else:
            self.settings_staged = staged

    def set_new_project_mode(self, value: str) -> None:
        """Set the mode and purge any staged files that don't belong to it.

        Cross-mode toggles should not carry stale uploads; a file staged for a
        sunlight-sim field is not reachable from the daylight-sim field list.
        """
        if value not in project_modes.MODES:
            return
        old_field_ids = {f.id for f in project_modes.MODES[self.new_project_mode].fields}
        new_field_ids = {f.id for f in project_modes.MODES[value].fields}
        stale = old_field_ids - new_field_ids
        if stale:
            staged = dict(self.new_project_staged)
            for fid in list(stale):
                entries = staged.pop(fid, [])
                for e in entries:
                    p = e.get("path") or ""
                    if p:
                        try:
                            Path(p).unlink(missing_ok=True)
                        except Exception:
                            pass
            self.new_project_staged = staged
        self.new_project_mode = value

    # =====================================================================
    # CREATE PROJECT — computed vars
    # =====================================================================

    @rx.var(
        auto_deps=False,
        deps=["project", "project_mode", "settings_staged", "settings_pending_removals"],
    )
    def settings_mode_fields(self) -> list[dict]:
        """UI-friendly serialisation for the settings modal (current project mode)."""
        mode = project_modes.MODES.get(self.project_mode)
        if mode is None:
            return []
        paths = self._current_project_paths()
        out = []
        for f in mode.fields:
            canonical_files: list[str] = []
            if paths is not None:
                dest = getattr(paths, f.dest_attr, None)
                if dest is not None and dest.exists():
                    for ext in f.allowed_extensions:
                        canonical_files.extend(
                            sorted(p.name for p in dest.glob(f"*{ext}"))
                        )
            out.append({
                "id": f.id,
                "label": f.label,
                "description": f.description,
                "accept_exts": ", ".join(f.allowed_extensions),
                "multiple": f.multiple,
                "required": f.required,
                "one_of": f.one_of or "",
                "canonical_files": canonical_files,
                "pending_removals": list(self.settings_pending_removals.get(f.id, [])),
                "files": self.settings_staged.get(f.id, []),
            })
        return out

    # Per-field accessors so Reflex foreach can hit a typed list var directly,
    # avoiding dict-key access on the dict-typed staged var (which Reflex 0.8
    # exposes only awkwardly).
    @rx.var
    def staged_create_pdf(self) -> list[dict]:
        return self.new_project_staged.get("pdf", [])
    @rx.var
    def staged_create_geometry(self) -> list[dict]:
        return self.new_project_staged.get("geometry", [])
    @rx.var
    def staged_create_hdr_results(self) -> list[dict]:
        return self.new_project_staged.get("hdr_results", [])
    @rx.var
    def staged_create_pic_results(self) -> list[dict]:
        return self.new_project_staged.get("pic_results", [])
    @rx.var
    def staged_create_oct(self) -> list[dict]:
        return self.new_project_staged.get("oct", [])
    @rx.var
    def staged_create_rdp(self) -> list[dict]:
        return self.new_project_staged.get("rdp", [])
    @rx.var
    def staged_create_room_data(self) -> list[dict]:
        return self.new_project_staged.get("room_data", [])
    @rx.var
    def staged_create_aoi_files(self) -> list[dict]:
        return self.new_project_staged.get("aoi_files", [])

    @rx.var
    def staged_settings_pdf(self) -> list[dict]:
        return self.settings_staged.get("pdf", [])
    @rx.var
    def staged_settings_geometry(self) -> list[dict]:
        return self.settings_staged.get("geometry", [])
    @rx.var
    def staged_settings_hdr_results(self) -> list[dict]:
        return self.settings_staged.get("hdr_results", [])
    @rx.var
    def staged_settings_pic_results(self) -> list[dict]:
        return self.settings_staged.get("pic_results", [])
    @rx.var
    def staged_settings_oct(self) -> list[dict]:
        return self.settings_staged.get("oct", [])
    @rx.var
    def staged_settings_rdp(self) -> list[dict]:
        return self.settings_staged.get("rdp", [])
    @rx.var
    def staged_settings_room_data(self) -> list[dict]:
        return self.settings_staged.get("room_data", [])
    @rx.var
    def staged_settings_aoi_files(self) -> list[dict]:
        return self.settings_staged.get("aoi_files", [])

    @rx.var
    def create_exclusivity_error(self) -> str:
        """Sunlight: non-empty when both room_boundaries.csv and .aoi files
        have been staged for the new project. Displayed inline in the modal
        so the user sees the exclusivity rule without clicking Create."""
        errors = project_modes.invalid_combinations(self.new_project_mode, self.new_project_staged)
        return errors[0] if errors else ""

    @rx.var
    def project_mode_display(self) -> str:
        """Human-readable workflow mode label for the header bar.
        Empty when no project is loaded or mode is unknown."""
        if not self.project:
            return ""
        mode = project_modes.MODES.get(self.project_mode)
        return mode.display if mode is not None else ""

    @rx.var(auto_deps=False, deps=["project", "project_mode"])
    def settings_canonical_files(self) -> dict[str, list[str]]:
        """Filenames currently in canonical destination dirs for the active project,
        keyed by field id. Used by the settings modal to show existing files."""
        out: dict[str, list[str]] = {}
        if not self.project:
            return out
        paths = self._current_project_paths()
        if paths is None:
            return out
        mode = project_modes.MODES.get(self.project_mode)
        if mode is None:
            return out
        for f in mode.fields:
            dest = getattr(paths, f.dest_attr, None)
            if dest is None or not dest.exists():
                out[f.id] = []
                continue
            names: list[str] = []
            for ext in f.allowed_extensions:
                names.extend(sorted(p.name for p in dest.glob(f"*{ext}")))
            out[f.id] = names
        return out

    @rx.var
    def create_form_is_valid(self) -> bool:
        name = self.new_project_name.strip()
        if not name:
            return False
        # Fast duplicate-name check without hitting disk every keystroke: rely
        # on scan_projects having populated available_projects. The authoritative
        # check still runs in create_project.
        if name in self.available_projects:
            return False
        missing = project_modes.missing_required(self.new_project_mode, self.new_project_staged)
        if missing:
            return False
        if project_modes.invalid_combinations(self.new_project_mode, self.new_project_staged):
            return False
        # Reject if any staged file failed its validator.
        for entries in self.new_project_staged.values():
            for e in entries:
                if not e.get("ok"):
                    return False
        return True

    @rx.var(
        auto_deps=False,
        deps=["project", "project_mode", "settings_staged", "settings_pending_removals"],
    )
    def settings_form_is_valid(self) -> bool:
        # All staged replacements must be valid.
        for entries in self.settings_staged.values():
            for e in entries:
                if not e.get("ok"):
                    return False
        # Removal integrity: for each required field in the current mode,
        # (canonical files - pending removals) + (staged new files) must be ≥1.
        mode = project_modes.MODES.get(self.project_mode)
        if mode is None:
            return False
        paths = self._current_project_paths()
        if paths is None:
            return False
        violated = self._settings_required_field_violations(paths)
        return not violated

    def _current_project_paths(self):
        if not self.project:
            return None
        try:
            from archilume.config import get_project_paths
            return get_project_paths(self.project)
        except Exception:
            return None

    def _settings_required_field_violations(self, paths) -> list[str]:
        """Return labels of required fields that would end up empty if the
        current set of staged replacements and pending removals were applied.
        """
        mode = project_modes.MODES.get(self.project_mode)
        if mode is None:
            return []
        violated: list[str] = []

        def count_after_apply(field) -> int:
            dest = getattr(paths, field.dest_attr, None)
            count = 0
            if dest is not None and dest.exists():
                for ext in field.allowed_extensions:
                    for p in dest.glob(f"*{ext}"):
                        if p.name not in self.settings_pending_removals.get(field.id, []):
                            count += 1
            for e in self.settings_staged.get(field.id, []):
                if e.get("ok"):
                    count += 1
            return count

        for f in mode.fields:
            if not f.required:
                continue
            if f.one_of:
                continue
            if count_after_apply(f) == 0:
                violated.append(f.label)

        for group_key, members in project_modes.mode_one_of_groups(self.project_mode).items():
            if not any(count_after_apply(m) > 0 for m in members):
                violated.append(" or ".join(m.label for m in members))
        return violated

    # =====================================================================
    # PROJECT SETTINGS MODAL
    # =====================================================================

    def open_settings_modal(self) -> None:
        import tempfile
        if not self.project:
            return
        self._cleanup_settings_staging_dir()
        self.settings_staging_dir = tempfile.mkdtemp(prefix="archilume-settings-")
        self.settings_staged = {}
        self.settings_pending_removals = {}
        self.settings_error = ""
        self.settings_modal_open = True

    def close_settings_modal(self) -> None:
        self._cleanup_settings_staging_dir()
        self.settings_staged = {}
        self.settings_pending_removals = {}
        self.settings_error = ""
        self.settings_modal_open = False

    def _cleanup_settings_staging_dir(self) -> None:
        import shutil
        if self.settings_staging_dir:
            shutil.rmtree(self.settings_staging_dir, ignore_errors=True)
        self.settings_staging_dir = ""

    # handle_settings_upload: replaced by upload_settings_<field_id> per-field
    # handlers defined earlier next to upload_create_<field_id>.

    def remove_settings_staged_file(self, field_id: str, filename: str) -> None:
        """Remove a staged (not-yet-applied) file from the settings modal."""
        self._remove_staged_file(field_id, filename, target="settings")

    def toggle_canonical_removal(self, field_id: str, filename: str) -> None:
        """Mark/unmark an existing canonical file for removal on apply."""
        pending = dict(self.settings_pending_removals)
        current = list(pending.get(field_id, []))
        if filename in current:
            current.remove(filename)
        else:
            current.append(filename)
        if current:
            pending[field_id] = current
        else:
            pending.pop(field_id, None)
        self.settings_pending_removals = pending

    def open_extract_modal(self) -> None:
        self.scan_archives()
        self.extract_modal_open = True

    def close_extract_modal(self) -> None:
        self.extract_modal_open = False

    # =====================================================================
    # KEYBOARD HANDLER
    # =====================================================================

    def log_js_trace(self, payload: dict) -> None:
        """Sink for JS-side tracer messages — logs one line per event to the
        unified trace file (``~/.archilume/logs/archilume_app.log``) when
        ``debug_mode`` is enabled.

        Invoked via ``window.applyEvent('editor_state.log_js_trace', {...})``.
        If the payload carries a ``rid`` field, it's adopted as the active
        correlation ID for the duration of this log line so JS traces
        interleave cleanly with backend handler traces.
        """
        if not self.debug_mode:
            return
        try:
            tag = payload.get("tag", "?")
            rid = payload.get("rid")
            if rid:
                with with_correlation_id(rid):
                    logger.debug(f"[JS:{tag}] {payload}")
            else:
                logger.debug(f"[JS:{tag}] {payload}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[JS:err] failed to log trace: {exc}")

    def handle_key_event(self, key: str, key_info: dict):  # type: ignore[override]
        """Route keyboard events from the Reflex on_key_down handler.

        This is the correct Reflex pattern — compiled to addEvents, not window.applyEvent.
        key_info contains: alt_key, ctrl_key, meta_key, shift_key.

        A fresh correlation ID is allocated per keystroke so sub-handlers
        (``handle_key`` → ``nudge_overlay`` → state change) share a rid
        that makes the chain trivially greppable in the unified log.
        """
        # Skip modifier-only keys — they generate noise with no action
        if key in ("Shift", "Control", "Alt", "Meta"):
            return

        with with_correlation_id(new_correlation_id()):
            # Unconditional arrow-key tracer — proves Reflex's
            # window_event_listener actually received the event.
            if self.debug_mode and key.startswith("Arrow"):
                logger.debug(
                    f"[PY:handle_key_event] received key={key!r} | "
                    f"overlay_align_mode={self.overlay_align_mode} "
                    f"overlay_visible={self.overlay_visible} "
                    f"viewport_width={self.viewport_width} "
                    f"key_info={key_info}"
                )
            yield from self._handle_key_event_body(key, key_info)

    def _handle_key_event_body(self, key: str, key_info: dict):
        """Core key dispatch, split out so ``handle_key_event`` can wrap it
        in a ``with_correlation_id`` block without cluttering the logic."""

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
            if shift:
                logger.debug("  → routing to: redo()")
                self.redo()
            else:
                logger.debug("  → routing to: undo()")
                self.undo()
        elif ctrl and key.lower() == "y":
            logger.debug("  → routing to: redo()")
            self.redo()
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
            if self.edit_mode:
                logger.debug("  → routing to: delete_hovered_vertex()")
                self.delete_hovered_vertex()
            elif self.selected_room_idx >= 0 or self.multi_selected_idxs:
                logger.debug("  → routing to: delete_room()")
                self.delete_room()
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
                    self.divider_room_name = self.rooms[self.selected_room_idx].get("name", "")
                    yield from self.fit_zoom()
                self.status_message = "Divider mode — click to place cut line, S to split, Esc to cancel"
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
        elif k == "g":
            logger.debug(f"  handle_key 'g' → toggle_pan_mode (was {self.pan_mode})")
            self.toggle_pan_mode()
        elif k == "t":
            logger.debug(f"  handle_key 't' → toggle_image_variant (idx={self.current_variant_idx})")
            self.toggle_image_variant()
        elif k == "c":
            logger.debug(
                f"  handle_key 'c' → cycle_room_type (selected={self.selected_room_idx} "
                f"multi={len(self.multi_selected_idxs)})"
            )
            if self.selected_room_idx >= 0 or self.multi_selected_idxs:
                idx = (
                    self.selected_room_idx
                    if self.selected_room_idx >= 0
                    else self.multi_selected_idxs[0]
                )
                self.cycle_room_type(idx)
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
            if self.overlay_align_mode:
                step = self._arrow_accel("up")
                logger.debug(f"  handle_key 'ArrowUp' → nudge_overlay(0, -{step})")
                self.nudge_overlay(0, -step)
            else:
                logger.debug(
                    f"  handle_key 'ArrowUp' → navigate_level(1) "
                    f"(sunlight={self.is_sunlight_mode} view_idx={self.current_view_idx} "
                    f"hdr_idx={self.current_hdr_idx})"
                )
                self.navigate_level(1)
                yield EditorState.prefetch_level_window
        elif k == "ArrowDown":
            if self.overlay_align_mode:
                step = self._arrow_accel("down")
                logger.debug(f"  handle_key 'ArrowDown' → nudge_overlay(0, {step})")
                self.nudge_overlay(0, step)
            else:
                logger.debug(
                    f"  handle_key 'ArrowDown' → navigate_level(-1) "
                    f"(sunlight={self.is_sunlight_mode} view_idx={self.current_view_idx} "
                    f"hdr_idx={self.current_hdr_idx})"
                )
                self.navigate_level(-1)
                yield EditorState.prefetch_level_window
        elif k == "ArrowLeft":
            if self.overlay_align_mode:
                step = self._arrow_accel("left")
                logger.debug(f"  handle_key 'ArrowLeft' → nudge_overlay(-{step}, 0)")
                self.nudge_overlay(-step, 0)
        elif k == "ArrowRight":
            if self.overlay_align_mode:
                step = self._arrow_accel("right")
                logger.debug(f"  handle_key 'ArrowRight' → nudge_overlay({step}, 0)")
                self.nudge_overlay(step, 0)
        else:
            logger.debug(f"  handle_key '{k}' → no matching action (unbound key)")

