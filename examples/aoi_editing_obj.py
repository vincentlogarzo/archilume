"""
Archilume Example: Interactive Room Boundary Editor
======================================================================================================

Launch an interactive tool for drawing room boundaries on a 2D floor plan
section extracted from a 3D OBJ model. The editor slices the mesh at a
user-controlled Z height and provides a matplotlib-based polygon drawing
tool. Drawn boundaries can be exported as .aoi files or room boundaries CSV
for the ViewGenerator pipeline.

Usage:
    python examples/aoi_editing_obj.py

Controls:
    Plan/Elev btns  Switch between Plan and Elevation views
    Edit Mode btn   Enable editing of existing room boundaries
    Z slider        Adjust the horizontal section height (Plan view)
    ↑/↓ arrows      Navigate to next/previous detected floor level
    Left-click      Place polygon vertices (Draw) OR drag vertex (Edit mode)
    Right-click     Select an existing room polygon (Plan view only)
    Scroll          Zoom in/out centred on cursor
    Snap button     Toggle vertex snapping on/off (works in Edit mode too)
    All Floors btn  Show rooms from all floors (grayed out) or current floor only
    Snap slider     Adjust snap distance threshold (0.1-2.0m)
    e               Toggle Edit Mode (modify existing boundaries)
    v               Cycle through views (Plan → Elev X → Elev Y → Plan)
    a               Toggle All Floors view
    s               Save current polygon/edited boundary
    S               Save session to JSON
    d               Delete selected room
    r               Reset zoom
    q               Quit

Features:
    - Elevation Views: View model and rooms from side (X and Y elevations)
    - Vertex snapping: Clicks automatically snap to nearest mesh vertex (KD-tree optimized)
    - Blue dots show available snap points when enabled
    - Adjustable snap distance for fine control
    - Automatic floor level detection with pre-caching
    - Session persistence: Auto-loads previous boundaries from JSON
    - Multi-floor visualization: View and edit rooms across all floors
    - Smart room selection: Right-click jumps to room's floor automatically
    - Vertex editing: Edit existing room boundaries by dragging vertices
    - View-aware editing: Boundary creation restricted to Plan view only
    - Hover detection: Visual feedback when hovering over rooms and vertices
    - Mesh simplification for large OBJ files
    - Slice caching for instant navigation

Performance Optimizations (NEW):
    - Set simplify_ratio (e.g., 0.5) to reduce mesh complexity for large models
    - Set detect_floors=False to skip floor detection for very large meshes
    - Vertex display downsampling for slices with >5000 vertices
    - KD-tree spatial indexing for O(log n) snap performance
    - LRU slice caching reduces re-computation
"""

# fmt: off
# autopep8: off

from archilume.obj_boundary_editor import BoundaryEditor
from archilume import config


# --- Configuration ---
obj_paths = [
    config.INPUTS_DIR / "cowles" / "87Cowles_BLD_withWindows.obj",
    # config.INPUTS_DIR / "22041_AR_T01_v2.obj",
]

# --- Performance Options for Large Meshes ---
# Uncomment and adjust these parameters if your OBJ file is very large (>100K faces)

# simplify_ratio: Reduce mesh complexity (0.0-1.0)
#   - 0.5 = reduce to 50% of original cells
#   - 0.3 = reduce to 30% of original cells
#   - None = no simplification (default)
simplify_ratio = 0.3 

# detect_floors: Auto-detect floor levels on load
#   - True = automatically detect floors (default, recommended)
#   - False = skip detection for faster loading of very large meshes
detect_floors = True

# max_vertex_display: Maximum vertices to render (downsample if exceeded)
#   - 5000 = default threshold (good balance)
#   - 10000 = show more detail but may slow rendering
#   - 2000 = faster rendering for dense slices
max_vertex_display = 5000


if __name__ == "__main__":
    # Standard usage (optimized with caching and KD-tree snapping)
    editor = BoundaryEditor(
        obj_paths=obj_paths,
        simplify_ratio=simplify_ratio,
        detect_floors=detect_floors,
        max_vertex_display=max_vertex_display,
    )
    editor.launch()

    # Example for very large meshes (uncomment to use):
    # editor = BoundaryEditor(
    #     obj_paths=obj_paths,
    #     simplify_ratio=0.5,         # Reduce mesh to 50%
    #     detect_floors=False,         # Skip floor detection
    #     max_vertex_display=2000,     # Downsample display aggressively
    # )
    # editor.launch()

# NOTE: For extremely large buildings, the mesh simplification (simplify_ratio)
# is now the recommended approach instead of splitting OBJ files manually. 
