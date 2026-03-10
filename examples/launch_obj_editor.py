"""Launch the OBJ-based Room Boundary Editor (Hierarchical)."""

from archilume.apps.obj_aoi_editor_matplotlib import launch

if __name__ == "__main__":
    # If no project is provided, it will auto-discover the last used or only available project.
    launch()
