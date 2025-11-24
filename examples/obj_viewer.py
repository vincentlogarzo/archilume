# Archilume imports
from archilume.utils import display_obj

# Standard library imports
from pathlib import Path

# Third-party imports


obj_paths = [
    Path(__file__).parent.parent / "inputs" / "22041_AR_T01_BLD_hiddenLine_simplified.obj",
    Path(__file__).parent.parent / "inputs" / "87cowles_site.obj"
    ]

if obj_paths:
    display_obj(obj_paths)
else:
    print("No files selected.")