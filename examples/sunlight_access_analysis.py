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

# Standard library imports
from pathlib import Path
import time

# Third-party imports

# TODO: execute sky view and aoi generator while the initial octree is being compiled with oconv as it is a heavy process currently only utilising 1 core of the CPU.
# TODO: The view generator does not deal well hen levels are deleted from the room boundaries, it does number levles corrector. Perhaps the Level number should be RL for reference line.
# TODO: see future implementation A in radiance_testpad.py to introduce optional falsecolour of the output images before stamping. See the command needed under this ection. 

# FIXME: room_boundaties csv from Rothe -> the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing.
# FIXME: obj_paths variable -> currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 
# FIXME:  ObjToOctree -> move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here.
# TODO: SkyGenerator -> all classes here that utilise a number of workers should have a user input to define number of workers. Currently defaults to all available cores which may not be ideal for all users.
# TODO: ViewGenerator -> for buildings with large podiums and smaller towers the view generator should dynamically determine that levels bounding box and use this as the input view parameters instead of generically applything the same view width and height for each level regardless. This will result in higher effieicny on the number of pixels to be rendered, especially when moving to rtrace implementation. 
# TODO: RenderingPipelines -> find a way to turn on/off the indirect lighting calculation to speed up rendering times if model does not visual validation.
# TODO: RenderingPipelines ->  introduce accelerad implemntation in place of daylight calcualtion for backing image. rendering speeds and high quality could be realised The user needs to be aware of drivre installs and accelerad installs, this stuff is likely not possible in the dev container situation, though it should be investigated. 
# TODO: RenderingPipelines ->  allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents and auto determine the x and y resolution to best fit the floor plate
# TODO: RenderingPipelines ->  implement rtrace mulitprocess rendering pipeline to speed up costly indirect rendering images.
# TODO: RenderingPipelines ->  Allow deletion of temp octrees immediately after oconv of the temp file occurs with the sky file. This will conserve storage for very large files. Thought this wone matter if the above rtrace is implement, as octree_skyless can be combined with each sky file in the rtrace call. These do not need to be precompiled into thier own octrees for rendering. 
# TODO: Rendering pipelineRenderingPipelines ->  implement low resolution fist pass rendering for visual validation, if higher resolution is needed then second pass at a higher resolution can be executed without much further cost.
# TODO: RenderingPipelines -> implement pfilt to downsize images for smoothing and faster processing.
# TODO: view_generator.create_aoi_files -> 
    # Develop interactive interface for dynamic AOI adjustment with persistence of aoi files into the aoi_modified dir.
    # set maximum number of workers checks within classes to ensure this value cannot exceed available cores on the users machine.
# TODO: view_generator.create_aoi_files -> 
    # vertical plane generation based on failing apartment results is also allowable, generation of views basedon the aoi room boundaries would then be necessary and subsequent rendering pipeline for these vertical surfaces without offset. 
    # move this generator upfront, it does not need a rendered hdr image to operate. This could be done upfonrt with the room boundaries data, in parallel with octree generation processes. 
#TODO: ResultsProcessor -> 
    # serious optimisation of the wpd extraction needs to occur. 
    # ensure modified file are used when they exist.
# TODO: Image_processor.nsw_adg_sunlight_access_results_pipeline() -> 
    # add implementation to stamp these tiffs with the .wpd results using a very simple matplotlib
        # Calculate illumination metrics per spatial zone with regulatory threshold evaluation for nsw adg compliance
    # chart overlay onto combined gifs. 
    # automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value.
# TODO: package all key results into a single output directory for user convenience and zip this dir for easy sharing.
# TODO: add custom parameters input into the gpu_quality, which should be albelelled rendering parameters that work for both these workflows if user does not want to use a preconfigured set of parameters. 
# TODO: potentiall simpler implemntation of gpu rendering using os.system(".\archilume\accelerad_rpict_batch.bat 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast fast 512 plan_L02") instead of the current in rendering_pipelines.py.

