"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

NOTE: daylight_workflow_iesve.py must be run successfully before launching
this interactive results viewer. It generates the HDR/TIFF images and .aoi
boundary files that this editor depends on.

Draw apartment and sub-room boundaries on top of HDR or associated TIFF
rendered floor plan images. JSON and CSV are saved automatically to the
image_dir on every save/delete.

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

from archilume.hdr_aoi_editor import HdrAoiEditor

if __name__ == "__main__":
    editor = HdrAoiEditor()
    editor.launch()

    # TODO: and allow for Green dot red dot viewer based on results after markup, allow another toggle, and then allow export of the green dot, or packaging of results into zip file with excel.
    # TODO: add in functionality to pull back the compliant area a distance from the polygon lines in to represetn wall thickness if a user wishes to do this. 
    # TODO: when drawing a subroom, better functionaly to detect parent room so that you dont have to click none placeholder in the parent room input box, and better functionality to snap a point to an existing vertex edge, subrooms are really only a divide or break down o fthe main apartment.
    #Remove the HDR file, it should not be loaded, it is slowing down the interface, determine what are the UI speed limits, the lag on the cursor etc.
    # TODO: Add grouping functionality if a user wishes to see the worst apartments overall contributing to non-comliance of the development. That way these apartments can be considered as a whole. or individual results can be considered. 
