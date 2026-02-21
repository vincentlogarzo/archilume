"""
Interactive Room Boundary Editor for HDR/TIFF rendered floor plan images.

Draws apartment and sub-room boundaries on top of HDR or associated TIFF images.
JSON and CSV are saved automatically alongside the image_dir on every save/delete.

Naming convention:
    U101          apartment boundary
    U101_BED1     sub-room (auto-prefixed when parent is selected)

Controls:
    ↑/↓           Navigate HDR files
    t             Toggle image variant (HDR / TIFFs)
    Left-click    Place vertex (draw) or drag vertex (edit mode)
    Shift+click   Drag entire edge in edit mode (moves both endpoints together)
    Right-click   Select existing room
    Scroll        Zoom centred on cursor
    s             Save room / confirm edit
    d             Delete selected room
    e             Toggle Edit Mode
    Ctrl+Z        Undo last vertex edit (edit mode)
    o             Toggle orthogonal lines (H/V snap)
    r             Reset zoom
    q             Quit

Workflow:
    1. Navigate to the desired HDR file with ↑/↓
    2. Draw apartment boundary → name "U101" → Save
    3. Select "U101" as parent
    4. Draw sub-rooms (e.g. "BED1" → auto-saved as "U101_BED1")
    5. Repeat for each HDR file / floor
"""

# fmt: off
# autopep8: off

# Standard library imports
import csv
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

# Third-party imports
import matplotlib.pyplot as plt
from matplotlib.widgets import PolygonSelector, TextBox, Button
from matplotlib.patches import Polygon, FancyBboxPatch
from matplotlib.path import Path as MplPath
import numpy as np

# Archilume imports
from archilume import config, utils
from archilume.hdr2wpd import Hdr2Wpd


