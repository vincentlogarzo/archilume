"""
Archilume: Room Boundary Editors

Two editors for different workflow stages:

  OBJ AOI Editor (pre-simulation):
        Draw room boundaries on a 3D OBJ mesh slice.
        Run this before simulation to define rooms.

        Workflow:
            1. Navigate to floor with ↑/↓
            2. Draw apartment boundary → name "U101" → Save
            3. Select "U101" as parent
            4. Draw sub-rooms (e.g. "BED1" → auto-saved as "U101_BED1")
            5. Repeat for each floor/apartment

  HDR AOI Editor (post-simulation):
      Review and refine room boundaries on rendered PNG floor plan images.
      Requires daylight_workflow_iesve.py to have been run successfully.

        Workflow:
            1. Navigate to the desired HDR file with Up/Down
            2. Draw apartment boundary, name "U101", press s to save
            3. Select "U101" as parent
            4. Draw sub-rooms (e.g. "BED1" auto-saved as "U101_BED1")
            5. Repeat for each HDR file / floor
            6. Export and archive results as CSV for analysis and reporting

Set EDITOR = 'obj' or 'hdr' to launch the desired editor.
"""

# fmt: off
# autopep8: off

from archilume.apps.obj_aoi_editor_matplotlib import ObjAoiEditor
from archilume.apps.hdr_aoi_editor_matplotlib import HdrAoiEditor

EDITOR = 'hdr'  # 'obj' or 'hdr'

if __name__ == "__main__":

    if EDITOR == 'obj':
        editor = ObjAoiEditor(
            project             = "527DM", # Optional: sub-folder within inputs/
            obj_path            = "223181_AR_LOFTUS_BTR_stripped_cleaned_decimate.obj",
            initial_csv_path    = "87cowles_BLD_room_boundaries.csv",  # optional: pre-existing room boundaries
            simplify_ratio      = None,    # 0.0-1.0 mesh decimation for large files (None = off)
            detect_floors       = True,    # False to skip auto floor detection on very large meshes
            max_vertex_display  = 5000,    # downsample snap-point display above this count
        )

    elif EDITOR == 'hdr':
        editor = HdrAoiEditor(
            project  = "527DP",             # Optional: sub-folder within inputs/
            pdf_path = "plans/SK01.09-PLAN - TYPICAL(P1).pdf",  # optional: auto-load PDF overlay
        )

    else:
        raise ValueError(f"EDITOR must be 'obj' or 'hdr', got {EDITOR!r}")

    editor.launch()
