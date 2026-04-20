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

from pathlib import Path

from archilume import config, clear_outputs_folder
from archilume.workflows import IESVEDaylightWorkflow

def run_daylight_analysis():
    project = "527DP-gcloud-lowRes-GregW"
    paths = config.get_project_paths(project)

    clear_outputs_folder(paths)

    workflow = IESVEDaylightWorkflow()
    workflow.run(
        octree_path                 = paths.inputs_dir / "527DP.oct",
        rendering_params            = paths.inputs_dir / "high_GregW.rdp",
        iesve_room_data             = paths.inputs_dir / "aoi" / "iesve_room_data.csv",
        project                     = project,
        image_resolution            = 1280,
        ffl_offset                  = 1.54,
        use_ambient_file            = True,
        n_cpus                      = 32,
    )


if __name__ == "__main__":
    run_daylight_analysis()
