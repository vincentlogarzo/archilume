# Archilume imports
from archilume.utils import display_obj

# Standard library imports
from pathlib import Path

# Third-party imports

"""

objview "C:/Projects/archilume/inputs/22041_AR_T01_BLD_hiddenLine_cleaned.obj"

Usage: robjutil [options] [input.obj ..]
Available options:
        +/-r                    # Radiance scene output on/off
        +/-v                    # on/off verbosity (progress reports)
        +/-g name               # save/delete group
        +/-m name               # save/delete faces with material
        +/-t                    # keep/remove texture coordinates
        +/-n                    # keep/remove vertex normals
        -c epsilon              # coalesce vertices within epsilon
        +T                      # turn all faces into triangles
        -x 'xf spec'            # apply the quoted transform

    
"""


obj_paths = [
    Path(__file__).parent.parent / "inputs" / "22041_AR_T01_BLD_hiddenLine_cleaned.obj",
    # Path(__file__).parent.parent / "inputs" / "87cowles_site.obj"
    ]

# MTL file for material definitions (glass will be colored ocean blue)
mtl_path = Path(__file__).parent.parent / "inputs" / "22041_AR_T01_BLD_hiddenLine.mtl"

# Optional: customize glass color (default is ocean blue [0.0, 0.4, 0.7])
# glass_color = [0.0, 0.5, 0.8]  # Lighter blue
# glass_color = [0.0, 0.3, 0.6]  # Darker blue

if obj_paths:
    display_obj(obj_paths, mtl_path=mtl_path)
else:
    print("No files selected.")