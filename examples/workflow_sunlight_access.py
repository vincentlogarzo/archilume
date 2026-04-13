"""
Archilume Example: Sunlight Exposure Analysis (Simplified)
=============================================================

This example demonstrates how to configure and run a sunlight
access workflow to determine the quantity of sunlight on
horizontal plane over a single day across many rooms in a
building. The core simulation logic is handled by the
`SunlightAccessWorkflow` class in sunlight_access_workflow.py

Workflow Overview:
1. Load 3D geometry (OBJ/MTL).
2. Generate solar conditions for a specific date/latitude.
3. Render time-series floor plans.
4. Export results to Excel and animated APNG/GIF.
"""

# fmt: off
# autopep8: off

from archilume import config
from archilume.workflows import SunlightAccessWorkflow

def run_sunlight_analysis():
    project = "cowles"
    paths = config.get_project_paths(project)

    SunlightAccessWorkflow().run(
        building_latitude   = -37.8134,
        month               = 6,
        day                 = 21,
        start_hour          = 9,
        end_hour            = 15,
        timestep            = 15,
        ffl_offset          = 1.0,
        grid_resolution     = 15,
        rendering_mode      = "gpu",
        rendering_quality   = "fast",
        animation_format    = "apng",
        paths               = paths,
        room_boundaries_csv = paths.aoi_inputs_dir / "87cowles_BLD_room_boundaries.csv",
        obj_paths           = [
                                paths.inputs_dir / "87Cowles_BLD_withWindows.obj",
                                paths.inputs_dir / "87cowles_site_decimated.obj",
                              ],
    )

if __name__ == "__main__":
    run_sunlight_analysis()
