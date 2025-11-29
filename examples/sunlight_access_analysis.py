"""
Archilume Example: Winter Solstice Sunlight Exposure Analysis
==============================================================

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
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator
from archilume.obj_to_octree import ObjToOctree
from archilume.rendering_pipelines import RenderingPipelines
from archilume.image_processor import ImageProcessor
from archilume.results_processor import ResultsProcessor
from archilume import utils
from archilume import config

# Standard library imports

# Third-party imports

# TODO: Implement checks on site rotation, validate simulation to be conducted at low res render and then set the rotation if it is off.
# TODO: include an option when seting up the grid point size with validation that a grid sparseness will not allow an rpict simulation to be value below 512 pixels. This it recommends moving to rtrace simulations. It should also allow options for a user to do floor plate rendering mode or room by room rendering mode based on the room boundaries. room-by-room will need to be constructed together into one image again on the output, with extneding boundaries of the image to be a bound box of the entire room. Where room boundaties are contained within another room bound exlucde this inner room boundaries form being simulated separately.
# TODO: Image_processor.nsw_adg_sunlight_access_results_pipeline() -> 
    # add implementation to stamp these tiffs with the .wpd results using a very simple matplotlib
        # Calculate illumination metrics per spatial zone with regulatory threshold evaluation for nsw adg compliance
    # chart overlay onto combined gifs. 
    # automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value. 

# TODO: RenderingPipelines ->  allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents and auto determine the x and y resolution to best fit the floor plate. give warning if resolution is greater than 2048 a stepped appraoch to results is needed 

# TODO: Enabled simultaneous operation of gpu rendering and rest of the workflow front load heavy oconv
# TODO: setup .bat files to run radiance executables with radiance binaries that are not on path, with binaries that are in the radiance distribution.
# TODO: RenderingPipelines -> find a way to turn on/off the indirect lighting calculation to speed up rendering times if model does not need visual validation.
# TODO: Pre-processing of .obj is recommended for speed  after decimation in blender has occured depending on model use case
# FIXME:  ObjToOctree -> move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here.

# TODO: view_generator.create_aoi_files -> 
    # Develop interactive interface for dynamic AOI adjustment with persistence of aoi files into the aoi_modified dir.
    # set maximum number of workers checks within classes to ensure this value cannot exceed available cores on the users machine.
#TODO: ResultsProcessor -> 
    # serious optimisation of the wpd extraction needs to occur. (look to nvmath-python to do the algenra matrix array operations in the GPU especially as larger images occur. 
    # ensure modified file are used when they exist.
# TODO: package all key results into a single output directory for user convenience and zip this dir for easy sharing.
# TODO: add custom parameters input into the gpu_quality, which should be albelelled rendering parameters that work for both these workflows if user does not want to use a preconfigured set of parameters. 
# TODO: potentiall simpler implemntation of gpu rendering using os.system(".\archilume\accelerad_rpict_batch.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast fast 512 plan_L02") instead of the current in rendering_pipelines.py.

# TODO: execute sky view and aoi generator while the initial octree is being compiled with oconv as it is a heavy process currently only utilising 1 core of the CPU.
# TODO: The view generator does not deal well hen levels are deleted from the room boundaries, it does number levles corrector. Perhaps the Level number should be RL for reference line.
# TODO: see future implementation A in radiance_testpad.py to introduce optional falsecolour of the output images before stamping. See the command needed under this ection. 
# FIXME: room_boundaties csv from Rothe -> the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing.
# FIXME: obj_paths variable -> currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 
# TODO: SkyGenerator -> all classes here that utilise a number of workers should have a user input to define number of workers. Currently defaults to all available cores which may not be ideal for all users.
# TODO: ViewGenerator -> for buildings with large podiums and smaller towers the view generator should dynamically determine that levels bounding box and use this as the input view parameters instead of generically applything the same view width and height for each level regardless. This will result in higher effieicny on the number of pixels to be rendered, especially when moving to rtrace implementation. it will also introduce a grwat amount of work to resize all aoi and room boundaries to be stamped. 
# TODO: RenderingPipelines ->  Allow deletion of temp octrees immediately after oconv of the temp file occurs with the sky file. This will conserve storage for very large files. Thought this wone matter if the above rtrace is implement, as octree_skyless can be combined with each sky file in the rtrace call. These do not need to be precompiled into thier own octrees for rendering. 
# TODO: Rendering pipelineRenderingPipelines ->  implement low resolution fist pass rendering for visual validation, if higher resolution is needed then second pass at a higher resolution can be executed without much further cost.
# TODO: view_generator.create_aoi_files -> 
    # vertical plane generation based on failing apartment results is also allowable, generation of views basedon the aoi room boundaries would then be necessary and subsequent rendering pipeline for these vertical surfaces without offset. 
    # move this generator upfront, it does not need a rendered hdr image to operate. This could be done upfonrt with the room boundaries data, in parallel with octree generation processes. 
# TODO: RenderingPipelines ->  implement rtrace mulitprocess rendering pipeline to speed up costly indirect rendering images.


def main():
    # Start runtime tracking
    timekeeper = utils.Timekeeper()

    print(f"\n{'=' * 100}\nARCHILUME - Winter Solstice Sunlight Exposure Analysis\n{'=' * 100}")

    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 0: Input 3D Scene Files and Rendering Parameters...\n{'=' * 100}")
    # ====================================================================================================
    project_latitude                    = -37.8134564   # Input building projcts latitude to 4 d.p.
    month                               = 6             # June
    day                                 = 21            # Winter solstice
    start_hour                          = 9             # 9:00 AM
    end_hour                            = 15            # 3:00 PM
    timestep                            = 15            # Minutes (recommended >= 5 min)
    ffl_offset                          = 1.0           # Camera height above finished floor level (FFL)
    image_resolution                    = 2048          # Image size in pixels (recommnded <= 2048)
    rendering_mode                      = 'gpu'         # select cpu or accelerated gpu rendering
    rendering_quality                   = 'high'        # select one quality option: fast, med, high, detailed, test, ark
    room_boundaries_csv_path            = config.INPUTS_DIR / "87cowles_BLD_room_boundaries.csv"

    obj_paths = [config.INPUTS_DIR / f for f in [
        "87Cowles_BLD_withWindows.obj",                 # Assessed building must be first
        "87cowles_site.obj"                             # .obj files must be exported as coarse in meters with hidden line visual style.
        ]]


    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 1: Establishing 3D Scene...\n{'=' * 100}")
    # ====================================================================================================
    octree_generator = ObjToOctree(obj_paths)
    octree_generator.create_skyless_octree_for_analysis()



    timekeeper("Phase 1: 3D Scene")
    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 2: Generate Sky Conditions for Analysis...\n{'=' * 100}")
    # ====================================================================================================
    sky_generator = SkyGenerator(lat=project_latitude)  # Input projcts latitude to at least 4 decimal places
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                       = month,
        day                         = day,
        start_hour_24hr_format      = start_hour,
        end_hour_24hr_format        = end_hour,
        minute_increment            = timestep
        )
    


    timekeeper("Phase 2: Sky Conditions")
    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 3: Prepare Camera Views...\n{'=' * 100}")
    # ====================================================================================================
    view_generator = ViewGenerator(
        room_boundaries_csv_path    = room_boundaries_csv_path,
        ffl_offset                  = ffl_offset
        )
    view_generator.create_plan_view_files()



    timekeeper("Phase 3: Camera Views")
    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 4: Executing Rendering Pipeline...\n{'=' * 100}")
    # ====================================================================================================
    renderer = RenderingPipelines(
        skyless_octree_path         = octree_generator.skyless_octree_path,
        overcast_sky_file_path      = sky_generator.TenK_cie_overcast_sky_file_path,
        x_res                       = image_resolution,
        y_res                       = image_resolution
        )
    rendering_phase_timings = renderer.sunlight_rendering_pipeline(
        render_mode                 = rendering_mode,
        gpu_quality                 = rendering_quality
        )



    timekeeper.phase_timings.update(rendering_phase_timings)
    timekeeper("Phase 4: Rendering")
    # ====================================================================================================
    print(f"\n{'=' * 100}\nPhase 5: Post-Process Stamping of Results...\n{'=' * 100}")
    # ====================================================================================================


    # ----------------------------------------------------------------------------------------------------
    # Phase 5a: Generate Area of Interest (AOI) files
    # ----------------------------------------------------------------------------------------------------
    coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)



    timekeeper("  5a: Generate AOI")
    # ----------------------------------------------------------------------------------------------------
    # Phase 5b: Generate Working plane data (WPD) and .csv results for sunlit areas ---
    # ----------------------------------------------------------------------------------------------------
    processor = ResultsProcessor(
        image_dir                   = renderer.image_dir,
        aoi_dir                     = view_generator.aoi_dir,
        wpd_dir                     = config.WPD_DIR,
        pixel_threshold_value       = 0,
        max_workers                 = 12,
        pixel_to_world_map          = coordinate_map_path
        )
    processor.sunlight_sequence_wpd_extraction()



    timekeeper("  5b: Generate WPD")
    # --------------------------------------------------------------------------------------------------------
    # Phase 5c: Stamp results onto images and generate combined gifs
    # --------------------------------------------------------------------------------------------------------
    image_processor = ImageProcessor(
        skyless_octree_path         = octree_generator.skyless_octree_path,
        overcast_sky_file_path      = sky_generator.TenK_cie_overcast_sky_file_path,
        x_res                       = renderer.x_res,
        y_res                       = renderer.y_res,
        latitude                    = sky_generator.lat
        )
    image_processor.nsw_adg_sunlight_access_results_pipeline()



    timekeeper("  5c: Stamp Images")
    timekeeper("Phase 5: Post-Processing")
    # ========================================================================================================
    print(f"\n{'=' * 100}\nPhase 6: Package Final Results and Simulation Summary...\n{'=' * 100}")
    # ========================================================================================================






    timekeeper.print_report(output_dir=config.OUTPUTS_DIR)

    return True


if __name__ == "__main__":
    main()