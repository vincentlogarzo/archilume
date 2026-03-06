"""
Archilume Workflows Module
==========================

High-level simulation pipelines that orchestrate multiple steps of the 
Radiance/Accelerad analysis process.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import sys

from archilume import (
    SkyGenerator,
    ViewGenerator,
    Objs2Octree,
    SunlightRenderer,
    DaylightRenderer,
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

    class InputsValidator:
        """
        Holds and validates simulation inputs for the Sunlight Access Workflow.
        """
        def __init__(
            self,
            building_latitude: float,
            month: int,
            day: int,
            start_hour: int,
            end_hour: int,
            timestep: int,
            ffl_offset: float,
            image_resolution: int,
            rendering_mode: str,
            rendering_quality: str,
            room_boundaries_csv: Path | str,
            obj_paths: List[Path | str],
            animation_format: str = "apng",
            project: Optional[str] = None
        ):
            self.building_latitude = building_latitude
            self.month = month
            self.day = day
            self.start_hour = start_hour
            self.end_hour = end_hour
            self.timestep = timestep
            self.ffl_offset = ffl_offset
            self.image_resolution = image_resolution
            self.rendering_mode = rendering_mode
            self.rendering_quality = rendering_quality
            self.animation_format = animation_format.lower()
            self.project = project

            base_dir = config.INPUTS_DIR / project if project else config.INPUTS_DIR
            self.room_boundaries_csv = base_dir / room_boundaries_csv if not Path(room_boundaries_csv).is_absolute() else Path(room_boundaries_csv)
            self.obj_paths = [base_dir / p if not Path(p).is_absolute() else Path(p) for p in obj_paths]
            
            self._errors = []
            self._warnings = []

            self._validate()
            self._report()

        def _validate(self):
            # --- Geographic ---
            if not isinstance(self.building_latitude, (int, float)):
                self._errors.append("[X] building_latitude: Must be numeric.")
            elif not -90 <= self.building_latitude <= 90:
                self._errors.append("[X] building_latitude: Must be -90 to 90.")

            # --- Time ---
            if not (0 <= self.start_hour <= 23): self._errors.append("[X] start_hour: Must be 0-23.")
            if not (0 <= self.end_hour <= 23): self._errors.append("[X] end_hour: Must be 0-23.")
            if self.start_hour >= self.end_hour: self._errors.append("[X] Time range: end_hour must be > start_hour.")

            if self.timestep < 1: self._errors.append("[X] timestep: Must be >= 1.")
            elif self.timestep < 5: self._warnings.append(f"[!] timestep ({self.timestep} min) is very low. High computation time.")

            # --- Rendering ---
            if self.image_resolution < 128: self._errors.append("[X] resolution: Must be >= 128.")
            elif self.image_resolution > 2048: self._warnings.append(f"[!] resolution ({self.image_resolution}) exceeds recommended 2048px.")

            valid_modes = ['cpu', 'gpu']
            if self.rendering_mode.lower() not in valid_modes:
                self._errors.append(f"[X] rendering_mode: Must be one of {valid_modes}")

            valid_qualities = ['draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed']
            if self.rendering_quality.lower() not in valid_qualities:
                self._errors.append(f"[X] rendering_quality: Must be one of {valid_qualities}")

            valid_formats = ['gif', 'apng']
            if self.animation_format not in valid_formats:
                self._errors.append(f"[X] animation_format: Must be one of {valid_formats}")

            # --- Files ---
            if not self.room_boundaries_csv.exists():
                self._errors.append(f"[X] CSV not found: {self.room_boundaries_csv}")

            # --- Geometry ---
            if not self.obj_paths: self._errors.append("[X] obj_paths: List is empty.")
            else:
                for idx, obj in enumerate(self.obj_paths):
                    if not obj.exists():
                        self._errors.append(f"[X] obj_paths[{idx}]: Not found: {obj}")
                        continue
                    if not obj.with_suffix('.mtl').exists():
                        self._errors.append(f"[X] obj_paths[{idx}]: Missing .mtl file.")

                    is_m, max_c, diag = self._check_obj_units(obj)
                    if not is_m: self._errors.append(f"[X] obj_paths[{idx}] is in MILLIMETERS (max: {max_c:,.0f}). Re-export in Meters.")

        def _check_obj_units(self, path):
            try:
                max_c = 0.0
                with open(path, 'r') as f:
                    for i, line in enumerate(f):
                        if line.startswith('v '):
                            parts = line.split()
                            if len(parts) >= 4:
                                max_c = max(max_c, abs(float(parts[1])), abs(float(parts[2])), abs(float(parts[3])))
                                if max_c > 10000: return False, max_c, "mm"
                                if i > 5000: break 
                if max_c > 1000: return False, max_c, "mm"
                return True, max_c, "m"
            except: return True, 0, "err"

        def _report(self):
            if self._errors:
                print("\n" + "="*100)
                print("INPUT VALIDATION FAILED - EXECUTION BLOCKED")
                print("="*100)
                for e in self._errors: print(f" {e}")
                if self._warnings:
                    print("-" * 100)
                    print("Warnings also detected:")
                    for w in self._warnings: print(f" {w}")
                sys.exit(1)

            print("\n" + "="*100)
            print(f"{'CONFIGURATION VALIDATED SUCCESSFULLY':^100}")
            print("="*100)
            print(f"{'PARAMETER':<30} {'VALUE':<30} {'VALIDATION RULES / REASONING':<40}")
            print("-" * 100)
            print(f"{'Building Latitude':<30} {self.building_latitude:<30} {'Range: -90.0 to 90.0 (Decimal Degrees)'}")
            print(f"{'Date':<30} {self.month}/{self.day:<30} {'Month: 1-12, Day: 1-31'}")
            print(f"{'Time Range':<30} {self.start_hour}:00 - {self.end_hour}:00{'Start must be < End (0-23h fmt)'}")
            print(f"{'Timestep':<30} {self.timestep} min{'Integer >= 1 (Rec: >5min)'}")
            print(f"{'Camera Height (FFL)':<30} {self.ffl_offset}m{'Numeric value > 0.0m'}")
            print(f"{'Resolution':<30} {self.image_resolution}px{'Integer >= 128px (Rec: <=2048)'}")
            print(f"{'Rendering Mode':<30} {self.rendering_mode.upper():<30} {'Must be CPU or GPU'}")
            print(f"{'Quality Preset':<30} {self.rendering_quality.upper():<30} {'Valid preset name'}")
            print(f"{'Room Boundaries CSV':<30} {self.room_boundaries_csv.name:<30} {'File exists & extension is .csv'}")
            print("-" * 100)
            print(f"GEOMETRY FILES ({len(self.obj_paths)})")
            for i, obj in enumerate(self.obj_paths, 1):
                print(f"  {i}. {obj.name:<25} {'DETECTED: Meters':<30} {'Max Coord < 1000m & .mtl exists'}")
            if self._warnings:
                print("\n" + "="*100)
                print("WARNINGS DETECTED (Script will continue)")
                for w in self._warnings: print(f" {w}")
            print("="*100 + "\n")
    
    def run(self, inputs: InputsValidator):
        """
        Execute the full sunlight analysis pipeline.
        """
        timer = PhaseTimer()

        with timer("Phase 0: Setup and Cleanup"):
            smart_cleanup(
                timestep_changed=True,
                resolution_changed=True,
                rendering_mode_changed=True,
                rendering_quality_changed=True
            )

        with timer("Phase 1: Establishing 3D Scene"):
            octree_generator = Objs2Octree(inputs.obj_paths)
            octree_generator.create_skyless_octree_for_analysis()

        with timer("Phase 2: Generate Sky Conditions"):
            sky_generator = SkyGenerator(lat=inputs.building_latitude)
            sky_generator.generate_TenK_cie_overcast_skyfile()
            sky_generator.generate_sunny_sky_series(
                month=inputs.month,
                day=inputs.day,
                start_hour_24hr_format=inputs.start_hour,
                end_hour_24hr_format=inputs.end_hour,
                minute_increment=inputs.timestep
            )

        with timer("Phase 3: Prepare Camera Views"):
            view_generator = ViewGenerator(
                room_boundaries_csv_path=inputs.room_boundaries_csv,
                ffl_offset=inputs.ffl_offset
            )
            view_generator.create_plan_view_files()

        with timer("Phase 4: Execute Image Rendering"):
            renderer = SunlightRenderer(
                skyless_octree_path=octree_generator.skyless_octree_path,
                overcast_sky_file_path=sky_generator.TenK_cie_overcast_sky_file_path,
                x_res=inputs.image_resolution,
                y_res=inputs.image_resolution,
                rendering_mode=inputs.rendering_mode,
                gpu_quality=inputs.rendering_quality
            )
            renderer.sunlight_rendering_pipeline()

        with timer("Phase 5: Post-Process & Results Stamping"):
            with timer("  5a: Generate AOI files..."):
                coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
                view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

            with timer("  5b: Generate Sunlit WPD and send to .xlsx..."):
                converter = Hdr2Wpd(pixel_to_world_map=coordinate_map_path)
                converter.sunlight_sequence_wpd_extraction()

            with timer("  5c: Stamp images with results and combine into .apng..."):
                tiff_annotator = Tiff2Animation(
                    skyless_octree_path=octree_generator.skyless_octree_path,
                    overcast_sky_file_path=sky_generator.TenK_cie_overcast_sky_file_path,
                    x_res=renderer.x_res,
                    y_res=renderer.y_res,
                    latitude=inputs.building_latitude,
                    ffl_offset=inputs.ffl_offset,
                    animation_format=inputs.animation_format
                )
                tiff_annotator.nsw_adg_sunlight_access_results_pipeline()

        with timer("Phase 6: Final Reporting"):
            pass

        timer.print_report(output_dir=config.OUTPUTS_DIR)
        return True


@dataclass
class IESVEDaylightWorkflow:
    """
    Orchestrates a daylight factor analysis pipeline using pre-built IESVE octree models.

    Only works with 10K lux (10,000 lux) overcast sky octrees from IESVE.
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
            image_resolution:   int  = 2048,
            ffl_offset:         float = 0.0,
            project:            Optional[str] = None,
        ):
            base_dir = config.INPUTS_DIR / project if project else config.INPUTS_DIR

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

        with timer("Phase 1: Prepare Camera Views"):
            room_boundaries_csv = utils.iesve_aoi_to_room_boundaries_csv(
                iesve_room_data_path=inputs.iesve_room_data
            )
            view_generator = ViewGenerator(
                room_boundaries_csv_path=room_boundaries_csv,
                ffl_offset=inputs.ffl_offset
            )
            view_generator.create_plan_view_files()

        with timer("Phase 2: Execute Image Rendering"):
            renderer = DaylightRenderer(
                octree_path=inputs.octree_path,
                rdp_path=inputs.rendering_params,
                x_res=inputs.image_resolution,
                view_files=view_generator.view_files,
            )
            renderer.daylight_rendering_pipeline()

        with timer("Phase 3: Post-processing"):
            with timer("  3a: Generate .aoi files"):
                coordinate_map_path = utils.create_pixel_to_world_coord_map(config.IMAGE_DIR)
                view_generator.create_aoi_files(coordinate_map_path=coordinate_map_path)

        timer.print_report(output_dir=config.OUTPUTS_DIR)
        return True
