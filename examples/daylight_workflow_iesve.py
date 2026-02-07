"""
Archilume Example: IESVE Daylight Factor Analysis
======================================================================================================

This example demonstrates a daylight factor (DF) analysis workflow using Archilume
with pre-built IESVE octree models. The pipeline converts IESVE room data and AOI
boundary files into Radiance view files, renders each view sequentially using all
available CPU cores, and post-processes the results into falsecolor and contour
overlay images.

The analysis workflow includes:
1. Converting IESVE AOI boundary files + room data into ViewGenerator-compatible CSV
2. Generating plan view files (.vp) for each floor level from room boundaries
3. Rendering each view against the pre-built IESVE octree (includes 10K lux sky)
4. Post-processing HDR images: smooth, falsecolor, contour overlays, and legends

Note:               Only works with 10K lux (10,000 lux) overcast sky models from IESVE.
                    The octree must include the sky definition. DF values are derived
                    by scaling rendered irradiance (pcomb -s 0.01) against the 10K lux reference.

Input:              IESVE octree (.oct), rendering parameters (.rdp), AOI files (.aoi),
                    IESVE room data csv
Output:             HDR images, falsecolor/contour TIFFs, legend images, view files
"""

# fmt: off
# autopep8: off

# Archilume imports
from archilume import (
    SkyGenerator,
    ViewGenerator,
    Objs2Octree,
    DaylightRenderer,
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
    # with real time logging
        pidstat -u -l 60 100 > outputs/image/pidstat_log.txt &

Only works with 10Klux sky.

"""

# TODO: eventually it this should utilised model.rad inputs and the source .mtl file to allow for parametetric simulation utilising different glass VLTs. e.g. 1 x model.rad + list of .mtl + list of cpu .rdp + list .rdv. This would allow for more flexible workflows and parametric analysis.
# TODO add inputs validator, extend its functionality for this use case. e.g. validate input IES room data csv has the correct columns identifiers. 
# TODO: add functionality to allow multiple parameters input files to run parametric analysis, or low param for initial checks and setup of aoi with high run results coming in later. 


def iesve_daylight_parallel_images():
    
    timer = PhaseTimer()
    
    with timer("Phase 0: Input scene Octree, Rendering param file (.rdp) and view files (.rdv)..."):
        image_resolution    = 2048                                      # Image resolution (pixels)
        ffl_offset          = 0.00                                      # Camera height above FFL (meters)
        octree_path         = config.INPUTS_DIR / "model.oct"           # Source 3D model from IESVE
        rendering_params    = config.INPUTS_DIR / "params_preview.rdp" # Rendering parameters
        iesve_room_data     = config.INPUTS_DIR / "aoi" / "iesve_room_data.csv" # Apache room data export (must contain room id + floor height columns)

    with timer("Phase 1: Prepare Camera Views..."):
        room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
            iesve_room_data_path        = iesve_room_data
            )

        view_generator = ViewGenerator(
            room_boundaries_csv_path    = room_boundaries_csv,
            ffl_offset                  = ffl_offset
            )
        view_generator.create_plan_view_files()

    with timer("Phase 2: Execute Rendering Pipeline..."):
        renderer = DaylightRenderer(
            octree_path                 = octree_path,
            rdp_path                    = rendering_params,
            x_res                       = image_resolution,
            view_files                  = view_generator.view_files,
            )
        renderer.daylight_rendering_pipeline()






    # with timer("Phase 3: Post-processing and Stamping of Results..."):
    #     with timer("  3a: Generate AOI files..."):
    #         coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
    #         if coordinate_map_path is None:
    #             raise RuntimeError("Failed to create pixel-to-world coordinate map")
    #         view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

    #     with timer("  3b: Generate Daylight WPD and send to .xlsx..."):
    #         converter = Hdr2Wpd(
    #             pixel_to_world_map          = coordinate_map_path
    #             )
    #         converter.sunlight_sequence_wpd_extraction()

"""

2. Rendering process
    # Recommend resolutions: 64, 128, 256, 512, 1024, 2048, 4096
        IMAGE_NAME="image1_shg_12ab"
        RES=$((2048))
        rtpict -n 19 -vf inputs/view.vp -x $RES -y $RES @inputs/${IMAGE_NAME}.rdp -af outputs/image/${IMAGE_NAME}.amb inputs/model.oct > outputs/image/${IMAGE_NAME}.hdr

    
3. Post-processing
    3.1 # Create separate legend for reporting
        pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -s 4 -n 10 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_false_legend.tiff
        pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -cl -s 2 -n 4 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_cntr_legend.tiff

    
    3.2 # Smooth image use could be effective for final visualisation. Source image must be used for results. 
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




