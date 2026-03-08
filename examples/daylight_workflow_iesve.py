"""
Archilume Example: IESVE Daylight Factor Analysis
=============================================================

Daylight factor (DF) analysis using a pre-built IESVE octree 
(10K lux CIE overcast sky). Converts IESVE room data + AOI files
 into Radiance views, renders per floor, and exports HDR results.

Note:   Runs fastest on Linux via rtpict multiprocessing (20 CPUs
         ≈ 20x speedup vs Windows). On WSL, increase RAM/CPU limits
        in %USERPROFILE%/.wslconfig — default limits cause failures
        on large models when rtpict is used with many cores.

Input:  IESVE octree (.oct), rendering parameters (.rdp), 
        IESVE room data CSV, AOI files (.aoi)
Output: HDR images, falsecolor/contour TIFFs, view files

Workflow Overview:
1. Convert IESVE room data + AOI files into room boundary CSV.
2. Generate plan view files (.vp) per floor level.
3. Render each view against the pre-built IESVE octree.
4. Generate AOI coordinate map for post-processing.

"""

# fmt: off
# autopep8: off

from archilume import smart_cleanup
from archilume.workflows import IESVEDaylightWorkflow

def run_daylight_analysis():
    # 1. cleanup redundant files or retain .amb file for faster simulation re-run
    smart_cleanup(
        timestep_changed            = False,
        resolution_changed          = True,
        rendering_mode_changed      = False,
        rendering_quality_changed   = False
    )

    # 2. Run the standardized workflow
    inputs = IESVEDaylightWorkflow.InputsValidator(
        project                     = "527DP",  # Optional: sub-folder in inputs/
        octree_path                 = "527DP.oct",  # Must use 10KLx sky
        rendering_params            = "preview.rdp",
        iesve_room_data             = "aoi/iesve_room_data.csv",
        image_resolution            = 2048,
        ffl_offset                  = 0.0,  # Camera height above floor (m)
    )

    workflow = IESVEDaylightWorkflow()
    workflow.run(inputs)


if __name__ == "__main__":
    run_daylight_analysis()