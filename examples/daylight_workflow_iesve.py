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


"""
T2D or N4D arhcitecture to run on gcloud services and more cost optimised rendering pipelines for large scale daylighting analysis.

for use with WSL distro on Windows machines, alter the .wslconfig file to allow for more RAM and processors. 

    @"
    [wsl2]
    memory=28GB
    processors=20
    "@ | Out-File -FilePath "$env:USERPROFILE\.wslconfig" -Encoding ASCII

"""


def iesve_daylight_parallel_images():

    timer = PhaseTimer()

    with timer("Phase 0: Input scene Octree, Rendering param file (.rdp) and view files (.rdv)...", print_header=True):
        renderer = DaylightRenderer(
                    image_resolution    = 2048, # Image resolution (pixels)
                    octree_path         = config.INPUTS_DIR / "image1.oct", # IESVE BLD + Site + Sky 
                    rendering_quality   = config.INPUTS_DIR / "image1.rdp", # Rendering params
                    views               = [config.INPUTS_DIR / f for f in [
                                                "L01.rdv",                      # 1st floor plan view
                                                "L02.rdv",                      # 2nd floor, add more below
                                                    ]]
                    )
        renderer.daylight_rendering_pipeline()

"""
1. TODO: convert to .vp from .rdv by adding rvu to begging of text file


2.  # 2048/32 = 64, /16 = 128, 2048/8 = 256, 2048/4 = 512, 2048/2 = 1024, 2048/1 = 2048
    RES=$((2048 / 1)) 
    rtpict -n 19 -vf inputs/image1.vp -x $RES -y $RES @inputs/image1.rdp -af outputs/image/image1.amb inputs/image1.oct > outputs/image/image1.hdr

    # allowance for play with ambient accuracy (-aa) will result in a smoother image possibly more effective than (recommend lowest -aa 0.1, lower means that subsequent re-runs at higher resolution take more time) post-processing

    # smooth image use could be effective for final visualisation, but not for compliance results generation. 
    pfilt -x /2 -y /2 outputs/image/image1.hdr | pfilt -x *2 -y *2 > outputs/image/image1_smooth.hdr
    

3. Generate falsecolour images for DF analysis and overlays
    # Raw image
        pcomb -s 0.01 outputs/image/image1.hdr | falsecolor -s 4 -n 10 -l "DF %" -lw 0 > outputs/image/image1_df_false.hdr
        pcomb -s 0.01 outputs/image/image1.hdr | falsecolor -cl -s 2 -n 4 -l "DF%" -lw 0 > outputs/image/image1_df_cntr.hdr

    # Create separate legend, to maintain main hdr image resolution. 
        pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -s 4 -n 10 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_legend.tiff




5. Perform post-processing to extact compliance results from falsecolour images with contours. use 5b and 5c in sunlight_access_workflow as reference. Stamp images and add contours as needed. 
    TODO: modify classes to perform this analysis. 

6. post process images to clean them. 




"""


if __name__ == "__main__":
    iesve_daylight_parallel_images()




