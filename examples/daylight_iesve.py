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
                    image_resolution    = 2048, # Image resolution (pixels)
                    octree_path         = config.INPUTS_DIR / "image10.oct", # IESVE BLD + Site + Sky 
                    rendering_quality   = config.INPUTS_DIR / "rendering_parameters.rdp", # Rendering parames
                    views               = [config.INPUTS_DIR / f for f in [
                                                "L01.rdv",                      # 1st floor plan view
                                                "L02.rdv",                      # 2nd floor, add more below
                                                    ]]
                    )
        renderer.daylight_rendering_pipeline()

"""
1. 
convert to .vp from .rdv by adding rvu to begging of text  file"
"""


"""
2. 
    rtpict -n 64 -t 1 -vf inputs/image1.vp -x 64 -y 64 @inputs/image1.rdp -af outputs/image/image1.amb inputs/image1.oct > outputs/image/image1.hdr

    rtpict -n 64 -t 1 -vf inputs/image1.vp -x 256 -y 256 @inputs/image1.rdp -af outputs/image/image1.amb inputs/image1.oct > outputs/image/image1.hdr

    rtpict -n 64 -t 1 -vf inputs/image1.vp -x 512 -y 512 @inputs/image1.rdp -af outputs/image/image1.amb inputs/image1.oct > outputs/image/image1.hdr


3.   
    pcomb -s 0.01 outputs/image/image1.hdr | falsecolor -s 4 -n 10 -l "DF %" > outputs/image/image1_df_false.hdr
    pcomb -s 0.01 outputs/image/image1.hdr | falsecolor -cl -s 2 -n 4 -l "DF%" > outputs/image/image1_df_cntr.hdr


TODO: update to create legend separately for a user to copy into a report. this way hdr image remain at their actual size and can be pcomb together as needed.

contour plot to be addressed with 0.5% and 1.0% thresholds, with allowance for a list of DF percentages to be show on the on the plot."


# Scale=2, n=4 gives contours at 0.5, 1.0, 1.5, 2.0

    pcomb -s 0.01 outputs/image/image1.hdr | falsecolor -cl -s 2 -n 4 -l "DF%" > outputs/image/image1_df_cntr.hdr




"""


"""
Results post-processing and overlays of results to be added here  ontop of the above falsecolour images with contours, it will show the exact compliance number ased on the current AOI, then a user can use the 
"""

"""
T2D or N4D arhcitecture to run on gcloud services and more cost optimised rendering pipelines for large scale daylighting analysis.
"""


if __name__ == "__main__":
    iesve_daylight_parallel_images()




