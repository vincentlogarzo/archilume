# Archilume imports
from archilume.utils import select_files, display_obj

# Standard library imports
from pathlib import Path

# Third-party imports

   # Locate the room boundaries CSV file
obj_paths = [
    Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj",
    Path(__file__).parent.parent / "inputs" / "87cowles_site.obj"
    ]

if obj_paths:
    display_obj(obj_paths)
else:
    print("No files selected.")