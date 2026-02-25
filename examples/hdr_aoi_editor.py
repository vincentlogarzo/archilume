"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

NOTE: daylight_workflow_iesve.py must be run before use of this editor. The workflow generates the HDR/Tiff images and .aoi boundaries this editors depends on.

Draw apartment and sub-room boundaries on top of HDR or associated TIFF
rendered floor plan images. JSON and CSV are saved automatically to the
image_dir on every save/delete.

Naming convention:
    U101          apartment boundary
    U101_BED1     sub-room (auto-prefixed when parent is selected)

Controls:
    Up/Dowb       Navigate HDR files
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
    Ctrl+click    Multi-select rooms in list (bulk type tagging)
    Ctrl+A        Select all rooms on current HDR
    r             Reset zoom
    q             Quit

Workflow:
    1. Navigate to the desired HDR file with ↑/↓
    2. Draw apartment boundary to name "U101" to  Save
    3. Select "U101" as parent
    4. Draw sub-rooms (e.g. "BED1" to auto-saved as "U101_BED1")
    5. Repeat for each HDR file / floor
    6. Export and archive results as CSV for analysis and reporting
"""

# fmt: off
# autopep8: off

from archilume.hdr_aoi_editor import HdrAoiEditor

# NOTE: daylight_workflow_iesve.py must be run before use of this editor. The workflow generates the HDR/Tiff images and .aoi boundaries this editors depends on.

if __name__ == "__main__":
    editor = HdrAoiEditor()
    editor.launch()

    # TODO: there should be building level and floor plate on screen level results shown in th editor that confirm to the BESS daylight factor requirments

    #TODO: add a room divsior tool, to split room boundaries with ortho lines only. room divsions must become sub-room of the parent room without a room type label.

    # TODO: allow deletion of a room boundaries in the UI, it should then wipe this from the JSON, and then upon reopn of the UI it should reinstate from the original aoi file. Or this feature should be a buttin hte ui to reinstant an AOI from its source or a group of selected AOIs. 

    #TODO: adjust room nme and results placement on screen to be at least a certain distance from the aoi boundary. The centroid is working in most cases, but in some cases the centroid is outside of the room boundary, and then the name and results are not visible.

    # TODO: add functionality to add points to the polygon, when adding a new point, two should be added side by side, as the user likely needs at least two if adding points. ortho point movement should be retained unless it is turned off.

    # TODO: and allow for Green dot red dot viewer based on results after markup, allow another toggle, and then allow export of the green dot

    # TODO: add in functionality to pull back the compliant area a distance from the polygon lines in to represetn wall thickness if a user wishes to do this.

    #TODO: enforce a restriction on the sub-rooms, there should only be one partent room, there should never be a parent room of a parent room. Only a 2 tier heirarchy. 


    # TODO: Add grouping functionality if a user wishes to see the worst apartments overall contributing to non-comliance of the development. That way these apartments can be considered as a whole. or individual results can be considered. Grouping should occur by multiple clicks of rooms and then click the button called group. 
