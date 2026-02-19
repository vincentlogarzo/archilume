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
3. Rendering each view against the pre-built IESVE octree (This code only works with 10Klux sky.)
4. Post-processing HDR images: smooth, falsecolor, contour overlays, and legends

Note:               Only works with 10K lux (10,000 lux) overcast sky models from IESVE.
                    The octree must include the sky definition. DF values are derived
                    by scaling rendered irradiance (pcomb -s 0.01) against the 10K lux reference.

Input:              IESVE octree (.oct), rendering parameters (.rdp), AOI files (.aoi),
                    IESVE room data csv
Output:             HDR images, falsecolor/contour TIFFs, legend images, view files


arhcitecture to run on gcloud services and more cost optimised rendering pipelines for large scale daylighting analysis.
    
    c4d-standard-64-lssd (64 vCPUs, 248 GB memory) + local ssd to mitigate IO bottlenecks

for use with WSL distro on Windows machines, alter the .wslconfig file to allow higher use of RAM and processors. 

    @"
    [wsl2]
    memory=28GB
    processors=20
    "@ | Out-File -FilePath "$env:USERPROFILE\.wslconfig" -Encoding ASCII

"""

# fmt: off
# autopep8: off

# Archilume imports
from archilume import (
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


def iesve_daylight_parallel_images():
    
    timer = PhaseTimer()
    
    with timer("Phase 0: User input 3D Scene file + Rendering parameter (.rdp) and aoi (.aoi)..."):
        image_resolution    = 2048                            
        ffl_offset          = 0.00
        octree_path         = config.INPUTS_DIR / "model.oct" # Must use a 10K Lux CIE Overcast sky
        rendering_params    = config.INPUTS_DIR / "preview.rdp"
        iesve_room_data     = config.INPUTS_DIR / "aoi" / "iesve_room_data.csv"
        df_thresholds       = (0.5, 1.0, 1.5) # % of floor area meeting daylight factor threshold

        # TODO: implement inputs validations checks alike to sunlight access workflow.

        # TODO: allowance for gpu rendering mode if a user wishes to have this. This would mean this could run on windows machine alike to the sunlight rendering workflow.

        smart_cleanup(
            timestep_changed            = True,  # Set TRUE if timestep changed (e.g., 5min → 10min)
            resolution_changed          = True,  # Set TRUE if image_resolution changed (e.g., 512 → 1024)
            rendering_mode_changed      = True,  # Set TRUE if switched cpu/gpu
            rendering_quality_changed   = True  # Set TRUE if quality preset changed (e.g., 'fast' → 'stand')
            )

    with timer("Phase 1: Prepare Camera Views..."):
        room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
            iesve_room_data_path        = iesve_room_data
            )

        view_generator = ViewGenerator(
            room_boundaries_csv_path    = room_boundaries_csv,
            ffl_offset                  = ffl_offset
            )
        view_generator.create_plan_view_files()

    # FIXME, check that the room boundaties created from the aoi files enforces consistent width, height and centre points coordinate for each plan view. This is important to ensure that the same pixel in each view corresponds to the same world coordinate, which is critical for post processing and analysis of results. views are consistent from level to level.

    with timer("Phase 2: Execute Image Rendering..."):
        renderer = DaylightRenderer(
            octree_path                 = octree_path,
            rdp_path                    = rendering_params,
            x_res                       = image_resolution,
            view_files                  = view_generator.view_files,
            )
        renderer.daylight_rendering_pipeline()

    #FIXME: move image post processing steps from this Renderer, and move them to stage 3c after the pixel to world coordinate map generation.

    with timer("Phase 3: Post-processing and Stamping of Results..."):
        with timer("  3a: Generate .aoi files..."):
            coordinate_map_path         = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
            view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

        with timer("  3b: Generate Daylight .wpd ..."):
            converter = Hdr2Wpd(
                pixel_to_world_map      = coordinate_map_path
                )
            converter.daylight_wpd_extraction(df_thresholds=df_thresholds)

    # TODO: Move to the next module for an interactive aoi editor using the df_false.tiff files. It overlays the aoi allows editing of subrooms using the existing json session implementation, df_thresholds for these spaces or by type assignment of space and then extraction of image stamped with what it viewed of screen, a toggle between green dot red dot, and actual result should be provided and then when export is clicked, both the amenede tiff files with suffix of its changed, df_false_stamped.tiff and df_false_dot.tiff. 

    #TODO: detemrine after the above is created if phase 3 is required at all. 



if __name__ == "__main__":
    iesve_daylight_parallel_images()


# TODO: eventually it this should utilised model.rad inputs and the source .mtl file to allow for parametetric simulation utilising different glass VLTs. e.g. 1 x model.rad + list of .mtl + list of cpu .rdp + list .rdv. This would allow for more flexible workflows and parametric analysis. I.e. modify window VLT given a window material name, or wall or ceiling LRV given an input name to modify.
    # TODO: add functionality to allow multiple parameters input files to run parametric analysis, or low param for initial checks and setup of aoi with high run results coming in later. 
#TODO: add feature to run by room or run by floor plate, this will either create a floor plate from input .aoi files or create a view per aoi file. This should only be implemented when the grid size in mm is implemneted instead of resolution input. 
#TODO: setup the inputs strcutrue to take in grid_res instead of image res, this wouuld be a dynamically calculated parameters. It would mean that we set the grid_red for images to be e.g. 20mm then no matter the size of the view the images will be consistent in their resolution when viewed by a human. This would mean that we could then setup half grid_res to run first then subsequent runs second, so that a user can use the first images to begging aoi checks and redrawing or intial setup of boundaries boundaries for post processing final results. 
# TODO add inputs validator, extend its functionality for this use case. e.g. validate input IES room data csv has the correct columns identifiers. 
#TODO: augment the view offset from FFL input to use the actual parameters for offset in the .views files as intended by radiance. This way, the offset will reveal itself in the image file header. 

#TODO : Fix the Smartcleanup function, it should not require inputs at all. It should only, It should look to either make a decision on retaining the ambient file or not based on the input given and the file headers of existing .hdr files. This is the largest time sink, all other processes can happen again no matter what.  look at the setup outputs checkings on commands just before they are run, then remove command from list if output file exists, (i.e. has same parameters or other conditions with which to not re-run this simulation e.g. the ambient file use can only be re-used for the same view with the all same parameters (except resolution, this can change between runs))