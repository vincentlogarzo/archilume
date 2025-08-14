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

# Standard library imports
from pathlib import Path

# Archilume imports  
from archilume.sky_generator import SkyFileGenerator
from archilume.view_generator import ViewFileGenerator
from archilume.obj_to_octree import ObjToOctree 
from archilume.utils import select_files


def main():
    """Execute the winter solstice daylight analysis workflow."""
    
    # --- Step 1. Generate Octree utilising building obj(s) and site obj(s) and their respective .mtl files ---
    # This octree can only be used for sunlight exposure analysis as material modifiers are assumed (i.e. colour and matieral type, glass, plastic, or metal)

    # Locate the room boundaries CSV file
    obj_file_paths = select_files(title="Select obj files")
    mtl_file_paths = [Path(obj_path).with_suffix('.mtl') for obj_path in obj_file_paths]

    octree_generator = ObjToOctree(
        obj_file_paths,
        mtl_file_paths
        )
    
    octree_generator.create_skyless_octree_for_sunlight_analysis()
    # TODO The implementation of multiple obj files is not yet supported, so only one obj file can be selected at a time. to be rectified in the input of ObjToOctree class.
    

    # --- Step 2: Generate Sky Files ---
    # Create sky files representing sun positions throughout the day
    
    print("Generating sky files for winter solstice analysis...")
    
    sky_generator = SkyFileGenerator(
        lat=-37.8136,                    # Melbourne latitude 
        month=6,                         # June (winter solstice)
        day=21,
        start_hour_24hr_format=9,        # 9:00 AM
        end_hour_24hr_format=15,         # 3:00 PM
        minute_increment=5               # Every 5 minutes
    )
    
    sky_generator.generate_sunny_sky_series()
    print("✓ Sky files generated in 'intermediates/sky/' directory")
    

    # --- Step 3: Generate View Files ----
    # Create view parameter files for building floor plans and Axonometric flyover images
    
    print("\nGenerating view files for building analysis...")
    
    # Locate the room boundaries CSV file
    script_dir = Path(__file__).parent
    csv_path = script_dir.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv"
    
    # Check if CSV file exists
    if not csv_path.exists():
        print(f"Error: Room boundaries CSV not found at {csv_path}")
        print("Please ensure the input file exists before running this analysis.")
        return False
    
    view_generator = ViewFileGenerator(
        room_boundaries_csv_path_input=csv_path,
        ffl_offset=1.0                   # Camera height above floor (eye level)
    )
    
    view_generator.create_aoi_and_view_files()


    # --- Step 4: Render scene for each view file octree and sky file combination octree for each timestep ----
    # Parallel processing will be used by default for all the following steps, it will utilise 75% of the cores available on the computer it is on. This step must combine the skyless octree with the sky file for each timestep, it will then render that combined octree using each view file and then destroy the root created octree used for rendering, it will natively check if the output files exist and skip running these commands again. This step must overlay only the illuminated pixels onto a higher quality rendering for each level, as the direct sunlight with -ab parameter set to 0 will produce images that show only the sunlight. 


    

    # --- Step 5: Post process results  ----
    # Post processing of the results will then occur on all ouptut images and results files. Create combined gif with room boundaries overlay, results for each time step on the images and the area of compliance, and the FFL of that level from the room boundaries for clarity. create final image that can be used in overlay that provides a heat map with user editable colour palette to reveal the number of timesteps in which a pixel has sunlight exposure. The ouput should then be gifs with overlay, final image for each level of the building as .tiff for import to revit, spreadsheet summary of results



    # --- Step 6: Analysis Setup Complete ---
    
    print("\n" + "="*60)
    print("WINTER SOLSTICE ANALYSIS SETUP COMPLETE")
    print("="*60)
    print(f"Location: Melbourne, Australia ({sky_generator.lat}°S")
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