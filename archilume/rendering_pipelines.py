"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

# Archilume imports
from archilume import utils, config
from archilume.utils import PhaseTimer

# Standard library imports
from dataclasses import dataclass, field
import os
from typing import List
from pathlib import Path
import logging
from concurrent.futures import ThreadPoolExecutor
import time
import subprocess
from PIL import Image

# Third-party imports
from itertools import product

logger = logging.getLogger(__name__)

# Rendering constants
X_RES_OVERTURE = 64
Y_RES_OVERTURE = 64

@dataclass
class RenderingPipelines:
    """
    Comprehensive solar illumination analysis engine for architectural daylight evaluation.

    This dataclass orchestrates the complete pipeline for analyzing sunlight exposure in
    architectural spaces, from geometric setup through final visualization generation.
    Implements industry-standard Radiance rendering with automated post-processing for
    regulatory compliance assessment.

    Required Attributes:
        skyless_octree_path (Path): Base octree file path (typically skyless geometry)
        overcast_sky_file_path (Path): Overcast sky file for ambient lighting analysis
        x_res (int): Horizontal resolution for medium quality rendering (must be positive)
        y_res (int): Vertical resolution for medium quality rendering (must be positive)

    Optional Attributes (default from config):
        skies_dir (Path): Directory containing solar condition sky files (default: config.SKY_DIR)
        views_dir (Path): Directory containing architectural viewpoint files (default: config.VIEW_DIR)
        render_mode (str): Rendering backend - 'cpu' or 'gpu' (default: 'cpu')
        gpu_quality (str): GPU quality preset - 'draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed' (default: 'stand')

    Auto-Generated Attributes (populated during initialization):
        image_dir (Path): Output directory for rendered images (default: config.IMAGE_DIR)
        sky_files (List[Path]): Discovered sky files from skies_dir (*.sky)
        view_files (List[Path]): Discovered view files from views_dir (*.vp)
        overcast_octree_command (str): Command for overcast sky octree generation
        rpict_daylight_overture_commands (List[str]): Overture rendering commands
        rpict_daylight_med_qual_commands (List[str]): Medium quality rendering commands
        temp_octree_with_sky_paths (List[Path]): Temporary octree file paths
        oconv_commands (List[str]): Octree compilation commands
        rpict_direct_sun_commands (List[str]): Direct sun rendering commands
        pcomb_commands (List[str]): Image composite commands
        ra_tiff_commands (List[str]): TIFF conversion commands
    """

    # Required fields - no defaults
    skyless_octree_path: Path
    overcast_sky_file_path: Path
    x_res: int
    y_res: int

    # Optional fields with config defaults
    skies_dir:                          Path = field(default_factory=lambda: config.SKY_DIR)
    views_dir:                          Path = field(default_factory=lambda: config.VIEW_DIR)
    render_mode:                        str = 'cpu'
    gpu_quality:                        str = 'stand'

    # Fields that will be populated after initialization
    image_dir:                          Path = field(init = False, default_factory=lambda: config.IMAGE_DIR)
    sky_files:                          List[Path] = field(default_factory=list, init=False)
    view_files:                         List[Path] = field(default_factory=list, init=False)
    overcast_octree_command:            str = field(default=None, init=False)
    rpict_daylight_overture_commands:   List[str] = field(default_factory=list, init=False)
    rpict_daylight_med_qual_commands:   List[str] = field(default_factory=list, init=False)
    temp_octree_with_sky_paths:         List[Path] = field(default_factory=list, init=False)
    oconv_commands:                     List[str] = field(default_factory=list, init=False)
    rpict_direct_sun_commands:          List[str] = field(default_factory=list, init=False)
    pcomb_commands:                     List[str] = field(default_factory=list, init=False)
    ra_tiff_commands:                   List[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        """
        Post-initialization to populate file lists from directories and validate parameters.
        """
        # Populate sky files from directory
        self.sky_files = sorted([path for path in self.skies_dir.glob('*.sky')])

        # Populate view files from directory
        self.view_files = sorted([path for path in self.views_dir.glob('*.vp')])

        # Validate resolution values
        if self.x_res <= 0 or self.y_res <= 0:
            raise ValueError(f"Resolution must be positive: x_res={self.x_res}, y_res={self.y_res}")

        # Validate render_mode
        if self.render_mode not in (valid_modes := ['cpu', 'gpu']):
            raise ValueError(f"Invalid render_mode '{self.render_mode}'. Valid options: {', '.join(valid_modes)}")

        # Validate gpu_quality
        if self.gpu_quality.lower() not in (valid_quals := ['draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed']):
            raise ValueError(f"Invalid gpu_quality '{self.gpu_quality}'. Valid options: {', '.join(valid_quals)}")

        if not os.path.exists(self.image_dir):
            try:
                os.makedirs(self.image_dir)
                print(f"Created output directory: {self.image_dir}")
            except OSError as e:
                print(f"Error creating directory {self.image_dir}: {e}")
    
    def sunlight_rendering_pipeline(self) -> dict:
        """
        Render images for each combination of sky and view files.

        Returns:
            dict: Dictionary containing timing information for each rendering phase.

        Example:
            >>> # CPU rendering (default)
            >>> renderer = RenderingPipelines(skyless_octree_path, overcast_sky_file_path, x_res=1024, y_res=1024)
            >>> timings = renderer.sunlight_rendering_pipeline()

            >>> # GPU rendering with standard quality
            >>> renderer = RenderingPipelines(..., render_mode='gpu', gpu_quality='stand')
            >>> timings = renderer.sunlight_rendering_pipeline()

            >>> # GPU rendering with production quality
            >>> renderer = RenderingPipelines(..., render_mode='gpu', gpu_quality='prod')
            >>> timings = renderer.sunlight_rendering_pipeline()
        """

        phase_timings = {}
        print("\nRenderingPipelines getting started...\n")

        # --- Phase 0: Prepare commands ---
        with PhaseTimer(phase_timings, "    Command preparation"):
            # Generate overcast sky rendering commands
            (self.overcast_octree_command, self.rpict_daylight_overture_commands, self.rpict_daylight_med_qual_commands) = self._generate_overcast_sky_rendering_commands()

            # Generate sunny sky rendering commands
            (self.temp_octree_with_sky_paths, self.oconv_commands, self.rpict_direct_sun_commands, self.pcomb_ra_tiff_commands) = self._generate_sunny_sky_rendering_commands()

        # --- Phase 1: Generate ambient lighting foundation using overcast sky conditions ---
        # Create octree with overcast sky for ambient file generation, establishing the indirect lighting baseline
        with PhaseTimer(phase_timings, "    Overcast octree creation"):
            utils.execute_new_radiance_commands(self.overcast_octree_command, number_of_workers=config.WORKERS["overcast_octree"])

        # --- Phase 2: Render overcast sky conditions (GPU or CPU) ---
        with PhaseTimer(phase_timings, f"    Overcast rendering ({self.render_mode.upper()})"):
            octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')
            overcast_sky_name = self.overcast_sky_file_path.stem

            if self.render_mode == 'gpu':
                _, future = self._render_overcast_gpu(octree_base_name, overcast_sky_name, self.gpu_quality)
            else:
                _, future = self._render_overcast_cpu(octree_base_name, overcast_sky_name)

        # --- Phase 3: Synthesize octree files for all sky-view combinations ---
        # Prepare temporary octree structures for comprehensive solar condition analysis
        with PhaseTimer(phase_timings, "    Sunny sky octrees"):
            utils.copy_files(self.skyless_octree_path, self.temp_octree_with_sky_paths)
            utils.execute_new_radiance_commands(self.oconv_commands, number_of_workers=config.WORKERS["oconv_compile"])
            utils.delete_files(self.temp_octree_with_sky_paths)

        # --- Phase 4: Execute Sunlight rendering Analysis, combined sunlight and daylight images, convert to tiff ---
        with PhaseTimer(phase_timings, "    Sunlight rendering"):
            utils.execute_new_radiance_commands(self.rpict_direct_sun_commands, number_of_workers=config.WORKERS["rpict_direct_sun"])

        # Wait for GPU/CPU overcast rendering to complete before combining
        phase_name = "    GPU rendering (total)" if self.render_mode == 'gpu' else "    Indirect diffuse rendering"
        with PhaseTimer(phase_timings, phase_name):
            future.result()  # Ensure overcast rendering is complete before combining

        with PhaseTimer(phase_timings, "    HDR combination & TIFF conversion"):
            utils.execute_new_radiance_commands(self.pcomb_ra_tiff_commands, number_of_workers=config.WORKERS["pcomb_tiff_conversion"])

        # --- Phase 5: Convert TIFF files to PNG format ---
        with PhaseTimer(phase_timings, "    TIFF to PNG conversion"):
            self._convert_tiff_to_png()

        print("RenderingPipelines completed successfully.")
        return phase_timings

    def _generate_overcast_sky_rendering_commands(self, aa: float=0.1, ab: int=1, ad: int=4096, ar: int=1024, as_val: int=1024, dj: float=0.7, lr: int=12, lw: float=0.002, pj: int=1, ps: int=4, pt: float=0.05) -> tuple[str, list[str], list[str]]:
        """
        Generates oconv, rpict warming run and rpict medium quality run for overcast sky view_file combinations.

        Creates all permutations of the instance's overcast sky file and view files with the skyless octree,
        generating the necessary Radiance commands for the complete rendering pipeline: octree compilation
        with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

        Uses instance variables:
            - self.skyless_octree_path: Base octree file (typically skyless)
            - self.overcast_sky_file_path: Overcast sky file (.sky or .rad file)
            - self.view_files: List of view file paths (.vp files)
            - self.image_dir: Directory path for output images
            - self.x_res, self.y_res: Resolution for medium quality rendering

        Args:
            aa (float, optional): Ambient accuracy for rpict. Defaults to 0.1. 
                If this value is set to zero then interpolations are not used
            ab (int, optional): Ambient bounces for rpict [low_qual=1, med_qual=2]. Defaults to 1.
            ad (int, optional): Ambient divisions for rpict [low_qual=2048, med_qual=4096]. Defaults to 4096.
            ar (int, optional): Ambient resolution for rpict [low_qual=512, med_qual=1024]. Defaults to 1024.
            as_val (int, optional): Ambient samples for rpict [low_qual=512, med_qual=1024]. Defaults to 1024.
            dj (float, optional): Direct jitter for rpict. Defaults to 0.7.
            lr (int, optional): Limit reflection for rpict. Defaults to 12.
            lw (float, optional): Limit weight for rpict. Defaults to 0.002.
            i : irradiance calculation on, limits blurry images with high contrast (i.e. deep buildings)
            pj (int, optional): Pixel jitter for rpict. Defaults to 1.
            ps (int, optional): Pixel sample spacing for rpict [low_qual=1, med_qual=4]. Defaults to 4.
            pt (float, optional): Pixel threshold for rpict [low_qual=0.06, med_qual=0.05]. Defaults to 0.05.

        Returns:
            Tuple[str, List[str], List[str]]: A 3-tuple containing:
                - overcast_octree_command (str): Command to combine octree with overcast sky file.
                - rpict_low_qual_commands (List[str]): Commands for low quality rendering (512x512, ambient file warming).
                - rpict_med_qual_commands (List[str]): Commands for medium quality rendering (using instance x_res/y_res).
                
        Note:
            # example radiance command warming up the ambient file:
                rpict -w -t 2 -vf view.vp -x 64 -y 64 -aa 0.1 -ab 1 -ad 4096 -ar 1024 -as 1024 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -lr 12 -lw 0.00200 -af ambient.amb model_overcast_sky.oct
            # subsequent medium quality rendering with the ambient file producing an ouptut indirect image
                rpict -w -t 2 -vf view.vp -x 2048 -y 2048 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -ab 2 -aa 0.1 -ar 1024 -ad 4096 -as 1024 -lr 12 -lw 0.00200 -af ambient_file.amb model_overcast_sky.oct > output_image.hdr
        """
        
        octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')
        octree_with_overcast_sky_path = self.skyless_octree_path.parent / f"{octree_base_name}_{self.overcast_sky_file_path.stem}.oct"
        overcast_octree_command = str(rf"oconv -i {self.skyless_octree_path} {self.overcast_sky_file_path} > {octree_with_overcast_sky_path}")

        rpict_overture_commands, rpict_med_qual_commands = [], []

        for octree_with_overcast_sky_path, view_file_path in product([octree_with_overcast_sky_path], self.view_files):

            ambient_file_path = self.image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{self.overcast_sky_file_path.stem}.amb"
            output_hdr_path = self.image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{self.overcast_sky_file_path.stem}.hdr"

            # constructed commands that will be executed in parallel from each other untill all are complete.
            rpict_overture_command, rpict_med_qual_command = [
                rf"rpict -w -t 2 -vf {view_file_path} -x {X_RES_OVERTURE} -y {Y_RES_OVERTURE} -aa {aa} -ab {ab} -ad {ad/2} -ar {ar} -as {as_val/2} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -i -af {ambient_file_path} {octree_with_overcast_sky_path}",
                rf"rpict -w -t 2 -vf {view_file_path} -x {self.x_res} -y {self.y_res} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -i -af {ambient_file_path} {octree_with_overcast_sky_path} > {output_hdr_path}"
            ]

            

            rpict_overture_commands.append(rpict_overture_command)
            rpict_med_qual_commands.append(rpict_med_qual_command)

        # Log summary before exit
        logger.info(
            f"Generated {len(rpict_overture_commands)} low-quality and "
            f"{len(rpict_med_qual_commands)} medium-quality overcast rendering commands "
            f"for {len(self.view_files)} views at resolution {self.x_res}x{self.y_res}"
        )

        return overcast_octree_command, rpict_overture_commands, rpict_med_qual_commands   

    def _generate_sunny_sky_rendering_commands(self, ab: int=0, ad: int=128, ar: int=64, as_val: int=64, ps: int=1, lw: float=0.005) -> tuple[list[Path], list[str], list[str], list[str], list[str]]:
        """
        TODO: increase the generic use of this function to include all parameters as optional for rpict.
        Generates oconv, rpict, and ra_tiff commands for rendering combinations of octree, sky, and view files.

        Creates all permutations of sky files and view files with a single octree file, generating
        the necessary Radiance commands for the complete rendering pipeline: octree compilation
        with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

        Args:
            ab (int, optional): Ambient bounces for rpict. Defaults to 2.
            ad (int, optional): Ambient divisions for rpict. Defaults to 128.
            ar (int, optional): Ambient resolution for rpict. Defaults to 64.
            as_val (int, optional): Ambient samples for rpict. Defaults to 64.
            ps (int, optional): Pixel sample spacing for rpict. Defaults to 6.
            lw (float, optional): Limit weight for rpict. Defaults to 0.00500.

        Returns:
            tuple: A 4-tuple containing:
                - temp_octree_with_sky_paths (list[Path]): Temporary octree file paths for oconv input.
                - oconv_commands (list[str]): Commands to combine octree with sky files.
                - rpict_commands (list[str]): Commands to render scenes from different viewpoints.
                - pcomb_commands (list[str]): Commands to combine indirect and direct hdr files.
                - ra_tiff_commands (list[str]): Commands to convert HDR output to tiff format with 8-bit flowting points precision.
                
        Note:
            Output files are named using the pattern: {octree_base}_{view_name}_{sky_name}.{ext}
            Duplicate oconv commands are automatically removed while preserving order.
        """

        rpict_commands, oconv_commands, temp_octree_with_sky_paths, pcomb_ra_tiff_commands = [], [], [], []

        octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')

        for sky_file_path, view_file_path in product(self.sky_files, self.view_files):
            
            sky_file_name = Path(sky_file_path).stem
            view_file_name = Path(view_file_path).stem
            octree_with_sky_path = self.skyless_octree_path.parent / f"{octree_base_name}_{sky_file_name}.oct"
            output_hdr_path = self.image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}.hdr"
            output_hdr_path_combined = self.image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}_combined.hdr"
            overcast_hdr_path = self.image_dir / f"{octree_base_name}_{view_file_name}__TenK_cie_overcast.hdr"

            # constructed commands that will be executed in parallel from each other untill all are complete.
            temp_octree_with_sky_path = self.skyless_octree_path.parent / f'{octree_base_name}_{sky_file_name}_temp.oct'
            oconv_command, rpict_command, pcomb_ra_tiff_command = [
                rf"oconv -i {str(temp_octree_with_sky_path).replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}" ,
                rf"rpict -w -t 3 -vf {view_file_path} -x {self.x_res} -y {self.y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}",
                rf'pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" {overcast_hdr_path} {output_hdr_path} | pfilt -1 | ra_tiff -e -4 - {self.image_dir / f'{output_hdr_path_combined.stem}.tiff'}',
            ]
    

            temp_octree_with_sky_paths.append(temp_octree_with_sky_path)
            oconv_commands.append(oconv_command)
            rpict_commands.append(rpict_command)
            pcomb_ra_tiff_commands.append(pcomb_ra_tiff_command)

        
        # get rid of duplicate oconv commands while retaining list order
        oconv_commands = list(dict.fromkeys(oconv_commands))

        # Log summary before exit
        logger.info(
            f"Generated sunny sky rendering commands: {len(oconv_commands)} oconv, "
            f"{len(rpict_commands)} rpict, {len(pcomb_ra_tiff_commands)} pcomb_ra_tiff"
            f"for {len(self.sky_files)} sky files {len(self.view_files)} views at resolution {self.x_res}x{self.y_res}"
        )

        return temp_octree_with_sky_paths, oconv_commands, rpict_commands, pcomb_ra_tiff_commands
 
    def _render_overcast_gpu(self, octree_base_name: str, overcast_sky_name: str, gpu_quality: str) -> tuple:
        """Handle GPU-based overcast rendering with file checking. Returns (executor, future)."""
        octree_name = f"{octree_base_name}_{overcast_sky_name}"
        expected_files = self._get_expected_overcast_files(octree_base_name, overcast_sky_name)

        if self._check_and_report_existing_files(expected_files):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(lambda: None)
        else:
            executor, future = self._launch_gpu_rendering(octree_name, gpu_quality, octree_base_name, overcast_sky_name)

        return executor, future

    def _get_expected_overcast_files(self, octree_base_name: str, overcast_sky_name: str) -> List[Path]:
            """Generate list of expected overcast HDR output files."""
            return [self.image_dir / f"{octree_base_name}_{Path(vf).stem}__{overcast_sky_name}.hdr" for vf in self.view_files]

    def _check_and_report_existing_files(self, expected_files: List[Path]) -> bool:
        """Check if files exist and print status. Returns True if all exist."""
        all_exist = all(f.exists() for f in expected_files)

        if all_exist:
            file_list = '\n'.join(f"  {f.name}" for f in expected_files[:3])
            extra = f"\n  ... and {len(expected_files) - 3} more" if len(expected_files) > 3 else ""
            print(f"\n{'='*80}\nSKIPPING OVERCAST RENDERING - Files Already Exist\n"
                  f"Found all {len(expected_files)} existing overcast HDR files:\n{file_list}{extra}\n{'='*80}\n")
        else:
            missing = [f for f in expected_files if not f.exists()]
            print(f"\n{'='*80}\nOVERCAST RENDERING REQUIRED\n"
                  f"Missing {len(missing)} of {len(expected_files)} overcast HDR files\n{'='*80}\n")

        return all_exist

    def _launch_gpu_rendering(self, octree_name: str, gpu_quality: str, octree_base_name: str, overcast_sky_name: str):
        """Launch asynchronous GPU rendering via PowerShell/Accelerad."""
        batch_command = f'powershell.exe -ExecutionPolicy Bypass -File .\\archilume\\accelerad_rpict.ps1 -OctreeName "{octree_name}" -Quality "{gpu_quality}" -Resolution {self.x_res}'
        
        project_root = os.getcwd()
        env = os.environ.copy()
        env['RAYPATH'] = config.RAYPATH

        print(f"Launching GPU rendering in background): Quality={gpu_quality}, Resolution={self.x_res}")
        gpu_process = subprocess.Popen(batch_command, shell=True, env=env, cwd=project_root)

        def wait_for_gpu_completion():
            """Wait for GPU process and verify outputs."""
            print("\nWaiting for GPU rendering to complete...")
            returncode = gpu_process.wait()
            time.sleep(0.5)  # Ensure file writes are flushed

            if returncode != 0:
                print(f"\nWarning: GPU rendering exited with code {returncode}")
                raise RuntimeError(f"GPU rendering failed with exit code {returncode}")

            print("\nGPU rendering completed successfully")

            # Verify expected output files exist
            expected_files = self._get_expected_overcast_files(octree_base_name, overcast_sky_name)
            missing = [f for f in expected_files if not f.exists()]
            if missing:
                print(f"\nWarning: {len(missing)} expected HDR files not found:")
                for f in missing[:5]:
                    print(f"  - {f.name}")
            else:
                print(f"Verified: All {len(expected_files)} HDR files created")

            return returncode

        executor = ThreadPoolExecutor(max_workers=1)
        return executor, executor.submit(wait_for_gpu_completion)

    def _render_overcast_cpu(self, octree_base_name: str, overcast_sky_name: str) -> tuple:
        """Handle CPU-based overcast rendering with file checking. Returns (executor, future)."""
        expected_files = self._get_expected_overcast_files(octree_base_name, overcast_sky_name)

        if self._check_and_report_existing_files(expected_files):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(lambda: None)
        else:
            utils.execute_new_radiance_commands(self.rpict_daylight_overture_commands, number_of_workers=config.WORKERS["rpict_overture"])
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                utils.execute_new_radiance_commands,
                self.rpict_daylight_med_qual_commands,
                number_of_workers=config.WORKERS["rpict_medium_quality"])

        return executor, future

    def _convert_tiff_to_png(self) -> None:
        """Convert all TIFF files in image directory to PNG format."""
        tiff_files = list(self.image_dir.glob('*.tiff')) + list(self.image_dir.glob('*.tif'))
        for tiff_path in tiff_files:
            Image.open(tiff_path).save(tiff_path.with_suffix('.png'), format='PNG', optimize=True)
        if tiff_files:
            print(f"Converted {len(tiff_files)} TIFF files to PNG")