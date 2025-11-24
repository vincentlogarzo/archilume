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


def main():
    # Start runtime tracking
    script_start_time = time.time()
    phase_timings = {}  # Store phase execution times

    print(f"\n{'=' * 80}\nARCHILUME - Winter Solstice Sunlight Exposure Analysis\n{'=' * 80}")

    # --- Phase 0: List building, site and other adjacent building files and input parameters --- 
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows_cleaned.obj", # first file must be building of interest
        Path(__file__).parent.parent / "inputs" / "87cowles_site_cleaned.obj" # REVIT .obj files must be exported in meters, coarse with visual style set to hidden line, all adjacent buildings should have their geomety decimated to reduce file size and speed up processing times.
        ]    
        # FIXME: currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 
    room_boundaries_csv_path            = Path(__file__).parent.parent / "inputs" / "87cowles_BLD_room_boundaries.csv"     
        # FIXME: the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing.

    project_latitude                    = -33.8244778   # Input building projcts latitude to at least 4 decimal places
    month                               = 6             # June
    day                                 = 21            # Winter solstice
    start_hour                          = 9             # 9:00 AM
    end_hour                            = 15            # 3:00 PM
    timestep                            = 5            # Minutes (must be greater than 5 min increments) 
    finished_floor_level_offset         = 1.0           # Meters above finished floor level for camera height
    image_resolution                    = 2048          # Image size in pixels to be rendered


    # --- Phase 1: Establish 3D Scene ---
    print(f"\n{'=' * 80}\nPhase 1: Establishing 3D Scene...\n{'=' * 80}")
    phase_start = time.time()

    octree_generator = ObjToOctree(obj_paths)
        # FIXME:  move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here.
    octree_generator.create_skyless_octree_for_analysis()

    phase_timings["Phase 1: 3D Scene"], phase_start = time.time() - phase_start, time.time()


    # --- Phase 2: Generate Sky Conditions for Analysis Period ---
    print(f"\n{'=' * 80}\nPhase 2: Generatore Sky Conditions for Analysis period...\n{'=' * 80}")

    sky_generator = SkyGenerator(lat=project_latitude)  # Input building projcts latitude to at least 4 decimal places
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                           = month,
        day                             = day,
        start_hour_24hr_format          = start_hour,
        end_hour_24hr_format            = end_hour,
        minute_increment                = timestep
        )
        # TODO: all classes here that utilise a number of workers should have a user input to define number of workers. Currently defaults to all available cores which may not be ideal for all users.
    phase_timings["Phase 2: Sky Conditions"], phase_start = time.time() - phase_start, time.time()


    # --- Phase 3: Generate Camera Views ---
    print(f"\n{'=' * 80}\nPhase 3: Configuring Camera Views...\n{'=' * 80}")

    view_generator = ViewGenerator(
        room_boundaries_csv_path        = room_boundaries_csv_path,
        ffl_offset                      = finished_floor_level_offset
        )
    view_generator.create_plan_view_files()

    phase_timings["Phase 3: Camera Views"], phase_start = time.time() - phase_start, time.time()


    # --- Phase 4: Execute Rendering Pipeline ---
    print(f"\n{'=' * 80}\nPhase 4: Executing Rendering Pipeline...\n{'=' * 80}")

    renderer = RenderingPipelines(
        skyless_octree_path             = octree_generator.skyless_octree_path,
        overcast_sky_file_path          = sky_generator.TenK_cie_overcast_sky_file_path,
        skies_dir                       = sky_generator.sky_file_dir,
        views_dir                       = view_generator.view_file_dir,
        x_res                           = image_resolution,
        y_res                           = image_resolution
        )
    renderer.sunlight_rendering_pipeline()
        # TODO: find a way to turn on/off the indirect lighting calculation to speed up rendering times if model does not visual validation.
        # TODO: allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents.
        # TODO: implement rtrace mulitprocess rendering pipeline to speed up costly indirect rendering images.
        # TODO: implement low resolution fist pass rendering for visual validation, if higher resolution is needed then second pass at a higher resolution can be executed without much further cost.  
        # TODO: implement pfilt to downsize images for smoothing and faster processing.
    phase_timings["Phase 4: Rendering"], phase_start = time.time() - phase_start, time.time()


    # --- Phase 5: Post-process all frames into .csv .wpd results and .gif with compliance stamps ---
    print(f"\nPhase 5: Execute Post-Processing of Results...\n{'=' * 80}")


    # --- Phase 5a: Generate Area of Interest (AOI) files ---
    sub_phase_start = time.time()
    coordinate_map_path = utils.create_pixel_to_world_coord_map(renderer.image_dir)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)
        # TODO: Develop interactive interface for dynamic AOI adjustment with persistence of aoi files into the aoi_modified dir.
        # TODO: set maximum number of workers checks within classes to ensure this value cannot exceed available cores on the users machine.
        # TODO: vertical plane generation based on failing apartment results is also allowable, generation of views basedon the aoi room boundaries would then be necessary and subsequent rendering pipeline for these vertical surfaces without offset. 

    phase_timings["  5a: Generate AOI"], sub_phase_start = time.time() - sub_phase_start, time.time()


    # --- Phase 5b: Generate Working plane data (WPD) and .csv results for sunlit areas ---
    processor = ResultsProcessor(
        image_dir                       = renderer.image_dir,
        aoi_dir                         = view_generator.aoi_dir,
        wpd_dir                         = Path(__file__).parent.parent / "outputs" / "wpd",
        pixel_threshold_value           = 0,
        max_workers                     = 20,
        pixel_to_world_map              = coordinate_map_path
        ) # TODO: ensure modified file are used when they exist.
    processor.nsw_adg_sunlight_sequence_wpd_extraction()
        #TODO:             # serious optimisation of the wpd extraction needs to occur. 


    phase_timings["  5b: Generate WPD"], sub_phase_start = time.time() - sub_phase_start, time.time()


   # --- Phase 5c: Stamp results onto images and generate combined gifs ---
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
        # TODO:
            # add implementation to stamp these tiffs with the .wpd results using a very simple matplotlib
                # Calculate illumination metrics per spatial zone with regulatory threshold evaluation for nsw adg compliance
            # chart overlay onto combined gifs. 
            # automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value.

    phase_timings["  5c: Stamp Images"] = time.time() - sub_phase_start
    phase_timings["Phase 5: Post-Processing"] = time.time() - phase_start


    # --- Phase 6: Final Packaging of Results ---
    print(f"\nPhase 6: Packaging Final Results...\n{'=' * 80}")
    # TODO: package all key results into a single output directory for user convenience and zip this dir for easy sharing.





    # Print final summary with timing breakdown
    total_runtime = time.time() - script_start_time
    print("\n" + "=" * 80 + "\nANALYSIS COMPLETE\n" + "=" * 80 + "\n\nExecution Time Summary:\n" + "-" * 80)

    # Print each phase timing
    for phase_name, duration in phase_timings.items():
        percentage = (duration / total_runtime) * 100
        print(f"{phase_name:<30} {duration:>8.2f}s  ({percentage:>5.1f}%)")

    print("-" * 80 + f"\n{'Total Runtime':<30} {total_runtime:>8.2f}s  ({total_runtime/60:>5.1f} min)\n" + "=" * 80 + f"\n\nOutput directory: {Path(__file__).parent.parent / 'outputs'}\n" + "=" * 80)

    return True


if __name__ == "__main__":
    main()