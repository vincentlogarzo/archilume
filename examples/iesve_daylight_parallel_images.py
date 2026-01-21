"""
Archilume Example: Sunlight Exposure Analysis
======================================================================================================

This example demonstrates a complete sunlight analysis workflow using Archilume
to evaluate daylight conditions during the winter solstice (June 21st in the
Southern Hemisphere).

The analysis workflow includes:
1. Converting building and site OBJ files into a computational octree structure
2. Generating sunny sky files for the winter solstice at specified time intervals
3. Creating plan view files from room boundary data (CSV from Revit)
4. Executing the sunlight rendering pipeline for all time steps and views
5. Post-processing rendered HDR images to final compliance results.

Location:           Melbourne, Australia (latitude: -37.8136°)
Date:               June 21, 2024 (Winter Solstice)
Analysis Period:    9:00 AM - 3:00 PM at 10-minute intervals
Output:             HDR images, view files, sky files, and coordinate mappings
"""

# fmt: off
# autopep8: off

# Archilume imports
from archilume import (
    SkyGenerator,
    ViewGenerator,
    Objs2Octree,
    RenderingPipelines,
    Tiff2Animation,
    Hdr2Wpd,
    smart_cleanup,
    utils,
    PhaseTimer,
    config
)

# Standard library imports

# Third-party imports



def iesve_daylight_parallel_images():

    timer = PhaseTimer()

    with timer("Phase 0: Input scene Octree, Rendering param file (.rdp) and view files (.rdv)...", print_header=True):
        renderer = DaylightRenderer(
                    octree_path         = config.INPUTS_DIR / "image10.oct",    # Assessed IESVE building + surroundings + sky,
                    views               = [config.INPUTS_DIR / f for f in [
                                                "L01.rdv",                      # 1st floor plan view
                                                "L02.rdv",                      # 2nd floor plan view, add further views to this list
                                                "L03.rdv",                      # 3rd floor plan view
                                                "L04.rdv",                      # 4th floor plan view
                                                "L05.rdv",
                                                    ]],
                    image_resolution    = 2048,
                    rendering_quality   = config.INPUTS_DIR / "rendering_parameters.rdp"     # Rendering parameters file
                    )
        renderer.sunlight_rendering_pipeline()

"rtpict -n 56 -t 1 -vf inputs/image10.vp -x 512 -y 512 @inputs/image10.rdp -af outputs/image/image10_high.amb inputs/image10.oct > outputs/image/image10_high.hdr"


if __name__ == "__main__":
    iesve_daylight_parallel_images()