class HdrAoiEditor:
    """Interactive room boundary drawing tool for HDR/TIFF floor plan images.

    Displays an HDR or associated TIFF image and provides a PolygonSelector
    for drawing room boundary polygons. Supports hierarchical parent/child
    relationships (e.g. U101 → U101_BED1). Auto-saves JSON and CSV on every
    save or delete action.

    Args:
        image_dir: Directory containing .hdr files and associated .tiff files.
        aoi_dir: Directory containing .aoi files with pixel-mapped room boundaries.
        session_path: Optional path for saving/loading editor sessions (JSON).
    """

    def __init__(
        self,
        image_dir:              Union[Path, str]            = config.IMAGE_DIR,
        aoi_dir:                Union[Path, str]            = config.AOI_DIR,
        session_path:           Optional[Path]              = None,
    ):
        self.image_dir                                  = Path(image_dir)
        self.aoi_dir                                    = Path(aoi_dir)
        self.session_path                               = session_path or (self.image_dir / "aoi_session.json")
        self.csv_path                                   = self.image_dir / "aoi_boundaries.csv"

        # Scan HDR files in image_dir
        self.hdr_files:             List[dict]          = self._scan_hdr_files()
        self.current_hdr_idx:       int                 = 0

        # Image variant toggle state (HDR + associated TIFFs for current HDR)
        self.image_variants:        List[Path]          = []
        self.current_variant_idx:   int                 = 0
        self._rebuild_image_variants()

        # Room storage
        self.rooms:                 List[dict]          = []
        self.room_patches:          List[Polygon]       = []
        self.room_labels:           List                = []
        self.current_polygon_vertices                   = []
        self.selected_room_idx:     Optional[int]       = None

        # Zoom state
        self.original_xlim                              = None
        self.original_ylim                              = None

        # Image dimensions (set on first render)
        self._image_width:          int                 = 1
        self._image_height:         int                 = 1
        self._reference_view_w:     float               = 1.0  # view width at default zoom

        # Snap to existing polygon vertices (always on, no UI control)
        self._snap_distance_px:     float               = 10.0
        self.current_vertices:      np.ndarray          = np.array([])
        self.ortho_mode:            bool                = True
        self._pending_snap:         Optional[tuple]     = None

        # Vertex editing mode
        self.edit_mode:             bool                = False
        self.edit_room_idx:         Optional[int]       = None
        self.edit_vertex_idx:       Optional[int]       = None
        self.hover_room_idx:        Optional[int]       = None
        self.hover_vertex_idx:      Optional[int]       = None
        self.hover_edge_room_idx:   Optional[int]       = None
        self.hover_edge_idx:        Optional[int]       = None
        self.hover_edge_point:      Optional[tuple]     = None
        self.edit_edge_room_idx:    Optional[int]       = None
        self.edit_edge_idx:         Optional[int]       = None
        self.edit_edge_start:       Optional[tuple]     = None

        # Parent apartment selection
        self.selected_parent:       Optional[str]       = None
        self.parent_options:        List[str]           = []

        # Room list scroll state
        self.room_list_scroll_offset: int               = 0
        self._room_list_hit_boxes:  List[Tuple]         = []

        # Undo stack for edit-mode vertex operations
        # Each entry: (room_idx, vertices_snapshot)
        self._edit_undo_stack:      List[Tuple]         = []
        self._edit_undo_max:        int                 = 50

        # Image cache: path → numpy array (avoids reloading from disk)
        self._image_cache:          dict                = {}

        # Cached matplotlib artists for incremental rendering
        self._room_patch_cache                          = {}
        self._room_label_cache                          = {}
        self._df_text_cache:        list                = []
        self._edit_vertex_scatter                       = None
        self._last_view_mode                            = None
        self._last_hover_check                          = 0.0
        self._image_handle                              = None
        self.ax_legend                                  = None

        # Daylight factor analysis
        self.df_thresholds:         List[float]         = [0.5, 1.0, 1.5]
        self._df_image:             Optional[np.ndarray]= None   # (H, W) DF% for current HDR
        self._df_image_cache:       dict                = {}     # hdr_path_str → np.ndarray
        self._room_df_results:      dict                = {}     # room_idx → list of result strings
        self._hdr2wpd:              Optional[Hdr2Wpd]   = None

    # -------------------------------------------------------------------------
    # Layout helper — top-left coordinate system
    # -------------------------------------------------------------------------

    def _axes(self, x, y, w, h):
        """Create figure axes at (x, y) measured from top-left corner.

        x increases right, y increases down — unlike matplotlib's native
        bottom-left origin. Converts to fig.add_axes([left, bottom, w, h]).
        """
        return self.fig.add_axes((x, 1.0 - y - h, w, h))

    # -------------------------------------------------------------------------
    # Coordinate mapping (world metres ↔ pixel)
    # -------------------------------------------------------------------------

    def _load_from_aoi_files(self, aoi_dir: Path):
        """Load room boundaries from .aoi files (pixel coordinates already included).

        AOI format:
            AOI Points File: <name> <level>
            ASSOCIATED VIEW FILE: plan_ffl_<z_mm>.vp
            FFL z height(m): <z>
            CENTRAL x,y: <cx> <cy>
            NO. PERIMETER POINTS <n>: x,y pixel_x pixel_y positions
            <world_x> <world_y> <pixel_x> <pixel_y>
            ...
        """
        aoi_files = sorted(aoi_dir.glob('*.aoi'))
        for aoi_path in aoi_files:
            with open(aoi_path, 'r') as f:
                lines = [l.strip() for l in f.readlines()]
            if len(lines) < 6:
                continue

            # Header: name from line 0
            name_match = re.match(r'AOI Points File:\s*(.+)', lines[0])
            name       = name_match.group(1).strip() if name_match else aoi_path.stem

            # HDR file from view file reference (plan_ffl_28700.vp → model_plan_ffl_28700)
            vp_match = re.search(r'plan_ffl_(\d+)', lines[1])
            hdr_file = self.current_hdr_name
            if vp_match:
                ffl_val = vp_match.group(1)
                for entry in self.hdr_files:
                    if ffl_val in entry['name']:
                        hdr_file = entry['name']
                        break

            # Vertex lines: world_x world_y pixel_x pixel_y
            vertices = []
            for line in lines[5:]:
                parts = line.split()
                if len(parts) >= 4:
                    px, py = float(parts[2]), float(parts[3])
                    vertices.append([px, py])

            if len(vertices) >= 3:
                self.rooms.append({
                    'name':     name,
                    'parent':   None,
                    'vertices': vertices,
                    'hdr_file': hdr_file,
                })

        print(f"Loaded {len(self.rooms)} rooms from {len(aoi_files)} .aoi files in {aoi_dir}")

    # -------------------------------------------------------------------------
    # Image scanning and loading
    # -------------------------------------------------------------------------

    def _scan_hdr_files(self) -> List[dict]:
        """Scan image_dir for HDR files and associated TIFFs.

        Returns:
            Sorted list of dicts with keys: hdr_path, tiff_paths, name (stem).
        """
        if not self.image_dir.exists():
            print(f"Warning: image_dir does not exist: {self.image_dir}")
            return []

        hdr_paths = sorted(self.image_dir.glob("*.hdr"))
        result = []
        for hdr_path in hdr_paths:
            stem = hdr_path.stem
            # Associated TIFFs: any .tiff in same dir whose stem starts with stem + '_'
            tiff_paths = sorted(
                p for p in self.image_dir.glob("*.tiff")
                if p.stem.startswith(stem + "_")
            )
            result.append({
                'hdr_path': hdr_path,
                'tiff_paths': tiff_paths,
                'name': stem,
            })

        # Build legend map: key → Path for files matching '*_legend.tiff'
        # e.g. 'df_cntr' → Path('df_cntr_legend.tiff')
        self.legend_map: dict = {}
        for legend_path in sorted(self.image_dir.glob("*_legend.tiff")):
            key = legend_path.stem[: -len("_legend")]  # strip trailing '_legend'
            self.legend_map[key] = legend_path
        if self.legend_map:
            print(f"Found legend(s): {list(self.legend_map.keys())}")

        print(f"Found {len(result)} HDR file(s) in {self.image_dir}")
        return result

    def _rebuild_image_variants(self):
        """Rebuild the image_variants list for the current HDR index."""
        if not self.hdr_files:
            self.image_variants = []
            self.current_variant_idx = 0
            return

        entry = self.hdr_files[self.current_hdr_idx]
        self.image_variants = [entry['hdr_path']] + list(entry['tiff_paths'])
        self.current_variant_idx = 0

    @property
    def current_hdr_name(self) -> str:
        """Stem of the currently active HDR file."""
        if not self.hdr_files:
            return ""
        return self.hdr_files[self.current_hdr_idx]['name']

    @property
    def current_variant_path(self) -> Optional[Path]:
        """Path of the currently displayed image variant."""
        if not self.image_variants:
            return None
        idx = self.current_variant_idx % len(self.image_variants)
        return self.image_variants[idx]

    def _load_image(self, path: Path) -> Optional[np.ndarray]:
        """Load an image file as a normalised float32 numpy array.

        Results are cached in memory so repeated renders don't hit disk.

        Args:
            path: Path to .hdr or .tiff file.

        Returns:
            Array of shape (H, W, 3) with values in [0, 1], or None on failure.
        """
        key = str(path)
        if key in self._image_cache:
            return self._image_cache[key]

        try:
            if path.suffix.lower() == '.hdr':
                import imageio.v2 as imageio
                img = imageio.imread(str(path)).astype(np.float32)
                if img.ndim == 2:
                    img = np.stack([img, img, img], axis=-1)
                p99 = np.percentile(img, 99)
                if p99 > 0:
                    img = img / p99
                img = np.clip(img ** (1.0 / 2.2), 0.0, 1.0)
            else:
                from PIL import Image
                pil_img = Image.open(path).convert('RGB')
                img = np.array(pil_img, dtype=np.float32) / 255.0

            self._image_cache[key] = img
            return img
        except Exception as exc:
            print(f"Warning: could not load image {path}: {exc}")
            return None

    def _get_legend_for_variant(self, path: Optional[Path]) -> Optional[Path]:
        """Return the legend TIFF matching the given image variant, or None.

        Matching rule: for a TIFF whose stem is '<hdr_stem>_<suffix>', find
        the first legend key that is a substring of '<suffix>'.
        HDR variants never have an associated legend.
        """
        if path is None or path.suffix.lower() == '.hdr':
            return None
        hdr_stem = self.current_hdr_name
        suffix = path.stem[len(hdr_stem) + 1:] if path.stem.startswith(hdr_stem + "_") else path.stem
        for key, legend_path in self.legend_map.items():
            if key in suffix:
                return legend_path
        return None

    # -------------------------------------------------------------------------
    # Launch
    # -------------------------------------------------------------------------

    _WINDOW_TITLE = "Archilume - HDR AOI Editor"

    def launch(self):
        """Open the interactive editor window."""
        if not self.hdr_files:
            raise FileNotFoundError(f"No .hdr files found in {self.image_dir}")

        # Close any previous editor window that was left open
        for fig_num in plt.get_fignums():
            fig = plt.figure(fig_num)
            if getattr(fig, '_archilume_editor', False):
                plt.close(fig)

        # Initialise daylight factor analysis (Phase 3 from daylight_workflow_iesve)
        try:
            coordinate_map_path = utils.create_pixel_to_world_coord_map(self.image_dir)
            self._hdr2wpd = Hdr2Wpd(pixel_to_world_map=coordinate_map_path)
            print(f"DF analysis ready (area_per_pixel={self._hdr2wpd.area_per_pixel} m2)")
        except Exception as exc:
            print(f"Warning: DF analysis unavailable ({exc}). Results will not be shown.")
            self._hdr2wpd = None

        # Setup matplotlib figure — wide to match ~2.6:1 floor plan aspect ratio
        plt.rcParams['savefig.directory'] = str(self.image_dir)
        self.fig = plt.figure(figsize=(20, 8), facecolor='#F5F5F0')
        self.fig._archilume_editor = True
        self.fig.canvas.manager.set_window_title(self._WINDOW_TITLE)
        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.05)

        # Maximise window
        try:
            import sys
            manager = plt.get_current_fig_manager()
            if sys.platform == "win32":
                manager.window.state('zoomed')
            else:
                manager.window.attributes('-zoomed', True)
            self.fig.canvas.mpl_connect('resize_event', self._on_resize)
            self.fig.canvas.get_tk_widget().after(100, self._force_resize_update)
        except AttributeError:
            try:
                manager = plt.get_current_fig_manager()
                manager.window.showMaximized()
                self.fig.canvas.mpl_connect('resize_event', self._on_resize)
            except AttributeError:
                pass

        # Main plot area (top-left: x=0.12, y=0.30, w=0.81, h=0.60)
        self.ax = self._axes(0.12, 0.30, 0.81, 0.60)
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.set_facecolor('#FAFAF8')

        # Legend axes: narrow strip to the right of the main image
        self.ax_legend = self._axes(0.93, 0.30, 0.06, 0.60)
        self.ax_legend.axis('off')
        self.ax_legend.set_visible(False)

        # Setup side panel
        self._setup_side_panel()

        # Initial render
        self._render_section()

        # Store original limits
        self.original_xlim = self.ax.get_xlim()
        self.original_ylim = self.ax.get_ylim()

        # Polygon selector for drawing
        self._create_polygon_selector()

        # Event handlers
        self.fig.canvas.mpl_connect('button_press_event', self._on_click_with_snap)
        self.fig.canvas.mpl_connect('button_press_event', self._on_list_click)
        self.fig.canvas.mpl_connect('button_release_event', self._on_button_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_motion)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key_press)
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)

        # Load existing session
        self._load_session()
        self._update_room_list()
        self._update_hdr_list()

        print("\n=== HDR Boundary Editor ===")
        print(f"Loaded {len(self.hdr_files)} HDR file(s) from {self.image_dir}")
        print("Use Up/Down to navigate HDR files, 't' to toggle image variant.")
        print("Scroll: zoom | Right-click: select room | s: save | d: delete | q: quit")
        print("===========================\n")
        plt.show()

    # -------------------------------------------------------------------------
    # UI setup
    # -------------------------------------------------------------------------

    def _setup_side_panel(self):
        """Create the side panel with inputs, buttons, and room list.

        All positions use _axes(x, y, w, h) where x/y are from the top-left
        corner of the figure. Increasing x → right, increasing y → down.
        """
        pl = 0.02   # panel left (x)
        pw = 0.28   # panel width

        self._btn_color    = '#E8E8E0'
        self._btn_hover    = '#D8D8D0'

        lbl_h   = 0.016
        input_h = 0.032
        gap     = 0.008
        sub_h   = 0.014

        # ── Instructions (top-left) ────────────────────────────────────────────
        instr_w = 0.12
        ax_instr = self._axes(pl, 0.02, instr_w, 0.15)
        ax_instr.axis('off')
        ax_instr.patch.set_visible(False)
        ax_instr.text(0, 0.95, "HDR BOUNDARY EDITOR", fontsize=9, fontweight='bold',
                      color='#404040', transform=ax_instr.transAxes)
        controls = [
            ("\u2191/\u2193", "Navigate HDR files"),
            ("t",             "Toggle image (HDR / TIFFs)"),
            ("Left-click",    "Place vertex / drag"),
            ("Shift+click",   "Drag edge (edit mode)"),
            ("Right-click",   "Select existing room"),
            ("Scroll",        "Zoom centred on cursor"),
            ("s",             "Save room / confirm edit"),
            ("d",             "Delete selected room"),
            ("e",             "Toggle Edit Mode"),
            ("ctrl+z",        "Undo last edit"),
            ("o",             "Toggle orthogonal lines"),
            ("r",             "Reset zoom"),
            ("q",             "Quit"),
        ]
        for i, (key, desc) in enumerate(controls):
            y = 0.87 - i * 0.08
            ax_instr.text(0.00, y, key,  fontsize=7.5, color='#404040', fontweight='bold',
                          transform=ax_instr.transAxes)
            ax_instr.text(0.38, y, desc, fontsize=7.5, color='#505050',
                          transform=ax_instr.transAxes)

        # ── HDR FILES nav (top, right of instructions) ─────────────────────
        col2_x  = pl + instr_w + 0.01
        row_y   = 0.02
        arrow_w = 0.025
        arrow_h = input_h * 2 + gap

        ax_hdr_hdr = self._axes(col2_x, row_y, arrow_w * 2 + 0.004, lbl_h)
        ax_hdr_hdr.axis('off')
        ax_hdr_hdr.text(0, 0.5, "HDR FILES:", fontsize=9, fontweight='bold', color='#404040')

        arrows_y = row_y + lbl_h + gap
        ax_next_hdr = self._axes(col2_x, arrows_y, arrow_w, arrow_h)
        self.btn_next_hdr = Button(ax_next_hdr, '\u25b2', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_next_hdr.on_clicked(self._on_next_hdr_click)

        ax_prev_hdr = self._axes(col2_x + arrow_w + 0.004, arrows_y, arrow_w, arrow_h)
        self.btn_prev_hdr = Button(ax_prev_hdr, '\u25bc', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_prev_hdr.on_clicked(self._on_prev_hdr_click)

        hdr_list_x = col2_x + arrow_w * 2 + 0.008
        self.ax_hdr_list = self._axes(hdr_list_x, row_y, 0.060, lbl_h + gap + arrow_h)
        self.ax_hdr_list.axis('off')

        # ── Parent Apartment (right of HDR files) ─────────────────────────
        prnt_x = col2_x + 0.18
        prnt_w = 0.150

        ax_parent_lbl = self._axes(prnt_x, row_y, prnt_w, lbl_h)
        ax_parent_lbl.axis('off')
        ax_parent_lbl.text(0, 0.5, "Parent Apartment:", fontsize=9, fontweight='bold')

        ax_parent_btn = self._axes(prnt_x, row_y + lbl_h + gap, prnt_w, input_h)
        self.btn_parent = Button(ax_parent_btn, '(None)', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_parent.label.set_fontsize(8)
        self.btn_parent.on_clicked(self._on_parent_cycle)

        # ── Apartment Name (below parent) ──────────────────────────────────
        name_y = row_y + lbl_h + gap + input_h + gap

        ax_name_lbl = self._axes(prnt_x, name_y, prnt_w, lbl_h)
        ax_name_lbl.axis('off')
        self.name_label_text = ax_name_lbl.text(0, 0.5, "Apartment Name:", fontsize=9, fontweight='bold')

        ax_name = self._axes(prnt_x, name_y + lbl_h + gap, prnt_w, input_h)
        self.name_textbox = TextBox(ax_name, '', initial='')
        self.name_textbox.on_text_change(self._on_name_changed)

        # ── Status / preview line ──────────────────────────────────────────
        status_y = name_y + lbl_h + gap + input_h + gap

        ax_preview = self._axes(prnt_x, status_y, prnt_w, sub_h)
        ax_preview.axis('off')
        self.name_preview_text = ax_preview.text(0, 0.5, "", fontsize=8, color='#666666', style='italic')

        ax_status = self._axes(prnt_x, status_y, prnt_w, sub_h)
        ax_status.axis('off')
        self.status_text = ax_status.text(
            0, 0.5, "Status: Ready to draw", fontsize=8, color='blue', style='italic')

        # ── Action buttons (right of parent/name) ─────────────────────────
        stack_x = prnt_x + prnt_w + 0.012
        stack_w = 0.090
        total_h = status_y + sub_h - row_y
        n_btns  = 3
        btn_gap = 0.004
        each_h  = (total_h - btn_gap * (n_btns - 1)) / n_btns

        for i, (attr, label, cb) in enumerate([
            ('btn_save',   'Save Room',       self._on_save_click),
            ('btn_clear',  'Clear Current',   self._on_clear_click),
            ('btn_delete', 'Delete Selected', self._on_delete_click),
        ]):
            btn_y  = row_y + i * (each_h + btn_gap)
            ax_btn = self._axes(stack_x, btn_y, stack_w, each_h)
            btn = Button(ax_btn, label, color=self._btn_color, hovercolor=self._btn_hover)
            btn.label.set_fontsize(7)
            btn.on_clicked(cb)
            setattr(self, attr, btn)

        # ── DF Thresholds (%) ────────────────────────────────────────────────
        df_y  = 0.21
        df_lbl_w = 0.06
        df_inp_w = 0.10
        df_btn_w = 0.025

        ax_df_lbl = self._axes(pl, df_y, df_lbl_w + df_inp_w, lbl_h)
        ax_df_lbl.axis('off')
        ax_df_lbl.text(0, 0.5, "DF Thresholds (%):", fontsize=9, fontweight='bold', color='#404040')

        df_refresh_w = 0.06
        ax_df_input = self._axes(pl, df_y + lbl_h + gap, df_inp_w, input_h)
        self.df_textbox = TextBox(ax_df_input, '', initial=', '.join(f'{t:g}' for t in self.df_thresholds))
        self.df_textbox.on_submit(self._on_df_thresholds_submit)

        ax_df_refresh = self._axes(pl + df_inp_w + 0.004, df_y + lbl_h + gap, df_refresh_w, input_h)
        self.btn_df_refresh = Button(ax_df_refresh, 'Refresh', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_df_refresh.label.set_fontsize(7)
        self.btn_df_refresh.on_clicked(self._on_df_refresh)

        # ── Saved rooms list ─────────────────────────────────────────────────
        list_w    = pw / 3
        list_hdr_y = 0.31

        ax_list_hdr = self._axes(pl, list_hdr_y, list_w, 0.025)
        ax_list_hdr.axis('off')
        ax_list_hdr.text(0, 0.5, "SAVED ROOMS:", fontsize=9, fontweight='bold')

        list_top = list_hdr_y + 0.030
        list_h   = 0.58
        self.ax_list = self._axes(pl, list_top, list_w, list_h)
        self.ax_list.set_facecolor('#FAFAF8')
        self.ax_list.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for spine in self.ax_list.spines.values():
            spine.set_edgecolor('#CCCCCC')
            spine.set_linewidth(0.5)

        # ── Export progress bar (hidden until export starts) ────────────────
        self.ax_progress = self._axes(0.35, 0.935, 0.63, 0.014)
        self.ax_progress.set_xlim(0, 1)
        self.ax_progress.set_ylim(0, 1)
        self.ax_progress.axis('off')
        self.ax_progress.set_visible(False)
        self._progress_bar_patch = None
        self._progress_text = None

        # ── Bottom strip: Toggle Image | Edit Mode | Reset Zoom | Export Report
        btm_x = 0.35
        btm_w = 0.63
        btm_h = 0.030
        btm_y = 0.955
        n_btm = 4
        btn_w = (btm_w - (n_btm - 1) * gap) / n_btm

        ax_toggle = self._axes(btm_x, btm_y, btn_w, btm_h)
        self.btn_image_toggle = Button(ax_toggle, 'Image: HDR (T)',
                                       color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_image_toggle.label.set_fontsize(8)
        self.btn_image_toggle.on_clicked(self._on_image_toggle_click)

        ax_edit = self._axes(btm_x + (btn_w + gap), btm_y, btn_w, btm_h)
        self.btn_edit_mode = Button(ax_edit, 'Edit Mode: OFF (Press E)',
                                    color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_edit_mode.label.set_fontsize(8)
        self.btn_edit_mode.on_clicked(self._on_edit_mode_toggle)

        ax_reset = self._axes(btm_x + 2 * (btn_w + gap), btm_y, btn_w, btm_h)
        self.btn_reset_zoom = Button(ax_reset, 'Reset Zoom',
                                     color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_reset_zoom.label.set_fontsize(8)
        self.btn_reset_zoom.on_clicked(self._on_reset_zoom_click)

        ax_export = self._axes(btm_x + 3 * (btn_w + gap), btm_y, btn_w, btm_h)
        self.btn_export = Button(ax_export, 'Export Report',
                                 color='#C8E6C9', hovercolor='#A5D6A7')
        self.btn_export.label.set_fontsize(8)
        self.btn_export.on_clicked(self._on_export_report)

        # ── Legend (colour key) — bottom of the side panel ───────────────────
        ax_legend = self._axes(pl, 0.89, pw / 3, 0.10)
        ax_legend.axis('off')
        ax_legend.set_facecolor('#F0F0EC')
        ax_legend.text(0.01, 0.93, "LEGEND", fontsize=7, fontweight='bold', color='#404040',
                       transform=ax_legend.transAxes)

        legend_items = [
            ('green',    0.4,  'Apartment (current HDR)'),
            ('#2196F3',  0.4,  'Sub-room (current HDR)'),
            ('yellow',   0.35, 'Selected'),
            ('cyan',     0.35, 'Being edited'),
            ('magenta',  0.35, 'Hover vertex (edit mode)'),
            ('gray',     0.15, 'Other HDR file'),
        ]
        row_h  = 0.27   # vertical step between rows
        swatch = 0.14   # swatch height
        for i, (color, alpha, label) in enumerate(legend_items):
            col    = i // 3
            row    = i % 3
            x_base = 0.01 + col * 0.50
            y0     = 0.74 - row * row_h
            rect = FancyBboxPatch((x_base, y0 - swatch / 2), 0.04, swatch,
                                  boxstyle='round,pad=0.01',
                                  facecolor=color, edgecolor=color, alpha=alpha,
                                  transform=ax_legend.transAxes, clip_on=False)
            ax_legend.add_patch(rect)
            ax_legend.text(x_base + 0.06, y0, label, fontsize=6, color='#404040',
                           va='center', transform=ax_legend.transAxes)

    # -------------------------------------------------------------------------
    # HDR file navigation
    # -------------------------------------------------------------------------

    def _on_prev_hdr_click(self, event):
        """Navigate to the previous HDR file (lower index)."""
        if not self.hdr_files:
            self._update_status("No HDR files loaded", 'red')
            return
        if self.current_hdr_idx > 0:
            self._jump_to_hdr(self.current_hdr_idx - 1)
        else:
            self._update_status("Already at first HDR file", 'orange')

    def _on_next_hdr_click(self, event):
        """Navigate to the next HDR file (higher index)."""
        if not self.hdr_files:
            self._update_status("No HDR files loaded", 'red')
            return
        if self.current_hdr_idx < len(self.hdr_files) - 1:
            self._jump_to_hdr(self.current_hdr_idx + 1)
        else:
            self._update_status("Already at last HDR file", 'orange')

    def _jump_to_hdr(self, hdr_idx: int):
        """Switch to the given HDR file index."""
        if not (0 <= hdr_idx < len(self.hdr_files)):
            return
        self.current_hdr_idx = hdr_idx
        self._rebuild_image_variants()
        self._update_image_toggle_label()
        self.selected_parent = None
        self.btn_parent.label.set_text('(None)')
        self.name_label_text.set_text("Apartment Name:")
        self._update_status(f"HDR: {self.current_hdr_name}", 'green')
        self._update_hdr_list()
        self._update_room_list()
        self._render_section(reset_view=True, force_full=True)
        self._create_polygon_selector()

    def _update_hdr_list(self):
        """Refresh the HDR file list in the side panel."""
        self.ax_hdr_list.clear()
        self.ax_hdr_list.axis('off')

        if not self.hdr_files:
            self.ax_hdr_list.text(0, 0.95, "(no HDR files)", fontsize=8, style='italic', color='gray')
        else:
            max_display = 8
            total = len(self.hdr_files)
            for display_idx in range(min(max_display, total)):
                i    = total - 1 - display_idx  # descending order (latest first)
                name = self.hdr_files[i]['name']
                y_pos = 0.95 - (display_idx * 0.12)
                is_current = (self.current_hdr_idx == i)
                room_count = sum(1 for r in self.rooms if r.get('hdr_file') == name)
                indicator  = "*" if is_current else "o"
                text       = f"{indicator} {name}"
                if room_count > 0:
                    text += f" ({room_count})"
                self.ax_hdr_list.text(
                    0, y_pos, text, fontsize=7,
                    fontweight='bold' if is_current else 'normal',
                    color='green' if is_current else 'darkgray',
                )
            if total > max_display:
                self.ax_hdr_list.text(0, 0.02, f"... and {total - max_display} more",
                                      fontsize=7, style='italic')

        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Image toggle
    # -------------------------------------------------------------------------

    def _on_image_toggle_click(self, event):
        """Cycle through image variants (HDR then associated TIFFs)."""
        if not self.image_variants:
            return
        self.current_variant_idx = (self.current_variant_idx + 1) % len(self.image_variants)
        self._update_image_toggle_label()
        self._render_section(force_full=True)

    def _update_image_toggle_label(self):
        """Update the toggle button label to show the active variant."""
        if not self.image_variants:
            self.btn_image_toggle.label.set_text('Image: (none)')
            return
        idx  = self.current_variant_idx % len(self.image_variants)
        path = self.image_variants[idx]
        # Show a short label: HDR stem or TIFF suffix portion
        if path.suffix.lower() == '.hdr':
            label = 'Image: HDR (T)'
        else:
            # e.g. model_plan_ffl_25300_df_false → show "df_false"
            hdr_stem = self.hdr_files[self.current_hdr_idx]['name']
            suffix   = path.stem[len(hdr_stem):]  # e.g. "_df_false"
            suffix   = suffix.lstrip('_')
            label    = f'Image: {suffix} (T)'
        self.btn_image_toggle.label.set_text(label)
        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Parent/child relationship helpers
    # -------------------------------------------------------------------------

    def _get_apartments_for_hdr(self, hdr_name: str) -> List[str]:
        """Return names of apartment-level rooms (no parent) for the given HDR file."""
        return [
            room['name'] for room in self.rooms
            if room.get('parent') is None and room.get('hdr_file') == hdr_name
        ]

    def _get_children(self, parent_name: str) -> List[dict]:
        """Return all rooms that have the given parent."""
        return [r for r in self.rooms if r.get('parent') == parent_name]

    def _get_parent_room(self, parent_name: str) -> Optional[dict]:
        """Return the room dict for the given parent name, or None."""
        for r in self.rooms:
            if r.get('name') == parent_name and r.get('parent') is None:
                return r
        return None

    # -------------------------------------------------------------------------
    # Name helpers
    # -------------------------------------------------------------------------

    def _make_unique_name(self, base_name: str, exclude_idx: Optional[int] = None) -> str:
        """Ensure room name is unique by appending numeric suffix if needed."""
        existing = {r['name'] for i, r in enumerate(self.rooms) if i != exclude_idx}
        if base_name not in existing:
            return base_name

        match = re.match(r'^(.*?)(\d+)$', base_name)
        root  = match.group(1) if match else base_name
        counter = 1
        while f"{root}{counter}" in existing:
            counter += 1
        return f"{root}{counter}"

    def _enforce_unique_names(self) -> int:
        """Ensure all room names are unique; returns count of rooms renamed."""
        seen       = set()
        renamed    = 0
        for room in self.rooms:
            name = room['name']
            if name not in seen:
                seen.add(name)
                continue
            match = re.match(r'^(.*?)(\d+)$', name)
            root  = match.group(1) if match else name
            counter = 1
            while f"{root}{counter}" in seen:
                counter += 1
            new_name = f"{root}{counter}"
            print(f"Renamed duplicate '{name}' -> '{new_name}'")
            room['name'] = new_name
            seen.add(new_name)
            renamed += 1
        return renamed

    def _check_boundary_containment(self, child_verts, parent_verts) -> bool:
        """Return True if all child vertices lie inside the parent polygon."""
        if not parent_verts or len(parent_verts) < 3:
            return True
        if not child_verts or len(child_verts) < 3:
            return True
        arr = np.array(parent_verts)
        if not np.allclose(arr[0], arr[-1]):
            arr = np.vstack([arr, arr[0]])
        path = MplPath(arr)
        return all(path.contains_point(v) for v in child_verts)

    def _update_parent_options(self):
        """Update the list of available parent apartments for the current HDR file."""
        self.parent_options = self._get_apartments_for_hdr(self.current_hdr_name)

    def _on_parent_cycle(self, event):
        """Cycle through parent apartment options."""
        self._update_parent_options()
        if not self.parent_options:
            self.selected_parent = None
            self.btn_parent.label.set_text('(None - New Apartment)')
            self.name_label_text.set_text("Apartment Name (Space ID):")
        else:
            options = [None] + self.parent_options
            try:
                current_idx = options.index(self.selected_parent)
                next_idx    = (current_idx + 1) % len(options)
            except ValueError:
                next_idx = 0
            self.selected_parent = options[next_idx]
            if self.selected_parent is None:
                self.btn_parent.label.set_text('(None - New Apartment)')
                self.name_label_text.set_text("Apartment Name (Space ID):")
            else:
                self.btn_parent.label.set_text(self.selected_parent)
                self.name_label_text.set_text("Room Name:")
        self._update_name_preview()
        self.fig.canvas.draw_idle()

    def _on_name_changed(self, text):
        """Update name preview when name textbox changes."""
        self._update_name_preview()

    def _update_name_preview(self):
        """Update the name preview text."""
        name = self.name_textbox.text.strip().upper()
        if not name:
            self.name_preview_text.set_text("")
        elif self.selected_parent:
            self.name_preview_text.set_text(f"Will save as: {self.selected_parent}_{name}")
        else:
            self.name_preview_text.set_text(f"Will save as: {name}")
        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # DF threshold controls
    # -------------------------------------------------------------------------

    def _on_df_thresholds_submit(self, text):
        """Parse comma-separated DF thresholds from the text box and refresh."""
        try:
            values = [float(v.strip()) for v in text.split(',') if v.strip()]
            if values:
                self.df_thresholds = sorted(values)
        except ValueError:
            self._update_status("Invalid DF thresholds - use comma-separated numbers", 'red')
            return
        self._compute_all_room_df_results()
        self._render_section(force_full=True)

    def _on_df_refresh(self, event):
        """Re-parse thresholds from the text box and refresh DF results on screen."""
        self._on_df_thresholds_submit(self.df_textbox.text)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _render_section(self, reset_view: bool = False, force_full: bool = False):
        """Render the current image and room overlays."""
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()

        need_full = force_full or reset_view
        if need_full:
            self._do_full_render(xlim, ylim, reset_view)
        else:
            self._update_room_visuals()
            self.fig.canvas.draw_idle()

    def _do_full_render(self, xlim, ylim, reset_view: bool):
        """Complete redraw of image and room polygons."""
        self.ax.clear()
        self._room_patch_cache.clear()
        self._room_label_cache.clear()
        self._df_text_cache.clear()
        self._edit_vertex_scatter = None
        self._image_handle = None

        # Load and display current image
        path = self.current_variant_path
        if path is not None:
            img = self._load_image(path)
        else:
            img = None

        if img is not None:
            H, W = img.shape[:2]
            self._image_width  = W
            self._image_height = H
            self._reference_view_w = float(W)
            self._image_handle = self.ax.imshow(
                img, origin='upper',
                extent=[0, W, H, 0],
                aspect='equal', zorder=0,
            )
            self.ax.set_xlim(0, W)
            self.ax.set_ylim(H, 0)
        else:
            # Blank canvas
            self.ax.set_xlim(0, 1000)
            self.ax.set_ylim(1000, 0)

        # Rebuild snap vertex pool from current-HDR room vertices
        all_verts = []
        for room in self.rooms:
            if room.get('hdr_file') == self.current_hdr_name:
                all_verts.extend(room['vertices'])
        self.current_vertices = np.array(all_verts) if all_verts else np.array([])

        # Load DF image for current HDR (cached)
        self._load_current_df_image()
        self._compute_all_room_df_results()

        # Draw room polygons
        self.room_patches.clear()
        self.room_labels.clear()
        self._draw_all_room_polygons()

        self.ax.set_aspect('equal', adjustable='box')
        self.ax.axis('off')

        # Restore or reset zoom
        if reset_view or not hasattr(self, 'original_xlim') or xlim == (0.0, 1.0):
            self.ax.autoscale()
        elif img is not None and xlim != (0.0, 1.0):
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        # Legend: show in dedicated axes to the left of the main image
        if self.ax_legend is not None:
            self.ax_legend.clear()
            legend_path = self._get_legend_for_variant(self.current_variant_path)
            if legend_path is not None:
                legend_img = self._load_image(legend_path)
                if legend_img is not None:
                    lH, lW = legend_img.shape[:2]
                    self.ax_legend.imshow(
                        legend_img, origin='upper',
                        extent=[0, lW, lH, 0], aspect='auto',
                    )
                    self.ax_legend.set_xlim(0, lW)
                    self.ax_legend.set_ylim(lH, 0)
                    self.ax_legend.axis('off')
                    self.ax_legend.set_visible(True)
                else:
                    self.ax_legend.set_visible(False)
            else:
                self.ax_legend.set_visible(False)

        # Title
        hdr_name = self.current_hdr_name or "(no HDR)"
        variant  = self.current_variant_path
        variant_label = variant.stem if variant else ""
        self.ax.set_title(f"{hdr_name}  -  {variant_label}", fontsize=11, fontweight='bold')

        self.fig.canvas.draw_idle()

    def _load_current_df_image(self):
        """Load the DF% image for the current HDR file (cached)."""
        if self._hdr2wpd is None or not self.hdr_files:
            self._df_image = None
            return
        hdr_path = self.hdr_files[self.current_hdr_idx]['hdr_path']
        key = str(hdr_path)
        if key in self._df_image_cache:
            self._df_image = self._df_image_cache[key]
            return
        self._df_image = Hdr2Wpd.load_df_image(hdr_path)
        if self._df_image is not None:
            self._df_image_cache[key] = self._df_image

    def _compute_all_room_df_results(self):
        """Compute DF threshold results for every room on the current HDR floor."""
        self._room_df_results.clear()
        if self._df_image is None or self._hdr2wpd is None:
            return
        for i, room in enumerate(self.rooms):
            if room.get('hdr_file') != self.current_hdr_name:
                continue
            verts = room['vertices']
            if len(verts) < 3:
                continue
            result = self._hdr2wpd.compute_df_for_polygon(
                self._df_image, verts, tuple(self.df_thresholds))
            total_area = result['total_area_m2']
            lines = []
            for tr in result['thresholds']:
                pct = (tr['area_m2'] / total_area * 100) if total_area > 0 else 0.0
                lines.append(f"{tr['area_m2']:.1f} m\u00b2 ({pct:.0f}%) @ {tr['threshold']:g}%")
            self._room_df_results[i] = lines

    def _draw_all_room_polygons(self):
        """Draw all room polygons for the current view."""
        for i, room in enumerate(self.rooms):
            is_current = (room.get('hdr_file') == self.current_hdr_name)
            if is_current:
                self._draw_room_polygon(room, i, is_current_floor=True)

    def _draw_room_polygon(self, room: dict, idx: int, is_current_floor: bool):
        """Draw a single room polygon with its label."""
        verts = room['vertices']
        if len(verts) < 3:
            return

        is_selected = (idx == self.selected_room_idx)
        is_hover    = (idx == self.hover_room_idx)
        is_editing  = (idx == self.edit_room_idx and self.edit_mode)
        is_subroom  = room.get('parent') is not None

        if is_editing:
            edge_color, lw = 'cyan',    3
        elif is_selected:
            edge_color, lw = 'yellow',  4
        elif is_hover and self.edit_mode:
            edge_color, lw = 'magenta', 2
        elif is_current_floor:
            edge_color, lw = 'red',     self._zoom_linewidth()
        else:
            edge_color, lw = 'gray',    self._zoom_linewidth(base=1.0)

        poly = Polygon(verts, closed=True,
                       edgecolor=edge_color, facecolor='none', alpha=1.0, linewidth=lw,
                       clip_on=True)
        self.ax.add_patch(poly)
        self.room_patches.append(poly)
        self._room_patch_cache[idx] = poly

        # Edit mode: draw vertex handles
        if self.edit_mode and is_current_floor:
            verts_array = np.array(verts)
            xs, ys, colors, sizes = [], [], [], []
            for v_idx, (vx, vy) in enumerate(verts_array):
                is_hovered  = (idx == self.hover_room_idx  and v_idx == self.hover_vertex_idx)
                is_dragging = (idx == self.edit_room_idx   and v_idx == self.edit_vertex_idx)
                if is_dragging:
                    c, s = 'yellow', 9
                elif is_hovered:
                    c, s = 'red', 8
                else:
                    c, s = 'cyan', 5
                xs.append(vx); ys.append(vy); colors.append(c); sizes.append(s ** 2)
            if xs:
                self.ax.scatter(xs, ys, c=colors, s=sizes,
                                edgecolors='black', linewidths=1.0, zorder=100, picker=5)

            # Highlight hovered edge
            if idx == self.hover_edge_room_idx and self.hover_edge_idx is not None:
                n = len(verts)
                j = self.hover_edge_idx
                ex = [verts[j][0], verts[(j + 1) % n][0]]
                ey = [verts[j][1], verts[(j + 1) % n][1]]
                self.ax.plot(ex, ey, '-', color='lime', linewidth=3, zorder=99, alpha=0.8)
                if self.hover_edge_point is not None:
                    self.ax.plot([self.hover_edge_point[0]], [self.hover_edge_point[1]], 'o',
                                 markersize=8, color='lime', markeredgecolor='darkgreen',
                                 markeredgewidth=1.5, zorder=101, alpha=0.9)

        # Label
        centroid = np.array(verts).mean(axis=0)
        label    = room.get('name', '')
        if not is_current_floor:
            hf = room.get('hdr_file', '')
            label += f"\n({hf})"

        label_text = self.ax.text(
            centroid[0], centroid[1], label,
            color='red', fontsize=self._zoom_fontsize(),
            ha='center', va='center', clip_on=True,
        )
        label_text.set_clip_path(self.ax.patch)
        self.room_labels.append(label_text)
        self._room_label_cache[idx] = label_text

        # DF results as smaller subtext below the room name
        df_lines = self._room_df_results.get(idx, [])
        if df_lines and is_current_floor:
            line_step = self._df_line_step()
            for line_i, line in enumerate(df_lines):
                dy = (line_i + 1) * line_step
                df_text = self.ax.text(
                    centroid[0], centroid[1] + dy, line,
                    color='red', fontsize=self._zoom_fontsize(base=6.5),
                    ha='center', va='center', clip_on=True, alpha=0.85,
                )
                df_text.set_clip_path(self.ax.patch)
                # Store centroid + line index for zoom repositioning
                df_text._df_centroid = centroid
                df_text._df_line_i  = line_i
                self._df_text_cache.append(df_text)

    def _update_room_visuals(self):
        """Update room colours without a full redraw (for hover/selection changes)."""
        for i, room in enumerate(self.rooms):
            is_current = (room.get('hdr_file') == self.current_hdr_name)
            if not is_current:
                continue
            patch = self._room_patch_cache.get(i)
            if patch is None:
                continue
            is_selected = (i == self.selected_room_idx)
            is_hover    = (i == self.hover_room_idx)
            is_editing  = (i == self.edit_room_idx and self.edit_mode)
            is_subroom  = room.get('parent') is not None

            if is_editing:
                patch.set_edgecolor('cyan');    patch.set_facecolor('none'); patch.set_alpha(1.0); patch.set_linewidth(3)
            elif is_selected:
                patch.set_edgecolor('yellow');  patch.set_facecolor('none'); patch.set_alpha(1.0); patch.set_linewidth(4)
            elif is_hover and self.edit_mode:
                patch.set_edgecolor('magenta'); patch.set_facecolor('none'); patch.set_alpha(1.0); patch.set_linewidth(2)
            elif is_current:
                patch.set_edgecolor('red');     patch.set_facecolor('none'); patch.set_alpha(1.0); patch.set_linewidth(self._zoom_linewidth())
            else:
                patch.set_edgecolor('gray');    patch.set_facecolor('none'); patch.set_alpha(1.0); patch.set_linewidth(self._zoom_linewidth(base=1.0))

        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Vertex snapping (snap to existing polygon vertices)
    # -------------------------------------------------------------------------

    def _push_undo(self, room_idx: int):
        """Push a snapshot of a room's vertices onto the undo stack."""
        verts_copy = [list(v) for v in self.rooms[room_idx]['vertices']]
        self._edit_undo_stack.append((room_idx, verts_copy))
        if len(self._edit_undo_stack) > self._edit_undo_max:
            self._edit_undo_stack.pop(0)

    def _undo_edit(self):
        """Restore the last undone vertex state (Ctrl+Z in edit mode)."""
        if not self.edit_mode:
            return
        if not self._edit_undo_stack:
            self._update_status("Nothing to undo", 'orange')
            return
        room_idx, verts_snapshot = self._edit_undo_stack.pop()
        self.rooms[room_idx]['vertices'] = verts_snapshot
        self.edit_vertex_idx     = None
        self.edit_room_idx       = None
        self.edit_edge_room_idx  = None
        self.edit_edge_idx       = None
        self.edit_edge_start     = None
        room_name = self.rooms[room_idx].get('name', 'unnamed')
        remaining = len(self._edit_undo_stack)
        self._update_status(
            f"Undid change to '{room_name}' ({remaining} undo{'s' if remaining != 1 else ''} left)", 'blue')
        self._save_session()
        self._render_section(force_full=True)

    def _snap_to_vertex(self, x: float, y: float) -> tuple:
        """Snap to nearest existing polygon vertex within snap_distance_px pixels."""
        if len(self.current_vertices) == 0:
            return x, y
        dists = np.hypot(self.current_vertices[:, 0] - x, self.current_vertices[:, 1] - y)
        min_idx  = int(np.argmin(dists))
        min_dist = dists[min_idx]
        if min_dist <= self._snap_distance_px:
            return float(self.current_vertices[min_idx, 0]), float(self.current_vertices[min_idx, 1])
        return x, y

    def _point_to_segment_dist(self, px, py, ax, ay, bx, by):
        """Return (distance, proj_x, proj_y) from point P to segment A→B."""
        dx, dy    = bx - ax, by - ay
        seg_len_sq = dx*dx + dy*dy
        if seg_len_sq == 0:
            return np.hypot(px - ax, py - ay), ax, ay
        t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / seg_len_sq))
        proj_x, proj_y = ax + t*dx, ay + t*dy
        return np.hypot(px - proj_x, py - proj_y), proj_x, proj_y

    @staticmethod
    def _snap_to_pixel(x: float, y: float) -> tuple:
        """Snap coordinates to the nearest pixel centre (int + 0.5)."""
        return int(x) + 0.5, int(y) + 0.5

    # -------------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------------

    def _on_click_with_snap(self, event):
        """Handle mouse clicks; snap left-clicks to existing polygon vertices."""
        if event.inaxes != self.ax:
            return

        # Right-click in edit mode: delete hovered vertex; otherwise select room
        if event.button == 3:
            if self.edit_mode and self.hover_vertex_idx is not None and self.hover_room_idx is not None:
                room = self.rooms[self.hover_room_idx]
                if len(room['vertices']) > 3:
                    self._push_undo(self.hover_room_idx)
                    room['vertices'].pop(self.hover_vertex_idx)
                    rname = room.get('name', 'unnamed')
                    self.hover_vertex_idx = None
                    self.hover_room_idx   = None
                    self._update_status(f"Removed vertex from '{rname}' - press 's' to save", 'green')
                    self._save_session()
                    self._render_section(force_full=True)
                else:
                    self._update_status("Cannot remove - polygon must have at least 3 vertices", 'red')
                return
            self._select_room_at(event.xdata, event.ydata)
            return

        # Left-click in edit mode: drag vertex or insert vertex on edge
        if event.button == 1 and self.edit_mode and event.xdata is not None and event.ydata is not None:
            if self.hover_vertex_idx is not None and self.hover_room_idx is not None:
                # Begin vertex drag
                self._push_undo(self.hover_room_idx)
                self.edit_room_idx   = self.hover_room_idx
                self.edit_vertex_idx = self.hover_vertex_idx
                room_name = self.rooms[self.edit_room_idx].get('name', 'unnamed')
                self._update_status(f"Dragging vertex in '{room_name}'", 'cyan')
                self._render_section(force_full=True)
                return

            if self.hover_edge_room_idx is not None and self.hover_edge_idx is not None and self.hover_edge_point is not None:
                if event.key == 'shift':
                    # Shift+click: begin edge drag (move both endpoints together)
                    self._push_undo(self.hover_edge_room_idx)
                    self.edit_edge_room_idx = self.hover_edge_room_idx
                    self.edit_edge_idx      = self.hover_edge_idx
                    self.edit_edge_start    = (event.xdata, event.ydata)
                    room_name = self.rooms[self.edit_edge_room_idx].get('name', 'unnamed')
                    self._update_status(f"Dragging edge in '{room_name}'", 'cyan')
                    return
                # Click: insert new vertex on edge
                self._push_undo(self.hover_edge_room_idx)
                room  = self.rooms[self.hover_edge_room_idx]
                j     = self.hover_edge_idx
                room['vertices'].insert(j + 1, list(self.hover_edge_point))
                self.edit_room_idx   = self.hover_edge_room_idx
                self.edit_vertex_idx = j + 1
                self.hover_edge_room_idx = None
                self.hover_edge_idx      = None
                self.hover_edge_point    = None
                self._update_status("Inserted vertex - drag to reposition", 'cyan')
                self._render_section(force_full=True)
                return
            return  # click on empty space in edit mode

        # Left-click in draw mode: store snapped position for correction on release
        if event.button == 1 and not self.edit_mode and event.xdata is not None and event.ydata is not None:
            x, y = event.xdata, event.ydata

            # Orthogonal constraint: lock to horizontal or vertical from last vertex
            if self.ortho_mode and hasattr(self, 'selector') and self.selector.verts:
                last_x, last_y = self.selector.verts[-1]
                dx, dy = abs(x - last_x), abs(y - last_y)
                if dx >= dy:
                    y = last_y   # horizontal line
                else:
                    x = last_x   # vertical line

            x, y = self._snap_to_pixel(x, y)
            snapped_x, snapped_y = self._snap_to_vertex(x, y)
            self._pending_snap = (snapped_x, snapped_y)

    def _on_button_release(self, event):
        """Handle mouse button release (end of drag, or snap correction)."""
        if event.inaxes != self.ax:
            return

        # Correct the vertex the PolygonSelector just placed with our snapped position
        if (event.button == 1 and not self.edit_mode
                and hasattr(self, '_pending_snap') and self._pending_snap is not None):
            sx, sy = self._pending_snap
            self._pending_snap = None
            # _xys[-1] is the cursor tracking point; the just-added vertex is [-2]
            if len(self.selector._xys) >= 2 and not self.selector._selection_completed:
                self.selector._xys[-2] = (sx, sy)
                self.selector._draw_polygon()

        if self.edit_vertex_idx is not None and self.edit_room_idx is not None:
            room = self.rooms[self.edit_room_idx]
            current_pos = room['vertices'][self.edit_vertex_idx]
            # Snap to pixel centre, then to existing vertex if close
            px, py = self._snap_to_pixel(current_pos[0], current_pos[1])
            sx, sy = self._snap_to_vertex(px, py)
            room['vertices'][self.edit_vertex_idx] = [float(sx), float(sy)]
            self.edit_vertex_idx = None
            self._save_session()
            room_name = room.get('name', 'unnamed')
            self._update_status(f"Moved vertex in '{room_name}'", 'green')
            self._render_section(force_full=True)
            self._create_polygon_selector()

        if self.edit_edge_room_idx is not None and self.edit_edge_idx is not None:
            room = self.rooms[self.edit_edge_room_idx]
            j  = self.edit_edge_idx
            j2 = (j + 1) % len(room['vertices'])
            # Snap both endpoints to pixel centre
            for vi in (j, j2):
                px, py = self._snap_to_pixel(room['vertices'][vi][0], room['vertices'][vi][1])
                room['vertices'][vi] = [float(px), float(py)]
            self.edit_edge_room_idx = None
            self.edit_edge_idx      = None
            self.edit_edge_start    = None
            self._save_session()
            room_name = room.get('name', 'unnamed')
            self._update_status(f"Moved edge in '{room_name}'", 'green')
            self._render_section(force_full=True)
            self._create_polygon_selector()

    def _on_mouse_motion(self, event):
        """Handle mouse movement for hover detection and vertex dragging."""
        if event.inaxes != self.ax:
            return
        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        # Vertex dragging — update polygon in-place without full re-render
        if self.edit_vertex_idx is not None and self.edit_room_idx is not None:
            self.rooms[self.edit_room_idx]['vertices'][self.edit_vertex_idx] = [float(x), float(y)]
            patch = self._room_patch_cache.get(self.edit_room_idx)
            if patch is not None:
                patch.set_xy(self.rooms[self.edit_room_idx]['vertices'])
                label = self._room_label_cache.get(self.edit_room_idx)
                if label is not None:
                    centroid = np.array(self.rooms[self.edit_room_idx]['vertices']).mean(axis=0)
                    label.set_position((centroid[0], centroid[1]))
                self.fig.canvas.draw_idle()
            else:
                self._render_section(force_full=True)
            return

        # Edge dragging — move both endpoints by the same delta
        if self.edit_edge_room_idx is not None and self.edit_edge_idx is not None:
            dx = x - self.edit_edge_start[0]
            dy = y - self.edit_edge_start[1]
            room = self.rooms[self.edit_edge_room_idx]
            j  = self.edit_edge_idx
            j2 = (j + 1) % len(room['vertices'])
            room['vertices'][j][0]  += dx
            room['vertices'][j][1]  += dy
            room['vertices'][j2][0] += dx
            room['vertices'][j2][1] += dy
            self.edit_edge_start = (x, y)
            patch = self._room_patch_cache.get(self.edit_edge_room_idx)
            if patch is not None:
                patch.set_xy(room['vertices'])
                label = self._room_label_cache.get(self.edit_edge_room_idx)
                if label is not None:
                    centroid = np.array(room['vertices']).mean(axis=0)
                    label.set_position((centroid[0], centroid[1]))
                self.fig.canvas.draw_idle()
            else:
                self._render_section(force_full=True)
            return

        if not self.edit_mode:
            return

        # Throttle hover detection
        now = time.monotonic()
        if now - self._last_hover_check < 0.067:
            return
        self._last_hover_check = now

        # Dynamic hover threshold: 1% of the larger image dimension, min 5px
        hover_threshold = max(5.0, max(self._image_width, self._image_height) * 0.01)

        # Vertex hover
        closest_vertex     = None
        closest_dist       = float('inf')
        closest_room_idx   = None
        closest_vertex_idx = None

        for i, room in enumerate(self.rooms):
            is_current = (room.get('hdr_file') == self.current_hdr_name)
            if not is_current:
                continue
            verts = np.array(room['vertices'])
            distances = np.hypot(verts[:, 0] - x, verts[:, 1] - y)
            min_idx   = int(np.argmin(distances))
            min_dist  = distances[min_idx]
            if min_dist < closest_dist:
                closest_dist       = min_dist
                closest_vertex_idx = min_idx
                closest_room_idx   = i

        if closest_dist < hover_threshold:
            changed = (self.hover_room_idx != closest_room_idx or
                       self.hover_vertex_idx != closest_vertex_idx)
            if changed:
                self.hover_room_idx   = closest_room_idx
                self.hover_vertex_idx = int(closest_vertex_idx) if closest_vertex_idx is not None else None
                self.hover_edge_room_idx = None
                self.hover_edge_idx      = None
                self.hover_edge_point    = None
                room_name = self.rooms[closest_room_idx].get('name', 'unnamed')
                self._update_status(f"Vertex in '{room_name}' - drag or right-click to remove", 'cyan')
                self._render_section()
        else:
            vertex_state_changed = self.hover_vertex_idx is not None or self.hover_room_idx is not None
            if vertex_state_changed:
                self.hover_vertex_idx = None
                self.hover_room_idx   = None

            # Edge hover for vertex insertion
            edge_threshold = hover_threshold * 1.3
            best_edge_dist  = float('inf')
            best_edge_room  = None
            best_edge_idx   = None
            best_edge_point = None

            for i, room in enumerate(self.rooms):
                is_current = (room.get('hdr_file') == self.current_hdr_name)
                if not is_current:
                    continue
                verts = room['vertices']
                n     = len(verts)
                for j in range(n):
                    ax_, ay_ = verts[j]
                    bx_, by_ = verts[(j + 1) % n]
                    dist, proj_x, proj_y = self._point_to_segment_dist(x, y, ax_, ay_, bx_, by_)
                    if dist < best_edge_dist:
                        best_edge_dist  = dist
                        best_edge_room  = i
                        best_edge_idx   = j
                        best_edge_point = (proj_x, proj_y)

            if best_edge_dist < edge_threshold:
                changed = (self.hover_edge_room_idx != best_edge_room or
                           self.hover_edge_idx != best_edge_idx)
                self.hover_edge_room_idx = best_edge_room
                self.hover_edge_idx      = best_edge_idx
                self.hover_edge_point    = best_edge_point
                if changed:
                    self._update_status("Click to insert vertex, Shift+click to drag edge", 'blue')
                    self._render_section()
            else:
                if self.hover_edge_room_idx is not None:
                    self.hover_edge_room_idx = None
                    self.hover_edge_idx      = None
                    self.hover_edge_point    = None
                    self._update_status("Edit Mode: Hover over any vertex to drag", 'blue')
                    self._render_section()
                elif vertex_state_changed:
                    self._update_status("Edit Mode: Hover over any vertex to drag", 'blue')
                    self._render_section()

    def _on_key_press(self, event):
        """Handle keyboard shortcuts."""
        if event.key in ('backspace', 'delete', 'escape'):
            if event.key == 'escape':
                self._deselect_room()
            return
        if event.key == 's':
            self._on_save_click(None)
        elif event.key == 'S':
            self._save_session()
        elif event.key == 'd':
            self._on_delete_click(None)
        elif event.key == 'r':
            self._on_reset_zoom_click(None)
        elif event.key == 'q':
            plt.close(self.fig)
        elif event.key == 'up':
            self._on_next_hdr_click(None)
        elif event.key == 'down':
            self._on_prev_hdr_click(None)
        elif event.key == 't':
            self._on_image_toggle_click(None)
        elif event.key == 'e':
            self._on_edit_mode_toggle(None)
        elif event.key == 'o':
            self.ortho_mode = not self.ortho_mode
            state = "ON" if self.ortho_mode else "OFF"
            self._update_status(f"Orthogonal mode: {state}", 'blue')
        elif event.key == 'ctrl+z':
            self._undo_edit()

    def _on_scroll(self, event):
        """Handle scroll wheel for zooming or room list scrolling."""
        if event.inaxes == self.ax_list:
            if event.button == 'down':
                self.room_list_scroll_offset += 1
            else:
                self.room_list_scroll_offset = max(0, self.room_list_scroll_offset - 1)
            now = time.monotonic()
            if now - getattr(self, '_last_list_scroll_draw', 0.0) >= 0.05:
                self._last_list_scroll_draw = now
                self._update_room_list()
            return

        if event.inaxes != self.ax:
            return
        scale  = 1.2 if event.button == 'down' else 1 / 1.2
        xlim   = self.ax.get_xlim()
        ylim   = self.ax.get_ylim()
        xdata, ydata = event.xdata, event.ydata
        new_w  = (xlim[1] - xlim[0]) * scale
        new_h  = (ylim[1] - ylim[0]) * scale
        relx   = (xdata - xlim[0]) / (xlim[1] - xlim[0])
        rely   = (ydata - ylim[0]) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xdata - new_w * relx,   xdata + new_w * (1 - relx)])
        self.ax.set_ylim([ydata - new_h * rely,   ydata + new_h * (1 - rely)])
        self._apply_zoom_linewidths()
        self._apply_zoom_fontsizes()

        now = time.monotonic()
        if now - getattr(self, '_last_scroll_draw', 0.0) >= 0.033:
            self._last_scroll_draw = now
            self.fig.canvas.draw_idle()
        else:
            if hasattr(self, '_scroll_draw_timer') and self._scroll_draw_timer:
                self._scroll_draw_timer.stop()
            self._scroll_draw_timer = self.fig.canvas.new_timer(interval=60)
            self._scroll_draw_timer.single_shot = True
            self._scroll_draw_timer.add_callback(lambda: self.fig.canvas.draw_idle())
            self._scroll_draw_timer.start()

    def _on_resize(self, event):
        """Handle window resize events."""
        if not getattr(self, '_launch_complete', False):
            return
        if event.width > 0 and event.height > 0:
            now = time.monotonic()
            if now - getattr(self, '_last_resize_draw', 0.0) >= 0.1:
                self._last_resize_draw = now
                self.fig.canvas.draw_idle()

    def _force_resize_update(self):
        """Force update after window maximisation."""
        try:
            self._launch_complete = True
            canvas    = self.fig.canvas
            tk_widget = canvas.get_tk_widget()
            tk_widget.update_idletasks()
            width  = tk_widget.winfo_width()
            height = tk_widget.winfo_height()
            if width > 1 and height > 1:
                canvas.resize(width, height)
            canvas.draw_idle()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Room selection
    # -------------------------------------------------------------------------

    def _select_room_at(self, x, y):
        """Select the room polygon at the given point."""
        if x is None or y is None:
            self._deselect_room()
            return
        for i, room in enumerate(self.rooms):
            is_current = (room.get('hdr_file') == self.current_hdr_name)
            if not is_current:
                continue
            verts = np.array(room['vertices'])
            if MplPath(verts).contains_point((x, y)):
                # If room belongs to a different HDR file, navigate to it
                if not is_current:
                    hdr_name = room.get('hdr_file', '')
                    for idx, entry in enumerate(self.hdr_files):
                        if entry['name'] == hdr_name:
                            self._jump_to_hdr(idx)
                            break
                self._select_room(i)
                return
        self._deselect_room()

    def _select_room(self, idx: int):
        """Select a room by index and populate the name textbox."""
        self._deselect_room()
        self.selected_room_idx = idx
        room = self.rooms[idx]
        self.name_textbox.set_val(room.get('name', ''))
        self._update_status(f"Selected: {room.get('name', 'unnamed')}", 'orange')
        self._render_section()

    def _deselect_room(self):
        """Deselect any selected room."""
        if self.selected_room_idx is not None:
            self.selected_room_idx = None
            self.name_textbox.set_val('')
            self._update_status("Ready to draw", 'blue')
            self._update_room_list()
            self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Polygon selector
    # -------------------------------------------------------------------------

    def _create_polygon_selector(self):
        """Create or recreate the polygon selector."""
        self.selector = PolygonSelector(
            self.ax,
            self._on_polygon_select,
            useblit=True,
            props=dict(color='cyan', linestyle='-', linewidth=2, alpha=0.5),
            handle_props=dict(markersize=8, markerfacecolor='lime',
                              markeredgecolor='darkgreen', markeredgewidth=1.5),
        )

    def _on_polygon_select(self, vertices):
        """Callback when a polygon drawing is completed."""
        if len(vertices) < 3:
            return
        self.current_polygon_vertices = list(vertices)
        if self.selected_room_idx is not None:
            self._deselect_room()
        area = 0.5 * abs(
            np.dot([v[0] for v in vertices], np.roll([v[1] for v in vertices], 1))
            - np.dot([v[1] for v in vertices], np.roll([v[0] for v in vertices], 1))
        )
        self._update_status(f"Polygon ready: {len(vertices)} pts, {area:.0f} px2", 'green')

    # -------------------------------------------------------------------------
    # Button callbacks
    # -------------------------------------------------------------------------

    def _on_save_click(self, event):
        """Save room, update selected room, or save edited boundary."""
        if self.edit_mode and self.edit_room_idx is not None:
            self._save_edited_room()
        elif self.selected_room_idx is not None:
            self._update_selected_room()
        else:
            self._save_current_room()

    def _save_edited_room(self):
        """Save changes to an edited room boundary (also applies name edit)."""
        if self.edit_room_idx is None:
            return
        room = self.rooms[self.edit_room_idx]

        # Apply name from textbox if provided
        typed_name = self.name_textbox.text.strip().upper()
        if typed_name and typed_name != room.get('name', ''):
            new_name = self._make_unique_name(typed_name, exclude_idx=self.edit_room_idx)
            room['name'] = new_name

        name = room.get('name', 'unnamed')
        self._save_session()
        self.edit_room_idx    = None
        self.hover_vertex_idx = None
        self._update_status(f"Saved changes for '{name}'", 'green')
        self._render_section(force_full=True)
        self._create_polygon_selector()
        self._update_room_list()
        self._update_hdr_list()
        print(f"Saved edited room '{name}'")

    def _save_current_room(self):
        """Save the currently drawn polygon as a new room."""
        if len(self.current_polygon_vertices) < 3:
            self._update_status("No polygon to save - draw one first", 'red')
            return

        name = self.name_textbox.text.strip().upper()
        if not name:
            name = f"ROOM_{len(self.rooms) + 1:03d}"

        if self.selected_parent:
            full_name = f"{self.selected_parent}_{name}"
        else:
            full_name = name

        full_name = self._make_unique_name(full_name)
        vertices  = [[float(x), float(y)] for x, y in self.current_polygon_vertices]

        # Boundary containment check
        warning_msg      = ""
        is_outside_parent = False
        if self.selected_parent:
            parent_room = self._get_parent_room(self.selected_parent)
            if parent_room:
                is_outside_parent = not self._check_boundary_containment(vertices, parent_room['vertices'])
                if is_outside_parent:
                    warning_msg = " (WARNING: extends outside parent boundary!)"
                    print(f"WARNING: Room '{full_name}' extends outside parent '{self.selected_parent}'")
            else:
                print(f"Warning: Parent room '{self.selected_parent}' not found")

        room = {
            'name':     full_name,
            'parent':   self.selected_parent,
            'vertices': vertices,
            'hdr_file': self.current_hdr_name,
        }
        self.rooms.append(room)

        status_color = 'orange' if is_outside_parent else 'green'
        self._update_status(f"Saved '{full_name}'{warning_msg}", status_color)
        print(f"Saved room '{full_name}' on HDR '{self.current_hdr_name}'")

        # Reset drawing state
        self.current_polygon_vertices = []
        self.name_textbox.set_val('')
        self._update_parent_options()
        self._save_session()
        self._update_room_list()
        self._update_hdr_list()
        self._render_section(force_full=True)
        self._create_polygon_selector()

    def _update_selected_room(self):
        """Update the name of the selected room."""
        if self.selected_room_idx is None:
            return
        idx      = self.selected_room_idx
        new_name = self.name_textbox.text.strip().upper() or self.rooms[idx]['name']
        new_name = self._make_unique_name(new_name, exclude_idx=idx)
        self.rooms[idx]['name'] = new_name
        self._update_status(f"Updated '{new_name}'", 'green')
        self._update_room_list()
        self._render_section(force_full=True)
        self._save_session()

    def _on_clear_click(self, event):
        """Clear the current polygon drawing."""
        self._deselect_room()
        self.current_polygon_vertices = []
        self.selector.clear()
        self._update_status("Cleared - ready to draw", 'blue')

    def _on_delete_click(self, event):
        """Delete the selected room."""
        if self.selected_room_idx is None:
            self._update_status("No room selected to delete", 'red')
            return
        idx  = self.selected_room_idx
        name = self.rooms[idx].get('name', 'unnamed')
        self.rooms.pop(idx)
        self.selected_room_idx = None
        self._update_status(f"Deleted '{name}'", 'green')
        self._update_room_list()
        self._update_hdr_list()
        self._render_section(force_full=True)
        print(f"Deleted room '{name}'")
        self._save_session()

    def _view_ratio(self) -> float:
        """Return view_w / image_width. 1.0 = fully zoomed out, <1 = zoomed in."""
        if self._image_width <= 1:
            return 1.0
        view_w = abs(self.ax.get_xlim()[1] - self.ax.get_xlim()[0])
        return max(0.01, view_w / self._image_width)

    def _zoom_fontsize(self, base: float = 8.0) -> float:
        """Return font size scaled relative to the default (full-image) zoom.

        At default zoom returns base. Scales down when zoomed out further,
        scales up when zoomed in. Clamps to [4, 20].
        """
        if self._reference_view_w <= 1:
            return base
        view_w = abs(self.ax.get_xlim()[1] - self.ax.get_xlim()[0])
        scale  = self._reference_view_w / max(view_w, 1.0)
        return max(4.0, min(20.0, base * scale))

    def _df_line_step(self) -> float:
        """Return zoom-aware vertical spacing (in data coords) between DF result lines."""
        view_w = abs(self.ax.get_xlim()[1] - self.ax.get_xlim()[0])
        return view_w * 0.025

    def _apply_zoom_fontsizes(self):
        """Reapply zoom-dependent font sizes to all cached room labels and DF text."""
        fs = self._zoom_fontsize()
        for label in self._room_label_cache.values():
            if label is not None:
                label.set_fontsize(fs)
        fs_df = self._zoom_fontsize(base=6.5)
        line_step = self._df_line_step()
        for dt in self._df_text_cache:
            dt.set_fontsize(fs_df)
            # Reposition based on current zoom-aware line step
            centroid = getattr(dt, '_df_centroid', None)
            line_i   = getattr(dt, '_df_line_i', None)
            if centroid is not None and line_i is not None:
                dt.set_position((centroid[0], centroid[1] + (line_i + 1) * line_step))

    def _zoom_linewidth(self, base: float = 1.5) -> float:
        """Return linewidth that stays visually constant regardless of zoom.

        Scales proportionally with view_ratio so the line appears the same
        screen thickness at all zoom levels. Clamps to [0.3, base].
        """
        lw = base * self._view_ratio()
        return max(0.3, min(base, lw))

    def _apply_zoom_linewidths(self):
        """Reapply zoom-dependent linewidths to all cached room patches."""
        for i, room in enumerate(self.rooms):
            patch = self._room_patch_cache.get(i)
            if patch is None:
                continue
            ec = patch.get_edgecolor()
            r, g, b = ec[0], ec[1], ec[2]
            # Only scale red and gray patches; leave cyan/yellow/magenta fixed
            if np.allclose([r, g, b], [1, 0, 0]):
                patch.set_linewidth(self._zoom_linewidth())
            elif np.allclose([r, g, b], [0.5, 0.5, 0.5], atol=0.1):
                patch.set_linewidth(self._zoom_linewidth(base=1.0))


    def _on_reset_zoom_click(self, event):
        """Reset zoom to the full image extent."""
        self.ax.set_xlim(0, self._image_width)
        self.ax.set_ylim(self._image_height, 0)
        self._apply_zoom_linewidths()
        self._apply_zoom_fontsizes()
        self.fig.canvas.draw_idle()

    def _on_edit_mode_toggle(self, event):
        """Toggle edit mode for modifying existing room boundaries."""
        self.edit_mode = not self.edit_mode
        self.btn_edit_mode.label.set_text(
            'Edit Mode: ON (Press E)' if self.edit_mode else 'Edit Mode: OFF (Press E)')

        if self.edit_mode:
            self._edit_undo_stack.clear()
            if hasattr(self, 'selector'):
                self.selector.set_active(False)
            self._update_status("Edit Mode: Hover over any vertex to drag (all rooms editable)", 'cyan')
        else:
            self.edit_room_idx       = None
            self.edit_vertex_idx     = None
            self.hover_room_idx      = None
            self.hover_vertex_idx    = None
            self.hover_edge_room_idx = None
            self.hover_edge_idx      = None
            self.hover_edge_point    = None
            self._edit_undo_stack.clear()
            self._save_session()
            self._create_polygon_selector()
            self._update_status("Edit Mode OFF - Draw mode enabled", 'blue')

        self._render_section(force_full=True)

    def _enter_edit_mode_for_room(self, room_idx: int):
        """Enter edit mode for a specific room."""
        self.edit_room_idx    = room_idx
        self.hover_vertex_idx = None
        room = self.rooms[room_idx]
        self._update_status(f"Editing: {room.get('name', 'unnamed')} - drag vertices to modify", 'cyan')
        self._render_section(force_full=True)
        self._create_polygon_selector()


    # -------------------------------------------------------------------------
    # Status and room list display
    # -------------------------------------------------------------------------

    def _update_status(self, message: str, color: str = 'blue'):
        """Update the status text in the side panel."""
        if hasattr(self, 'status_text') and self.status_text is not None:
            self.status_text.set_text(f"Status: {message}")
            self.status_text.set_color(color)
            self.fig.canvas.draw_idle()

    def _update_room_list(self):
        """Refresh the saved rooms list as a scrollable, click-to-select panel."""
        self.ax_list.clear()
        self.ax_list.set_facecolor('#FAFAF8')
        self.ax_list.set_xlim(0, 1)
        self.ax_list.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for spine in self.ax_list.spines.values():
            spine.set_edgecolor('#CCCCCC')
            spine.set_linewidth(0.5)

        self._room_list_hit_boxes = []

        # Filter rooms to current HDR
        hdr_rooms = [(i, r) for i, r in enumerate(self.rooms)
                     if r.get('hdr_file') == self.current_hdr_name]

        if not hdr_rooms:
            self.ax_list.set_ylim(0, 1)
            self.ax_list.text(0.05, 0.5, "(no rooms on this HDR)", fontsize=7,
                              style='italic', color='gray', va='center')
            self.fig.canvas.draw_idle()
            return

        # Build flat list: apartments → children
        flat_items           = []
        apartments           = [(i, r) for i, r in hdr_rooms if r.get('parent') is None]
        children_by_parent   = {}
        for i, room in hdr_rooms:
            parent = room.get('parent')
            if parent is not None:
                children_by_parent.setdefault(parent, []).append((i, room))

        for apt_idx, apt in apartments:
            flat_items.append((apt_idx, 0))
            for child_idx, _ in children_by_parent.get(apt.get('name', ''), []):
                flat_items.append((child_idx, 1))

        total_items  = len(flat_items)
        visible_rows = 22
        pad_top      = 0.01
        pad_bot      = 0.03
        content_h    = 1.0 - pad_top - pad_bot
        row_h        = content_h / visible_rows

        max_offset = max(0, total_items - visible_rows)
        self.room_list_scroll_offset = max(0, min(self.room_list_scroll_offset, max_offset))
        self.ax_list.set_ylim(0, 1)

        visible_slice = flat_items[self.room_list_scroll_offset:
                                   self.room_list_scroll_offset + visible_rows]

        for row_i, (room_idx, indent) in enumerate(visible_slice):
            room    = self.rooms[room_idx]
            name    = room.get('name', 'unnamed')
            is_sel  = (room_idx == self.selected_room_idx)
            is_subroom = indent > 0

            row_top = (1.0 - pad_top) - row_i * row_h
            row_bot = row_top - row_h
            row_mid = (row_top + row_bot) / 2

            if is_sel:
                bg = FancyBboxPatch((0.01, row_bot + 0.002), 0.98, row_h - 0.004,
                                    boxstyle='round,pad=0.01',
                                    facecolor='#FFE082', edgecolor='orange', linewidth=1.0,
                                    transform=self.ax_list.transAxes, clip_on=True)
                self.ax_list.add_patch(bg)

            if is_subroom:
                parent_name = room.get('parent', '')
                short_name  = name[len(parent_name) + 1:] if name.startswith(f"{parent_name}_") else name
                display_text = f"  \u2514 {short_name}"
                txt_color = '#0D47A1' if not is_sel else '#E65100'
                fs, fw = 6.5, 'normal'
            else:
                child_count  = len(children_by_parent.get(name, []))
                suffix       = f" ({child_count})" if child_count else ""
                display_text = f"{name}{suffix}"
                txt_color = '#1B5E20' if not is_sel else '#E65100'
                fs, fw = 7, 'bold'

            self.ax_list.text(
                0.03 + indent * 0.04, row_mid, display_text,
                fontsize=fs, fontweight=fw, color=txt_color,
                va='center', transform=self.ax_list.transAxes, clip_on=True,
            )
            self._room_list_hit_boxes.append((row_bot, row_top, room_idx))

        if total_items > visible_rows:
            scroll_pct  = self.room_list_scroll_offset / max(1, max_offset)
            indicator_h = visible_rows / total_items
            indicator_y = (1.0 - indicator_h) * (1.0 - scroll_pct)
            scrollbar = FancyBboxPatch((0.965, indicator_y), 0.025, indicator_h,
                                       boxstyle='round,pad=0.005',
                                       facecolor='#AAAAAA', edgecolor='none',
                                       transform=self.ax_list.transAxes, clip_on=True)
            self.ax_list.add_patch(scrollbar)
            self.ax_list.text(0.5, 0.01,
                              f"\u2191\u2193 scroll  ({self.room_list_scroll_offset + 1}"
                              f"-{min(self.room_list_scroll_offset + visible_rows, total_items)}"
                              f" of {total_items})",
                              fontsize=6, color='#888888', ha='center', va='bottom',
                              transform=self.ax_list.transAxes)

        self.fig.canvas.draw_idle()

    def _on_list_click(self, event):
        """Handle clicks on the saved rooms list to select a room."""
        if event.inaxes != self.ax_list:
            return
        if event.xdata is None or event.ydata is None:
            return
        y = event.ydata
        for (y_min, y_max, room_idx) in self._room_list_hit_boxes:
            if y_min <= y <= y_max:
                if self.selected_room_idx == room_idx:
                    self.selected_room_idx = None
                else:
                    self.selected_room_idx = room_idx
                self._render_section()
                self._update_room_list()
                return

    # -------------------------------------------------------------------------
    # Session persistence
    # -------------------------------------------------------------------------

    def _save_session(self):
        """Save all room boundaries to JSON only."""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'image_dir': str(self.image_dir),
            'rooms':     self.rooms,
        }
        with open(self.session_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Session saved to {self.session_path}")
        # Remove stale CSV so the JSON is the single source of truth
        if self.csv_path.exists():
            self.csv_path.unlink()
            print(f"Removed stale CSV: {self.csv_path}")

    def _load_session(self):
        """Load room boundaries from JSON session or AOI files."""
        if self.session_path.exists():
            with open(self.session_path, 'r') as f:
                data = json.load(f)
            self.rooms = data.get('rooms', [])
            source = "session"
        elif self.aoi_dir.exists() and list(self.aoi_dir.glob('*.aoi')):
            self._load_from_aoi_files(self.aoi_dir)
            source = "AOI files"
        else:
            return

        renamed_count = self._enforce_unique_names()
        if renamed_count > 0:
            print(f"Renamed {renamed_count} rooms to ensure uniqueness")
            self._save_session()

        self._update_status(f"Loaded {len(self.rooms)} rooms from {source}", 'green')
        if hasattr(self, 'ax'):
            self._render_section(force_full=True)
        print(f"Loaded {len(self.rooms)} rooms from {source}")


    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def _show_progress(self, fraction: float, label: str = ""):
        """Update the export progress bar (0.0–1.0) and optional label."""
        if not hasattr(self, 'ax_progress'):
            return
        self.ax_progress.clear()
        self.ax_progress.set_xlim(0, 1)
        self.ax_progress.set_ylim(0, 1)
        self.ax_progress.axis('off')

        # Background track
        self.ax_progress.add_patch(FancyBboxPatch(
            (0, 0.1), 1.0, 0.8, boxstyle='round,pad=0.02',
            facecolor='#E0E0E0', edgecolor='#CCCCCC', linewidth=0.5,
        ))
        # Filled portion
        if fraction > 0:
            self.ax_progress.add_patch(FancyBboxPatch(
                (0, 0.1), max(0.01, min(fraction, 1.0)), 0.8,
                boxstyle='round,pad=0.02',
                facecolor='#4CAF50', edgecolor='none',
            ))
        # Label
        display = label or f"{fraction * 100:.0f}%"
        self.ax_progress.text(
            0.5, 0.5, display, fontsize=7, color='#333333',
            ha='center', va='center', fontweight='bold',
        )
        self.ax_progress.set_visible(True)

    def _hide_progress(self):
        """Hide the export progress bar."""
        if hasattr(self, 'ax_progress'):
            self.ax_progress.set_visible(False)

    def _on_export_report(self, event):
        """Export .aoi files for all rooms, generate .wpd files, and produce Excel report.

        The heavy work (pvalue, rasterisation, Excel) runs in a background
        thread so the UI stays responsive.  A matplotlib timer polls for
        completion and updates the progress bar.
        """
        if self._hdr2wpd is None:
            self._update_status("Export unavailable - DF analysis not initialised", 'red')
            return
        if not self.rooms:
            self._update_status("No rooms to export", 'red')
            return
        if getattr(self, '_export_thread', None) and self._export_thread.is_alive():
            self._update_status("Export already in progress...", 'orange')
            return

        # Phase 1 (fast, main thread): write .aoi files and clear stale .wpd
        try:
            n_aoi = self._export_rooms_as_aoi_files()
            wpd_dir = config.WPD_DIR
            if wpd_dir.exists():
                for wpd_file in wpd_dir.glob('*.wpd'):
                    wpd_file.unlink()
        except Exception as exc:
            self._update_status(f"Export failed writing .aoi: {exc}", 'red')
            return

        self._update_status(f"Exporting {n_aoi} rooms...", 'orange')
        self.btn_export.label.set_text('Exporting...')
        self._show_progress(0.0, f"0 / {n_aoi} rooms")
        self.fig.canvas.draw_idle()

        # Shared progress state updated by background thread
        progress = {'done': 0, 'total': n_aoi, 'phase': 'wpd', 'error': None}

        def _run():
            try:
                # --- WPD generation (per-room progress) ---
                hdr_files, aoi_files = self._hdr2wpd._scan_directories()
                if hdr_files and aoi_files:
                    view_groups = self._hdr2wpd._group_aoi_by_view(aoi_files, hdr_files)
                    # Count total AOIs across all groups
                    total_aois = sum(len(g['aoi_files']) for g in view_groups.values())
                    progress['total'] = max(total_aois, 1)
                    processed = 0
                    for view_name, group in view_groups.items():
                        aoi_list, hdr_list = group['aoi_files'], group['hdr_files']
                        if not aoi_list or not hdr_list:
                            continue
                        # Process this view group (creates .wpd files)
                        self._hdr2wpd._process_daylight_view_groups({view_name: group})
                        processed += len(aoi_list)
                        progress['done'] = processed

                # --- Excel report ---
                progress['phase'] = 'excel'
                self._hdr2wpd._generate_daylight_excel_report(
                    df_thresholds=tuple(self.df_thresholds))
                progress['phase'] = 'done'
            except Exception as exc:
                progress['error'] = exc

        self._export_thread = threading.Thread(target=_run, daemon=True)
        self._export_thread.start()

        # Poll every 300 ms — update progress bar on the main thread
        def _check_progress():
            total = max(progress['total'], 1)
            done  = progress['done']
            phase = progress['phase']

            if self._export_thread.is_alive():
                if phase == 'excel':
                    self._show_progress(0.95, "Generating Excel report...")
                else:
                    frac = done / total * 0.9  # reserve last 10% for Excel
                    self._show_progress(frac, f"{done} / {total} rooms")
                self.fig.canvas.draw_idle()
                return  # timer fires again

            # Thread finished
            self._export_poll_timer.stop()
            if progress['error']:
                self._update_status(f"Export failed: {progress['error']}", 'red')
                print(f"Export error: {progress['error']}")
                self._show_progress(1.0, "Export failed")
            else:
                self._update_status(f"Export complete - {n_aoi} rooms -> Excel report", 'green')
                self._show_progress(1.0, "Export complete")
            self.btn_export.label.set_text('Export Report')
            self.fig.canvas.draw_idle()

            # Auto-hide progress bar after 4 seconds
            hide_timer = self.fig.canvas.new_timer(interval=4000)
            hide_timer.single_shot = True
            hide_timer.add_callback(lambda: (self._hide_progress(), self.fig.canvas.draw_idle()))
            hide_timer.start()

        self._export_poll_timer = self.fig.canvas.new_timer(interval=300)
        self._export_poll_timer.add_callback(_check_progress)
        self._export_poll_timer.start()

    def _export_rooms_as_aoi_files(self) -> int:
        """Write editor rooms as .aoi files compatible with Hdr2Wpd.

        Each .aoi file follows the standard format with headers that
        Hdr2Wpd._group_aoi_by_view() and _process_daylight_view_groups()
        expect. Pixel→world conversion uses the coordinate map header.

        Returns:
            Number of .aoi files written.
        """
        # Parse pixel→world mapping parameters from the coordinate map header
        coord_map_path = self.aoi_dir / "pixel_to_world_coordinate_map.txt"
        vp_x = vp_y = vh = vv = 0.0
        img_w = img_h = 1
        if coord_map_path.exists():
            with open(coord_map_path, 'r') as f:
                header_lines = [f.readline() for _ in range(4)]
            # Line 0: # VIEW: VIEW= -vtl v -vp X Y Z ... -vh VH -vv VV
            view_line = header_lines[0]
            vp_match = re.search(r'-vp\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', view_line)
            if vp_match:
                vp_x, vp_y = float(vp_match.group(1)), float(vp_match.group(2))
            vh_match = re.search(r'-vh\s+([\d.-]+)', view_line)
            vv_match = re.search(r'-vv\s+([\d.-]+)', view_line)
            if vh_match:
                vh = float(vh_match.group(1))
            if vv_match:
                vv = float(vv_match.group(1))
            # Line 1: # Image dimensions in pixels: width=W, height=H
            dim_line = header_lines[1]
            img_w = int(dim_line.split('width=')[1].split(',')[0])
            img_h = int(dim_line.split('height=')[1])

        self.aoi_dir.mkdir(parents=True, exist_ok=True)
        count = 0

        for room in self.rooms:
            name     = room.get('name', 'unnamed')
            hdr_name = room.get('hdr_file', '')
            verts    = room['vertices']
            if len(verts) < 3:
                continue

            # Derive associated view file from HDR name (e.g. model_plan_ffl_25300 → plan_ffl_25300.vp)
            ffl_match = re.search(r'plan_ffl_(\d+)', hdr_name)
            associated_vp = f"plan_ffl_{ffl_match.group(1)}.vp" if ffl_match else f"{hdr_name}.vp"

            # Compute centroid in pixel space
            cx = sum(v[0] for v in verts) / len(verts)
            cy = sum(v[1] for v in verts) / len(verts)

            # Build vertex lines: world_x world_y pixel_x pixel_y
            vertex_lines = []
            for px, py in verts:
                if vh > 0 and vv > 0:
                    world_x = vp_x + (px - img_w / 2) * (vh / img_w)
                    world_y = vp_y + (img_h / 2 - py) * (vv / img_h)
                else:
                    world_x, world_y = px, py
                vertex_lines.append(f"{world_x:.4f} {world_y:.4f} {int(round(px))} {int(round(py))}")

            content = "\n".join([
                f"AOI Points File: {name}",
                f"ASSOCIATED VIEW FILE: {associated_vp}",
                f"FFL z height(m): 0.0",
                f"CENTRAL x,y: {cx:.4f} {cy:.4f}",
                f"NO. PERIMETER POINTS {len(verts)}: x,y pixel_x pixel_y positions",
            ] + vertex_lines)

            clean_name = re.sub(r'[^\w\s-]', '', name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
            filepath = self.aoi_dir / f"{clean_name}.aoi"
            with open(filepath, 'w') as f:
                f.write(content)
            count += 1

        print(f"Wrote {count} .aoi files to {self.aoi_dir}")
        return count

    def export_room_boundaries_csv(self, output_path: Optional[Path] = None):
        """Export room boundaries as CSV.

        Format: name, parent, hdr_file, X_px Y_px, X_px Y_px, ...
        """
        if not self.rooms:
            return

        output_path = Path(output_path) if output_path else self.csv_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for room in self.rooms:
            coord_strings = [f"X_{x:.3f} Y_{y:.3f}" for x, y in room['vertices']]
            parent   = room.get('parent') or ''
            hdr_file = room.get('hdr_file', '')
            rows.append([room['name'], parent, hdr_file] + coord_strings)

        max_cols = max(len(r) for r in rows)
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            for row in rows:
                row += [''] * (max_cols - len(row))
                writer.writerow(row)

        self._update_status(f"Exported CSV ({len(self.rooms)} rooms)", 'green')
        print(f"Exported room boundaries CSV to {output_path}")
