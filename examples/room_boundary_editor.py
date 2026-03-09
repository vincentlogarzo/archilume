"""
Archilume: Room Boundary Editors

AOI = Area of interest

Two editors for different workflow stages:

  OBJ AOI Editor (pre-simulation):
        Draw room boundaries on a 3D OBJ mesh slice.
        Run this before simulation to define rooms to be analyse.

        Workflow:
            1. Launch editor
            2. Navigate floors using ↑/↓ arrow keys 
            3. Draw apartment boundary → name "U101" → Save
            4. Select "U101" as parent, and Draw sub-rooms 
                (e.g. "BED1" → auto-saved as "U101_BED1")
            5. Repeat for each floor/apartment

  HDR AOI Editor (post-simulation):
      Review and refine room boundaries on rendered PNG floor plan images.
      Requires daylight_workflow_iesve.py to have been run successfully.

        Workflow:
            1. Launch editor
            2. Navigate floors using ↑/↓ arrow keys
            3. Adjust overlaid PDF architectural plans scale and position 
            4. Draw new apartment boundary, or divide existing boundary, press s to save
            5. Export and archive results as CSV for analysis and reporting

    IESVE editor
        This is a no simulation editor. Where the user wishes to do boundary markup on 
        existing radiance simulated .pic illuminance images. 

Set EDITOR = 'obj' or 'hdr' to launch the desired editor.
"""

# fmt: off
# autopep8: off

from archilume.apps.obj_aoi_editor_matplotlib import ObjAoiEditor
from archilume.apps.hdr_aoi_editor_matplotlib import HdrAoiEditor
from pathlib import Path

EDITOR = 'hdr'  # 'obj' or 'hdr' or 'iesve'

if __name__ == "__main__":

    if EDITOR == 'obj':
        editor = ObjAoiEditor(
            project             = "527DM", # Project name under projects/ (e.g. projects/527DM/inputs/)
            obj_path            = "223181_AR_LOFTUS_BTR_stripped_cleaned_decimate.obj",
            initial_csv_path    = "87cowles_BLD_room_boundaries.csv",  # optional: pre-existing boundaries
            simplify_ratio      = None,    # 0.0-1.0 mesh decimation for large files (None = off)
            detect_floors       = True,    # False to skip auto floor detection on very large meshes
            max_vertex_display  = 5000,    # downsample snap-point display above this count
        )

    elif EDITOR == 'hdr':
        editor = HdrAoiEditor(
            project     = "527DP", # Project name under projects/ (e.g. projects/527DP/inputs/)
            pdf_path    = "plans/SK01.09-PLAN - TYPICAL(P1).pdf",  # optional: PDF from projects/527DP/inputs/plans/
        )

    elif EDITOR == 'iesve':
        editor = HdrAoiEditor(
            project          = "1523A",                        # Project name under projects/ (e.g. projects/1523A/inputs/)
            pdf_path         = "plans/1523A_IFC_Plans.pdf",    # optional: PDF from projects/1523A/inputs/plans/
            image_dir        = "pic",                          # resolves to projects/1523A/inputs/pic/
            iesve_room_data  = "aoi/iesve_room_data.csv",      # optional: seed rooms from IESVE CSV (first launch only)
        )

    else:
        raise ValueError(f"EDITOR must be 'obj' or 'hdr' or 'iesve', got {EDITOR!r}")

    editor.launch()
