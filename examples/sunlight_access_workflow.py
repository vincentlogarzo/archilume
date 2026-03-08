"""
Archilume Example: Sunlight Exposure Analysis (Simplified)
=============================================================

This example demonstrates how to configure and run a sunlight 
access workflow to determine the quantity of sunlight on 
horizontal plane over a single day across many rooms in a
building. The core simulation logic is handled by the 
`SunlightAccessWorkflow` class in sunlight_access_workflow.py

Workflow Overview:
1. Load 3D geometry (OBJ/MTL).
2. Generate solar conditions for a specific date/latitude.
3. Render time-series floor plans.
4. Export results to Excel and animated APNG/GIF.
"""

# fmt: off
# autopep8: off

from archilume.workflows import SunlightAccessWorkflow

def run_sunlight_analysis():
    # 1. Define simulation parameters and paths
    inputs = SunlightAccessWorkflow.InputsValidator(
        building_latitude   = -37.8134,  # Melbourne, Australia
        month               = 6,         # June
        day                 = 21,        # Winter Solstice
        start_hour          = 9,         # 9:00 AM
        end_hour            = 15,        # 3:00 PM
        timestep            = 15,        # 15-minute intervals
        ffl_offset          = 1.0,       # Camera height above floor (m)
        image_resolution    = 2048,      # Pixel resolution
        rendering_mode      = "gpu",     # Backend: 'cpu' or 'gpu'
        rendering_quality   = "stand",   # Quality: 'draft', 'stand', 'prod', etc.
        animation_format    = "apng",    # Options: 'apng', 'gif'
        project             = "cowles",  # Optional: project sub-folder within inputs/
        room_boundaries_csv = "87cowles_BLD_room_boundaries.csv",
        obj_paths           = [
                                "87Cowles_BLD_withWindows.obj",
                                "87cowles_site_decimated.obj" #add to this list if necessary
                                ]
    )

    # 2. Run the standardized workflow
    workflow = SunlightAccessWorkflow()
    workflow.run(inputs)

if __name__ == "__main__":
    run_sunlight_analysis()
