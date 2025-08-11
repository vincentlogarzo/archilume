# Archilume imports
from archilume.utils import select_files, display_obj

obj_paths = select_files(title="Select obj files to view, 1st file should be the main object, others will be used as additional geometry",)

if obj_paths:
    display_obj(obj_paths)
else:
    print("No files selected.")