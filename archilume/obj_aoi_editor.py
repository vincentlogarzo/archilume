"""
Interactive Room Boundary Editor for OBJ Models - Version 2 (Hierarchical).

Slices a 3D OBJ mesh at a user-specified Z height to produce a 2D floor plan
cross-section for drawing apartment and sub-room boundaries. Supports hierarchical
parent/child relationships (e.g. U101 → U101_BED1). Auto-saves JSON and CSV
alongside the input OBJ on every save or delete action.

Usage:
    from archilume.obj_aoi_editor import ObjAoiEditor
    editor = ObjAoiEditor(obj_path="model.obj")
    editor.launch()
"""

# Archilume imports
from archilume import config

# Standard library imports
import csv
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

# Third-party imports
import matplotlib.pyplot as plt
from matplotlib.widgets import PolygonSelector, TextBox, Button, Slider
from matplotlib.patches import Polygon, FancyBboxPatch
from matplotlib.path import Path as MplPath
from matplotlib.collections import LineCollection
import numpy as np
import pyvista as pv
from scipy.spatial import cKDTree

# fmt: off
# autopep8: off


class MeshSlicer:
    """Extract 2D cross-sections from 3D triangle meshes at specified Z heights.

    Loads OBJ files via PyVista and uses VTK's cutter filter to compute
    horizontal plane intersections, returning 2D line segments in world
    coordinates (meters).

    Attributes:
        mesh: Combined PyVista mesh from all loaded OBJ files.
        z_min: Minimum Z coordinate across all vertices.
        z_max: Maximum Z coordinate across all vertices.
        floor_levels: List of detected floor level Z heights (meters).
    """

    def __init__(self, obj_path: Union[Path, str], simplify_ratio: Optional[float] = None, detect_floors: bool = True):
        """Initialize mesh slicer with optional simplification.

        Args:
            obj_path: OBJ file path to load
            simplify_ratio: Optional mesh decimation ratio (0.0-1.0). E.g., 0.5 reduces mesh to 50% of original.
                           Useful for large meshes to improve performance. None = no simplification.
            detect_floors: Whether to automatically detect floor levels on load. Set to False for very large
                          meshes to speed up initialization.
        """
        obj_path = Path(obj_path)
        if not obj_path.exists():
            raise FileNotFoundError(f"OBJ file not found: {obj_path}")
        self.mesh = pv.read(str(obj_path))

        # Apply mesh simplification if requested
        if simplify_ratio is not None and 0.0 < simplify_ratio < 1.0:
            original_cells = self.mesh.n_cells
            print(f"Simplifying mesh from {original_cells:,} cells to {int(original_cells * simplify_ratio):,} cells...")
            self.mesh = self.mesh.decimate(1.0 - simplify_ratio)  # decimate takes reduction ratio
            print(f"Mesh simplified to {self.mesh.n_cells:,} cells ({self.mesh.n_cells / original_cells * 100:.1f}% of original)")

        bounds = self.mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
        self.z_min = bounds[4]
        self.z_max = bounds[5]
        self.x_min = bounds[0]
        self.x_max = bounds[1]
        self.y_min = bounds[2]
        self.y_max = bounds[3]

        # Detect floor levels if requested
        if detect_floors:
            self.floor_levels = self._detect_floor_levels()
        else:
            self.floor_levels = []
            print("Floor detection skipped (can be enabled later)")

        # Initialize slice cache (LRU cache for performance)
        self.slice_cache: OrderedDict[float, Tuple] = OrderedDict()
        self.cache_size_limit = 50  # Store up to 50 slices

    def _detect_floor_levels(self,
                            z_resolution: float = 0.1,
                            horizontal_tolerance: float = 0.1,
                            min_area_ratio: float = 0.01,
                            vertical_separation: float = 2.0) -> List[float]:
        """Detect floor levels by analyzing horizontal surfaces in the mesh.

        Identifies horizontal surfaces (floors) by:
        1. Extracting face normals and checking for upward-facing surfaces
        2. Clustering these surfaces by Z height
        3. Filtering by area to find significant floor levels
        4. Ensuring minimum vertical separation between levels

        Args:
            z_resolution: Z-height binning resolution (meters)
            horizontal_tolerance: Maximum angle deviation from horizontal (radians)
            min_area_ratio: Minimum floor area as ratio of total horizontal area
            vertical_separation: Minimum Z distance between floor levels (meters)

        Returns:
            Sorted list of detected floor level Z heights (meters)
        """
        print("Detecting floor levels...")

        # Compute face normals if not present
        mesh_with_normals = self.mesh.compute_normals(cell_normals=True, point_normals=False)

        # Extract cell centers and normals
        cell_centers = mesh_with_normals.cell_centers().points
        cell_normals = mesh_with_normals['Normals']

        # Filter for horizontal upward-facing surfaces
        # Check if normals point upward (z-component close to 1)
        z_component = cell_normals[:, 2]
        horizontal_mask = z_component > np.cos(horizontal_tolerance)

        if not horizontal_mask.any():
            print("No horizontal surfaces detected")
            return []

        horizontal_centers = cell_centers[horizontal_mask]
        horizontal_z = horizontal_centers[:, 2]

        # Compute cell areas for horizontal faces (VECTORIZED for performance)
        # Use PyVista's compute_cell_sizes for fast area calculation
        mesh_with_sizes = mesh_with_normals.compute_cell_sizes(length=False, area=True, volume=False)
        all_areas = mesh_with_sizes['Area']

        # Extract only horizontal face areas
        horizontal_areas = all_areas[horizontal_mask]
        total_horizontal_area = horizontal_areas.sum()

        if total_horizontal_area == 0:
            print("No significant horizontal area detected")
            return []

        # Bin horizontal surfaces by Z height
        z_bins = np.arange(self.z_min, self.z_max + z_resolution, z_resolution)
        z_bin_indices = np.digitize(horizontal_z, z_bins)

        # Aggregate area by Z bin
        bin_areas = {}
        for bin_idx, area in zip(z_bin_indices, horizontal_areas):
            if bin_idx not in bin_areas:
                bin_areas[bin_idx] = 0.0
            bin_areas[bin_idx] += area

        # Find significant floor levels
        min_area_threshold = min_area_ratio * total_horizontal_area
        candidate_floors = []

        for bin_idx, area in bin_areas.items():
            if area >= min_area_threshold and 0 <= bin_idx < len(z_bins):
                z_height = z_bins[bin_idx]
                candidate_floors.append((z_height, area))

        # Sort by Z height
        candidate_floors.sort(key=lambda x: x[0])

        # Filter to ensure minimum vertical separation
        filtered_floors = []
        for z, area in candidate_floors:
            if not filtered_floors or (z - filtered_floors[-1] >= vertical_separation):
                filtered_floors.append(z)

        print(f"Detected {len(filtered_floors)} floor levels: {[f'{z:.2f}m' for z in filtered_floors]}")
        return filtered_floors

    def slice_at_z(self, z_height: float) -> tuple:
        """Compute the intersection of the mesh with a horizontal plane.

        Uses LRU caching for improved performance with repeated slicing operations.

        Args:
            z_height: The Z coordinate of the slicing plane (meters).

        Returns:
            Tuple of (segments, vertices):
            - segments: List of line segments as [(x1, y1, x2, y2), ...] in world coordinates
            - vertices: numpy array of unique vertices (N, 2) from the slice
        """
        # Round to avoid floating point cache misses
        z_rounded = round(z_height, 1)

        # Check cache first
        if z_rounded in self.slice_cache:
            # Move to end (most recently used)
            self.slice_cache.move_to_end(z_rounded)
            return self.slice_cache[z_rounded]

        # Compute slice
        result = self._compute_slice(z_height)

        # Update cache with LRU eviction
        if len(self.slice_cache) >= self.cache_size_limit:
            # Remove least recently used (first item)
            self.slice_cache.popitem(last=False)
        self.slice_cache[z_rounded] = result

        return result

    def _compute_slice(self, z_height: float) -> tuple:
        """Internal method to compute mesh slice without caching.

        Args:
            z_height: The Z coordinate of the slicing plane (meters).

        Returns:
            Tuple of (segments, vertices)
        """
        section = self.mesh.slice(normal='z', origin=(0, 0, z_height))

        if section.n_points == 0:
            return [], np.array([])

        points = section.points  # (N, 3) array
        segments = []
        unique_vertices = set()

        # Extract line segments from the PolyData lines connectivity
        if section.lines is not None and len(section.lines) > 0:
            lines = section.lines
            i = 0
            while i < len(lines):
                n_pts = lines[i]
                for j in range(n_pts - 1):
                    p1 = points[lines[i + 1 + j]]
                    p2 = points[lines[i + 2 + j]]
                    segments.append((p1[0], p1[1], p2[0], p2[1]))
                    unique_vertices.add((p1[0], p1[1]))
                    unique_vertices.add((p2[0], p2[1]))
                i += n_pts + 1

        # Convert to numpy array
        vertices_array = np.array(list(unique_vertices)) if unique_vertices else np.array([])

        return segments, vertices_array

    def slice_elevation_x(self, x_position: float) -> tuple:
        """Compute elevation slice perpendicular to X-axis (YZ plane).

        Args:
            x_position: The X coordinate of the slicing plane (meters).

        Returns:
            Tuple of (segments, vertices):
            - segments: List of line segments as [(y1, z1, y2, z2), ...]
            - vertices: numpy array of unique vertices (N, 2) as (y, z) coordinates
        """
        section = self.mesh.slice(normal='x', origin=(x_position, 0, 0))

        if section.n_points == 0:
            return [], np.array([])

        points = section.points  # (N, 3) array
        segments = []
        unique_vertices = set()

        if section.lines is not None and len(section.lines) > 0:
            lines = section.lines
            i = 0
            while i < len(lines):
                n_pts = lines[i]
                for j in range(n_pts - 1):
                    p1 = points[lines[i + 1 + j]]
                    p2 = points[lines[i + 2 + j]]
                    # Return (y, z) coordinates for elevation
                    segments.append((p1[1], p1[2], p2[1], p2[2]))
                    unique_vertices.add((p1[1], p1[2]))
                    unique_vertices.add((p2[1], p2[2]))
                i += n_pts + 1

        vertices_array = np.array(list(unique_vertices)) if unique_vertices else np.array([])
        return segments, vertices_array

    def slice_elevation_y(self, y_position: float) -> tuple:
        """Compute elevation slice perpendicular to Y-axis (XZ plane).

        Args:
            y_position: The Y coordinate of the slicing plane (meters).

        Returns:
            Tuple of (segments, vertices):
            - segments: List of line segments as [(x1, z1, x2, z2), ...]
            - vertices: numpy array of unique vertices (N, 2) as (x, z) coordinates
        """
        section = self.mesh.slice(normal='y', origin=(0, y_position, 0))

        if section.n_points == 0:
            return [], np.array([])

        points = section.points  # (N, 3) array
        segments = []
        unique_vertices = set()

        if section.lines is not None and len(section.lines) > 0:
            lines = section.lines
            i = 0
            while i < len(lines):
                n_pts = lines[i]
                for j in range(n_pts - 1):
                    p1 = points[lines[i + 1 + j]]
                    p2 = points[lines[i + 2 + j]]
                    # Return (x, z) coordinates for elevation
                    segments.append((p1[0], p1[2], p2[0], p2[2]))
                    unique_vertices.add((p1[0], p1[2]))
                    unique_vertices.add((p2[0], p2[2]))
                i += n_pts + 1

        vertices_array = np.array(list(unique_vertices)) if unique_vertices else np.array([])
        return segments, vertices_array

    def precache_floor_slices(self):
        """Pre-compute and cache slices at all detected floor levels for instant access."""
        if not self.floor_levels:
            return

        print(f"Pre-caching slices at {len(self.floor_levels)} floor levels...")
        for floor_z in self.floor_levels:
            # This will populate the cache
            self.slice_at_z(floor_z)
        print(f"Pre-cached {len(self.slice_cache)} floor slices")


