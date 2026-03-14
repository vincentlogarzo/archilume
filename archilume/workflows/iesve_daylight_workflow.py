from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import sys

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

    class InputsValidator:
        """
        Holds and validates simulation inputs for the IESVE Daylight Workflow.
        """
        def __init__(
            self,
            octree_path:        Path | str,
            rendering_params:   Path | str,
            iesve_room_data:    Path | str,
            project:            str,
            image_resolution:   int  = 2048,
            ffl_offset:         float = 0.0,
        ):
            self.paths = config.get_project_paths(project)
            base_dir = self.paths.inputs_dir

            self.image_resolution   = image_resolution
            self.ffl_offset         = ffl_offset
            self.project            = project

            def _resolve(p):
                p = Path(p)
                return p if p.is_absolute() else base_dir / p

            self.octree_path        = _resolve(octree_path)
            self.rendering_params   = _resolve(rendering_params)
            self.iesve_room_data    = _resolve(iesve_room_data)

            self._errors = []
            self._validate()
            self._report()

        def _validate(self):
            if self.image_resolution < 128:
                self._errors.append("[X] image_resolution: Must be >= 128.")

            for label, path in [
                ("octree_path",      self.octree_path),
                ("rendering_params", self.rendering_params),
                ("iesve_room_data",  self.iesve_room_data),
            ]:
                if not path.exists():
                    self._errors.append(f"[X] {label}: Not found: {path}")

        def _report(self):
            if self._errors:
                print("\n" + "="*100)
                print("INPUT VALIDATION FAILED - EXECUTION BLOCKED")
                print("="*100)
                for e in self._errors: print(f" {e}")
                sys.exit(1)

            print("\n" + "="*100)
            print(f"{'CONFIGURATION VALIDATED SUCCESSFULLY':^100}")
            print("="*100)
            print(f"{'PARAMETER':<30} {'VALUE':<70}")
            print("-" * 100)
            print(f"{'Octree':<30} {str(self.octree_path.name):<70}")
            print(f"{'Rendering Params':<30} {str(self.rendering_params.name):<70}")
            print(f"{'IESVE Room Data':<30} {str(self.iesve_room_data.name):<70}")
            print(f"{'Resolution':<30} {self.image_resolution}px")
            print(f"{'Camera Height (FFL)':<30} {self.ffl_offset}m")
            print("="*100 + "\n")

    def run(self, inputs: InputsValidator):
        """
        Execute the IESVE daylight analysis pipeline.
        """
        timer = PhaseTimer()
        inputs.paths.create_dirs()

        with timer("Phase 1: Prepare Camera Views"):
            room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
                iesve_room_data_path=inputs.iesve_room_data,
                output_dir=inputs.paths.aoi_dir,
            )
            view_generator = ViewGenerator(
                room_boundaries_csv_path=room_boundaries_csv,
                ffl_offset=inputs.ffl_offset,
                view_file_dir=inputs.paths.view_dir,
                aoi_dir=inputs.paths.aoi_dir,
            )
            view_generator.create_plan_view_files()

        with timer("Phase 2: Execute Image Rendering"):
            renderer = DaylightRenderer(
                octree_path=inputs.octree_path,
                rdp_path=inputs.rendering_params,
                x_res=inputs.image_resolution,
                view_files=view_generator.view_files,
                image_dir=inputs.paths.image_dir,
            )
            renderer.daylight_rendering_pipeline()

        with timer("Phase 3: Post-processing"):
            with timer("  3a: Generate .aoi files"):
                coordinate_map_path = utils.create_pixel_to_world_coord_map(inputs.paths.image_dir)
                view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

        timer.print_report(output_dir=inputs.paths.outputs_dir)
        return True
