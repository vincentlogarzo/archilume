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

    # List building, site and other adjacent building files
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj", # first file must be building of interest
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj" # REVIT .obj files must be exported in meters.
        ]    # FIXME: currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 


    # --- Phase 1: Establish 3D Scene ---
    # Convert building and site geometry into octree structure with standard materials
    octree_generator = ObjToOctree(obj_paths) #FIXME move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here. 
    octree_generator.create_skyless_octree_for_analysis()


    # --- Phase 2: Define external sky conditions for each time step ---
    # Generate comprehensive solar position matrix for critical winter solstice temporal analysis
    print("\nGenerating sky files for winter solstice analysis 'outputs/sky/' directory\n")

    sky_generator = SkyGenerator(lat=-37.8136)  # Input your projects latitude to 4 decimal places
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series(
        month                           = 6,        # June
        day                             = 21,       # Winter solstice
        start_hour_24hr_format          = 9,        # 9:00 AM
        end_hour_24hr_format            = 15,       # 3:00 PM
        minute_increment                = 10        # Minutes
        )


    # --- Phase 3: Configure camera view from which images will be taken ---
    # Establish strategic viewpoints for comprehensive architectural space evaluation and axonometric visualization
    print("\nGenerating view files for building analysis...\n")

    # TODO: future iteration to allow input of .rvt file to extract room boundaries.
    view_generator = ViewGenerator(
        room_boundaries_csv_path        = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv",
        ffl_offset                      = 1.0 # Image height plane in meters above finished floor level
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
        x_res                           = 2048, # image x pixels 
        y_res                           = 2048  # image y pixels
        ) #FIXME allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents.
    renderer.sunlight_rendering_pipeline()


    # --- Phase 5: Post-process all image frames into compliance mp3, gifs, and csv results ---
    print("\nImageProcessor getting started...\n")

    # Generate AOI perimeter points to stamp onto images using a rendered .HDR image
    coordinate_map_path = utils.create_pixel_to_world_coord_map(renderer.image_dir)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path) #TODO: allow multiprocessing of the file generation. its relatiely time consuming to generate these serially. 

    # Third pass overlay of the results of each time step on each .gif file for each aoi, there may need to be work to exclude full height or determine of % of compliant area. If its an absolute amount of area, then discrpancies between the AOI and say kitchen joinery does not need ot be considere , it is is a % of compliance area, then excluding part of the aoi that are acually our of bounds is important.Also output a csv file with the results of each aoi

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
    image_processor.sepp65_results_pipeline() #FIXME automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value.

    # Phase 4c: Quantitative Compliance Analysis and Data Export
    # Calculate illumination metrics per spatial zone with regulatory threshold evaluation
    # TODO: Develop interactive interface for dynamic AOI adjustment with persistence of aoi files for future analysis
    

    return True


if __name__ == "__main__":
    main()