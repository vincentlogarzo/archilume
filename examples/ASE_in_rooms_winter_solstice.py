"""
Archilume Example: Winter Solstice Sunlight Analysis
===================================================

This example demonstrates how to use Archilume to analyze daylight conditions
during the winter solstice (June 21st in the Southern Hemisphere).

The analysis includes:
1. Generating sky files for specified time ranges
2. Creating view files for building floor plans
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


def main():
    """Execute the winter solstice daylight analysis workflow."""
    
    # === Step 1: Generate Sky Files ===
    # Create sky files representing sun positions throughout the day
    
    print("Generating sky files for winter solstice analysis...")
    
    sky_generator = SkyFileGenerator(
        lat=-37.8136,                    # Melbourne latitude
        lon=144.9631,                    # Melbourne longitude  
        std_meridian=145.0,              # Australian Eastern Standard Time
        year=2024,
        month=6,                         # June (winter solstice)
        day=21,
        start_hour_24hr_format=9,        # 9:00 AM
        end_hour_24hr_format=15,         # 3:00 PM
        minute_increment=5               # Every 5 minutes
    )
    
    sky_generator.generate_sunny_sky_series()
    print("✓ Sky files generated in 'intermediates/sky/' directory")
    
    
    # === Step 2: Generate View Files ===
    # Create view parameter files for building floor plans
    
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
    
    success = view_generator.create_aoi_and_view_files()
    
    if success:
        print("✓ View files generated successfully")
        print("  - AOI files: 'aoi/' directory")
        print("  - View parameter files: 'intermediates/views_grids/' directory")
    else:
        print("✗ Failed to generate view files. Check the CSV file format and content.")
        return False
    
    
    # === Step 3: Analysis Setup Complete ===
    
    print("\n" + "="*60)
    print("WINTER SOLSTICE ANALYSIS SETUP COMPLETE")
    print("="*60)
    print(f"Location: Melbourne, Australia ({sky_generator.lat}°S, {sky_generator.lon}°E)")
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