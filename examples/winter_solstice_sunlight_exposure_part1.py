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
from archilume.sunlight_rendering_engine import SunlightRenderingEngine


# Standard library imports
from pathlib import Path
import sys

# Third-party imports 

def main():
    """Execute the winter solstice daylight analysis workflow."""

    # Locate the room boundaries CSV file
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj",
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj"
        ]     # TODO: currently only takes in Obj files exported in meters. Future iteration should handle .obj file exported in milimeters.

    # Locate the room boundaries CSV file of the building of interest to this study. This should be exported from Revit
    csv_path = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv" # TODO: future iteration to allow input of .rvt file to extract room boundaries. 
    # Check if CSV file exists
    if not csv_path.exists():
        print(f"\nError: Room boundaries CSV not found at {csv_path}")
        sys.exit(1)


    # Phase 1: Establish Three-Dimensional Spatial Foundation
    # Synthesize architectural geometry and contextual site elements into computational octree structure
    # Note: Material properties are standardized for solar analysis (surface reflectance characteristics assumed)
    octree_generator = ObjToOctree(obj_paths)
    octree_generator.create_skyless_octree_for_analysis()


    # Phase 2: Define Celestial Illumination Conditions
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
    sky_generator.generate_sunny_sky_series() # TODO: input class inputs to this function as inputs to the class, therefore the class can be instantiated without any variables, unless a wants to override the defaults.
    sky_generator.generate_overcast_skyfile()


    # Phase 3: Configure Analytical Observation Framework
    # Establish strategic viewpoints for comprehensive architectural space evaluation and axonometric visualization
    
    print("\nGenerating view files for building analysis...")
    
    view_generator = ViewFileGenerator(
        room_boundaries_csv_path_input=csv_path,
        ffl_offset = 1.0 # Image height plane above floor
    )
    view_generator.create_view_files()


    # Phase 4: Execute Comprehensive Solar Analysis Pipeline
    # Process all geometric-temporal combinations with advanced post-processing for regulatory compliance assessment
    sunlight_renderer = SunlightRenderingEngine()

    sunlight_renderer.render_sequences()


    
    return True


if __name__ == "__main__":
    main()