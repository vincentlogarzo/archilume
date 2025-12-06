"""
Archilume Example: Winter Solstice Sunlight Exposure Analysis
==========================================================================================================

This example demonstrates a complete sunlight analysis workflow using Archilume
to evaluate daylight conditions during the winter solstice (June 21st in the
Southern Hemisphere).

The analysis workflow includes:
1. Converting building and site OBJ files into a computational octree structure
2. Generating sunny sky files for the winter solstice at specified time intervals
3. Creating plan view files from room boundary data (CSV from Revit)
4. Executing the sunlight rendering pipeline for all time steps and views
5. Post-processing rendered HDR images to final compliance results.

Location: Melbourne, Australia (latitude: -37.8136°)
Date: June 21, 2024 (Winter Solstice)
Analysis Period: 9:00 AM - 3:00 PM at 10-minute intervals
Output: HDR images, view files, sky files, and coordinate mappings
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
    config
)

# Standard library imports

# Third-party imports

def main():
    # Start runtime tracking
    timekeeper = utils.Timekeeper()


    # ====================================================================================================
    print(f"\n{'=' * 100}\nARCHILUME - Winter Solstice Sunlight Exposure Analysis\n{'=' * 100}")
    # ====================================================================================================


    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 0: Input 3D Scene Files and Rendering Parameters...\n{'=' * 100}")
    # ====================================================================================================

    inputs = config.InputValidator(
        # ------------------------------------------------------------------------------------------------
        # FIXED INPUTS (Rarely changed)
        # ------------------------------------------------------------------------------------------------
        project_latitude            = -37.8134564,  # Building latitude to 4 decimal places
        month                       = 6,            # June
        day                         = 21,           # Winter solstice
        start_hour                  = 9,            # Analysis start: 9:00 AM
        end_hour                    = 15,           # Analysis end: 3:00 PM
        ffl_offset                  = 1.0,          # Camera height above finished floor level (meters)        
        room_boundaries_csv         = config.INPUTS_DIR / "87cowles_BLD_room_boundaries.csv",
        obj_paths = 
            [config.INPUTS_DIR / f for f in [
                    "87Cowles_BLD_withWindows.obj", # Assessed building (must be first)
                    "87cowles_site.obj"             # Site context
                        ]],                         # OBJ exports must be coarse, in meters, hidden line visual style, assumed model is oriented to true north
        # ------------------------------------------------------------------------------------------------
        # RENDERING SETTINGS (Modify per simulation run - balance quality vs speed)
        # ------------------------------------------------------------------------------------------------
        timestep                    = 15,            # Time interval in minutes (recommended >= 5 min) 
        image_resolution            = 512,         # Image size in pixels (512, 1024, 2048 <- recommended max, 4096)
        rendering_mode              = "gpu",        # Options: 'cpu', 'gpu'
        rendering_quality           = "fast",       # Options: 'draft', 'stand', 'prod', 'final', '4K', 'custom', 'fast', 'med', 'high', 'detailed'
    )

    smart_cleanup(
        timestep_changed            = False,  # Set TRUE if timestep changed (e.g., 5min → 10min)
        resolution_changed          = True,  # Set TRUE if image_resolution changed (e.g., 512 → 1024)
        rendering_mode_changed      = False,  # Set TRUE if switched cpu ↔ gpu
        rendering_quality_changed   = True   # Set TRUE if quality preset changed (e.g., 'fast' → 'stand')
    )



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 1: Establishing 3D Scene...\n{'=' * 100}")
    # ====================================================================================================
    octree_generator = Objs2Octree(inputs.obj_paths)
    octree_generator.create_skyless_octree_for_analysis()
    timekeeper("Phase 1: 3D Scene")



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 2: Generate Sky Conditions for Analysis...\n{'=' * 100}")
    # ====================================================================================================
    sky_generator = SkyGenerator(lat=inputs.project_latitude)
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                       = inputs.month,
        day                         = inputs.day,
        start_hour_24hr_format      = inputs.start_hour,
        end_hour_24hr_format        = inputs.end_hour,
        minute_increment            = inputs.timestep
        )
    timekeeper("Phase 2: Sky Conditions")



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 3: Prepare Camera Views...\n{'=' * 100}")
    # ====================================================================================================
    view_generator = ViewGenerator(
        room_boundaries_csv_path    = inputs.room_boundaries_csv,
        ffl_offset                  = inputs.ffl_offset
        )
    view_generator.create_plan_view_files()
    timekeeper("Phase 3: Camera Views")



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 4: Executing Rendering Pipeline...\n{'=' * 100}")
    # ====================================================================================================
    renderer = RenderingPipelines(
        skyless_octree_path         = octree_generator.skyless_octree_path,
        overcast_sky_file_path      = sky_generator.TenK_cie_overcast_sky_file_path,
        x_res                       = inputs.image_resolution,
        y_res                       = inputs.image_resolution
        )
    rendering_phase_timings = renderer.sunlight_rendering_pipeline(
        render_mode                 = inputs.rendering_mode,
        gpu_quality                 = inputs.rendering_quality
        )
    timekeeper.phase_timings.update(rendering_phase_timings)
    timekeeper("Phase 4: Rendering")



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 5: Post-Process Stamping of Results...\n{'=' * 100}")
    # ====================================================================================================

        # ------------------------------------------------------------------------------------------------
        # Phase 5a: Generate Area of Interest (AOI) files
        # ------------------------------------------------------------------------------------------------
    coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)
    timekeeper("  5a: Generate AOI")

        # ------------------------------------------------------------------------------------------------
        # Phase 5b: Generate Working plane data (WPD) for sunlit areas and send results to .xlsx
        # ------------------------------------------------------------------------------------------------
    converter = Hdr2Wpd(
        pixel_to_world_map          = coordinate_map_path
        )
    converter.sunlight_sequence_wpd_extraction()
    timekeeper("  5b: Generate WPD")

        # ------------------------------------------------------------------------------------------------
        # Phase 5c: Stamp images with results and combine into .gifs
        # ------------------------------------------------------------------------------------------------
    tiff_annotator = Tiff2Animation(
        skyless_octree_path         = octree_generator.skyless_octree_path,
        overcast_sky_file_path      = sky_generator.TenK_cie_overcast_sky_file_path,
        x_res                       = renderer.x_res,
        y_res                       = renderer.y_res,
        latitude                    = inputs.project_latitude,
        ffl_offset                  = inputs.ffl_offset,
        animation_format            = "apng"  # Options: "gif" or "apng"
        )
    tiff_annotator.nsw_adg_sunlight_access_results_pipeline()
    timekeeper("  5c: Stamp Images")
    timekeeper("Phase 5: Post-Processing")



    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 6: Package Final Results and Simulation Summary...\n{'=' * 100}")
    # ====================================================================================================

    timekeeper.print_report(output_dir=config.OUTPUTS_DIR)

    return True


if __name__ == "__main__":
    main()

# TODO: integrate wpd2report in substitue of the current excel file generation in the hdr2wpd class. 
# TODO: implement move smar_cleanup function into the input validator. As it validates each input, it will check the previously . cache simulation parameters, and the files in the outputs dir. for each input change an action must occur.
# TODO: Image_processor.nsw_adg_sunlight_access_results_pipeline() -> 
    # add implementation to stamp these tiffs with the .wpd results using a very simple matplotlib
        # Calculate illumination metrics per spatial zone with regulatory threshold evaluation for nsw adg compliance
    # chart overlay onto combined gifs. 
    # automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value. 
# TODO: there is no compatibility for input files that have spaces in them. This would mean throughout the code that strings would need to be implemented to prevent a crash if this occured.
# DONE: Smart cleanup system implemented - use smart_cleanup() before re-runs with parameter changes. See SMART_CLEANUP_GUIDE.md 
# TODO option to autogenerate room boundaries if user specified Y or N to Do You have room_boundaries_csv?
# TODO: include an option when seting up the grid point size with validation that a grid sparseness will not allow an rpict simulation to be value below 512 pixels. This it recommends moving to rtrace simulations. It should also allow options for a user to do floor plate rendering mode or room by room rendering mode based on the room boundaries. room-by-room will need to be constructed together into one image again on the output, with extneding boundaries of the image to be a bound box of the entire room. Where room boundaties are contained within another room bound exlucde this inner room boundaries from being simulated separately.
# TODO: RenderingPipelines ->  allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents and auto determine the x and y resolution to best fit the floor plate. give warning if resolution is greater than 2048 a stepped appraoch can be used as a result of ambient file caching. Caching is more effective in CPU mode than GPU mode. 

# TODO: for cross machines compatibility, implement .ps1 files for all radiance commands. Specifically to address path issues and remove the need for the user to download external software. 
# FIXME: room_boundaties csv from Rothe -> the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing.
# TODO: implement for accelerad_rpict.ps1 correct handling of large obj files, single precision values in accelerad simulation result in lower accuracy of output results, thus this needs tobe considered if running a daylight simulation. The model must also be close to the origin. If it is very far away, >100m, this will also introduce calculation erorr and thus low quality images that need not exist. 

# TODO: invesitgate a simpler implemntation of file paths, currently this prints out the full path, but surely there is a way to allow relative paths to be used to simplify the terminal printouts for readability.
# TODO: tests to be conducted on fine detail obj exports as to their impact on speed and size.
# DONE: GPU spikiness eliminated - Two-phase batch rendering implemented in accelerad_rpict.ps1. All ambient files generated first, then all main renders. GPU stays warm within each phase, reducing context switches from 2N to 2. 

# TODO: RenderingPipelines ->  allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents and auto determine the x and y resolution to best fit the floor plate. give warning if resolution is greater than 2048 a stepped appraoch to results is needed 

#TODO code is not equipped to handle vertical view positions in the file naming conventions. This feature would need to be added for future use and tested. Vertical view positions, would need to be named as such. Instead of plan, elevation_aoi_x_surfaceA.vp
# TODO: setup .bat files to run radiance executables with radiance binaries that are not on path, with binaries that are in the radiance distribution.
# TODO: RenderingPipelines -> find a way to turn on/off the indirect lighting calculation to speed up rendering times if model does not need visual validation.
# TODO: Pre-processing of .obj is recommended for speed  after decimation in blender has occured depending on model use case
# TODO:  ObjToOctree -> move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here.
# TODO: investgate https://www.schorsch.com/en/download/rradout/ as an export solution
# TODO: view_generator.create_aoi_files ->
    # Develop interactive interface for dynamic AOI adjustment with persistence of aoi files into the aoi_modified dir.
    # set maximum number of workers checks within classes to ensure this value cannot exceed available cores on the users machine.
# TODO: Hdr2Wpd ->
    # serious optimisation of the wpd extraction needs to occur. (look to nvmath-python to do the algenra matrix array operations in the GPU especially as larger images occur.
    # ensure modified file are used when they exist.
# TODO: package all key results into a single output directory for user convenience and zip this dir for easy sharing.
# TODO: add custom parameters input into the gpu_quality, which should be albelelled rendering parameters that work for both these workflows if user does not want to use a preconfigured set of parameters. 
# TODO: potentiall simpler implemntation of gpu rendering using os.system(".\archilume\accelerad_rpict.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast fast 512 plan_ffl_90000") instead of the current in rendering_pipelines.py.
# TODO: execute sky view and aoi generator while the initial octree is being compiled with oconv as it is a heavy process currently only utilising 1 core of the CPU.
# TODO: see future implementation A in radiance_testpad.py to introduce optional falsecolour of the output images before stamping. See the command needed under this ection. 
# FIXME: obj_paths variable -> currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce user error
# TODO: view_generator.create_aoi_files -> 
    # move this generator upfront, it does not need a rendered hdr image to operate. This could be done upfonrt with the room boundaries data, in parallel with octree generation processes. 
# TODO: RenderingPipelines ->  implement rtrace mulitprocess rendering pipeline to speed up costly indirect rendering images for those without a compatible cuda enabled GPU.
    #invetigate section 3.3.2 of https://www.jaloxa.eu/resources/radiance/documentation/docs/radiance_cookbook.pdf for rtrace at 10K luc daylight factor simulations. 
    # Investigate use of rtpict, newer versions of radiance arent meant to have resolved the issues of using this on windows. 
# TODO: RenderingPipelines ->  Allow deletion of temp octrees immediately after oconv of the temp file occurs with the sky file. This will conserve storage for very large files. Thought this wont matter if the above rtrace is implement, as octree_skyless can be combined with each sky file in the rtrace call. These do not need to be precompiled into thier own octrees for rendering. 
# TODO: view_generator.create_aoi_files -> 
    # vertical plane generation based on failing apartment results is also allowable, generation of views basedon the aoi room boundaries would then be necessary and subsequent rendering pipeline for these vertical surfaces without offset. 
# TODO: ViewGenerator -> for buildings with large podiums and smaller towers the view generator should dynamically determine that levels bounding box and use this as the input view parameters instead of generically applything the same view width and height for each level regardless. This will result in higher effieicny on the number of pixels to be rendered, especially when moving to rtrace implementation. it will also introduce a grwat amount of work to resize all aoi and room boundaries to be stamped. 
# TODO: invesitgate cloud computing, specifically costs of G4 compute on https://docs.cloud.google.com/compute/docs/gpus/create-vm-with-gpus. $1.73 per hour of us 34 core CPU and 1 x cuda GPU NVIDIA 
# TODO: create a scheduling system for overnight runs, multiple different models groups and perhpas even subsequent convergence runs on the same model groups. 