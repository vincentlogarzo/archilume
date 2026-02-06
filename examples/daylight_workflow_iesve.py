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
    SunlightRenderer,
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
arhcitecture to run on gcloud services and more cost optimised rendering pipelines for large scale daylighting analysis.
    T2D  
    N4D 
    E2 (google cloud high compute 32 vCPU + 100Gb storage VM cost=$2.5 to simulate 1 floor plate, Scotch hill gardens model at -ab 2 res=2048)

for use with WSL distro on Windows machines, alter the .wslconfig file to allow for more RAM and processors. 

    @"
    [wsl2]
    memory=28GB
    processors=20
    "@ | Out-File -FilePath "$env:USERPROFILE\.wslconfig" -Encoding ASCII

Utility terminal commands 
    # with relative time logging 100 snapshots, 60 seconds apart
        top -b -c -n 100 -d 60 > outputs/image/top_log.txt
        htop -d 600 --no-color > outputs/image/htop_log.txt

    # with real time logging
        script -c "top -b -c -d 60 -n 100" outputs/image/top_log.txt 
        pidstat -u -l 60 100 > outputs/image/pidstat_log.txt &

Only works with 10Klux sky.

"""

# TODO: eventually it this should utilised model.rad inputs and the source .mtl file to allow for parametetric simulation utilising different glass VLTs. e.g. 1 x model.rad + list of .mtl + list of cpu .rdp + list .rdv. This would allow for more flexible workflows and parametric analysis.
# TODO add inputs validator, extend its functionality for this use case. 
# 


def iesve_daylight_parallel_images():
    
    timer = PhaseTimer()
    
    with timer("Phase 0: Input scene Octree, Rendering param file (.rdp) and view files (.rdv)..."):
        image_resolution    = 2048                              # Image resolution (pixels)
        ffl_offset          = 0.00                              # Camera height above finished floor (meters)
        octree_path         = config.INPUTS_DIR / "image1.oct"  # IESVE BLD + Site + Sky
        rendering_quality   = [config.INPUTS_DIR / f for f in [
                                    "params_preview.rdp",       # Rendering params
                                    "params_standard.rdp",
                                    "params_high.rdp",                       
                                        ]]
    
    with timer("Phase 1: Prepare Camera Views..."):
        room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
            iesve_room_data_path        = config.INPUTS_DIR / "aoi" / "iesve_room_data.csv",
            output_path                 = config.WPD_DIR / "iesve_room_boundaries.csv"
            )

        view_generator = ViewGenerator(
            room_boundaries_csv_path    = room_boundaries_csv,
            ffl_offset                  = ffl_offset
            )
        view_generator.create_plan_view_files()







    with timer("Phase 2: Execute Rendering Pipeline..."):
        renderer = DaylightRenderer(
            x_res                       = inputs.image_resolution,
            y_res                       = inputs.image_resolution,
            )
        renderer.sunlight_rendering_pipeline()

    with timer("Phase 3: Post-processing and Stamping of Results..."):
        with timer("  3a: Generate AOI files..."):
            coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
            if coordinate_map_path is None:
                raise RuntimeError("Failed to create pixel-to-world coordinate map")
            view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

        with timer("  3b: Generate Daylight WPD and send to .xlsx..."):
            converter = Hdr2Wpd(
                pixel_to_world_map          = coordinate_map_path
                )
            converter.sunlight_sequence_wpd_extraction()

"""

    TODO: setup pre-set radiance parameters files .rdp, # Recommended lowest -aa 0.10. Lower values result in smoother output, but longer high resolution re-runs.


2. Rendering process
    # Recommend resolutions: 64, 128, 256, 512, 1024, 2048, 4096
        IMAGE_NAME="image1_shg_12ab"
        RES=$((2048))
        rtpict -n 19 -vf inputs/view.vp -x $RES -y $RES @inputs/${IMAGE_NAME}.rdp -af outputs/image/${IMAGE_NAME}.amb inputs/model.oct > outputs/image/${IMAGE_NAME}.hdr

    
3. Post-processing
    # Create separate legend for reporting
        pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -s 4 -n 10 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_false_legend.tiff
        pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -cl -s 2 -n 4 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_cntr_legend.tiff

    
    # Smooth image use could be effective for final visualisation. Source image must be used for results. 
        IMAGE_NAME="image1_shg_12ab"
        pfilt -x /2 -y /2 outputs/image/${IMAGE_NAME}.hdr > outputs/image/${IMAGE_NAME}_smooth.hdr
        pcomb -s 0.01 outputs/image/${IMAGE_NAME}.hdr | falsecolor -s 4 -n 10 -l "DF %" -lw 0 > outputs/image/${IMAGE_NAME}_df_false.hdr
        pcomb -s 0.01 outputs/image/${IMAGE_NAME}.hdr \
            | falsecolor -cl -s 2 -n 4 -l "DF %" -lw 0 \
            | tee outputs/image/${IMAGE_NAME}_df_cntr.hdr \
            | pcomb \
                -e 'cond=ri(2)+gi(2)+bi(2)' \
                -e 'ro=if(cond-.01,ri(2),ri(1))' \
                -e 'go=if(cond-.01,gi(2),gi(1))' \
                -e 'bo=if(cond-.01,bi(2),bi(1))' \
                <(pfilt -e 0.5 outputs/image/${IMAGE_NAME}.hdr) \
                - \
            | ra_tiff - outputs/image/${IMAGE_NAME}_df_cntr_overlay.tiff













4. Stamping and compliance results generation use 5b and 5c in sunlight_access_workflow as reference. Stamp images and add contours as needed. 
    TODO: modify classes to perform this analysis.





"""


if __name__ == "__main__":
    iesve_daylight_parallel_images()




