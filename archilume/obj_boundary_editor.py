# fmt: off
# autopep8: off

"""
Interactive Room Boundary Editor for OBJ Models.

Slices a 3D OBJ mesh at a user-specified Z height to produce a 2D floor plan
cross-section, then provides an interactive matplotlib-based polygon drawing
tool for defining room boundaries. Exports to .aoi files and room boundaries
CSV compatible with the existing ViewGenerator pipeline.

Usage:
    from archilume.obj_boundary_editor import BoundaryEditor
    editor = BoundaryEditor(obj_paths=["model.obj"])
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
from typing import List, Optional, Tuple

# Third-party imports
import matplotlib.pyplot as plt
from matplotlib.widgets import PolygonSelector, TextBox, Button, Slider
from matplotlib.patches import Polygon
from matplotlib.collections import LineCollection
import numpy as np
import pyvista as pv
from scipy.spatial import cKDTree


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

    def __init__(self, obj_paths: List[Path], simplify_ratio: Optional[float] = None, detect_floors: bool = True):
        """Initialize mesh slicer with optional simplification.

        Args:
            obj_paths: List of OBJ file paths to load
            simplify_ratio: Optional mesh decimation ratio (0.0-1.0). E.g., 0.5 reduces mesh to 50% of original.
                           Useful for large meshes to improve performance. None = no simplification.
            detect_floors: Whether to automatically detect floor levels on load. Set to False for very large
                          meshes to speed up initialization.
        """
        meshes = []
        for p in obj_paths:
            p = Path(p)
            if not p.exists():
                raise FileNotFoundError(f"OBJ file not found: {p}")
            meshes.append(pv.read(str(p)))

        if len(meshes) == 1:
            self.mesh = meshes[0]
        else:
            self.mesh = meshes[0].merge(meshes[1:])

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

    def precache_floor_slices(self):
        """Pre-compute and cache slices at all detected floor levels for instant access."""
        if not self.floor_levels:
            return

        print(f"Pre-caching slices at {len(self.floor_levels)} floor levels...")
        for floor_z in self.floor_levels:
            # This will populate the cache
            self.slice_at_z(floor_z)
        print(f"Pre-cached {len(self.slice_cache)} floor slices")


class BoundaryEditor:
    """Interactive room boundary drawing tool on a 2D floor plan section.

    Displays a PyVista-sliced cross-section in a matplotlib figure and
    provides a PolygonSelector for drawing room boundary polygons. Exports
    to .aoi files and room boundaries CSV for the ViewGenerator pipeline.

    Args:
        obj_paths: One or more OBJ file paths to load.
        mtl_path: Optional MTL file (not used for slicing, reserved for future).
        session_path: Path for saving/loading editor sessions (JSON).
    """

    def __init__(
        self,
        obj_paths: List[Path],
        mtl_path: Optional[Path] = None,
        session_path: Optional[Path] = None,
        simplify_ratio: Optional[float] = None,
        detect_floors: bool = True,
        max_vertex_display: int = 5000,
    ):
        """Initialize the boundary editor.

        Args:
            obj_paths: One or more OBJ file paths to load
            mtl_path: Optional MTL file path (not currently used)
            session_path: Path for saving/loading editor sessions
            simplify_ratio: Optional mesh decimation ratio (0.0-1.0) for large meshes
            detect_floors: Whether to auto-detect floor levels (disable for very large meshes)
            max_vertex_display: Maximum vertices to display (downsample if exceeded)
        """
        if isinstance(obj_paths, (str, Path)):
            obj_paths = [Path(obj_paths)]
        else:
            obj_paths = [Path(p) for p in obj_paths]

        self.obj_paths = obj_paths
        self.mtl_path = mtl_path
        self.session_path = session_path or (config.AOI_DIR / "boundary_editor_session.json")
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
        self.snap_distance: float = 0.5  # meters
        self.current_vertices: np.ndarray = np.array([])  # (N, 2) array of slice vertices
        self._vertex_kdtree: Optional[cKDTree] = None  # Spatial index for fast snapping

        # Visualization options
        self.show_all_floors: bool = False  # Toggle to show rooms from all floors

        # Slider debouncing
        self._z_slider_timer: Optional[int] = None
        self._pending_z_value: Optional[float] = None

    def launch(self):
        """Load the mesh and open the interactive editor window."""
        print("Loading OBJ mesh(es)...")
        self.slicer = MeshSlicer(
            self.obj_paths,
            simplify_ratio=self.simplify_ratio,
            detect_floors=self.detect_floors
        )
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

        # Setup matplotlib figure
        self.fig = plt.figure(figsize=(18, 10))
        # Main plot area on the right, side panel on the left
        self.ax = self.fig.add_axes([0.32, 0.10, 0.66, 0.85])
        self.ax.set_aspect('equal')

        # Setup side panel and slider
        self._setup_side_panel()
        self._setup_z_slider()
        self._setup_floor_level_indicators()

        # Initial section render
        self._render_section()

        # Store original limits
        self.original_xlim = self.ax.get_xlim()
        self.original_ylim = self.ax.get_ylim()

        # Polygon selector for drawing room boundaries
        self._create_polygon_selector()

        # Event handlers (snap handler must come first to intercept before selector)
        self.fig.canvas.mpl_connect('button_press_event', self._on_click_with_snap)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key_press)
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)

        # Load existing session if available
        self._load_session()
        self._update_room_list()
        self._update_floor_level_list()

        print("\n=== Boundary Editor ===")
        print("Draw room boundary polygons on the floor plan section.")
        if self.slicer.floor_levels:
            print(f"Detected {len(self.slicer.floor_levels)} floor levels - use ↑↓ arrow keys to navigate")
        print("Adjust the Z slider to change the section height.")
        print("Vertex snapping is ENABLED - clicks snap to mesh vertices.")
        print("Scroll: zoom | Right-click: select room | s: save | d: delete | q: quit")
        print("↑/↓: next/prev floor | r: reset zoom | S: save session")
        print("========================\n")
        plt.show()

    # -------------------------------------------------------------------------
    # UI setup
    # -------------------------------------------------------------------------

    def _setup_z_slider(self):
        """Create the Z-height slider below the main axes."""
        # Position slider under the main plot area (right side only)
        ax_slider = self.fig.add_axes([0.32, 0.02, 0.66, 0.04])
        self.z_slider = Slider(
            ax_slider,
            'Z Height (m)',
            self.slicer.z_min,
            self.slicer.z_max,
            valinit=self.current_z,
            valstep=0.2,  # Coarser step for better performance (was 0.1)
        )
        self.z_slider.on_changed(self._on_z_changed_debounced)

    def _setup_floor_level_indicators(self):
        """Add visual indicators for detected floor levels on the Z-slider."""
        if not self.slicer.floor_levels:
            return

        # Add vertical lines at each floor level on the slider axis
        ax_slider = self.z_slider.ax
        for floor_z in self.slicer.floor_levels:
            # Normalize position within slider range
            normalized_pos = (floor_z - self.slicer.z_min) / (self.slicer.z_max - self.slicer.z_min)
            ax_slider.axvline(normalized_pos, color='green', linewidth=2, alpha=0.6, zorder=10)

    def _setup_side_panel(self):
        """Create the side panel with inputs, buttons, and room list."""
        pl = 0.02   # panel left (moved to left side)
        pw = 0.28   # panel width

        # Instructions
        ax_instr = self.fig.add_axes([pl, 0.90, pw, 0.08])
        ax_instr.axis('off')
        ax_instr.text(0, 0.9, "BOUNDARY EDITOR", fontsize=11, fontweight='bold')
        ax_instr.text(0, 0.55, "1. Use ↑↓ arrow keys or buttons to navigate floors", fontsize=9)
        ax_instr.text(0, 0.25, "2. Click to draw (snaps to vertices)", fontsize=9)
        ax_instr.text(0, -0.05, "3. Enter name, click Save Room", fontsize=9)

        # Floor level navigation section
        ax_floor_hdr = self.fig.add_axes([pl, 0.835, pw, 0.03])
        ax_floor_hdr.axis('off')
        ax_floor_hdr.text(0, 0.5, "FLOOR LEVELS:", fontsize=10, fontweight='bold')

        # Floor level list area
        self.ax_floor_list = self.fig.add_axes([pl, 0.70, pw, 0.13])
        self.ax_floor_list.axis('off')

        # Floor navigation buttons
        ax_prev_floor = self.fig.add_axes([pl, 0.64, pw * 0.48, 0.05])
        self.btn_prev_floor = Button(ax_prev_floor, '↓ Lower Floor')
        self.btn_prev_floor.on_clicked(self._on_prev_floor_click)

        ax_next_floor = self.fig.add_axes([pl + pw * 0.52, 0.64, pw * 0.48, 0.05])
        self.btn_next_floor = Button(ax_next_floor, '↑ Upper Floor')
        self.btn_next_floor.on_clicked(self._on_next_floor_click)

        # Room name input
        ax_name_lbl = self.fig.add_axes([pl, 0.57, pw, 0.03])
        ax_name_lbl.axis('off')
        ax_name_lbl.text(0, 0.5, "Room Name (Space ID):", fontsize=10, fontweight='bold')
        ax_name = self.fig.add_axes([pl, 0.53, pw, 0.04])
        self.name_textbox = TextBox(ax_name, '', initial='')

        # Room type input
        ax_type_lbl = self.fig.add_axes([pl, 0.49, pw, 0.03])
        ax_type_lbl.axis('off')
        ax_type_lbl.text(0, 0.5, "Room Type:", fontsize=10, fontweight='bold')
        ax_type = self.fig.add_axes([pl, 0.45, pw, 0.04])
        self.type_textbox = TextBox(ax_type, '', initial='')

        # Status display
        ax_status = self.fig.add_axes([pl, 0.40, pw, 0.04])
        ax_status.axis('off')
        self.status_text = ax_status.text(
            0, 0.5, "Status: Ready to draw", fontsize=9, color='blue', style='italic')

        # Buttons row 1
        ax_save = self.fig.add_axes([pl, 0.35, pw * 0.48, 0.04])
        self.btn_save = Button(ax_save, 'Save Room')
        self.btn_save.on_clicked(self._on_save_click)

        ax_clear = self.fig.add_axes([pl + pw * 0.52, 0.35, pw * 0.48, 0.04])
        self.btn_clear = Button(ax_clear, 'Clear Current')
        self.btn_clear.on_clicked(self._on_clear_click)

        # Buttons row 2
        ax_export_aoi = self.fig.add_axes([pl, 0.30, pw * 0.48, 0.04])
        self.btn_export_aoi = Button(ax_export_aoi, 'Export AOI')
        self.btn_export_aoi.on_clicked(self._on_export_aoi_click)

        ax_delete = self.fig.add_axes([pl + pw * 0.52, 0.30, pw * 0.48, 0.04])
        self.btn_delete = Button(ax_delete, 'Delete Selected')
        self.btn_delete.on_clicked(self._on_delete_click)

        # Buttons row 3
        ax_export_csv = self.fig.add_axes([pl, 0.25, pw * 0.48, 0.04])
        self.btn_export_csv = Button(ax_export_csv, 'Export CSV')
        self.btn_export_csv.on_clicked(self._on_export_csv_click)

        ax_reset = self.fig.add_axes([pl + pw * 0.52, 0.25, pw * 0.48, 0.04])
        self.btn_reset_zoom = Button(ax_reset, 'Reset Zoom')
        self.btn_reset_zoom.on_clicked(self._on_reset_zoom_click)

        # Snap to vertex toggle button
        ax_snap = self.fig.add_axes([pl, 0.20, pw * 0.48, 0.04])
        self.btn_snap = Button(ax_snap, 'Snap: ON' if self.snap_enabled else 'Snap: OFF')
        self.btn_snap.on_clicked(self._on_snap_toggle)

        # Show all floors toggle button
        ax_show_all = self.fig.add_axes([pl + pw * 0.52, 0.20, pw * 0.48, 0.04])
        self.btn_show_all = Button(ax_show_all, 'All Floors: OFF')
        self.btn_show_all.on_clicked(self._on_show_all_toggle)

        # Snap distance slider
        ax_snap_dist_lbl = self.fig.add_axes([pl, 0.16, pw, 0.03])
        ax_snap_dist_lbl.axis('off')
        ax_snap_dist_lbl.text(0, 0.5, f"Snap Distance: {self.snap_distance:.1f}m", fontsize=9)
        self.snap_dist_label = ax_snap_dist_lbl

        ax_snap_slider = self.fig.add_axes([pl, 0.13, pw, 0.02])
        self.snap_slider = Slider(
            ax_snap_slider,
            '',
            0.1,
            2.0,
            valinit=self.snap_distance,
            valstep=0.1,
        )
        self.snap_slider.on_changed(self._on_snap_distance_changed)

        # Room list header
        ax_list_hdr = self.fig.add_axes([pl, 0.09, pw, 0.03])
        ax_list_hdr.axis('off')
        ax_list_hdr.text(0, 0.5, "SAVED ROOMS (right-click to select):", fontsize=9, fontweight='bold')

        # Room list area
        self.ax_list = self.fig.add_axes([pl, 0.02, pw, 0.07])
        self.ax_list.axis('off')

    # -------------------------------------------------------------------------
    # Section rendering
    # -------------------------------------------------------------------------

    def _render_section(self):
        """Render the mesh cross-section at the current Z height."""
        self.ax.clear()

        segments, vertices = self.slicer.slice_at_z(self.current_z)
        self.current_vertices = vertices

        # Rebuild KD-tree for snapping whenever vertices change
        self._vertex_kdtree = None  # Will be lazily rebuilt on next snap

        if segments:
            line_data = [[(s[0], s[1]), (s[2], s[3])] for s in segments]
            lc = LineCollection(line_data, colors='black', linewidths=0.5)
            self.ax.add_collection(lc)

        # Draw vertices as points if snap is enabled (with downsampling for performance)
        if self.snap_enabled and len(vertices) > 0:
            if len(vertices) <= self.max_vertex_display:
                # Show all vertices
                self.ax.plot(vertices[:, 0], vertices[:, 1], 'o',
                            markersize=1.5, color='blue', alpha=0.4, zorder=1)
            else:
                # Downsample vertices for display only (snapping still uses all vertices)
                step = len(vertices) // self.max_vertex_display
                self.ax.plot(vertices[::step, 0], vertices[::step, 1], 'o',
                            markersize=1.5, color='blue', alpha=0.3, zorder=1)
                # Add small notice in corner
                self.ax.text(0.02, 0.02, f'Showing {len(vertices[::step]):,}/{len(vertices):,} vertices',
                           transform=self.ax.transAxes, fontsize=7, color='gray',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))

        # Redraw saved room polygons
        self.room_patches.clear()
        self.room_labels.clear()
        for i, room in enumerate(self.rooms):
            is_current_floor = abs(room['z_height'] - self.current_z) < 0.5

            if self.show_all_floors:
                # Show all rooms, but distinguish current floor vs others
                self._draw_room_polygon(room, i, is_current_floor=is_current_floor)
            elif is_current_floor:
                # Only show rooms at current Z level
                self._draw_room_polygon(room, i, is_current_floor=True)

        self.ax.set_aspect('equal')
        self.ax.autoscale()
        self.ax.set_xlabel('X (m)')
        self.ax.set_ylabel('Y (m)')

        # Build title with floor level info if applicable
        title = f'Floor Plan Section at Z = {self.current_z:.1f}m'
        if self.current_floor_idx is not None and self.slicer.floor_levels:
            title = f'Floor Level {self.current_floor_idx} (Z = {self.current_z:.1f}m)'

        self.ax.set_title(title, fontsize=12, fontweight='bold')
        self.ax.grid(True, alpha=0.3)
        self.fig.canvas.draw_idle()

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

        # Color scheme based on floor level and selection state
        if is_selected:
            edge_color = 'yellow'
            face_color = 'yellow'
            alpha = 0.35
            lw = 4
            label_bg = 'orange'
        elif is_current_floor:
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
        self._render_section()
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
        """Handle scroll wheel for zooming."""
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
        self.fig.canvas.draw_idle()

    def _on_click_with_snap(self, event):
        """Handle mouse clicks with snapping for left-click, room selection for right-click."""
        if event.inaxes != self.ax:
            return

        # Right-click: select room
        if event.button == 3:
            self._select_room_at(event.xdata, event.ydata)
            return

        # Left-click: apply snapping before selector sees the event
        if event.button == 1 and event.xdata is not None and event.ydata is not None:
            snapped_x, snapped_y = self._snap_to_vertex(event.xdata, event.ydata)
            # Modify event in-place so selector sees snapped coordinates
            event.xdata = snapped_x
            event.ydata = snapped_y

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
        self.type_textbox.set_val(room.get('room_type', ''))
        self._update_status(f"Selected: {room.get('name', 'unnamed')}", 'orange')
        self._render_section()  # Refresh to highlight

    def _deselect_room(self):
        """Deselect any selected room."""
        if self.selected_room_idx is not None:
            self.selected_room_idx = None
            self.name_textbox.set_val('')
            self.type_textbox.set_val('')
            self._update_status("Ready to draw", 'blue')
            self._update_room_list()
            self.fig.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # Button callbacks
    # -------------------------------------------------------------------------

    def _on_save_click(self, event):
        """Save the current polygon as a room, or update the selected room."""
        if self.selected_room_idx is not None:
            self._update_selected_room()
        else:
            self._save_current_room()

    def _save_current_room(self):
        """Save the currently drawn polygon as a new room."""
        if len(self.current_polygon_vertices) < 3:
            self._update_status("No polygon to save - draw one first", 'red')
            return

        name = self.name_textbox.text.strip()
        if not name:
            name = f"ROOM_{len(self.rooms) + 1:03d}"

        room_type = self.type_textbox.text.strip()

        room = {
            'name': name,
            'room_type': room_type,
            'vertices': [[float(x), float(y)] for x, y in self.current_polygon_vertices],
            'z_height': self.current_z,
        }
        self.rooms.append(room)

        # Reset drawing state
        self.current_polygon_vertices = []
        self.selector.clear()
        self.name_textbox.set_val('')
        self.type_textbox.set_val('')

        self._update_status(f"Saved '{name}' ({len(self.rooms)} total)", 'green')
        self._update_room_list()
        self._update_floor_level_list()
        self._render_section()
        # Re-create selector after render
        self._create_polygon_selector()
        print(f"Saved room '{name}' at Z={self.current_z:.1f}m ({len(self.rooms)} total)")

    def _update_selected_room(self):
        """Update the name/type of the selected room."""
        if self.selected_room_idx is None:
            return
        idx = self.selected_room_idx
        new_name = self.name_textbox.text.strip() or self.rooms[idx]['name']
        new_type = self.type_textbox.text.strip()
        self.rooms[idx]['name'] = new_name
        self.rooms[idx]['room_type'] = new_type
        self._update_status(f"Updated '{new_name}'", 'green')
        self._update_room_list()
        self._render_section()

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
        self._render_section()
        print(f"Deleted room '{name}'")

    def _on_reset_zoom_click(self, event):
        """Reset zoom to the full section extent."""
        if self.original_xlim and self.original_ylim:
            self.ax.set_xlim(self.original_xlim)
            self.ax.set_ylim(self.original_ylim)
            self.fig.canvas.draw_idle()

    def _on_export_aoi_click(self, event):
        """Export all rooms as .aoi files."""
        self.export_aoi_files()

    def _on_export_csv_click(self, event):
        """Export all rooms as a room boundaries CSV."""
        self.export_room_boundaries_csv()

    def _on_snap_toggle(self, event):
        """Toggle vertex snapping on/off."""
        self.snap_enabled = not self.snap_enabled
        self.btn_snap.label.set_text('Snap: ON' if self.snap_enabled else 'Snap: OFF')
        status = "ON" if self.snap_enabled else "OFF"
        self._update_status(f"Vertex snapping: {status}", 'blue')
        self._render_section()

    def _on_snap_distance_changed(self, val):
        """Handle snap distance slider changes."""
        self.snap_distance = round(val, 1)
        self.snap_dist_label.texts[0].set_text(f"Snap Distance: {self.snap_distance:.1f}m")
        self.fig.canvas.draw_idle()

    def _on_show_all_toggle(self, event):
        """Toggle showing rooms from all floors vs current floor only."""
        self.show_all_floors = not self.show_all_floors
        self.btn_show_all.label.set_text('All Floors: ON' if self.show_all_floors else 'All Floors: OFF')
        status = "all floors" if self.show_all_floors else "current floor only"
        self._update_status(f"Showing rooms from {status}", 'blue')
        self._render_section()
        # Re-create selector after render
        self._create_polygon_selector()

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
        """Refresh the saved rooms list in the side panel."""
        self.ax_list.clear()
        self.ax_list.axis('off')

        if not self.rooms:
            self.ax_list.text(0, 0.95, "(no rooms saved)", fontsize=8, style='italic', color='gray')
        else:
            max_display = 6
            for i, room in enumerate(self.rooms[:max_display]):
                y_pos = 0.95 - (i * 0.16)
                name = room.get('name', 'unnamed')
                z = room.get('z_height', 0)
                text = f"{i + 1}. {name} (Z={z:.1f}m)"
                if len(text) > 30:
                    text = text[:27] + "..."
                is_sel = (i == self.selected_room_idx)
                self.ax_list.text(
                    0, y_pos, text, fontsize=7,
                    fontweight='bold' if is_sel else 'normal',
                    color='orange' if is_sel else 'black',
                )
            if len(self.rooms) > max_display:
                self.ax_list.text(0, 0.02, f"... and {len(self.rooms) - max_display} more",
                                 fontsize=7, style='italic')

        self.fig.canvas.draw_idle()

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

    def export_aoi_files(self, output_dir: Optional[Path] = None):
        """Export room boundaries as .aoi files (IESVE-compatible format).

        Each room is written to a separate file in the output directory.

        Args:
            output_dir: Directory for .aoi files. Defaults to config.AOI_DIR.
        """
        if not self.rooms:
            self._update_status("No rooms to export", 'red')
            return

        output_dir = Path(output_dir) if output_dir else config.AOI_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        for room in self.rooms:
            name = room['name']
            room_type = room.get('room_type', '')
            verts = room['vertices']
            filepath = output_dir / f"{name}.aoi"

            with open(filepath, 'w') as f:
                f.write("AoI Points File : X,Y positions\n")
                f.write(f"ZONE {name} {room_type}\n")
                f.write(f"POINTS {len(verts)}\n")
                for x, y in verts:
                    f.write(f"{x:.4f} {y:.4f}\n")

        self._update_status(f"Exported {len(self.rooms)} .aoi files", 'green')
        print(f"Exported {len(self.rooms)} AOI files to {output_dir}")

    def export_room_boundaries_csv(self, output_path: Optional[Path] = None):
        """Export room boundaries as CSV compatible with ViewGenerator.

        The CSV uses the headerless format with coordinate strings in
        millimetres: apartment_no, room, X_mm Y_mm Z_mm, ...

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

            row = [room['name'], room.get('room_type', '')] + coord_strings
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
    # Session persistence
    # -------------------------------------------------------------------------

    def _save_session(self):
        """Save all room boundaries to JSON for later editing."""
        if not self.rooms:
            self._update_status("No rooms to save", 'red')
            return

        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'obj_paths': [str(p) for p in self.obj_paths],
            'rooms': self.rooms,
        }
        with open(self.session_path, 'w') as f:
            json.dump(data, f, indent=2)

        self._update_status(f"Session saved ({len(self.rooms)} rooms)", 'green')
        print(f"Session saved to {self.session_path}")

    def _load_session(self):
        """Load previously saved room boundaries from JSON."""
        if not self.session_path.exists():
            return

        with open(self.session_path, 'r') as f:
            data = json.load(f)

        self.rooms = data.get('rooms', [])
        self._update_status(f"Loaded {len(self.rooms)} rooms from session", 'green')
        if hasattr(self, 'ax'):
            self._render_section()
        print(f"Loaded {len(self.rooms)} rooms from {self.session_path}")
