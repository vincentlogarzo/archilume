from dataclasses import dataclass
from pathlib import Path
from typing import List
import math

from archilume import (
    SkyGenerator,
    ViewGenerator,
    Objs2Octree,
    SunlightRenderer,
    Tiff2Animation,
    Hdr2Wpd,
    smart_cleanup,
    utils,
    PhaseTimer,
    config
)


@dataclass
class SunlightAccessWorkflow:
    """
    Orchestrates a full sunlight access simulation from geometry to results.
    """

    def run(
        self,
        *,
        building_latitude: float,
        month: int,
        day: int,
        start_hour: int,
        end_hour: int,
        timestep: int,
        ffl_offset: float,
        grid_resolution: int,
        rendering_mode: str,
        rendering_quality: str,
        room_boundaries_csv: Path,
        obj_paths: List[Path],
        paths: config.ProjectPaths,
        animation_format: str = "apng",
    ) -> bool:
        """Execute the full sunlight analysis pipeline."""
        timer = PhaseTimer()

        print("\n" + "=" * 100)
        print(f"{'SUNLIGHT ACCESS WORKFLOW':^100}")
        print("=" * 100)
        print(f"{'Building Latitude':<30} {building_latitude}")
        print(f"{'Date':<30} {month}/{day}")
        print(f"{'Time Range':<30} {start_hour}:00 - {end_hour}:00")
        print(f"{'Timestep':<30} {timestep} min")
        print(f"{'Camera Height (FFL)':<30} {ffl_offset}m")
        print(f"{'Grid Resolution':<30} {grid_resolution} mm/px")
        print(f"{'Rendering Mode':<30} {rendering_mode.upper()}")
        print(f"{'Quality Preset':<30} {rendering_quality.upper()}")
        print(f"{'Room Boundaries CSV':<30} {room_boundaries_csv.name}")
        print(f"{'Geometry Files':<30} {len(obj_paths)}")
        for i, obj in enumerate(obj_paths, 1):
            print(f"  {i}. {obj.name}")
        print("=" * 100 + "\n")

        with timer("Phase 0: Setup and Cleanup"):
            paths.create_dirs()
            smart_cleanup(
                paths=paths,
                timestep_changed=True,
                resolution_changed=True,
                rendering_mode_changed=True,
                rendering_quality_changed=True
            )

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
            sky_generator.generate_TenK_cie_overcast_skyfile()
            sky_generator.generate_sunny_sky_series(
                month=month,
                day=day,
                start_hour_24hr_format=start_hour,
                end_hour_24hr_format=end_hour,
                minute_increment=timestep
            )

        with timer("Phase 3: Prepare Camera Views"):
            view_generator = ViewGenerator(
                room_boundaries_csv_path=room_boundaries_csv,
                ffl_offset=ffl_offset,
                view_file_dir=paths.view_dir,
                aoi_dir=paths.aoi_dir,
            )
            view_generator.create_plan_view_files()

            # Compute pixel resolution from grid_resolution and view horizontal extent
            view_h_mm = view_generator.view_horizontal * 1000
            image_resolution = math.ceil(view_h_mm / grid_resolution)

            if image_resolution < 128:
                print(f"[!] WARNING: Computed resolution {image_resolution}px is below 128px.")
                print(f"    This is unlikely to produce useful results. Consider decreasing grid_resolution.")
            if image_resolution > 4000:
                print(f"[!] WARNING: Computed resolution {image_resolution}px exceeds 4000px.")
                print(f"    grid_resolution={grid_resolution}mm on view width {view_generator.view_horizontal:.2f}m")
                print(f"    This may cause long render times or memory issues. Consider increasing grid_resolution.")
            if image_resolution > 6000:
                raise ValueError(
                    f"Computed resolution {image_resolution}px exceeds 6000px hard limit. "
                    f"Increase grid_resolution to reduce pixel count."
                )

            print(f"Grid: {grid_resolution}mm/px -> Resolution: {image_resolution}px "
                  f"(view width: {view_generator.view_horizontal:.2f}m)")

        with timer("Phase 4: Execute Image Rendering"):
            renderer = SunlightRenderer(
                skyless_octree_path=octree_generator.skyless_octree_path,
                overcast_sky_file_path=sky_generator.TenK_cie_overcast_sky_file_path,
                x_res=image_resolution,
                y_res=image_resolution,
                rendering_mode=rendering_mode,
                gpu_quality=rendering_quality,
                skies_dir=paths.sky_dir,
                views_dir=paths.view_dir,
                image_dir=paths.image_dir,
            )
            renderer.sunlight_rendering_pipeline()

        with timer("Phase 5: Post-Process & Results Stamping"):
            with timer("  5a: Generate AOI files..."):
                coordinate_map_path = utils.create_pixel_to_world_coord_map(paths.image_dir)
                view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

            with timer("  5b: Generate Sunlit WPD and send to .xlsx..."):
                converter = Hdr2Wpd(
                    pixel_to_world_map=coordinate_map_path,
                    aoi_dir=paths.aoi_dir,
                    wpd_dir=paths.wpd_dir,
                    image_dir=paths.image_dir,
                )
                converter.sunlight_sequence_wpd_extraction()

            with timer("  5c: Stamp images with results and combine into .apng..."):
                tiff_annotator = Tiff2Animation(
                    skyless_octree_path=octree_generator.skyless_octree_path,
                    overcast_sky_file_path=sky_generator.TenK_cie_overcast_sky_file_path,
                    x_res=renderer.x_res,
                    y_res=renderer.y_res,
                    latitude=building_latitude,
                    ffl_offset=ffl_offset,
                    sky_files_dir=paths.sky_dir,
                    view_files_dir=paths.view_dir,
                    image_dir=paths.image_dir,
                    aoi_dir=paths.aoi_dir,
                    animation_format=animation_format,
                )
                tiff_annotator.nsw_adg_sunlight_access_results_pipeline()

        with timer("Phase 6: Final Reporting"):
            pass

        timer.print_report(output_dir=paths.outputs_dir)
        return True
