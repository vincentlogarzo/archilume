"""
Archilume Example: IESVE Daylight Factor Analysis
=============================================================

Daylight factor (DF) analysis using a pre-built IESVE octree 
(10K lux CIE overcast sky). Converts IESVE room data + AOI files
 into Radiance views, renders per floor, and exports HDR results.

Note:   Runs fastest in the dev container via rtpict multiprocessing
        (20 CPUs ≈ 20x speedup vs native Windows).

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
        project                     = "527DP-gcloud-lowRes-GregW",  # Required: project name under projects/ (e.g. projects/527DP/)
        octree_path                 = "527DP.oct",  # Must use 10KLx sky
        rendering_params            = "high_GregW.rdp",
        iesve_room_data             = "aoi/iesve_room_data.csv",
        image_resolution            = 1280,
        ffl_offset                  = 1.54,  # Camera height above floor (m)
        use_ambient_file            = True,  # Enable/disable ambient file warming pass
        n_cpus                      = 32,   # Number of CPUs for rtpict (None = all available)
    )

    smart_cleanup(
        inputs.paths,
        resolution_changed          = True,
        rendering_quality_changed   = True,
    )

    workflow = IESVEDaylightWorkflow()
    workflow.run(inputs)


if __name__ == "__main__":
    run_daylight_analysis()