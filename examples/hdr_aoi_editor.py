"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

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
    Right-click   Select existing room
    Scroll        Zoom centred on cursor
    s             Save room / confirm edit
    d             Delete selected room
    e             Toggle Edit Mode
    a             Toggle all-HDR display
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
from archilume import config

if __name__ == "__main__":
    editor = HdrAoiEditor(
        image_dir        = config.IMAGE_DIR,
        initial_csv_path = config.AOI_DIR / "iesve_room_data_boundaries.csv"
    )
    editor.launch()

    # TODO: reshuffle all the buttons to allow the image to be largers and minimise hite space between all the buttons.
    #TODO ensure that intial csv aoi are presented on load, they do not show up.
    # TODO: and allow for Green dot red dot viewer based on results after markup, allow another toggle, and then allow export of the green dot, or packaging of results into zip file with excel.
    # TODO: when drawing a subroom, better functionaly to detect parent room so that you dont have to click none placeholder in the parent room input box, and better functionality to snap a point to an existing vertex edge, subrooms are really only a divide or break down o fthe main apartment. 
    #Remove the HDR file, it should not be loaded, it is slowing down the interface, determine what are the UI speed limits, the lag on the cursor etc. 

    


