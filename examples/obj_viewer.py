# Archilume imports
from archilume.utils import select_files, display_obj

# Standard library imports

# Third-party imports


obj_paths = select_files(title="Select one ore more obj files to view, 1st file should be the main object, subsequent files will be used as additional geometry")

if obj_paths:
    display_obj(obj_paths)
else:
    print("No files selected.")