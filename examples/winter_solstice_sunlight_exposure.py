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
        ]

    # Locate the room boundaries CSV file of the building of interest to this study. This should be exported from Revit
    #TODO: future iteration of this code will allow for input of a revit file, and use of revit API to extract the room boundaries csv, this could also be visualised in the obj_viewer.py example file.
    csv_path = Path(__file__).parent.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv"
    

    # --- Step 1. Generate Octree utilising building obj(s) and site obj(s) and their respective .mtl files ---
    # This octree can only be used for sunlight exposure analysis as material modifiers are assumed (i.e. colour and matieral type, glass, plastic, or metal)
    
    octree_generator = ObjToOctree(obj_paths)
    octree_generator.create_skyless_octree_for_analysis()

    
    # --- Step 2: Generate Sky Files ---
    # Create sky files representing sun positions throughout the day
    
    print("\nGenerating sky files for winter solstice analysis 'outputs/sky/' directory")
    
    sky_generator = SkyFileGenerator(
        lat                             = -37.8136, # Melbourne latitude 
        month                           = 6,        # June (winter solstice)
        day                             = 21,
        start_hour_24hr_format          = 9,        # 9:00 AM
        end_hour_24hr_format            = 15,       # 3:00 PM
        minute_increment                = 30        # Minutes
    )

    sky_generator.generate_sunny_sky_series()
    sky_generator.generate_overcast_skyfile()


    # --- Step 3: Generate View Files ----
    # Create view parameter files for building floor plans and Axonometric flyover images
    
    print("\nGenerating view files for building analysis...")
    
    # Check if CSV file exists
    if not csv_path.exists():
        print(f"\nError: Room boundaries CSV not found at {csv_path}")
        sys.exit(1)
    
    view_generator = ViewFileGenerator(
        room_boundaries_csv_path_input=csv_path,
        ffl_offset=1.0                   # Image height plane above floor
    )
    
    view_generator.create_aoi_and_view_files()


    # --- Step 4: Render scene for each view file octree and sky file combination octree for each timestep ----



    # --- Step 5: Post process results  ----
    # Post processing of the results will then occur on all ouptut images and results files. Create combined gif with room boundaries overlay, results for each time step on the images and the area of compliance, and the FFL of that level from the room boundaries for clarity. create final image that can be used in overlay that provides a heat map with user editable colour palette to reveal the number of timesteps in which a pixel has sunlight exposure. The ouput should then be gifs with overlay, final image for each level of the building as .tiff for import to revit, spreadsheet summary of results


    # --- Step 6: Analysis Setup Complete ---
    
    print("\n" + "="*60)
    print("WINTER SOLSTICE ANALYSIS SETUP COMPLETE")
    print("="*60)
    print(f"Location: Melbourne, Australia ({sky_generator.lat}")
    print(f"Date: {sky_generator.month}/{sky_generator.day}/{sky_generator.year}")
    print(f"Time range: {sky_generator.start_hour_24hr_format}:00 - {sky_generator.end_hour_24hr_format}:00")
    print(f"Time intervals: {sky_generator.minute_increment} minutes")
    print(f"Total sky files: {(sky_generator.end_hour_24hr_format - sky_generator.start_hour_24hr_format) * 60 // sky_generator.minute_increment + 1}")
    print("\nNext steps:")
    print("1. Use the generated sky files for Radiance lighting simulations")
    print("2. Apply view files to render floor plan daylight analysis")
    print("3. Calculate Annual Sunlight Exposure (ASE) metrics")
    
    return True


if __name__ == "__main__":
    main()