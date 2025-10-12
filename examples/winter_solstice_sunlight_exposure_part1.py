"""
Archilume Example: Winter Solstice Sunlight Analysis
===================================================

This example demonstrates how to use Archilume to analyze daylight conditions
during the winter solstice (June 21st in the Southern Hemisphere).

The analysis includes:
1. Generating sky files for specified time ranges
2. Creating view files for building floor plans
3. 
3. Setting up for Annual Sunlight Exposure (ASE) calculations

Location: Melbourne, Australia
Date: June 21, 2024 (Winter Solstice)
Analysis Period: 9:00 AM - 3:00 PM at 5-minute intervals
"""

# Archilume imports  
from archilume.sky_generator import SkyFileGenerator
from archilume.view_generator import ViewFileGenerator
from archilume.obj_to_octree import ObjToOctree
from archilume.rendering_pipelines import RenderingPipelines
from archilume.image_processor import ImageProcessor



# Standard library imports
from pathlib import Path
import sys

# Third-party imports 

def main():
    """Execute the winter solstice daylight analysis workflow."""

    # List the nominated building obj file and the site and any other supplementary geometry files like adjacent buildings
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj", # The first file must always be the building under analysis
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj" # These OBJ files must be exported from Revit in  meters.
        ]     # TODO: currently only takes in Obj files exported in meters. Future iteration should handle .obj file exported in milimeters to reduce error user error. 

    # Locate the room boundaries CSV file of the building of interest to this study. This should be exported from Revit
    csv_path = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv" # TODO: future iteration to allow input of .rvt file to extract room boundaries. 
    # Check if CSV file exists
    if not csv_path.exists():
        print(f"\nError: Room boundaries CSV not found at {csv_path}")
        sys.exit(1)


    # Phase 1: Establish 3D Scene
    # Synthesize architectural geometry and contextual site elements into computational octree structure
    # Note: Material properties are standardized for solar analysis (surface reflectance characteristics assumed)
    octree_generator = ObjToOctree(obj_paths)
    octree_generator.create_skyless_octree_for_analysis()


    # Phase 2: Define external sky conditions for each time step
    # Generate comprehensive solar position matrix for critical winter solstice temporal analysis
    
    print("\nGenerating sky files for winter solstice analysis 'outputs/sky/' directory")
    
    sky_generator = SkyFileGenerator(
        lat                             = -37.8136, # Input your projects latitude 
        month                           = 6,        # June
        day                             = 21,       # Winter solstice
        start_hour_24hr_format          = 9,        # 9:00 AM
        end_hour_24hr_format            = 15,       # 3:00 PM
        minute_increment                = 10        # Minutes
        )
    sky_generator.generate_TenK_cie_overcast_skyfile()
    sky_generator.generate_sunny_sky_series() # TODO: the inputs required to generate this sunny sky series should be here not in the class instantiation.


    # Phase 3: Configure camera view from which images will be taken
    # Establish strategic viewpoints for comprehensive architectural space evaluation and axonometric visualization
    
    print("\nGenerating view files for building analysis...")
    
    view_generator = ViewFileGenerator(
        room_boundaries_csv_path_input=csv_path,
        ffl_offset = 1.0 # Image height plane above finished floor level
        )
    view_generator.create_view_files()


    # Phase 4: Execute Comprehensive Solar Analysis Pipeline
    # Process all geometric-temporal combinations with advanced post-processing for regulatory compliance assessment
    renderer = RenderingPipelines(
        skyless_octree_path             = octree_generator.skyless_octree_path,
        overcast_sky_file_path          = sky_generator.TenK_cie_overcast_sky_file_path,
        sky_files_dir                   = sky_generator.sky_file_dir,
        view_files_dir                  = view_generator.view_file_dir,
        x_res                           = 2048, # image x pixels 
        y_res                           = 2048  # image y pixels
        )
    renderer.sunlight_rendering_pipeline()


    # Phase 5: Post-process all image frames into compliance results (video, gifs, and csv results)
    # processor = ImageProcessor()

    return True


if __name__ == "__main__":
    main()