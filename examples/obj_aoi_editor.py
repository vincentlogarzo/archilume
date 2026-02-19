"""
Archilume: Interactive Room Boundary Editor (V2 - Hierarchical)

Draw apartment and sub-room boundaries on a 2D floor plan sliced from a 3D OBJ.
JSON and CSV are saved automatically alongside the OBJ on every save/delete.

Naming convention:
    U101          apartment boundary
    U101_BED1     sub-room (auto-prefixed when parent is selected)

Controls:
    ↑/↓           Navigate floor levels
    Left-click    Place vertex (draw) or drag vertex (edit mode)
    Right-click   Select existing room
    Scroll        Zoom centred on cursor
    s             Save room / confirm edit
    d             Delete selected room
    e             Toggle Edit Mode
    v             Cycle views: Plan → Elev X → Elev Y
    a             Toggle all-floors display
    r             Reset zoom
    q             Quit

Workflow:
    1. Navigate to floor with ↑/↓
    2. Draw apartment boundary → name "U101" → Save
    3. Select "U101" as parent
    4. Draw sub-rooms (e.g. "BED1" → auto-saved as "U101_BED1")
    5. Repeat for each floor/apartment
"""

# fmt: off
# autopep8: off

from archilume.obj_aoi_editor import ObjAoiEditor
from archilume import config

# initial_csv_path: optional CSV with pre-existing room boundaries (loaded if no session exists)
# simplify_ratio: 0.0-1.0 mesh decimation for large files (None = off)
# detect_floors: set False to skip auto floor detection on very large meshes
# max_vertex_display: downsample snap-point display above this count


if __name__ == "__main__":
    editor = ObjAoiEditor(
        obj_path            = config.INPUTS_DIR / "cowles" / "87Cowles_BLD_withWindows.obj",
        initial_csv_path    = config.INPUTS_DIR / "cowles" /"87cowles_BLD_room_boundaries.csv",
        simplify_ratio      = None,
        detect_floors       = True,
        max_vertex_display  = 5000,
    )
    editor.launch()

# TODO: add option to copy boundaries up a level if levels are identical. add in flag to have a user double accept that their selection to copy up will remove any existing boundaries on the target level. add in option to copy down a level as well. add in option to copy across to another level (e.g. copy from 1st floor to 2nd floor if they are identical). add in option to mirror boundaries across a plane (e.g. mirror left half of floor plan to right half if they are symmetrical).

