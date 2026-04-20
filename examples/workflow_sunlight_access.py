"""
Archilume Example: Sunlight Exposure Analysis
=============================================================

Renders sun-only HDR + PNG frames for each timestep in the requested time
range. The PNGs are what the archilume-app reads back as the sunlight
time-series movie. AOI/WPD extraction lives outside this workflow.
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
        timestep_min        = 15,
        ffl_offset_mm       = 1000,
        grid_resolution_mm  = 15,
        project             = project,
        aoi_inputs_dir      = paths.aoi_inputs_dir,
        obj_paths           = [
                                paths.inputs_dir / "87Cowles_BLD_withWindows.obj",
                                paths.inputs_dir / "87cowles_site_decimated.obj",
                              ],
    )

if __name__ == "__main__":
    run_sunlight_analysis()