def main():
    # Start runtime tracking
    script_start_time = time.time()
    phase_timings = {}  # Store phase execution times

    print(f"\n{'=' * 100}\nARCHILUME - Winter Solstice Sunlight Exposure Analysis\n{'=' * 100}")


    # ========================================================================================================
    # Phase 0: List building, site and other adjacent building files and input parameters
    # ========================================================================================================
    project_latitude                    = -37.8134564   # Input building projcts latitude to at least 4 decimal places
    month                               = 6             # June
    day                                 = 21            # Winter solstice
    start_hour                          = 9             # 9:00 AM
    end_hour                            = 15            # 3:00 PM
    timestep                            = 15            # Minutes (must be greater than 5 min increments) 
    finished_floor_level_offset         = 1.0           # Meters above finished floor level for camera height
    image_resolution                    = 2048          # Image size in pixels to be rendered (must <= 2048)
    rendering_mode                      = 'gpu'         # select from convention cpu rendering or accelerated gpu rendering
    rendering_quality                   = 'high'        # select from a range of rendering quality options: fast, med, high, detailed, test, ark
    room_boundaries_csv_path            = Path(__file__).parent.parent / "inputs" / "87cowles_BLD_room_boundaries.csv"
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87Cowles_BLD_withWindows.obj", # first file must be building of interest
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj" # .obj files must be exported in meters + coarse + 3d view visual style as hidden line. Geometry decimation optional via blender
        ]    


    # ========================================================================================================
    # Phase 1: Establish 3D Scene
    # ========================================================================================================
    print(f"\n{'=' * 100}\nPhase 1: Establishing 3D Scene...\n{'=' * 100}")
    phase_start = time.time()

    octree_generator = ObjToOctree(obj_paths)
    octree_generator.create_skyless_octree_for_analysis()

    phase_timings["Phase 1: 3D Scene"], phase_start = time.time() - phase_start, time.time()


    # ========================================================================================================
    # Phase 2: Generate Sky Conditions for Analysis Period
    # ========================================================================================================
    print(f"\n{'=' * 100}\nPhase 2: Generatore Sky Conditions for Analysis period...\n{'=' * 100}")

    sky_generator = SkyGenerator(lat=project_latitude)  # Input projcts latitude to at least 4 decimal places
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                           = month,
        day                             = day,
        start_hour_24hr_format          = start_hour,
        end_hour_24hr_format            = end_hour,
        minute_increment                = timestep
        )
    phase_timings["Phase 2: Sky Conditions"], phase_start = time.time() - phase_start, time.time()


    # ========================================================================================================
    # Phase 3: Generate Camera Views
    # ========================================================================================================
    print(f"\n{'=' * 100}\nPhase 3: Configuring Camera Views...\n{'=' * 100}")

    view_generator = ViewGenerator(
        room_boundaries_csv_path        = room_boundaries_csv_path,
        ffl_offset                      = finished_floor_level_offset
        )
    view_generator.create_plan_view_files()

    phase_timings["Phase 3: Camera Views"], phase_start = time.time() - phase_start, time.time()


    # ========================================================================================================
    # Phase 4: Execute Rendering Pipeline
    # ========================================================================================================
    print(f"\n{'=' * 100}\nPhase 4: Executing Rendering Pipeline...\n{'=' * 100}")

    renderer = RenderingPipelines(
        skyless_octree_path             = octree_generator.skyless_octree_path,
        overcast_sky_file_path          = sky_generator.TenK_cie_overcast_sky_file_path,
        skies_dir                       = sky_generator.sky_file_dir,
        views_dir                       = view_generator.view_file_dir,
        x_res                           = image_resolution,
        y_res                           = image_resolution
        )
    rendering_phase_timings = renderer.sunlight_rendering_pipeline(
        render_mode                     =rendering_mode, 
        gpu_quality                     =rendering_quality
        )

    phase_timings.update(rendering_phase_timings)
    phase_timings["Phase 4: Rendering"], phase_start = time.time() - phase_start, time.time()


    # ========================================================================================================
    # Phase 5: Post-process all frames into .csv .wpd results and .gif with compliance stamps
    # ========================================================================================================
    print(f"\nPhase 5: Execute Post-Processing of Results...\n{'=' * 100}")

    # --------------------------------------------------------------------------------------------------------
    # Phase 5a: Generate Area of Interest (AOI) files
    # --------------------------------------------------------------------------------------------------------
    sub_phase_start = time.time()
    coordinate_map_path = utils.create_pixel_to_world_coord_map(renderer.image_dir)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)
 
    phase_timings["  5a: Generate AOI"], sub_phase_start = time.time() - sub_phase_start, time.time()
    
    # --------------------------------------------------------------------------------------------------------
    # Phase 5b: Generate Working plane data (WPD) and .csv results for sunlit areas ---
    # --------------------------------------------------------------------------------------------------------
    processor = ResultsProcessor(
        image_dir                       = renderer.image_dir,
        aoi_dir                         = view_generator.aoi_dir,
        wpd_dir                         = Path(__file__).parent.parent / "outputs" / "wpd",
        pixel_threshold_value           = 0,
        max_workers                     = 12,
        pixel_to_world_map              = coordinate_map_path
        ) 
    processor.sunlight_sequence_wpd_extraction()

    phase_timings["  5b: Generate WPD"], sub_phase_start = time.time() - sub_phase_start, time.time()

    # --------------------------------------------------------------------------------------------------------
    # Phase 5c: Stamp results onto images and generate combined gifs
    # --------------------------------------------------------------------------------------------------------
    image_processor = ImageProcessor(
        skyless_octree_path             = octree_generator.skyless_octree_path,
        overcast_sky_file_path          = sky_generator.TenK_cie_overcast_sky_file_path,
        sky_files_dir                   = sky_generator.sky_file_dir,
        view_files_dir                  = view_generator.view_file_dir,
        image_dir                       = renderer.image_dir,
        x_res                           = renderer.x_res,
        y_res                           = renderer.y_res,
        latitude                        = sky_generator.lat
        )
    image_processor.nsw_adg_sunlight_access_results_pipeline()


    phase_timings["  5c: Stamp Images"] = time.time() - sub_phase_start
    phase_timings["Phase 5: Post-Processing"] = time.time() - phase_start


    # ========================================================================================================
    # Phase 6: Final Packaging of Results
    # ========================================================================================================
    print(f"\nPhase 6: Packaging Final Results...\n{'=' * 100}")



    # Print final summary with timing breakdown
    total_runtime = time.time() - script_start_time
    utils.print_timing_report(
        phase_timings=phase_timings,
        total_runtime=total_runtime,
        output_dir=Path(__file__).parent.parent / 'outputs'
    )

    return True


if __name__ == "__main__":
    main()