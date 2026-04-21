from dataclasses import dataclass
from pathlib import Path
from typing import List
import math

from archilume import config
from archilume.utils import clear_outputs_folder, PhaseTimer
from archilume.core.sky_generator import SkyGenerator
from archilume.core.view_generator import ViewGenerator
from archilume.core.objs2octree import Objs2Octree
from archilume.core.rendering_pipelines import SunlightRenderer


@dataclass
class SunlightAccessWorkflow:
    """Render sun-only sunlight-access frames as HDR + PNG per timestep.

    The app consumes the PNGs directly for its time-series movie. AOI/WPD
    extraction and APNG/MP4 stamping are deliberately *not* part of this
    workflow — those live in separate post-processing steps.
    """

    def run(
        self,
        *,
        building_latitude: float,
        month: int,
        day: int,
        start_hour: int,
        end_hour: int,
        timestep_min: int,
        ffl_offset_mm: float,
        grid_resolution_mm: int,
        aoi_inputs_dir: Path,
        obj_paths: List[Path],
        project: str,
        include_overcast: bool = False,
        rendering_mode: str = "cpu",
        rendering_quality: str = "stand",
    ) -> bool:
        """Execute the sunlight access pipeline.

        Args:
            include_overcast: When True, also render the overcast ambient baseline
                and composite it onto each sun frame via pcomb (full sunlight
                pipeline). When False (default), run the sun-only pipeline —
                faster, no ambient bounce light.
            rendering_mode: "cpu" or "gpu". Only consulted when
                include_overcast=True; the sun-only path is CPU-only.
            rendering_quality: GPU quality preset — one of "draft", "stand",
                "prod", "final", "4k", "custom", "fast", "med", "high",
                "detailed". Ignored when rendering_mode="cpu".
        """
        timer = PhaseTimer()

        paths = config.get_project_paths(project)
        ffl_offset_m = ffl_offset_mm / 1000

        print("\n" + "=" * 100)
        print(f"{'SUNLIGHT ACCESS WORKFLOW (sun-only)':^100}")
        print("=" * 100)
        print(f"{'Project':<30} {project}")
        print(f"{'Building Latitude':<30} {building_latitude}")
        print(f"{'Date':<30} {month}/{day}")
        print(f"{'Time Range':<30} {start_hour}:00 - {end_hour}:00")
        print(f"{'Timestep':<30} {timestep_min} min")
        print(f"{'Camera Height (FFL)':<30} {ffl_offset_mm} mm ({ffl_offset_m} m)")
        print(f"{'Grid Resolution':<30} {grid_resolution_mm} mm/px")
        print(f"{'Overcast Baseline':<30} {'ON' if include_overcast else 'OFF (sun-only)'}")
        if include_overcast:
            print(f"{'Rendering Mode':<30} {rendering_mode.upper()}")
            if rendering_mode == 'gpu':
                print(f"{'Rendering Quality':<30} {rendering_quality}")
        print(f"{'AOI Inputs Dir':<30} {aoi_inputs_dir}")
        print(f"{'Geometry Files':<30} {len(obj_paths)}")
        for i, obj in enumerate(obj_paths, 1):
            print(f"  {i}. {obj.name}")
        print("=" * 100 + "\n")

        with timer("Phase 0: Setup and Cleanup"):
            paths.create_dirs()
            clear_outputs_folder(paths)

        with timer("Phase 1: Establishing 3D Scene"):
            octree_generator = Objs2Octree(
                input_obj_paths=obj_paths,
                output_dir=paths.octree_dir,
                rad_dir=paths.rad_dir,
            )
            octree_generator.create_skyless_octree_for_analysis()

        with timer("Phase 2: Generate Sky Conditions"):
            sky_generator = SkyGenerator(
                lat=building_latitude,
                sky_file_dir=paths.sky_dir,
            )
            sky_generator.generate_sunny_sky_series(
                month=month,
                day=day,
                start_hour_24hr_format=start_hour,
                end_hour_24hr_format=end_hour,
                minute_increment=timestep_min,
            )
            if include_overcast:
                sky_generator.generate_TenK_cie_overcast_skyfile()

        with timer("Phase 3: Prepare Camera Views"):
            view_generator = ViewGenerator(
                aoi_inputs_dir=aoi_inputs_dir,
                ffl_offset=ffl_offset_m,
                view_file_dir=paths.view_dir,
                aoi_dir=paths.aoi_dir,
            )
            view_generator.create_plan_view_files()

            view_h_mm = view_generator.view_horizontal * 1000
            image_resolution = math.ceil(view_h_mm / grid_resolution_mm)

            if image_resolution < 128:
                print(f"[!] WARNING: Computed resolution {image_resolution}px is below 128px.")
                print(f"    This is unlikely to produce useful results. Consider decreasing grid_resolution_mm.")
            if image_resolution > 4000:
                print(f"[!] WARNING: Computed resolution {image_resolution}px exceeds 4000px.")
                print(f"    grid_resolution_mm={grid_resolution_mm}mm on view width {view_generator.view_horizontal:.2f}m")
                print(f"    This may cause long render times or memory issues. Consider increasing grid_resolution_mm.")
            if image_resolution > 6000:
                raise ValueError(
                    f"Computed resolution {image_resolution}px exceeds 6000px hard limit. "
                    f"Increase grid_resolution_mm to reduce pixel count."
                )

            print(f"Grid: {grid_resolution_mm}mm/px -> Resolution: {image_resolution}px "
                  f"(view width: {view_generator.view_horizontal:.2f}m)")

        phase_label = (
            "Phase 4: Render overcast + sun frames + PNGs"
            if include_overcast else
            "Phase 4: Render sun-only frames + PNGs"
        )
        with timer(phase_label):
            renderer = SunlightRenderer(
                skyless_octree_path=octree_generator.skyless_octree_path,
                x_res=image_resolution,
                y_res=image_resolution,
                skies_dir=paths.sky_dir,
                views_dir=paths.view_dir,
                image_dir=paths.image_dir,
                overcast_sky_file_path=(
                    sky_generator.TenK_cie_overcast_sky_file_path
                    if include_overcast else None
                ),
                rendering_mode=rendering_mode,
                gpu_quality=rendering_quality,
            )
            if include_overcast:
                renderer.sunlight_rendering_pipeline()
            else:
                renderer.sun_only_rendering_pipeline()

        timer.print_report(output_dir=paths.outputs_dir)
        return True
