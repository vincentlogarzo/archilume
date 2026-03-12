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
    # 2. Run the standardized workflow
    inputs = IESVEDaylightWorkflow.InputsValidator(
        project                     = "527DP_demo",  # Required: project name under projects/ (e.g. projects/527DP/)
        octree_path                 = "L7_Lightwell_260226.oct",  # Must use 10KLx sky
        rendering_params            = "preview.rdp",
        iesve_room_data             = "aoi/iesve_room_data.csv",
        image_resolution            = 2048,
        ffl_offset                  = 0.0,  # Camera height above floor (m)
    )

    workflow = IESVEDaylightWorkflow()
    workflow.run(inputs)


if __name__ == "__main__":
    run_daylight_analysis()