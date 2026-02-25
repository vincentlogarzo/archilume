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
        octree_path         = config.INPUTS_DIR / "527DP_model_wSite.oct" # Must use a 10K Lux CIE Overcast sky
        rendering_params    = config.INPUTS_DIR / "high.rdp"
        iesve_room_data     = config.INPUTS_DIR / "aoi" / "iesve_room_data.csv"

        # TODO: implement inputs validations checks alike to sunlight access workflow.

        # TODO: allowance for gpu rendering mode if a user wishes to have this. This would mean this could run on windows machine alike to the sunlight rendering workflow.

        smart_cleanup(
            timestep_changed            = False,  # Set TRUE if timestep changed (e.g., 5min → 10min)
            resolution_changed          = True,  # Set TRUE if image_resolution changed (e.g., 512 → 1024)
            rendering_mode_changed      = False,  # Set TRUE if switched cpu/gpu
            rendering_quality_changed   = False  # Set TRUE if quality preset changed (e.g., 'fast' → 'stand')
            )

        #FIXME: AOI dir isnt properly cleaned when the smart clean up is True. 

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

    #FIXME: move image post processing steps from this Renderer into the aoi editor, that way a user can update the values as they see fit before export of results. It would also mean that only one input id needed the .hdr files. Some meta data could be shown regarding image on the aoi editor so that i user can see what parameters were run, and a button to launch the accelerat_RT programm on the model the simulation was run on. 

    with timer("Phase 3: Post-processing and Stamping of Results..."):
        with timer("  3a: Generate .aoi files..."):
            coordinate_map_path         = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
            view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)


if __name__ == "__main__":
    iesve_daylight_parallel_images()


# TODO: Parametric materials – use model.rad + swappable .mtl files to vary
#   glass VLT, wall/ceiling LRV, etc. Support multiple .rdp/.rdv per run.
# TODO: Parametric params – accept multiple parameter input files (or
#   low/high param sets) for incremental refinement of AOI checks.
# TODO: Grid-based resolution – replace image resolution with grid_res (mm). this brings consistency to any image produced across any model no matter how large the building. 
#   Dynamically size images so pixel density is consistent across views.
#   Run at half grid_res first for quick AOI review, full res second.
# TODO: Room/floor-plate mode – run per-room or per-floor by compositing
#   .aoi files into a single floor-plate view (depends on grid_res).
# TODO: Input validation – extend validator to check IES room-data CSV
#   column identifiers and other workflow-specific constraints.
# TODO: View offset – use Radiance .views offset parameters instead of
#   manual FFL offset, so the offset is captured in the .hdr header.
# TODO: Smart cleanup – remove input dependency; decide whether to keep
#   the ambient file by comparing .hdr headers to current parameters.
#   Skip commands whose output files already match (same view, same
#   params; resolution changes are allowed).