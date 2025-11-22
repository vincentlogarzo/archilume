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

# Set Radiance environment variables before any imports
import os
os.environ['RAYPATH'] = '/usr/local/radiance/lib'
if '/usr/local/radiance/bin' not in os.environ.get('PATH', ''):
    os.environ['PATH'] = f"/usr/local/radiance/bin:{os.environ.get('PATH', '')}"

# Archilume imports
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator
from archilume.obj_to_octree import ObjToOctree
from archilume.rendering_pipelines import RenderingPipelines
from archilume.image_processor import ImageProcessor
from archilume import geometry_utils
from archilume import utils

# Standard library imports
from pathlib import Path

# Third-party imports


def main():
    """Execute the winter solstice daylight analysis workflow."""

    # --- Inputs: List building, site and other adjacent building files and input parameters --- 
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj", # first file must be building of interest
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj" # REVIT .obj files must be exported in meters.
        ]    # FIXME: currently only takes in OBJ files exported in meters. Future iteration should handle .obj file exported in millimeters to reduce error user error. 

    room_boundaries_csv_path            = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv"     # FIXME: the room boundaries data may have duplicate room names, terraces for example my have UG02T and a second room boundary called UG02T, there needs to be some care or automation of separating these for post processing.
    project_latitude                    = -33.8244778   # Input building projcts latitude to at least 4 decimal places
    month                               = 6             # June
    day                                 = 21            # Winter solstice
    start_hour                          = 9             # 9:00 AM
    end_hour                            = 15            # 3:00 PM
    timestep                            = 10            # Minutes
    finished_floor_level_offset         = 1.0           # Meters above finished floor level for camera height
    image_resolution                    = 2048          # Image size in pixels to be rendered
        # TODO: add a variable here for the ADG compliance metric which is depended on systney metropolitan area or not. A simple TRUE/FALSE boolean variable would suffice.


    # --- Phase 1: Establish 3D Scene ---
    # Convert building and site geometry into octree structure with standard materials
    octree_generator = ObjToOctree(obj_paths) 
        # FIXME:  move the obj_paths input to be inside the create_skyless_octree_for_analysis function it should not be here. 
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
        ) 
        # TODO: all classes here that utilise a number of workers should have a user input to define number of workers. Currently defaults to all available cores which may not be ideal for all users.


    # --- Phase 3: Configure camera view from which images will be taken ---
    # Establish strategic viewpoints for comprehensive architectural space evaluation and axonometric visualization
    print("\nGenerating view files for building analysis...\n")

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
        ) 
    renderer.sunlight_rendering_pipeline()
        # TODO: allow user inputs of grid size in millimeters and then have this function back calculate a pixel y and pixel x value based on the room boundary extents.
        # TODO: implement rtrace mulitprocess rendering pipeline to speed up costly indirect rendering images.


    # --- Phase 5: Post-process all frames into csv results and gifs with complianc overlays ---
    print("\nImageProcessor getting started...\n")

    # Generate Area of Interest (AOI) files
    coordinate_map_path = utils.create_pixel_to_world_coord_map(renderer.image_dir)
    view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path) 
        # TODO: Implement multiprocess for aoi file generation, it could be faster
        # TODO: Develop interactive interface for dynamic AOI adjustment with persistence of aoi files into the aoi_modified dir.



    # TODO: create a class that perform this function usinf multiprocess
        # Generate Working Plan Data (WPD) results
        # TODO: ensure there is implementation to utilise modified aoi files in place of source aoi if these exist.
        # TODO: get the values from an hdr image using pvalue below. 
            # pvalue -b +di outputs/images/87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_1500.hdr > outputs/wpd/points.txt
        # TODO: post process this points file to retain non-zero lines
        # Process this files to get the points that fall within the AOI polygons.
            # geometry_utils.ray_casting_batch(points, polygon) #TODO: implement this on the set of point that come out of each image per timestep. 
        # TODO: write the returned points to a .wpd file for each time step write file header and then all other data. 
        # TODO: write all data to a single .csv file for easier analysis later on, time steps for columns and rows for various spaces. 

   

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
            # automate the image exposure adjustment based on hdr sampling of points illuminance max values to min value.

    # TODO: package all key results into a single output directory for user convenience and zip this dir for easy sharing. 

    return True


if __name__ == "__main__":
    main()