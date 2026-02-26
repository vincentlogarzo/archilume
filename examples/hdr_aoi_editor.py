"""
Archilume: Interactive Room Boundary Editor for HDR/TIFF Floor Plan Images

See archilume/hdr_aoi_editor.py for full documentation.
NOTE: daylight_workflow_iesve.py must be run before use of this editor.
"""

from archilume.hdr_aoi_editor import HdrAoiEditor

if __name__ == "__main__":
    editor = HdrAoiEditor()
    editor.launch()

    # TODO: there should be building level and floor plate on screen level results shown in th editor that confirm to the BESS daylight factor requirments. For future. Implementation.

    # TODO: update vertex e 
    # TODO: fix functionality for control z undo actiosn. After creation of romdivision i cannot under this.  
    #TODO: wrt room divisor tool, the parent room boundary should always remain the same size, currenty thereis confusion , when a divisison is made the sub-room cannot be deleted to restor the original room boundary.
    #FIXME, multi select of spaces doesnt highlight all the selected rooms at one, multi selec also isnt currenyly available to left click on the rooms themsevles, it is only available in the rooms list at the top.

    #TODO: all hot key functions on the keyboard should have a button in the UI that also performs this function, and the button should also show the hot key in brackets next to the name of the function. This is to make it more intuitive for users to learn the hot keys, and to make it easier for users who prefer to use the mouse to access these functions. buttons like dividor should be greyed out unless in edit mode, and there should be tooltips giving info about this functionality. 

    # TODO add in functionality to coppy room boundaties up a level (Or onlt the current selected room boundaries to copy up), If they appear to be identical, then draw new boundaries make some edits to one level, and then copy up to next level, the original AOI names should be retained unless it is a new subboundary. Check and do the same the next level up. This functionality should be able to be undone, and restoration of original aois by use of the room name.  should also be allowable on a room-by-room basis, or on a whole floor basis. This is to allow for quick drawing of room boundaries on multiple levels of a building, when the floor plates are similar.

    # TODO: and allow for Green dot red dot viewer based on results after markup, allow another toggle, and then allow export of the green dot.

    # TODO: add in functionality to pull back the compliant area a distance from the polygon lines in to represetn wall thickness if a user wishes to do this.

    # TODO: add in post processing into cnt and df false into the viewer, it should generate ad destroy these upon each open and close, herefore only the hdr files are of interest.

    # TODO: allow deletion of a room boundaries in the UI, it should then wipe this from the JSON, and then upon reopn of the UI it should reinstate from the original aoi file. Or this feature should be a buttin hte ui to reinstant an AOI from its source or a group of selected AOIs.

    # TODO: adjust room name and results placement on screen to be at least a certain distance from the aoi boundary. The centroid is working in most cases, but in some cases the centroid is outside of the room boundary, and then the name and results are not visible. It could be something like the room boundary line that has the highest daylight factor, as these results are closest to the largest window. 

    # TODO: enforce a restriction on the sub-rooms, there should only be one partent room, there should never be a parent room of a parent room. Only a 2 tier heirarchy. 

    # TODO: Add grouping/split of grouped rooms function functionality if a user wishes to see the worst apartments overall contributing to non-comliance of the development. That way these apartments can be considered as a whole. or individual results can be considered. Grouping should occur by multiple clicks of rooms and then click the button called group.
    
    # TODO: could use the aoi editor to enforce grouping of room by level, so that multuple views are created based on this grouping. This could work for strangely shaped buildings, or very large floors plates with internal sqaute courtyard like buildings. The user would then need to take the resulting, aoi files and feed them back into the inputs of the workflow.