class ObjAoiEditor:
    """Interactive room boundary drawing tool with hierarchical apartment/room support.

    Version 2 Features:
    - Draw apartment boundaries (parent rooms)
    - Draw sub-room boundaries within apartments (children)
    - Auto-prefix child room names with parent apartment name
    - Warning when sub-room extends outside parent boundary

    Displays a PyVista-sliced cross-section in a matplotlib figure and
    provides a PolygonSelector for drawing room boundary polygons. Exports
    to .aoi files and room boundaries CSV for the ViewGenerator pipeline.

    Args:
        obj_path: OBJ file path to load.
        mtl_path: Optional MTL file (not used for slicing, reserved for future).
        session_path: Path for saving/loading editor sessions (JSON).
    """

    def __init__(
        self,
        obj_path: Union[Path, str],
        mtl_path: Optional[Path] = None,
        session_path: Optional[Path] = None,
        initial_csv_path: Optional[Union[Path, str]] = None,
        simplify_ratio: Optional[float] = None,
        detect_floors: bool = True,
        max_vertex_display: int = 5000,
    ):
        """Initialize the boundary editor.

        Args:
            obj_path: OBJ file path to load
            mtl_path: Optional MTL file path (not currently used)
            session_path: Path for saving/loading editor sessions
            initial_csv_path: Optional CSV file with initial room boundaries (used if no session exists)
            simplify_ratio: Optional mesh decimation ratio (0.0-1.0) for large meshes
            detect_floors: Whether to auto-detect floor levels (disable for very large meshes)
            max_vertex_display: Maximum vertices to display (downsample if exceeded)
        """
        self.obj_path = Path(obj_path)
        self.mtl_path = mtl_path
        self.session_path = session_path or (self.obj_path.parent / f"{self.obj_path.stem}_room_boundaries.json")
        self.initial_csv_path = Path(initial_csv_path) if initial_csv_path else None
        self.csv_path = self.obj_path.parent / f"{self.obj_path.stem}_room_boundaries.csv"
        self.simplify_ratio = simplify_ratio
        self.detect_floors = detect_floors
        self.max_vertex_display = max_vertex_display

        # Room storage
        self.rooms: List[dict] = []
        self.room_patches: List[Polygon] = []
        self.room_labels: List = []
        self.current_polygon_vertices = []
        self.selected_room_idx: Optional[int] = None

        # Zoom state
        self.original_xlim = None
        self.original_ylim = None

        # Mesh slicer (loaded on launch)
        self.slicer: Optional[MeshSlicer] = None
        self.current_z: float = 0.0
        self.current_floor_idx: Optional[int] = None  # Index into floor_levels list

        # Vertex snapping with KD-tree optimization
        self.snap_enabled: bool = True
        self.snap_distance: float = 0.1  # meters
        self.current_vertices: np.ndarray = np.array([])  # (N, 2) array of slice vertices
        self._vertex_kdtree: Optional[cKDTree] = None  # Spatial index for fast snapping

        # Visualization options
        self.show_all_floors: bool = False  # Toggle to show rooms from all floors
        self.view_mode: str = 'plan'  # 'plan', 'elevation_x', or 'elevation_y'
        self.elevation_position: float = 0.0  # Position of elevation slice

        # Vertex editing mode
        self.edit_mode: bool = False  # Toggle for editing existing boundaries
        self.edit_room_idx: Optional[int] = None  # Index of room being edited
        self.edit_vertex_idx: Optional[int] = None  # Index of vertex being dragged
        self.hover_room_idx: Optional[int] = None  # Room under cursor
        self.hover_vertex_idx: Optional[int] = None  # Vertex under cursor
        self.hover_edge_room_idx: Optional[int] = None  # Room containing hovered edge
        self.hover_edge_idx: Optional[int] = None  # Index of first vertex of hovered edge
        self.hover_edge_point: Optional[tuple] = None  # Projected insertion point on edge

        # Parent apartment selection (hierarchical support)
        self.selected_parent: Optional[str] = None  # Currently selected parent apartment name
        self.parent_options: List[str] = []  # List of available parent apartments on current floor

        # Room list scroll state
        self.room_list_scroll_offset: int = 0  # Scroll offset for saved rooms list
        self._room_list_hit_boxes: List[Tuple] = []  # [(y_min, y_max, room_idx), ...] in axes coords

        # Slider debouncing
        self._z_slider_timer: Optional[Any] = None  # matplotlib TimerBase
        self._pending_z_value: Optional[float] = None

        # Cached matplotlib artists for incremental rendering (performance optimization)
        self._mesh_line_collection = None  # Persistent LineCollection for mesh segments
        self._vertex_scatter = None        # Persistent scatter plot for snap vertices
        self._room_patch_cache = {}        # room_idx -> Polygon artist
        self._room_label_cache = {}        # room_idx -> Text artist
        self._edit_vertex_scatter = None   # Batched scatter for edit mode vertices
        self._last_view_mode = None        # Track view mode changes for full redraws
        self._last_hover_check = 0.0       # Throttle hover detection

    def launch(self):
        """Load the mesh and open the interactive editor window."""
        # Check for cached floor levels in session to skip expensive detection on repeat runs
        cached_floor_levels = None
        if self.session_path.exists():
            try:
                with open(self.session_path, 'r') as f:
                    cached_floor_levels = json.load(f).get('floor_levels')
            except Exception:
                pass

        print("Loading OBJ mesh...")
        self.slicer = MeshSlicer(
            self.obj_path,
            simplify_ratio=self.simplify_ratio,
            detect_floors=self.detect_floors and not cached_floor_levels
        )
        if cached_floor_levels:
            self.slicer.floor_levels = cached_floor_levels
            print(f"Floor levels loaded from session cache ({len(cached_floor_levels)} floors, detection skipped)")
        print(f"Mesh loaded: {self.slicer.mesh.n_cells:,} cells, Z range [{self.slicer.z_min:.2f}, {self.slicer.z_max:.2f}]m")

        # Pre-cache floor level slices for instant navigation
        if self.slicer.floor_levels:
            self.slicer.precache_floor_slices()

        # Set initial Z to first detected floor level or middle of mesh
        if self.slicer.floor_levels:
            self.current_z = self.slicer.floor_levels[0]
            self.current_floor_idx = 0
        else:
            self.current_z = (self.slicer.z_min + self.slicer.z_max) / 2
            self.current_floor_idx = None

        # Setup matplotlib figure with soft off-white background
        # Use a moderate default size that fits most screens; window will be maximized after
        self.fig = plt.figure(figsize=(14, 8), facecolor='#F5F5F0')

        # Adjust subplot parameters to ensure content fits within the figure
        self.fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.05)

        # Maximise the window on open so it fills the screen regardless of OS placement
        try:
            import sys
            manager = plt.get_current_fig_manager()
            if sys.platform == "win32":
                manager.window.state('zoomed')       # Windows TkAgg
            else:
                manager.window.attributes('-zoomed', True)  # Linux TkAgg
            # Force a resize event after maximization to update figure content
            self.fig.canvas.mpl_connect('resize_event', self._on_resize)
            # Schedule a deferred resize to ensure the window has finished maximizing
            self.fig.canvas.get_tk_widget().after(100, self._force_resize_update)
        except AttributeError:
            try:
                manager = plt.get_current_fig_manager()
                manager.window.showMaximized()  # Qt backends
                self.fig.canvas.mpl_connect('resize_event', self._on_resize)
            except AttributeError:
                pass

        # Main plot area on the right, side panel on the left
        self.ax = self.fig.add_axes([0.35, 0.10, 0.63, 0.85])
        self.ax.set_aspect('equal')
        self.ax.set_facecolor('#FAFAF8')  # Slightly lighter for the plot area

        # Setup side panel, slider, and view mode buttons
        self._setup_side_panel()
        self._setup_z_slider()
        self._setup_floor_level_indicators()
        self._setup_view_mode_buttons()

        # Initial section render
        self._render_section()

        # Store original limits
        self.original_xlim = self.ax.get_xlim()
        self.original_ylim = self.ax.get_ylim()

        # Polygon selector for drawing room boundaries
        self._create_polygon_selector()

        # Event handlers (snap handler must come first to intercept before selector)
        self.fig.canvas.mpl_connect('button_press_event', self._on_click_with_snap)
        self.fig.canvas.mpl_connect('button_press_event', self._on_list_click)
        self.fig.canvas.mpl_connect('button_release_event', self._on_button_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_mouse_motion)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key_press)
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)

        # Load existing session if available
        self._load_session()
        self._update_room_list()
        self._update_floor_level_list()

        print("\n=== Boundary Editor ===")
        print("Draw room boundary polygons on the floor plan section.")
        if self.slicer.floor_levels:
            print(f"Detected {len(self.slicer.floor_levels)} floor levels - use up/down arrow keys to navigate")
        print("Adjust the Z slider to change the section height.")
        print("Vertex snapping is ENABLED - clicks snap to mesh vertices.")
        print("Scroll: zoom | Right-click: select room | s: save | d: delete | q: quit")
        print("Up/Down: next/prev floor | r: reset zoom | S: save session")
        print("========================\n")
        plt.show()

    # -------------------------------------------------------------------------
    # UI setup
    # -------------------------------------------------------------------------

    def _setup_z_slider(self):
        """Create the Z-height slider vertically on the left side of the main axes."""
        # Position slider vertically between the panel (ends at 0.30) and figure (starts at 0.35)
        # Placing at 0.325 puts it halfway in the gap
        ax_slider = self.fig.add_axes([0.325, 0.10, 0.015, 0.85])
        self.z_slider = Slider(
            ax_slider,
            '',  # No label - we'll add it separately
            self.slicer.z_min,
            self.slicer.z_max,
            valinit=self.current_z,
            valstep=0.2,  # Coarser step for better performance (was 0.1)
            orientation='vertical',
            color='#A8C8A8',  # Soft sage green
        )
        self.z_slider.valtext.set_visible(False)  # Hide built-in value display
        self.z_slider.on_changed(self._on_z_changed_debounced)

        # Add label above the slider
        self.fig.text(0.332, 0.96, 'Z (m)', ha='center', va='bottom', fontsize=9, fontweight='bold', color='#404040')

    def _setup_floor_level_indicators(self):
        """Add visual indicators for detected floor levels on the Z-slider."""
        if not self.slicer.floor_levels:
            return

        # Add horizontal lines at each floor level on the vertical slider axis
        ax_slider = self.z_slider.ax
        for floor_z in self.slicer.floor_levels:
            # Normalize position within slider range
            normalized_pos = (floor_z - self.slicer.z_min) / (self.slicer.z_max - self.slicer.z_min)
            ax_slider.axhline(normalized_pos, color='green', linewidth=2, alpha=0.6, zorder=10)

    def _setup_view_mode_buttons(self):
        """Create view mode buttons (Plan, Elev X, Elev Y) vertically stacked on the top right."""
        # Position buttons outside the top right of the main plot area
        btn_right = 0.99   # Right edge of figure
        btn_width = 0.045
        btn_height = 0.04
        btn_spacing = 0.005

        # Soft colors for view mode buttons
        view_btn_color = "#E8E8E0"
        view_btn_hover = '#D8D8D0'
        view_btn_active = '#C8E0C8'  # Soft green when active

        # Plan button (top)
        ax_view_plan = self.fig.add_axes([btn_right - btn_width, 0.91, btn_width, btn_height])
        self.btn_view_plan = Button(ax_view_plan, 'Plan', color=view_btn_active, hovercolor=view_btn_hover)
        self.btn_view_plan.on_clicked(lambda e: self._set_view_mode('plan'))

        # Elev X button (middle)
        ax_view_elev_x = self.fig.add_axes([btn_right - btn_width, 0.91 - btn_height - btn_spacing, btn_width, btn_height])
        self.btn_view_elev_x = Button(ax_view_elev_x, 'Elev X', color=view_btn_color, hovercolor=view_btn_hover)
        self.btn_view_elev_x.on_clicked(lambda e: self._set_view_mode('elevation_x'))

        # Elev Y button (bottom)
        ax_view_elev_y = self.fig.add_axes([btn_right - btn_width, 0.91 - 2 * (btn_height + btn_spacing), btn_width, btn_height])
        self.btn_view_elev_y = Button(ax_view_elev_y, 'Elev Y', color=view_btn_color, hovercolor=view_btn_hover)
        self.btn_view_elev_y.on_clicked(lambda e: self._set_view_mode('elevation_y'))

        # Store colors for updating active state
        self._view_btn_color = view_btn_color
        self._view_btn_active = view_btn_active

    def _setup_side_panel(self):
        """Create the side panel with inputs, buttons, and room list."""
        pl = 0.02    # panel left
        pw = 0.28    # total panel width
        pw_l = 0.13  # left column width (floor levels / inputs)
        pw_r = 0.14  # right column width (button stack)
        pr = pl + pw_l + 0.01  # right column start x

        # Soft color palette for UI elements
        self._btn_color = '#E8E8E0'       # Soft warm gray for buttons
        self._btn_hover = '#D8D8D0'       # Slightly darker on hover
        self._slider_color = '#A8C8A8'    # Soft sage green for sliders

        # Instructions (full width)
        ax_instr = self.fig.add_axes([pl, 0.83, pw, 0.15])
        ax_instr.axis('off')
        ax_instr.patch.set_visible(False)
        ax_instr.text(0, 0.93, "BOUNDARY EDITOR", fontsize=11, fontweight='bold', color='#404040',
                      transform=ax_instr.transAxes)
        controls = [
            ("\u2191/\u2193",     "Navigate floor levels"),
            ("Left-click",        "Place vertex / drag (edit mode)"),
            ("Right-click",       "Select existing room"),
            ("Scroll",            "Zoom centred on cursor"),
            ("s",                 "Save room / confirm edit"),
            ("d",                 "Delete selected room"),
            ("e",                 "Toggle Edit Mode"),
            ("v",                 "Cycle views: Plan \u2192 Elev X \u2192 Elev Y"),
            ("a",                 "Toggle all-floors display"),
            ("r",                 "Reset zoom"),
            ("q",                 "Quit"),
        ]
        for i, (key, desc) in enumerate(controls):
            y = 0.85 - i * 0.08
            ax_instr.text(0.00, y, key,  fontsize=7, color='#404040', fontweight='bold',
                          transform=ax_instr.transAxes)
            ax_instr.text(0.32, y, desc, fontsize=7, color='#505050',
                          transform=ax_instr.transAxes)

        # ── LEFT COLUMN: floor levels + input fields ──────────────────────────

        # Floor level navigation section (left column)
        ax_floor_hdr = self.fig.add_axes([pl, 0.75, pw_l, 0.03])
        ax_floor_hdr.axis('off')
        ax_floor_hdr.text(0, 0.5, "FLOOR LEVELS:", fontsize=10, fontweight='bold', color='#404040')

        # Floor navigation arrow buttons
        btn_arrow_width = 0.025
        btn_arrow_height = 0.05
        floor_list_left = pl + btn_arrow_width + 0.005

        ax_next_floor = self.fig.add_axes([pl, 0.68, btn_arrow_width, btn_arrow_height])
        self.btn_next_floor = Button(ax_next_floor, '\u25b2', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_next_floor.on_clicked(self._on_next_floor_click)

        ax_prev_floor = self.fig.add_axes([pl, 0.62, btn_arrow_width, btn_arrow_height])
        self.btn_prev_floor = Button(ax_prev_floor, '\u25bc', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_prev_floor.on_clicked(self._on_prev_floor_click)

        self.ax_floor_list = self.fig.add_axes([floor_list_left, 0.62, pw_l - btn_arrow_width - 0.005, 0.12])
        self.ax_floor_list.axis('off')

        # Parent apartment selector (half width - left column only)
        ax_parent_lbl = self.fig.add_axes([pl, 0.565, pw_l, 0.03])
        ax_parent_lbl.axis('off')
        ax_parent_lbl.text(0, 0.5, "Parent Apartment:", fontsize=10, fontweight='bold')

        ax_parent_btn = self.fig.add_axes([pl, 0.525, pw_l, 0.035])
        self.btn_parent = Button(ax_parent_btn, '(None)', color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_parent.label.set_fontsize(8)
        self.btn_parent.on_clicked(self._on_parent_cycle)

        # Name preview label
        ax_name_preview = self.fig.add_axes([pl, 0.500, pw_l, 0.02])
        ax_name_preview.axis('off')
        self.name_preview_text = ax_name_preview.text(0, 0.5, "", fontsize=8, color='#666666', style='italic')

        # Room name input (half width - left column only)
        ax_name_lbl = self.fig.add_axes([pl, 0.465, pw_l, 0.03])
        ax_name_lbl.axis('off')
        self.name_label_text = ax_name_lbl.text(0, 0.5, "Apartment Name:", fontsize=9, fontweight='bold')
        ax_name = self.fig.add_axes([pl, 0.420, pw_l, 0.040])
        self.name_textbox = TextBox(ax_name, '', initial='')
        self.name_textbox.on_text_change(self._on_name_changed)

        # Status display (left column)
        ax_status = self.fig.add_axes([pl, 0.375, pw_l, 0.03])
        ax_status.axis('off')
        self.status_text = ax_status.text(
            0, 0.5, "Status: Ready to draw", fontsize=8, color='blue', style='italic')

        # ── RIGHT COLUMN: SAVED ROOMS list ──────────────────────────────────────

        list_hdr_y = 0.750
        ax_list_hdr = self.fig.add_axes([pr, list_hdr_y, pw_r, 0.025])
        ax_list_hdr.axis('off')
        ax_list_hdr.text(0, 0.5, "SAVED ROOMS:",
                         fontsize=9, fontweight='bold')

        # Scrollable room list — in right column
        list_bottom = 0.375  # aligns with Status text level
        list_top = list_hdr_y - 0.005
        self.ax_list = self.fig.add_axes([pr, list_bottom, pw_r, list_top - list_bottom])
        self.ax_list.set_facecolor('#FAFAF8')
        self.ax_list.tick_params(left=False, bottom=False,
                                 labelleft=False, labelbottom=False)
        for spine in self.ax_list.spines.values():
            spine.set_edgecolor('#CCCCCC')
            spine.set_linewidth(0.5)

        # ── BOTTOM STRIP: Snap | Edit Mode | Reset Zoom (below figure only) ──

        fig_left  = 0.35   # matches main axes left
        fig_width = 0.63   # matches main axes width
        gap = 0.005
        bottom_btn_h = 0.030
        bottom_btn_w = (fig_width - 2 * gap) / 3
        bottom_btn_y = 0.015

        ax_snap_btn = self.fig.add_axes([fig_left, bottom_btn_y, bottom_btn_w, bottom_btn_h])
        self.btn_snap = Button(ax_snap_btn,
                               'Snap: ON' if self.snap_enabled else 'Snap: OFF',
                               color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_snap.label.set_fontsize(8)
        self.btn_snap.on_clicked(self._on_snap_toggle)

        ax_edit_btn = self.fig.add_axes([fig_left + bottom_btn_w + gap, bottom_btn_y,
                                         bottom_btn_w, bottom_btn_h])
        self.btn_edit_mode = Button(ax_edit_btn, 'Edit Mode: OFF (Press E)',
                                    color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_edit_mode.label.set_fontsize(8)
        self.btn_edit_mode.on_clicked(self._on_edit_mode_toggle)

        ax_reset_btn = self.fig.add_axes([fig_left + 2 * (bottom_btn_w + gap), bottom_btn_y,
                                          bottom_btn_w, bottom_btn_h])
        self.btn_reset_zoom = Button(ax_reset_btn, 'Reset Zoom',
                                     color=self._btn_color, hovercolor=self._btn_hover)
        self.btn_reset_zoom.label.set_fontsize(8)
        self.btn_reset_zoom.on_clicked(self._on_reset_zoom_click)

        # ── FULL-WIDTH SECTION: snap slider ───────────────────────────────────

        snap_lbl_y = 0.33
        ax_snap_dist_lbl = self.fig.add_axes([pl, snap_lbl_y, pw, 0.02])
        ax_snap_dist_lbl.axis('off')
        ax_snap_dist_lbl.text(0, 0.5, f"Snap Distance: {self.snap_distance:.1f}m", fontsize=9, color='#505050')
        self.snap_dist_label = ax_snap_dist_lbl

        ax_snap_slider = self.fig.add_axes([pl, snap_lbl_y - 0.025, pw, 0.015])
        self.snap_slider = Slider(
            ax_snap_slider, '', 0.1, 2.0,
            valinit=self.snap_distance, valstep=0.1, color=self._slider_color,
        )
        self.snap_slider.valtext.set_visible(False)  # Hide built-in value display (we have our own label)
        self.snap_slider.on_changed(self._on_snap_distance_changed)

        # ── ACTION BUTTONS (between snap slider and legend) ─────────────────────
        btn_h = 0.028   # button height
        btn_gap = 0.005  # gap between buttons
        btn_w = (pw - 2 * btn_gap) / 3  # three buttons side by side
        btn_y = snap_lbl_y - 0.070  # below snap slider

        btn_labels = [
            ('btn_save',   'Save Room',       self._on_save_click),
            ('btn_clear',  'Clear Current',   self._on_clear_click),
            ('btn_delete', 'Delete Selected', self._on_delete_click),
        ]

        for i, (attr_name, label, callback) in enumerate(btn_labels):
            btn_x = pl + i * (btn_w + btn_gap)
            ax_btn = self.fig.add_axes([btn_x, btn_y, btn_w, btn_h])
            btn = Button(ax_btn, label, color=self._btn_color, hovercolor=self._btn_hover)
            btn.label.set_fontsize(8)
            btn.on_clicked(callback)
            setattr(self, attr_name, btn)

        # ── LEGEND (in left panel, below buttons) ───────────────────────────────
        legend_height = 0.085
        legend_bottom = btn_y - btn_h - 0.015 - legend_height  # below action buttons
        ax_legend = self.fig.add_axes([pl, legend_bottom, pw, legend_height])
        ax_legend.axis('off')
        ax_legend.set_facecolor('#F0F0EC')
        ax_legend.text(0.01, 0.92, "LEGEND", fontsize=7, fontweight='bold', color='#404040',
                       transform=ax_legend.transAxes)

        legend_items = [
            ('green',    0.4,  'Apartment (current floor)'),
            ('#2196F3',  0.4,  'Sub-room (current floor)'),
            ('yellow',   0.35, 'Selected'),
            ('cyan',     0.35, 'Being edited'),
            ('magenta',  0.35, 'Hover vertex (edit mode)'),
            ('gray',     0.15, 'Other floor'),
        ]

        # Two-column layout for legend items
        for i, (color, alpha, label) in enumerate(legend_items):
            col = i // 3  # 0 for first 3, 1 for last 3
            row = i % 3
            x_base = 0.01 + col * 0.50
            y0 = 0.72 - row * 0.26
            rect = FancyBboxPatch((x_base, y0 - 0.10), 0.04, 0.18,
                                  boxstyle='round,pad=0.01',
                                  facecolor=color, edgecolor=color,
                                  alpha=alpha, transform=ax_legend.transAxes,
                                  clip_on=False)
            ax_legend.add_patch(rect)
            ax_legend.text(x_base + 0.06, y0, label, fontsize=6, color='#404040',
                           va='center', transform=ax_legend.transAxes)

    # -------------------------------------------------------------------------
    # Parent/Child relationship helpers (hierarchical support)
    # -------------------------------------------------------------------------

    def _get_apartments_on_floor(self, z_height: float, tolerance: float = 0.5) -> List[str]:
        """Return names of rooms without parents (apartments) on the given floor.

        Args:
            z_height: Floor Z-height in meters
            tolerance: Z-height matching tolerance in meters

        Returns:
            List of apartment names on this floor
        """
        apartments = []
        for room in self.rooms:
            # Room is an apartment if it has no parent
            if room.get('parent') is None:
                if abs(room['z_height'] - z_height) < tolerance:
                    apartments.append(room['name'])
        return apartments

    def _get_children(self, parent_name: str) -> List[dict]:
        """Return all rooms that have the given parent.

        Args:
            parent_name: Name of the parent apartment

        Returns:
            List of child room dictionaries
        """
        return [room for room in self.rooms if room.get('parent') == parent_name]

    def _get_parent_room(self, parent_name: str) -> Optional[dict]:
        """Get the parent room dictionary by name.

        Args:
            parent_name: Name of the parent apartment

        Returns:
            Parent room dictionary or None if not found
        """
        for room in self.rooms:
            if room['name'] == parent_name:
                return room
        return None

    def _make_unique_name(self, base_name: str, exclude_idx: Optional[int] = None) -> str:
        """Ensure room name is unique by appending numeric suffix if needed.

        Args:
            base_name: The desired room name
            exclude_idx: Room index to exclude from check (for updates)

        Returns:
            Unique name, possibly with numeric suffix (e.g., BED -> BED1 -> BED2)
        """
        existing_names = set()
        for i, room in enumerate(self.rooms):
            if exclude_idx is not None and i == exclude_idx:
                continue
            existing_names.add(room['name'])

        if base_name not in existing_names:
            return base_name

        # Strip any existing numeric suffix to get the root name
        import re
        match = re.match(r'^(.*?)(\d+)$', base_name)
        if match:
            root = match.group(1)
        else:
            root = base_name

        # Find the next available number
        counter = 1
        while f"{root}{counter}" in existing_names:
            counter += 1

        return f"{root}{counter}"

    def _check_boundary_containment(self, child_verts: List[List[float]], parent_verts: List[List[float]]) -> bool:
        """Check if child polygon is fully within parent polygon.

        Args:
            child_verts: List of [x, y] coordinates for child room
            parent_verts: List of [x, y] coordinates for parent apartment

        Returns:
            True if all child vertices are inside parent polygon
        """
        if not parent_verts or len(parent_verts) < 3:
            return True  # Can't check, assume OK

        if not child_verts or len(child_verts) < 3:
            return True  # Can't check, assume OK

        # Ensure parent polygon is closed for proper containment checking
        parent_array = np.array(parent_verts)
        if not np.allclose(parent_array[0], parent_array[-1]):
            # Close the polygon by appending the first vertex
            parent_array = np.vstack([parent_array, parent_array[0]])

        parent_path = MplPath(parent_array)

        for vertex in child_verts:
            if not parent_path.contains_point(vertex):
                return False

        return True

    def _update_parent_options(self):
        """Update the list of available parent apartments for current floor."""
        self.parent_options = self._get_apartments_on_floor(self.current_z)

    def _on_parent_cycle(self, event):
        """Cycle through parent apartment options when button is clicked."""
        self._update_parent_options()

        if not self.parent_options:
            # No apartments available - keep as None
            self.selected_parent = None
            self.btn_parent.label.set_text('(None - New Apartment)')
            self.name_label_text.set_text("Apartment Name (Space ID):")
        else:
            # Build options list: None + all apartments
            options = [None] + self.parent_options

            # Find current index and move to next
            try:
                current_idx = options.index(self.selected_parent)
                next_idx = (current_idx + 1) % len(options)
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
        """Update the name preview text showing what name will be saved."""
        name = self.name_textbox.text.strip().upper()
        if not name:
            self.name_preview_text.set_text("")
        elif self.selected_parent:
            full_name = f"{self.selected_parent}_{name}"
            self.name_preview_text.set_text(f"Will save as: {full_name}")
        else:
            self.name_preview_text.set_text(f"Will save as: {name}")
        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Section rendering
    # -------------------------------------------------------------------------

    def _render_section(self, reset_view: bool = False, force_full: bool = False):
        """Render the mesh cross-section (plan or elevation view).

        Uses incremental rendering for performance - only does full redraws when
        view mode changes, Z level changes, or force_full=True.

        Args:
            reset_view: If True, reset zoom/pan to fit content (used when switching view modes)
            force_full: If True, force a complete redraw (used after room modifications)
        """
        # Preserve current zoom state before clearing (unless resetting)
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()

        # Determine if we need a full redraw
        view_changed = self._last_view_mode != self.view_mode
        need_full_redraw = force_full or view_changed or reset_view

        if need_full_redraw:
            self._last_view_mode = self.view_mode
            self._do_full_render(xlim, ylim, reset_view)
        else:
            # Incremental update - just update room visuals without clearing
            self._update_room_visuals()
            self.fig.canvas.draw_idle()

    def _do_full_render(self, xlim, ylim, reset_view: bool):
        """Perform a complete redraw of the scene (expensive, avoid when possible)."""
        self.ax.clear()

        # Clear cached artists since we're doing a full redraw
        self._mesh_line_collection = None
        self._vertex_scatter = None
        self._room_patch_cache.clear()
        self._room_label_cache.clear()
        self._edit_vertex_scatter = None

        # Get slice based on view mode
        if self.view_mode == 'plan':
            segments, vertices = self.slicer.slice_at_z(self.current_z)
        elif self.view_mode == 'elevation_x':
            segments, vertices = self.slicer.slice_elevation_x(self.elevation_position)
        elif self.view_mode == 'elevation_y':
            segments, vertices = self.slicer.slice_elevation_y(self.elevation_position)
        else:
            segments, vertices = [], np.array([])

        self.current_vertices = vertices

        # Rebuild KD-tree for snapping whenever vertices change
        self._vertex_kdtree = None  # Will be lazily rebuilt on next snap

        if segments:
            line_data = [[(s[0], s[1]), (s[2], s[3])] for s in segments]
            self._mesh_line_collection = LineCollection(line_data, colors='black', linewidths=0.5)
            self.ax.add_collection(self._mesh_line_collection)

        # Draw vertices as points if snap is enabled (with downsampling for performance)
        if self.snap_enabled and len(vertices) > 0:
            if len(vertices) <= self.max_vertex_display:
                # Show all vertices
                self._vertex_scatter, = self.ax.plot(vertices[:, 0], vertices[:, 1], 'o',
                            markersize=1.5, color='blue', alpha=0.4, zorder=1)
            else:
                # Downsample vertices for display only (snapping still uses all vertices)
                step = len(vertices) // self.max_vertex_display
                self._vertex_scatter, = self.ax.plot(vertices[::step, 0], vertices[::step, 1], 'o',
                            markersize=1.5, color='blue', alpha=0.3, zorder=1)
                # Add small notice in corner
                self.ax.text(0.02, 0.02, f'Showing {len(vertices[::step]):,}/{len(vertices):,} vertices',
                           transform=self.ax.transAxes, fontsize=7, color='gray',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))

        # Redraw saved room polygons (only in plan view)
        self.room_patches.clear()
        self.room_labels.clear()

        if self.view_mode == 'plan':
            self._draw_all_room_polygons()
        else:
            # In elevation view, show room boundaries as vertical lines
            self._draw_rooms_elevation()

        self.ax.set_aspect('equal')

        # Restore zoom state (or autoscale on first render or view mode change)
        if reset_view:
            # Reset view when switching modes - autoscale to fit new content
            self.ax.autoscale()
        elif hasattr(self, 'original_xlim') and xlim != (0, 1):  # (0,1) is default for cleared axes
            # Restore previous zoom
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)
        else:
            # First render - autoscale to fit content
            self.ax.autoscale()

        # Set axis labels based on view mode
        if self.view_mode == 'plan':
            self.ax.set_xlabel('X (m)')
            self.ax.set_ylabel('Y (m)')
            title = f'Floor Plan Section at Z = {self.current_z:.1f}m'
            if self.current_floor_idx is not None and self.slicer.floor_levels:
                title = f'Floor Level {self.current_floor_idx} (Z = {self.current_z:.1f}m)'
        elif self.view_mode == 'elevation_x':
            self.ax.set_xlabel('Y (m)')
            self.ax.set_ylabel('Z (m)')
            title = f'Elevation View (X = {self.elevation_position:.1f}m) - VIEW ONLY'
        elif self.view_mode == 'elevation_y':
            self.ax.set_xlabel('X (m)')
            self.ax.set_ylabel('Z (m)')
            title = f'Elevation View (Y = {self.elevation_position:.1f}m) - VIEW ONLY'
        else:
            title = 'Unknown View'

        self.ax.set_title(title, fontsize=12, fontweight='bold')
        self.ax.grid(True, alpha=0.3)
        self.fig.canvas.draw_idle()

    def _draw_all_room_polygons(self):
        """Draw all room polygons for the current view."""
        for i, room in enumerate(self.rooms):
            is_current_floor = abs(room['z_height'] - self.current_z) < 0.5

            if self.show_all_floors:
                self._draw_room_polygon(room, i, is_current_floor=is_current_floor)
            elif is_current_floor:
                self._draw_room_polygon(room, i, is_current_floor=True)

    def _update_room_visuals(self):
        """Update room polygon colors/styles without full redraw (for hover/selection changes)."""
        if self.view_mode != 'plan':
            return

        # Update existing patches in place where possible
        for i, room in enumerate(self.rooms):
            is_current_floor = abs(room['z_height'] - self.current_z) < 0.5
            if not is_current_floor and not self.show_all_floors:
                continue

            patch = self._room_patch_cache.get(i)
            if patch is None:
                continue

            # Determine current visual state
            is_selected = (i == self.selected_room_idx)
            is_hover = (i == self.hover_room_idx)
            is_editing = (i == self.edit_room_idx and self.edit_mode)
            is_subroom = room.get('parent') is not None

            # Update colors based on state
            if is_editing:
                patch.set_edgecolor('cyan')
                patch.set_facecolor('cyan')
                patch.set_alpha(0.3)
                patch.set_linewidth(3)
            elif is_selected:
                patch.set_edgecolor('yellow')
                patch.set_facecolor('yellow')
                patch.set_alpha(0.35)
                patch.set_linewidth(4)
            elif is_hover and self.edit_mode:
                patch.set_edgecolor('magenta')
                patch.set_facecolor('magenta')
                patch.set_alpha(0.2)
                patch.set_linewidth(2)
            elif is_current_floor:
                if is_subroom:
                    patch.set_edgecolor('#2196F3')
                    patch.set_facecolor('#2196F3')
                    patch.set_alpha(0.3)
                    patch.set_linewidth(2)
                else:
                    patch.set_edgecolor('green')
                    patch.set_facecolor('green')
                    patch.set_alpha(0.25)
                    patch.set_linewidth(2)
            else:
                patch.set_edgecolor('gray')
                patch.set_facecolor('gray')
                patch.set_alpha(0.15)
                patch.set_linewidth(1)

    def _draw_room_polygon(self, room: dict, idx: int, is_current_floor: bool = True):
        """Draw a single saved room polygon on the axes.

        Args:
            room: Room dictionary with vertices, name, etc.
            idx: Room index in self.rooms list
            is_current_floor: Whether room is at the current Z height
        """
        verts = room['vertices']
        if len(verts) < 3:
            return

        is_selected = (idx == self.selected_room_idx)
        is_hover = (idx == self.hover_room_idx)
        is_editing = (idx == self.edit_room_idx and self.edit_mode)
        is_subroom = room.get('parent') is not None  # Has a parent = is a sub-room

        # Color scheme based on state
        if is_editing:
            edge_color = 'cyan'
            face_color = 'cyan'
            alpha = 0.3
            lw = 3
            label_bg = 'cyan'
        elif is_selected:
            edge_color = 'yellow'
            face_color = 'yellow'
            alpha = 0.35
            lw = 4
            label_bg = 'orange'
        elif is_hover and self.edit_mode:
            edge_color = 'magenta'
            face_color = 'magenta'
            alpha = 0.2
            lw = 2
            label_bg = 'magenta'
        elif is_current_floor:
            if is_subroom:
                # Sub-rooms: use blue/teal color to distinguish from apartments
                edge_color = '#2196F3'  # Material blue
                face_color = '#2196F3'
                alpha = 0.3
                lw = 2
                label_bg = '#1976D2'  # Darker blue for label
            else:
                # Apartments: use green
                edge_color = 'green'
                face_color = 'green'
                alpha = 0.25
                lw = 2
                label_bg = 'green'
        else:
            # Other floors: use gray with lower opacity
            edge_color = 'gray'
            face_color = 'gray'
            alpha = 0.15
            lw = 1
            label_bg = 'gray'

        poly = Polygon(
            verts, closed=True,
            edgecolor=edge_color, facecolor=face_color, alpha=alpha, linewidth=lw,
        )
        self.ax.add_patch(poly)
        self.room_patches.append(poly)
        self._room_patch_cache[idx] = poly  # Cache for incremental updates

        # Draw vertices as editable points in edit mode (ALL rooms, not just one being edited)
        # Use batched scatter plot for better performance
        if self.edit_mode and is_current_floor:
            verts_array = np.array(verts)
            xs, ys, colors, sizes = [], [], [], []

            for v_idx, (vx, vy) in enumerate(verts_array):
                # Highlight vertex under cursor
                is_hovered = (idx == self.hover_room_idx and v_idx == self.hover_vertex_idx)
                is_dragging = (idx == self.edit_room_idx and v_idx == self.edit_vertex_idx)

                if is_dragging:
                    marker_color = 'yellow'
                    marker_size = 9
                elif is_hovered:
                    marker_color = 'red'
                    marker_size = 8
                else:
                    marker_color = 'cyan'
                    marker_size = 5

                xs.append(vx)
                ys.append(vy)
                colors.append(marker_color)
                sizes.append(marker_size ** 2)  # scatter uses area, not diameter

            # Single batched scatter call instead of individual plots
            if xs:
                self.ax.scatter(xs, ys, c=colors, s=sizes,
                               edgecolors='black', linewidths=1.0,
                               zorder=100, picker=5)

            # Highlight hovered edge and show insertion preview
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

        # Add label with floor level info if showing all floors
        centroid = np.array(verts).mean(axis=0)
        label = room.get('name', '')
        if not is_current_floor:
            # Add floor level indicator for rooms on other floors
            label += f"\n(Z={room['z_height']:.1f}m)"

        label_text = self.ax.text(
            centroid[0], centroid[1], label,
            color='white', fontsize=8 if is_current_floor else 7,
            ha='center', va='center',
            bbox=dict(boxstyle='round', facecolor=label_bg, alpha=0.7 if is_current_floor else 0.5),
        )
        self.room_labels.append(label_text)
        self._room_label_cache[idx] = label_text  # Cache for incremental updates

    def _draw_rooms_elevation(self):
        """Draw room boundaries in elevation view as colored rectangles at their Z-height."""
        for i, room in enumerate(self.rooms):
            z_height = room['z_height']
            verts = room['vertices']

            if len(verts) < 3:
                continue

            # Get room extents in plan view
            verts_array = np.array(verts)
            x_min, y_min = verts_array.min(axis=0)
            x_max, y_max = verts_array.max(axis=0)

            # Assume typical room height (3m) for visualization
            room_height = 3.0
            z_top = z_height + room_height

            # Draw rectangle based on view orientation
            if self.view_mode == 'elevation_x':
                # YZ plane: show Y extent at room Z height
                rect_verts = [
                    (y_min, z_height),
                    (y_max, z_height),
                    (y_max, z_top),
                    (y_min, z_top)
                ]
            elif self.view_mode == 'elevation_y':
                # XZ plane: show X extent at room Z height
                rect_verts = [
                    (x_min, z_height),
                    (x_max, z_height),
                    (x_max, z_top),
                    (x_min, z_top)
                ]
            else:
                continue

            # Color based on selection
            is_selected = (i == self.selected_room_idx)
            edge_color = 'yellow' if is_selected else 'green'
            face_color = 'yellow' if is_selected else 'green'
            alpha = 0.3 if is_selected else 0.2
            lw = 3 if is_selected else 1.5

            poly = Polygon(
                rect_verts, closed=True,
                edgecolor=edge_color, facecolor=face_color, alpha=alpha, linewidth=lw,
            )
            self.ax.add_patch(poly)
            self.room_patches.append(poly)

            # Add label at center
            center_h = (rect_verts[0][0] + rect_verts[1][0]) / 2
            center_z = z_height + room_height / 2
            label_text = self.ax.text(
                center_h, center_z, room.get('name', ''),
                color='white', fontsize=7, ha='center', va='center',
                bbox=dict(boxstyle='round', facecolor='green', alpha=0.6),
            )
            self.room_labels.append(label_text)

    # -------------------------------------------------------------------------
    # Polygon selector with snapping
    # -------------------------------------------------------------------------

    def _create_polygon_selector(self):
        """Create or recreate the polygon selector."""
        self.selector = PolygonSelector(
            self.ax,
            self._on_polygon_select,
            useblit=True,
            props=dict(color='cyan', linestyle='-', linewidth=2, alpha=0.5),
            # Handle markers at snapped vertices - use lime/green to match snap indicator
            handle_props=dict(markersize=8, markerfacecolor='lime', markeredgecolor='darkgreen', markeredgewidth=1.5),
        )

    # -------------------------------------------------------------------------
    # Vertex snapping helper
    # -------------------------------------------------------------------------

    def _point_to_segment_dist(self, px, py, ax, ay, bx, by):
        """Return (distance, proj_x, proj_y) from point P to segment A→B."""
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx*dx + dy*dy
        if seg_len_sq == 0:
            return np.hypot(px - ax, py - ay), ax, ay
        t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / seg_len_sq))
        proj_x, proj_y = ax + t*dx, ay + t*dy
        return np.hypot(px - proj_x, py - proj_y), proj_x, proj_y

    def _snap_to_vertex(self, x: float, y: float) -> tuple:
        """Snap a point to the nearest vertex if within snap distance.

        Uses KD-tree spatial indexing for O(log n) performance instead of O(n).

        Args:
            x, y: Input coordinates

        Returns:
            Tuple of (snapped_x, snapped_y)
        """
        if not self.snap_enabled or len(self.current_vertices) == 0:
            return x, y

        # Build KD-tree lazily on first use
        if self._vertex_kdtree is None:
            self._vertex_kdtree = cKDTree(self.current_vertices)

        # Query nearest vertex using KD-tree (much faster than linear search)
        point = np.array([x, y])
        min_dist, min_idx = self._vertex_kdtree.query(point)

        # Snap if within threshold
        if min_dist <= self.snap_distance:
            snapped = tuple(self.current_vertices[min_idx])
            # Briefly highlight the snapped vertex
            self._highlight_snap_point(snapped[0], snapped[1])
            return snapped

        return x, y

    def _highlight_snap_point(self, x: float, y: float):
        """Briefly highlight a vertex that was snapped to.

        Shows only the snapped location with a prominent marker that fades quickly.
        """
        if not hasattr(self, 'ax') or self.ax is None:
            return

        # Remove previous snap highlight
        if hasattr(self, '_snap_highlight') and self._snap_highlight:
            try:
                self._snap_highlight.remove()
            except (ValueError, AttributeError):
                pass

        # Draw prominent snap indicator at snapped location
        # Using larger marker with green color to clearly show the snap happened
        self._snap_highlight = self.ax.plot([x], [y], 'o',
                                           markersize=10,
                                           color='lime',
                                           markeredgecolor='darkgreen',
                                           markeredgewidth=2,
                                           alpha=0.8,
                                           zorder=100)[0]  # Higher z-order to be on top
        self.fig.canvas.draw_idle()

        # Schedule removal of highlight after brief delay (so user sees the snap)
        if hasattr(self, '_snap_highlight_timer') and self._snap_highlight_timer:
            self._snap_highlight_timer.stop()

        def _clear_highlight():
            if hasattr(self, '_snap_highlight') and self._snap_highlight:
                try:
                    self._snap_highlight.remove()
                    self.fig.canvas.draw_idle()
                except (ValueError, AttributeError):
                    pass

        self._snap_highlight_timer = self.fig.canvas.new_timer(interval=300)  # 300ms flash
        self._snap_highlight_timer.single_shot = True
        self._snap_highlight_timer.add_callback(_clear_highlight)
        self._snap_highlight_timer.start()

    # -------------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------------

    def _on_z_changed_debounced(self, val):
        """Handle Z-slider changes with debouncing to reduce lag during dragging.

        Only triggers re-slice after user stops dragging for 200ms.
        """
        self._pending_z_value = val
        self.current_z = round(val, 1)

        # Cancel existing timer
        if self._z_slider_timer is not None:
            self._z_slider_timer.stop()

        # Create new timer to execute after 200ms
        self._z_slider_timer = self.fig.canvas.new_timer(interval=200)
        self._z_slider_timer.single_shot = True
        self._z_slider_timer.add_callback(self._execute_z_change)
        self._z_slider_timer.start()

    def _execute_z_change(self):
        """Execute the pending Z-slider change after debounce delay."""
        if self._pending_z_value is None:
            return

        val = self._pending_z_value
        self._pending_z_value = None
        self._on_z_changed(val)

    def _on_z_changed(self, val):
        """Handle Z-slider changes."""
        self.current_z = round(val, 1)

        # Update current floor index if near a detected floor level
        if self.slicer and self.slicer.floor_levels:
            closest_floor_idx = None
            min_dist = float('inf')
            for i, floor_z in enumerate(self.slicer.floor_levels):
                dist = abs(floor_z - self.current_z)
                if dist < min_dist and dist < 0.3:  # Within 30cm threshold
                    min_dist = dist
                    closest_floor_idx = i
            self.current_floor_idx = closest_floor_idx
            self._update_floor_level_list()

        # Preserve zoom state
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        self._render_section(force_full=True)  # Z level changed, need full redraw
        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)
        # Re-create the polygon selector after clearing axes
        self._create_polygon_selector()

    def _on_polygon_select(self, vertices):
        """Callback when a polygon is completed."""
        if len(vertices) < 3:
            return
        self.current_polygon_vertices = list(vertices)
        if self.selected_room_idx is not None:
            self._deselect_room()

        area = 0.5 * abs(
            np.dot([v[0] for v in vertices], np.roll([v[1] for v in vertices], 1))
            - np.dot([v[1] for v in vertices], np.roll([v[0] for v in vertices], 1))
        )
        self._update_status(f"Polygon ready: {len(vertices)} pts, {area:.1f} m2", 'green')

    def _on_scroll(self, event):
        """Handle scroll wheel for zooming (main axes) or list scrolling (room list)."""
        # Scroll the room list when cursor is over it
        if event.inaxes == self.ax_list:
            if event.button == 'down':
                self.room_list_scroll_offset += 1
            else:
                self.room_list_scroll_offset = max(0, self.room_list_scroll_offset - 1)
            # Throttle room list redraws for smoother scrolling
            now = time.monotonic()
            last = getattr(self, '_last_list_scroll_draw', 0.0)
            if now - last >= 0.05:  # ~20fps max for list scrolling
                self._last_list_scroll_draw = now
                self._update_room_list()
            return

        if event.inaxes != self.ax:
            return
        scale = 1.2 if event.button == 'down' else 1 / 1.2
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        xdata, ydata = event.xdata, event.ydata
        new_w = (xlim[1] - xlim[0]) * scale
        new_h = (ylim[1] - ylim[0]) * scale
        relx = (xdata - xlim[0]) / (xlim[1] - xlim[0])
        rely = (ydata - ylim[0]) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xdata - new_w * relx, xdata + new_w * (1 - relx)])
        self.ax.set_ylim([ydata - new_h * rely, ydata + new_h * (1 - rely)])

        # Throttle redraws: at most ~30fps during rapid scrolling.
        # Axis limits are already updated above; we only skip the expensive draw.
        now = time.monotonic()
        last = getattr(self, '_last_scroll_draw', 0.0)
        if now - last >= 0.033:
            self._last_scroll_draw = now
            self.fig.canvas.draw_idle()
        else:
            # Schedule a final draw so the view settles after scrolling stops.
            if hasattr(self, '_scroll_draw_timer') and self._scroll_draw_timer:
                self._scroll_draw_timer.stop()
            self._scroll_draw_timer = self.fig.canvas.new_timer(interval=60)
            self._scroll_draw_timer.single_shot = True
            self._scroll_draw_timer.add_callback(lambda: self.fig.canvas.draw_idle())
            self._scroll_draw_timer.start()

    def _on_resize(self, event):
        """Handle window resize events to ensure proper redraw of figure content."""
        # Skip if not fully initialized yet
        if not getattr(self, '_launch_complete', False):
            return
        # Only redraw if the figure is actually visible and has meaningful dimensions
        if event.width > 0 and event.height > 0:
            # Throttle resize redraws to avoid excessive work during drag-resizing
            now = time.monotonic()
            last = getattr(self, '_last_resize_draw', 0.0)
            if now - last >= 0.1:  # Max 10fps for resize redraws
                self._last_resize_draw = now
                self.fig.canvas.draw_idle()

    def _force_resize_update(self):
        """Force a resize update after window maximization completes.

        This is called after a short delay to ensure the window manager has
        finished the maximization before we try to update the figure.
        """
        try:
            # Mark launch as complete so resize events are handled
            self._launch_complete = True
            # Get the Tk widget and force it to update its geometry
            canvas = self.fig.canvas
            tk_widget = canvas.get_tk_widget()
            # Force Tk to process pending events and update geometry
            tk_widget.update_idletasks()
            # Get actual window dimensions and resize the figure to match
            width = tk_widget.winfo_width()
            height = tk_widget.winfo_height()
            if width > 1 and height > 1:
                # Resize figure to actual widget size
                canvas.resize(width, height)
            # Trigger a full redraw
            canvas.draw_idle()
        except Exception:
            pass  # Ignore errors if figure is not ready

    def _on_click_with_snap(self, event):
        """Handle mouse clicks with snapping for left-click, room selection for right-click."""
        if event.inaxes != self.ax:
            return

        # Disable left-click drawing in elevation view
        if event.button == 1 and self.view_mode != 'plan':
            self._update_status('Cannot draw in elevation view - press "v" for Plan view', 'red')
            return

        # Right-click in edit mode: delete hovered vertex; otherwise select room
        if event.button == 3:
            if self.edit_mode and self.hover_vertex_idx is not None and self.hover_room_idx is not None:
                room = self.rooms[self.hover_room_idx]
                if len(room['vertices']) > 3:
                    room['vertices'].pop(self.hover_vertex_idx)
                    rname = room.get('name', 'unnamed')
                    self.hover_vertex_idx = None
                    self.hover_room_idx = None
                    self._update_status(f"Removed vertex from '{rname}' - press 's' to save", 'green')
                    self._save_session()
                    self._render_section(force_full=True)  # Vertex removed
                else:
                    self._update_status("Cannot remove - polygon must have at least 3 vertices", 'red')
                return
            # Normal right-click: select room
            if self.view_mode == 'plan':
                self._select_room_at(event.xdata, event.ydata)
            else:
                self._update_status('Room selection only in Plan view', 'orange')
            return

        # Left-click in edit mode: drag vertex or insert vertex on edge
        if event.button == 1 and self.edit_mode and event.xdata is not None and event.ydata is not None:
            if self.hover_vertex_idx is not None and self.hover_room_idx is not None:
                # Start dragging this vertex
                self.edit_room_idx = self.hover_room_idx
                self.edit_vertex_idx = self.hover_vertex_idx
                room_name = self.rooms[self.hover_room_idx].get('name', 'unnamed')
                self._update_status(f"Dragging vertex in '{room_name}'", 'cyan')
                return
            elif self.hover_edge_room_idx is not None and self.hover_edge_point is not None:
                # Insert new vertex on the hovered edge
                room = self.rooms[self.hover_edge_room_idx]
                insert_idx = self.hover_edge_idx + 1
                px, py = self.hover_edge_point
                if self.snap_enabled:
                    px, py = self._snap_to_vertex(px, py)
                room['vertices'].insert(insert_idx, [float(px), float(py)])
                rname = room.get('name', 'unnamed')
                self.hover_edge_room_idx = None
                self.hover_edge_idx = None
                self.hover_edge_point = None
                self._update_status(f"Added vertex to '{rname}' - press 's' to save", 'green')
                self._save_session()
                self._render_section(force_full=True)  # Vertex added
                return
            # Click on empty space in edit mode — no action
            return

        # Left-click: apply snapping before selector sees the event (plan view only, not in edit mode)
        if event.button == 1 and not self.edit_mode and event.xdata is not None and event.ydata is not None:
            snapped_x, snapped_y = self._snap_to_vertex(event.xdata, event.ydata)
            # Modify event in-place so selector sees snapped coordinates
            event.xdata = snapped_x
            event.ydata = snapped_y

    def _on_button_release(self, event):
        """Handle mouse button release (end of drag)."""
        if event.inaxes != self.ax:
            return

        # End vertex dragging - apply snap and full render
        if self.edit_vertex_idx is not None and self.edit_room_idx is not None:
            room = self.rooms[self.edit_room_idx]
            current_pos = room['vertices'][self.edit_vertex_idx]

            # Apply snap to mesh vertex if enabled
            if self.snap_enabled and event.xdata is not None and event.ydata is not None:
                snapped_x, snapped_y = self._snap_to_vertex(current_pos[0], current_pos[1])
                room['vertices'][self.edit_vertex_idx] = [float(snapped_x), float(snapped_y)]

            # Full render with selector recreation
            self.edit_vertex_idx = None
            self._save_session()
            room_name = room.get('name', 'unnamed')
            self._update_status(f"Moved vertex in '{room_name}'", 'green')
            self._render_section(force_full=True)  # Vertex moved
            self._create_polygon_selector()

    def _on_mouse_motion(self, event):
        """Handle mouse movement for hover detection and vertex dragging."""
        if event.inaxes != self.ax or self.view_mode != 'plan':
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        # Handle vertex dragging - fast update without full render
        if self.edit_vertex_idx is not None and self.edit_room_idx is not None:
            room = self.rooms[self.edit_room_idx]
            # Update vertex position (don't snap during drag for responsiveness)
            room['vertices'][self.edit_vertex_idx] = [float(x), float(y)]
            # Quick redraw without recreating selector
            self._render_section(force_full=True)
            return

        # Hover detection in edit mode only
        if not self.edit_mode:
            return

        # Throttle hover detection to ~15fps for performance (O(m×v) is expensive)
        now = time.monotonic()
        if now - self._last_hover_check < 0.067:
            return
        self._last_hover_check = now

        # Check for vertex hover across ALL visible rooms
        hover_threshold = 0.3  # metres - kept tight so edge hover activates near existing vertices
        closest_vertex = None
        closest_dist = float('inf')
        closest_room_idx = None
        closest_vertex_idx = None

        for i, room in enumerate(self.rooms):
            # Only check rooms on current floor (or all if show_all_floors)
            is_current_floor = abs(room['z_height'] - self.current_z) < 0.5
            if not self.show_all_floors and not is_current_floor:
                continue

            verts = np.array(room['vertices'])
            distances = np.sqrt((verts[:, 0] - x)**2 + (verts[:, 1] - y)**2)
            min_dist_idx = np.argmin(distances)
            min_dist = distances[min_dist_idx]

            if min_dist < closest_dist:
                closest_dist = min_dist
                closest_vertex_idx = min_dist_idx
                closest_room_idx = i

        # Update hover state if found vertex within threshold
        if closest_dist < hover_threshold:
            changed = (self.hover_room_idx != closest_room_idx or
                      self.hover_vertex_idx != closest_vertex_idx)
            if changed:
                self.hover_room_idx = closest_room_idx
                self.hover_vertex_idx = int(closest_vertex_idx) if closest_vertex_idx is not None else None
                self.hover_edge_room_idx = None
                self.hover_edge_idx = None
                self.hover_edge_point = None
                room_name = self.rooms[closest_room_idx].get('name', 'unnamed')
                self._update_status(f"Vertex in '{room_name}' - drag or right-click to remove", 'cyan')
                self._render_section(force_full=True)  # Vertex highlight colors changed
        else:
            # No vertex nearby - clear vertex hover and check for edge hover
            vertex_state_changed = self.hover_vertex_idx is not None or self.hover_room_idx is not None
            if vertex_state_changed:
                self.hover_vertex_idx = None
                self.hover_room_idx = None

            # Check proximity to polygon edges for vertex insertion
            edge_threshold = 0.4  # slightly larger than vertex hover so edges are reachable near vertices
            best_edge_dist = float('inf')
            best_edge_room = None
            best_edge_idx = None
            best_edge_point = None

            for i, room in enumerate(self.rooms):
                is_current_floor = abs(room['z_height'] - self.current_z) < 0.5
                if not self.show_all_floors and not is_current_floor:
                    continue
                verts = room['vertices']
                n = len(verts)
                for j in range(n):
                    ax_, ay_ = verts[j]
                    bx_, by_ = verts[(j + 1) % n]
                    dist, proj_x, proj_y = self._point_to_segment_dist(x, y, ax_, ay_, bx_, by_)
                    if dist < best_edge_dist:
                        best_edge_dist = dist
                        best_edge_room = i
                        best_edge_idx = j
                        best_edge_point = (proj_x, proj_y)

            if best_edge_dist < edge_threshold:
                changed = (self.hover_edge_room_idx != best_edge_room or
                           self.hover_edge_idx != best_edge_idx)
                self.hover_edge_room_idx = best_edge_room
                self.hover_edge_idx = best_edge_idx
                self.hover_edge_point = best_edge_point
                if changed:
                    rname = self.rooms[best_edge_room].get('name', 'unnamed')
                    self._update_status(f"Click to add vertex to '{rname}'", 'green')
                    self._render_section(force_full=True)  # Edge highlight changed
            else:
                if self.hover_edge_room_idx is not None:
                    self.hover_edge_room_idx = None
                    self.hover_edge_idx = None
                    self.hover_edge_point = None
                    self._update_status("Edit Mode: Hover over any vertex to drag", 'blue')
                    self._render_section(force_full=True)  # Edge highlight cleared
                elif vertex_state_changed:
                    # Vertex hover was cleared but no edge found - redraw to remove old highlight
                    self._update_status("Edit Mode: Hover over any vertex to drag", 'blue')
                    self._render_section(force_full=True)  # Vertex highlight cleared

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
            self._on_next_floor_click(None)  # Up arrow = next (higher) floor
        elif event.key == 'down':
            self._on_prev_floor_click(None)  # Down arrow = previous (lower) floor
        elif event.key == 'a':
            self._on_show_all_toggle(None)  # 'a' = toggle All floors view
        elif event.key == 'v':
            # Cycle through views: plan -> elevation_x -> elevation_y -> plan
            if self.view_mode == 'plan':
                self._set_view_mode('elevation_x')
            elif self.view_mode == 'elevation_x':
                self._set_view_mode('elevation_y')
            else:
                self._set_view_mode('plan')
        elif event.key == 'e':
            self._on_edit_mode_toggle(None)  # 'e' = toggle Edit mode

    # -------------------------------------------------------------------------
    # Room selection
    # -------------------------------------------------------------------------

    def _select_room_at(self, x, y):
        """Select the room polygon that contains the given point.

        If show_all_floors is enabled, can select rooms from any visible floor
        and will automatically jump to that floor's Z-height.
        """
        from matplotlib.path import Path as MplPath
        for i, room in enumerate(self.rooms):
            # Skip rooms not on current floor unless showing all floors
            if not self.show_all_floors and abs(room['z_height'] - self.current_z) > 0.5:
                continue

            verts = np.array(room['vertices'])
            if MplPath(verts).contains_point((x, y)):
                # If room is on a different floor, jump to that floor
                room_z = room['z_height']
                if abs(room_z - self.current_z) > 0.5:
                    self.current_z = room_z
                    self.z_slider.set_val(room_z)
                    # Update floor index if near a detected floor
                    if self.slicer and self.slicer.floor_levels:
                        for floor_idx, floor_z in enumerate(self.slicer.floor_levels):
                            if abs(floor_z - room_z) < 0.3:
                                self.current_floor_idx = floor_idx
                                break
                    self._update_status(f"Jumped to floor at Z={room_z:.1f}m", 'blue')
                    self._update_floor_level_list()
                    # Note: _render_section will be called by _select_room

                self._select_room(i)
                return
        self._deselect_room()

    def _select_room(self, idx):
        """Select a room by index and populate the input fields."""
        self._deselect_room()
        self.selected_room_idx = idx
        room = self.rooms[idx]
        self.name_textbox.set_val(room.get('name', ''))
        self._update_status(f"Selected: {room.get('name', 'unnamed')}", 'orange')
        self._render_section()  # Selection change can use incremental update

    def _deselect_room(self):
        """Deselect any selected room."""
        if self.selected_room_idx is not None:
            self.selected_room_idx = None
            self.name_textbox.set_val('')
            self._update_status("Ready to draw", 'blue')
            self._update_room_list()
            self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Button callbacks
    # -------------------------------------------------------------------------

    def _on_save_click(self, event):
        """Save the current polygon as a room, update selected room, or save edited boundary."""
        if self.edit_mode and self.edit_room_idx is not None:
            # Save edited room boundary
            self._save_edited_room()
        elif self.selected_room_idx is not None:
            # Update room name/type
            self._update_selected_room()
        else:
            # Save new polygon
            self._save_current_room()

    def _save_edited_room(self):
        """Save changes to an edited room boundary."""
        if self.edit_room_idx is None:
            return

        room = self.rooms[self.edit_room_idx]
        name = room.get('name', 'unnamed')

        # Auto-save session to JSON
        self._save_session()

        # Exit edit mode for this room
        self.edit_room_idx = None
        self.hover_vertex_idx = None
        self._update_status(f"Saved boundary changes for '{name}'", 'green')
        self._render_section(force_full=True)  # Room changed, need full redraw
        self._create_polygon_selector()
        self._update_room_list()
        self._update_floor_level_list()
        print(f"Saved edited boundary for '{name}'")

    def _save_current_room(self):
        """Save the currently drawn polygon as a new room with optional parent relationship."""
        if len(self.current_polygon_vertices) < 3:
            self._update_status("No polygon to save - draw one first", 'red')
            return

        name = self.name_textbox.text.strip().upper()
        if not name:
            name = f"ROOM_{len(self.rooms) + 1:03d}"

        # Auto-prefix with parent name if parent is selected
        if self.selected_parent:
            full_name = f"{self.selected_parent}_{name}"
        else:
            full_name = name

        # Ensure unique name by appending numeric suffix if needed
        full_name = self._make_unique_name(full_name)

        vertices = [[float(x), float(y)] for x, y in self.current_polygon_vertices]

        # Check boundary containment if parent is selected
        warning_msg = ""
        is_outside_parent = False
        if self.selected_parent:
            parent_room = self._get_parent_room(self.selected_parent)
            if parent_room:
                is_outside_parent = not self._check_boundary_containment(vertices, parent_room['vertices'])
                if is_outside_parent:
                    warning_msg = " (WARNING: extends outside parent boundary!)"
                    print(f"WARNING: Room '{full_name}' extends outside parent '{self.selected_parent}' boundary")
            else:
                print(f"Warning: Parent room '{self.selected_parent}' not found in rooms list")

        room = {
            'name': full_name,
            'parent': self.selected_parent,  # None for apartments, parent name for sub-rooms
            'vertices': vertices,
            'z_height': self.current_z,
        }
        self.rooms.append(room)

        # Reset drawing state
        self.current_polygon_vertices = []
        self.selector.clear()
        self.name_textbox.set_val('')

        # Update parent options since we may have added a new apartment
        self._update_parent_options()
        self._update_name_preview()

        status_color = 'orange' if warning_msg else 'green'
        self._update_status(f"Saved '{full_name}'{warning_msg}", status_color)
        self._update_room_list()
        self._update_floor_level_list()
        self._render_section(force_full=True)  # New room added
        # Re-create selector after render
        self._create_polygon_selector()
        print(f"Saved room '{full_name}' at Z={self.current_z:.1f}m ({len(self.rooms)} total){warning_msg}")

        # Auto-save session to JSON after saving room
        self._save_session()

    def _update_selected_room(self):
        """Update the name of the selected room."""
        if self.selected_room_idx is None:
            return
        idx = self.selected_room_idx
        new_name = self.name_textbox.text.strip().upper() or self.rooms[idx]['name']

        # Ensure unique name by appending numeric suffix if needed
        new_name = self._make_unique_name(new_name, exclude_idx=idx)

        self.rooms[idx]['name'] = new_name
        self._update_status(f"Updated '{new_name}'", 'green')
        self._update_room_list()
        self._render_section(force_full=True)  # Room name changed

        # Auto-save session to JSON after updating room
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
        idx = self.selected_room_idx
        name = self.rooms[idx].get('name', 'unnamed')
        self.rooms.pop(idx)
        self.selected_room_idx = None
        self._update_status(f"Deleted '{name}'", 'green')
        self._update_room_list()
        self._update_floor_level_list()
        self._render_section(force_full=True)  # Room deleted
        print(f"Deleted room '{name}'")

        # Auto-save session to JSON after deleting room
        self._save_session()

    def _on_reset_zoom_click(self, event):
        """Reset zoom to the full section extent."""
        if self.original_xlim and self.original_ylim:
            self.ax.set_xlim(self.original_xlim)
            self.ax.set_ylim(self.original_ylim)
            self.fig.canvas.draw_idle()

    def _on_snap_toggle(self, event):
        """Toggle vertex snapping on/off."""
        self.snap_enabled = not self.snap_enabled
        self.btn_snap.label.set_text('Snap: ON' if self.snap_enabled else 'Snap: OFF')
        status = "ON" if self.snap_enabled else "OFF"
        self._update_status(f"Vertex snapping: {status}", 'blue')
        self._render_section(force_full=True)  # Snap points visibility changed

    def _on_snap_distance_changed(self, val):
        """Handle snap distance slider changes."""
        self.snap_distance = round(val, 1)
        self.snap_dist_label.texts[0].set_text(f"Snap Distance: {self.snap_distance:.1f}m")
        self.fig.canvas.draw_idle()

    def _on_show_all_toggle(self, event):
        """Toggle showing rooms from all floors vs current floor only."""
        self.show_all_floors = not self.show_all_floors
        status = "all floors" if self.show_all_floors else "current floor only"
        self._update_status(f"Showing rooms from {status}", 'blue')
        self._render_section(force_full=True)  # Display mode changed
        # Re-create selector after render
        self._create_polygon_selector()

    def _on_edit_mode_toggle(self, event):
        """Toggle edit mode for modifying existing room boundaries."""
        self.edit_mode = not self.edit_mode
        self.btn_edit_mode.label.set_text('Edit Mode: ON (Press E)' if self.edit_mode else 'Edit Mode: OFF (Press E)')

        if self.edit_mode:
            # Disable polygon selector when in edit mode
            if hasattr(self, 'selector'):
                self.selector.set_active(False)
            self._update_status("Edit Mode: Hover over any vertex to drag (all rooms editable)", 'cyan')
        else:
            # Exit edit mode - clear edit state
            self.edit_room_idx = None
            self.edit_vertex_idx = None
            self.hover_room_idx = None
            self.hover_vertex_idx = None
            self.hover_edge_room_idx = None
            self.hover_edge_idx = None
            self.hover_edge_point = None
            # Save any pending vertex changes before leaving edit mode
            self._save_session()
            # Re-enable polygon selector
            self._create_polygon_selector()
            self._update_status("Edit Mode OFF - Draw mode enabled", 'blue')

        self._render_section(force_full=True)  # Edit mode visual state changed

    def _enter_edit_mode_for_room(self, room_idx: int):
        """Enter edit mode for a specific room's boundary.

        Args:
            room_idx: Index of room in self.rooms list
        """
        self.edit_room_idx = room_idx
        self.hover_vertex_idx = None
        room = self.rooms[room_idx]
        self._update_status(f"Editing: {room.get('name', 'unnamed')} - drag vertices to modify", 'cyan')
        self._render_section(force_full=True)  # Edit room selection changed
        self._create_polygon_selector()

    def _set_view_mode(self, mode: str):
        """Switch between plan and elevation views.

        Args:
            mode: 'plan', 'elevation_x', or 'elevation_y'
        """
        if mode == self.view_mode:
            return

        self.view_mode = mode

        # Set elevation slice position to middle of building
        if mode == 'elevation_x':
            self.elevation_position = (self.slicer.x_min + self.slicer.x_max) / 2
        elif mode == 'elevation_y':
            self.elevation_position = (self.slicer.y_min + self.slicer.y_max) / 2

        # Update button colors to show active view (soft colors)
        self.btn_view_plan.color = self._view_btn_active if mode == 'plan' else self._view_btn_color
        self.btn_view_elev_x.color = self._view_btn_active if mode == 'elevation_x' else self._view_btn_color
        self.btn_view_elev_y.color = self._view_btn_active if mode == 'elevation_y' else self._view_btn_color

        # Update status
        view_names = {
            'plan': 'Plan View (editing enabled)',
            'elevation_x': 'Elevation X View (view only)',
            'elevation_y': 'Elevation Y View (view only)'
        }
        self._update_status(view_names.get(mode, 'Unknown view'), 'blue')

        # Disable polygon selector in elevation view
        if mode != 'plan':
            if hasattr(self, 'selector'):
                self.selector.set_active(False)
                self._update_status('Elevation view - editing disabled. Press "v" for Plan view', 'orange')
        else:
            self._create_polygon_selector()

        # Reset view limits when switching modes so autoscale works correctly
        self._render_section(reset_view=True)

    def _on_prev_floor_click(self, event):
        """Navigate to the previous floor level."""
        if not self.slicer or not self.slicer.floor_levels:
            self._update_status("No floor levels detected", 'red')
            return

        if self.current_floor_idx is None:
            # Find nearest floor below current Z
            for i in range(len(self.slicer.floor_levels) - 1, -1, -1):
                if self.slicer.floor_levels[i] < self.current_z:
                    self.current_floor_idx = i
                    break
            if self.current_floor_idx is None:
                self.current_floor_idx = len(self.slicer.floor_levels) - 1
        elif self.current_floor_idx > 0:
            self.current_floor_idx -= 1
        else:
            self._update_status("Already at lowest floor", 'orange')
            return

        self._jump_to_floor(self.current_floor_idx)

    def _on_next_floor_click(self, event):
        """Navigate to the next floor level."""
        if not self.slicer or not self.slicer.floor_levels:
            self._update_status("No floor levels detected", 'red')
            return

        if self.current_floor_idx is None:
            # Find nearest floor above current Z
            for i, floor_z in enumerate(self.slicer.floor_levels):
                if floor_z > self.current_z:
                    self.current_floor_idx = i
                    break
            if self.current_floor_idx is None:
                self.current_floor_idx = 0
        elif self.current_floor_idx < len(self.slicer.floor_levels) - 1:
            self.current_floor_idx += 1
        else:
            self._update_status("Already at highest floor", 'orange')
            return

        self._jump_to_floor(self.current_floor_idx)

    def _jump_to_floor(self, floor_idx: int):
        """Jump to a specific floor level by index."""
        if not self.slicer or not self.slicer.floor_levels:
            return

        if 0 <= floor_idx < len(self.slicer.floor_levels):
            target_z = self.slicer.floor_levels[floor_idx]
            self.current_z = target_z
            self.current_floor_idx = floor_idx
            self.z_slider.set_val(target_z)
            self._update_status(f"Floor L{floor_idx}: Z={target_z:.2f}m", 'green')
            self._update_floor_level_list()
            # Note: _render_section will be called by z_slider.set_val

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
        self.ax_list.tick_params(left=False, bottom=False,
                                  labelleft=False, labelbottom=False)
        for spine in self.ax_list.spines.values():
            spine.set_edgecolor('#CCCCCC')
            spine.set_linewidth(0.5)

        self._room_list_hit_boxes = []

        # Filter rooms to current floor level only
        floor_rooms = [(i, r) for i, r in enumerate(self.rooms)
                       if abs(r.get('z_height', 0) - self.current_z) < 0.5]

        if not floor_rooms:
            self.ax_list.set_ylim(0, 1)
            self.ax_list.text(0.05, 0.5, "(no rooms on this floor)", fontsize=7,
                              style='italic', color='gray', va='center')
            self.fig.canvas.draw_idle()
            return

        # Build flat ordered list: apartments with children interleaved
        flat_items = []  # list of (room_idx, indent_level)
        floor_indices = {i for i, _ in floor_rooms}
        apartments = [(i, r) for i, r in floor_rooms if r.get('parent') is None]
        children_by_parent = {}
        for i, room in floor_rooms:
            parent = room.get('parent')
            if parent is not None:
                children_by_parent.setdefault(parent, []).append((i, room))

        for apt_idx, apt in apartments:
            flat_items.append((apt_idx, 0))
            for child_idx, _ in children_by_parent.get(apt.get('name', ''), []):
                flat_items.append((child_idx, 1))

        total_items = len(flat_items)
        visible_rows = 22  # number of rows visible at once (tight spacing)
        pad_top = 0.01     # fraction of axes height reserved at top
        pad_bot = 0.03     # fraction of axes height reserved at bottom
        content_h = 1.0 - pad_top - pad_bot
        row_h = content_h / visible_rows  # height per row in axes units

        # Clamp scroll offset
        max_offset = max(0, total_items - visible_rows)
        self.room_list_scroll_offset = max(0, min(self.room_list_scroll_offset, max_offset))

        self.ax_list.set_ylim(0, 1)

        visible_slice = flat_items[self.room_list_scroll_offset:
                                   self.room_list_scroll_offset + visible_rows]

        for row_i, (room_idx, indent) in enumerate(visible_slice):
            room = self.rooms[room_idx]
            name = room.get('name', 'unnamed')
            z = room.get('z_height', 0)
            is_sel = (room_idx == self.selected_room_idx)
            is_subroom = indent > 0

            # Row top/bottom in axes coords (rows go top-down)
            row_top = (1.0 - pad_top) - row_i * row_h
            row_bot = row_top - row_h
            row_mid = (row_top + row_bot) / 2

            # Highlight background for selected room
            if is_sel:
        
                bg = FancyBboxPatch((0.01, row_bot + 0.002), 0.98, row_h - 0.004,
                                    boxstyle='round,pad=0.01',
                                    facecolor='#FFE082', edgecolor='orange',
                                    linewidth=1.0, transform=self.ax_list.transAxes,
                                    clip_on=True)
                self.ax_list.add_patch(bg)

            # Build display text
            if is_subroom:
                short_name = name
                parent_name = room.get('parent', '')
                if name.startswith(f"{parent_name}_"):
                    short_name = name[len(parent_name) + 1:]
                display_text = f"  \u2514 {short_name}"
                txt_color = '#0D47A1' if not is_sel else '#E65100'
                fs = 6.5
                fw = 'normal'
            else:
                child_count = len(children_by_parent.get(name, []))
                suffix = f" ({child_count})" if child_count else ""
                display_text = f"{name}{suffix}"
                txt_color = '#1B5E20' if not is_sel else '#E65100'
                fs = 7
                fw = 'bold'

            self.ax_list.text(
                0.03 + indent * 0.04, row_mid, display_text,
                fontsize=fs, fontweight=fw, color=txt_color,
                va='center', transform=self.ax_list.transAxes, clip_on=True,
            )

            # Store hit box (in axes coords 0-1) for click detection
            self._room_list_hit_boxes.append((row_bot, row_top, room_idx))

        # Scroll indicator if list is scrollable
        if total_items > visible_rows:
            scroll_pct = self.room_list_scroll_offset / max(1, max_offset)
            indicator_h = visible_rows / total_items
            indicator_y = (1.0 - indicator_h) * (1.0 - scroll_pct)
    
            scrollbar = FancyBboxPatch((0.965, indicator_y), 0.025, indicator_h,
                                       boxstyle='round,pad=0.005',
                                       facecolor='#AAAAAA', edgecolor='none',
                                       transform=self.ax_list.transAxes, clip_on=True)
            self.ax_list.add_patch(scrollbar)
            # Scroll hint text at bottom
            self.ax_list.text(0.5, 0.01,
                              f"\u2191\u2193 scroll  ({self.room_list_scroll_offset + 1}"
                              f"-{min(self.room_list_scroll_offset + visible_rows, total_items)}"
                              f" of {total_items})",
                              fontsize=6, color='#888888', ha='center', va='bottom',
                              transform=self.ax_list.transAxes)

        self.fig.canvas.draw_idle()

    def _on_list_click(self, event):
        """Handle clicks on the saved rooms list to select and highlight a room."""
        if event.inaxes != self.ax_list:
            return
        if event.xdata is None or event.ydata is None:
            return

        # ydata is in data coordinates which equal axes coords since ylim=(0,1) and xlim=(0,1)
        y = event.ydata
        for (y_min, y_max, room_idx) in self._room_list_hit_boxes:
            if y_min <= y <= y_max:
                if self.selected_room_idx == room_idx:
                    # Clicking again deselects
                    self.selected_room_idx = None
                else:
                    self.selected_room_idx = room_idx
                self._render_section()
                self._update_room_list()
                return

    def _update_floor_level_list(self):
        """Refresh the floor level list in the side panel (descending order - top floor first)."""
        self.ax_floor_list.clear()
        self.ax_floor_list.axis('off')

        if not self.slicer or not self.slicer.floor_levels:
            self.ax_floor_list.text(0, 0.95, "(no floors detected)", fontsize=8, style='italic', color='gray')
        else:
            max_display = 8
            total_floors = len(self.slicer.floor_levels)

            # Display in descending order (highest floor first)
            for display_idx in range(min(max_display, total_floors)):
                # Reverse the index to show top floor first
                i = total_floors - 1 - display_idx
                floor_z = self.slicer.floor_levels[i]
                y_pos = 0.95 - (display_idx * 0.12)
                is_current = (self.current_floor_idx == i)

                # Count rooms at this floor level
                room_count = sum(1 for r in self.rooms if abs(r['z_height'] - floor_z) < 0.5)

                # Format the display text
                indicator = "●" if is_current else "○"
                text = f"{indicator} L{i}: {floor_z:.2f}m"
                if room_count > 0:
                    text += f" ({room_count} rooms)"

                self.ax_floor_list.text(
                    0, y_pos, text, fontsize=8,
                    fontweight='bold' if is_current else 'normal',
                    color='green' if is_current else 'darkgray',
                )

            if total_floors > max_display:
                self.ax_floor_list.text(0, 0.02, f"... and {total_floors - max_display} more",
                                       fontsize=7, style='italic')

        self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Export functions
    # -------------------------------------------------------------------------

    def export_room_boundaries_csv(self, output_path: Optional[Path] = None):
        """Export room boundaries as CSV compatible with ViewGenerator.

        The CSV format includes the parent column for hierarchical relationships:
        name, parent, X_mm Y_mm Z_mm, ...

        Args:
            output_path: Output CSV path. Defaults to config.WPD_DIR / 'drawn_room_boundaries.csv'.
        """
        if not self.rooms:
            self._update_status("No rooms to export", 'red')
            return

        output_path = Path(output_path) if output_path else (config.WPD_DIR / "drawn_room_boundaries.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for room in self.rooms:
            z_mm = room['z_height'] * 1000
            coord_strings = []
            for x, y in room['vertices']:
                coord_strings.append(f"X_{x * 1000:.3f} Y_{y * 1000:.3f} Z_{z_mm:.3f}")

            # Include parent column (empty string if no parent)
            parent = room.get('parent', '') or ''
            row = [room['name'], parent] + coord_strings
            rows.append(row)

        # Pad all rows to the same column count
        max_cols = max(len(r) for r in rows)
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            for row in rows:
                row += [''] * (max_cols - len(row))
                writer.writerow(row)

        self._update_status(f"Exported CSV ({len(self.rooms)} rooms)", 'green')
        print(f"Exported room boundaries CSV to {output_path}")

    # -------------------------------------------------------------------------
    # Floor level alignment
    # -------------------------------------------------------------------------

    def _align_floor_levels_with_rooms(self, tolerance: float = 0.5):
        """Align detected floor levels with Z-heights from loaded rooms.

        If a room's Z-height is close to (but not exactly matching) a detected
        floor level, override the detected floor's Z-height with the room's Z-height.
        This ensures rooms from CSV are correctly associated with floor levels.

        Args:
            tolerance: Maximum Z-difference (meters) to consider a match
        """
        if not self.rooms or not self.slicer or not self.slicer.floor_levels:
            return

        # Collect unique Z-heights from rooms
        room_z_heights = set()
        for room in self.rooms:
            z = room.get('z_height')
            if z is not None:
                room_z_heights.add(round(z, 3))  # Round to avoid float precision issues

        if not room_z_heights:
            return

        # Check each detected floor level against room Z-heights
        updated_floors = []
        alignments_made = 0

        for floor_z in self.slicer.floor_levels:
            best_match = None
            best_dist = float('inf')

            # Find closest room Z-height within tolerance
            for room_z in room_z_heights:
                dist = abs(floor_z - room_z)
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    best_match = room_z

            if best_match is not None and best_match != floor_z:
                # Override with room Z-height
                print(f"Aligned floor Z={floor_z:.2f}m -> Z={best_match:.2f}m (from CSV rooms)")
                updated_floors.append(best_match)
                alignments_made += 1
            else:
                updated_floors.append(floor_z)

        if alignments_made > 0:
            self.slicer.floor_levels = sorted(updated_floors)
            # Update current Z if it was on an aligned floor
            if self.current_floor_idx is not None and self.current_floor_idx < len(self.slicer.floor_levels):
                self.current_z = self.slicer.floor_levels[self.current_floor_idx]
            print(f"Aligned {alignments_made} floor level(s) with CSV room Z-heights")

    # -------------------------------------------------------------------------
    # Session persistence
    # -------------------------------------------------------------------------

    def _save_session(self):
        """Save all room boundaries to JSON for later editing."""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'obj_path': str(self.obj_path),
            'floor_levels': self.slicer.floor_levels if hasattr(self, 'slicer') else [],
            'rooms': self.rooms,
        }
        with open(self.session_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Session saved to {self.session_path}")

        # Write CSV alongside JSON so both are always in sync
        self.export_room_boundaries_csv(output_path=self.csv_path)

    def _load_session(self):
        """Load previously saved room boundaries from JSON, or from initial CSV if no session exists."""
        if self.session_path.exists():
            with open(self.session_path, 'r') as f:
                data = json.load(f)
            self.rooms = data.get('rooms', [])
            source = "session"
        elif self.initial_csv_path and self.initial_csv_path.exists():
            # No session exists, load from initial CSV
            self._load_from_csv(self.initial_csv_path)
            source = "initial CSV"
        else:
            return

        # Enforce unique names on load (fix any duplicates from older sessions)
        renamed_count = self._enforce_unique_names()
        if renamed_count > 0:
            print(f"Renamed {renamed_count} rooms to ensure uniqueness")
            self._save_session()  # Persist the fixes

        # Align detected floor levels with CSV Z-heights if loading from CSV
        if source == "initial CSV" and self.slicer and self.slicer.floor_levels:
            self._align_floor_levels_with_rooms()

        self._update_status(f"Loaded {len(self.rooms)} rooms from {source}", 'green')
        if hasattr(self, 'ax'):
            self._render_section(force_full=True)  # Session loaded
        print(f"Loaded {len(self.rooms)} rooms from {source}")

    def _load_from_csv(self, csv_path: Path):
        """Load room boundaries from a CSV file.

        CSV format: apartment_name, room_type, X_val Y_val Z_val, X_val Y_val Z_val, ...
        Coordinates are in millimeters and converted to meters.

        Room type interpretation:
        - Descriptive types like "3 BED", "4 BED", "STUDIO" = apartment boundary (parent=None)
        - Short codes like "T", "K", "L", "B1" = sub-room (parent=apartment_name)

        Args:
            csv_path: Path to the CSV file
        """
        import re
        self.rooms = []
        seen_apartments = set()  # Track which apartments we've seen

        with open(csv_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split(',')
                if len(parts) < 3:
                    continue

                apartment_name = parts[0].strip()
                room_type = parts[1].strip()

                # Determine if this is an apartment boundary or a sub-room
                # Apartment boundaries have descriptive types like "3 BED", "4 BED", "STUDIO", etc.
                # or are the first entry for a given apartment name
                is_apartment_boundary = (
                    apartment_name not in seen_apartments or
                    ' BED' in room_type.upper() or
                    room_type.upper() in ('STUDIO', 'PENTHOUSE', '')
                )

                if is_apartment_boundary:
                    name = apartment_name
                    parent = None
                    seen_apartments.add(apartment_name)
                else:
                    # Sub-room: use apartment_name_room_type
                    name = f"{apartment_name}_{room_type}"
                    parent = apartment_name

                # Parse vertices (format: X_value Y_value Z_value)
                vertices = []
                z_height = None
                for vertex_str in parts[2:]:
                    vertex_str = vertex_str.strip()
                    if not vertex_str:
                        continue

                    match = re.match(r'X_([-\d.]+)\s+Y_([-\d.]+)\s+Z_([-\d.]+)', vertex_str)
                    if match:
                        x_mm = float(match.group(1))
                        y_mm = float(match.group(2))
                        z_mm = float(match.group(3))
                        # Convert mm to meters
                        x_m = x_mm / 1000.0
                        y_m = y_mm / 1000.0
                        z_m = z_mm / 1000.0
                        vertices.append([x_m, y_m])
                        if z_height is None:
                            z_height = z_m

                if len(vertices) >= 3 and z_height is not None:
                    self.rooms.append({
                        'name': name,
                        'parent': parent,
                        'vertices': vertices,
                        'z_height': z_height,
                    })

        print(f"Loaded {len(self.rooms)} rooms from CSV: {csv_path}")

    def _enforce_unique_names(self) -> int:
        """Ensure all room names are unique by appending numeric suffixes to duplicates.

        Returns:
            Number of rooms that were renamed
        """
        import re
        seen_names = set()
        renamed_count = 0

        for room in self.rooms:
            name = room['name']
            if name not in seen_names:
                seen_names.add(name)
                continue

            # Duplicate found - generate unique name
            match = re.match(r'^(.*?)(\d+)$', name)
            root = match.group(1) if match else name

            counter = 1
            while f"{root}{counter}" in seen_names:
                counter += 1

            new_name = f"{root}{counter}"
            print(f"Renamed duplicate '{name}' -> '{new_name}'")
            room['name'] = new_name
            seen_names.add(new_name)
            renamed_count += 1

        return renamed_count
