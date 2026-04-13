from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from archilume import utils, config
from archilume.utils import PhaseTimer
from archilume.core.view_generator import ViewGenerator
from archilume.core.rendering_pipelines import DaylightRenderer


@dataclass
class IESVEDaylightWorkflow:
    """
    Orchestrates a daylight factor analysis pipeline using pre-built IESVE octree models.

    Only works with 10K lux (10,000 lux) overcast sky octree's from IESVE.
    The octree must include the sky definition. DF values are derived by
    scaling rendered irradiance (pcomb -s 0.01) against the 10K lux reference.
    """

    def run(
        self,
        *,
        octree_path: Path,
        rendering_params: Path,
        iesve_room_data: Path,
        paths: config.ProjectPaths,
        image_resolution: int = 2048,
        ffl_offset: float = 0.0,
        use_ambient_file: bool = True,
        n_cpus: Optional[int] = None,
    ) -> bool:
        """Execute the IESVE daylight analysis pipeline."""
        timer = PhaseTimer()
        paths.create_dirs()

        print("\n" + "=" * 100)
        print(f"{'IESVE DAYLIGHT WORKFLOW':^100}")
        print("=" * 100)
        print(f"{'Octree':<30} {octree_path.name}")
        print(f"{'Rendering Params':<30} {rendering_params.name}")
        print(f"{'IESVE Room Data':<30} {iesve_room_data.name}")
        print(f"{'Resolution':<30} {image_resolution}px")
        print(f"{'Camera Height (FFL)':<30} {ffl_offset}m")
        print(f"{'Ambient File':<30} {'Enabled' if use_ambient_file else 'Disabled'}")
        print(f"{'CPUs':<30} {n_cpus if n_cpus else 'All available'}")
        print("=" * 100 + "\n")

        with timer("Phase 1: Prepare Camera Views"):
            room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
                iesve_room_data_path=iesve_room_data,
                output_dir=paths.aoi_dir,
            )
            view_generator = ViewGenerator(
                room_boundaries_csv_path=room_boundaries_csv,
                ffl_offset=ffl_offset,
                view_file_dir=paths.view_dir,
                aoi_dir=paths.aoi_dir,
            )
            view_generator.create_plan_view_files()

        with timer("Phase 2: Execute Image Rendering"):
            renderer = DaylightRenderer(
                octree_path=octree_path,
                rdp_path=rendering_params,
                x_res=image_resolution,
                view_files=view_generator.view_files,
                image_dir=paths.image_dir,
                use_ambient_file=use_ambient_file,
                n_cpus=n_cpus,
            )
            renderer.daylight_rendering_pipeline()

        with timer("Phase 3: Post-processing"):
            with timer("  3a: Generate .aoi files"):
                coordinate_map_path = utils.create_pixel_to_world_coord_map(paths.image_dir)
                view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

        timer.print_report(output_dir=paths.outputs_dir)
        return True
