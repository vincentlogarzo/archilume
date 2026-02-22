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
    2. Draw apartment boundary to name "U101" to  Save
    3. Select "U101" as parent
    4. Draw sub-rooms (e.g. "BED1" to auto-saved as "U101_BED1")
    5. Repeat for each HDR file / floor
"""

# fmt: off
# autopep8: off

from archilume.hdr_aoi_editor import HdrAoiEditor

# NOTE: daylight_workflow_iesve.py must be run before use of this editor. The workflow generates the HDR/Tiff images and .aoi boundaries this editors depends on.

if __name__ == "__main__":
    editor = HdrAoiEditor()
    editor.launch()

    # FIXME: the living room type tag button does not work, implement a multi click option, to select multiple or change all types to one, then a user can just change living rooms. 
    
    # TODO: add functionality to add points to the polygon, when adding a new point, two should be added side by side, as the user likely needs at least two if adding points.

    # TODO: ensure all results are extract to excel report, every pixel inside each AOI is extracted to excel, and its illuminance and DF% results, therefore a user can calculate it themselves if they wish to validate. They would need only to calcualt the number of pixels above a certain threshodl and divide by the total number etc. 

    # TODO: and allow for Green dot red dot viewer based on results after markup, allow another toggle, and then allow export of the green dot, or packaging of results into zip file with excel.

    # TODO: add in functionality to pull back the compliant area a distance from the polygon lines in to represetn wall thickness if a user wishes to do this.

    # TODO: when drawing a subroom, better functionaly to detect parent room so that you dont have to click none placeholder in the parent room input box, and better functionality to snap a point to an existing vertex edge, subrooms are really only a divide or break down of the main apartment.

    # TODO: Add grouping functionality if a user wishes to see the worst apartments overall contributing to non-comliance of the development. That way these apartments can be considered as a whole. or individual results can be considered. Grouping should occur by multiple clicks of rooms and then click the button called group. 
