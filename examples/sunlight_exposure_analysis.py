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

# Archilume imports
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator
from archilume.obj_to_octree import ObjToOctree
from archilume.rendering_pipelines import RenderingPipelines
from archilume.image_processor import ImageProcessor
from archilume import utils

# Standard library imports
from pathlib import Path

# Third-party imports


def main():
    """Execute the winter solstice daylight analysis workflow."""

    # List building, site and other adjacent building files and input parameters
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj", # first file must be building of interest
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj" # REVIT .obj files must be exported in meters.
        ]    # FIXME: currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 

    room_boundaries_csv_path = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv"

    project_latitude = -33.8244778      # Input building projcts latitude to at least 4 decimal places
    month = 6                           # June
    day = 21                            # Winter solstice
    start_hour = 9                      # 9:00 AM
    end_hour = 15                       # 3:00 PM
    timestep = 10                       # Minutes
    finished_floor_level_offset = 1.0   # Meters above finished floor level for camera height
    image_resolution = 2048              # Image size in pixels to be rendered
    # TODO: add a variable here for the ADG compliance metric which is depended on systney metropolitan area or not. A simple TRUE/FALSE boolean variable would suffice.
    

    # --- Phase 1: Establish 3D Scene ---
    # Convert building and site geometry into octree structure with standard materials
    octree_generator = ObjToOctree(obj_paths) #FIXME move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here. 
    octree_generator.create_skyless_octree_for_analysis()


    # --- Phase 2: Define external sky conditions for each time step ---
    # Generate comprehensive solar position matrix for critical winter solstice temporal analysis
    print("\nGenerating sky files for winter solstice analysis 'outputs/sky/' directory\n")

    sky_generator = SkyGenerator(lat=project_latitude)  # Input building projcts latitude to at least 4 decimal places
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                           = month,
        day                             = day,
        start_hour_24hr_format          = start_hour,    
        end_hour_24hr_format            = end_hour,
        minute_increment                = timestep
        ) #TODO: all classes here that utilise a number of workers should have a user input to define number of workers. Currently defaults to all available cores which may not be ideal for all users.


    # --- Phase 3: Configure camera view from which images will be taken ---
    # Establish strategic viewpoints for comprehensive architectural space evaluation and axonometric visualization
    print("\nGenerating view files for building analysis...\n")

    # FIXME: the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing. 
    view_generator = ViewGenerator(
        room_boundaries_csv_path        = room_boundaries_csv_path,
        ffl_offset                      = finished_floor_level_offset
        )
    view_generator.create_plan_view_files() 


    # --- Phase 4: Execute Comprehensive Solar Analysis Pipeline
    # Process all geometric-temporal combinations with advanced post-processing for regulatory compliance assessment
    print("\nRenderingPipelines getting started...\n")

    renderer = RenderingPipelines(
        skyless_octree_path             = octree_generator.skyless_octree_path,
        overcast_sky_file_path          = sky_generator.TenK_cie_overcast_sky_file_path,
        sky_files_dir                   = sky_generator.sky_file_dir,
        view_files_dir                  = view_generator.view_file_dir,
        x_res                           = image_resolution, 
        y_res                           = image_resolution
        ) #TODO allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents.
    renderer.sunlight_rendering_pipeline()


    # --- Phase 5: Post-process all image frames into compliance mp3, gifs, and csv results ---
    print("\nImageProcessor getting started...\n")

    # Generate AOI perimeter points to stamp onto images using a rendered .HDR image
    coordinate_map_path = utils.create_pixel_to_world_coord_map(renderer.image_dir)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path) #TODO: allow multiprocessing of the file generation. its relatively time consuming to generate these sequentially

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
    image_processor.nsw_adg_sunlight_access_results_pipeline() #FIXME automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value.

    # Phase 4c: Quantitative Compliance Analysis and Data Export
    # Calculate illumination metrics per spatial zone with regulatory threshold evaluation
    # TODO: Develop interactive interface for dynamic AOI adjustment with persistence of aoi files for future analysis
    

    return True


if __name__ == "__main__":
    main()