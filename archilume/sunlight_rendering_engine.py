"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

# Archilume imports
from archilume import utils

# Standard library imports
from dataclasses import dataclass, field
from typing import List
from datetime import datetime
from pathlib import Path
import json

# Third-party imports
from itertools import product

@dataclass
class SunlightRenderingEngine:
    """
    Comprehensive solar illumination analysis engine for architectural daylight evaluation.
    
    This dataclass orchestrates the complete pipeline for analyzing sunlight exposure in
    architectural spaces, from geometric setup through final visualization generation.
    Implements industry-standard Radiance rendering with automated post-processing for
    regulatory compliance assessment.

    Required Attributes:
        skyless_octree_path (Path): Base octree file path (typically skyless geometry)
        overcast_sky_file_path (Path): Overcast sky file for ambient lighting analysis
        sky_files_dir (Path): Directory containing solar condition sky files
        view_files_dir (Path): Directory containing architectural viewpoint files
        image_dir (Path): Output directory for rendered images and analysis results
        x_res (int): Horizontal resolution for medium quality rendering (must be positive)
        y_res (int): Vertical resolution for medium quality rendering (must be positive)

    Auto-Generated Attributes (populated during initialization):
        sky_files (List[Path]): Discovered sky files from sky_files_dir (*.sky)
        view_files (List[Path]): Discovered view files from view_files_dir (*.vp)
        overcast_octree_command (str): Command for overcast sky octree generation
        rpict_low_qual_commands (List[str]): Low quality rendering commands (512x512)
        rpict_med_qual_commands (List[str]): Medium quality rendering commands (x_res × y_res)
        temp_octree_with_sky_paths (List[Path]): Temporary octree file paths
        oconv_commands (List[str]): Octree compilation commands
        rpict_commands (List[str]): Solar rendering commands
        pcomb_commands (List[str]): Image composite commands
        ra_tiff_commands (List[str]): TIFF conversion commands
    """

    # Required fields - no defaults
    skyless_octree_path: Path
    overcast_sky_file_path: Path
    sky_files_dir: Path
    view_files_dir: Path
    image_dir: Path
    x_res: int
    y_res: int
    
    # Fields that will be populated after initialization
    sky_files: List[Path] = field(default_factory=list, init=False)
    view_files: List[Path] = field(default_factory=list, init=False)
    overcast_octree_command: str = field(default="", init=False)
    rpict_low_qual_commands: List[str] = field(default_factory=list, init=False)
    rpict_med_qual_commands: List[str] = field(default_factory=list, init=False)
    temp_octree_with_sky_paths: List[Path] = field(default_factory=list, init=False)
    oconv_commands: List[str] = field(default_factory=list, init=False)
    rpict_commands: List[str] = field(default_factory=list, init=False)
    pcomb_commands: List[str] = field(default_factory=list, init=False)
    ra_tiff_commands: List[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        """
        Post-initialization to populate file lists from directories.
        """
        # Populate sky files from directory
        self.sky_files = sorted([path for path in self.sky_files_dir.glob('*.sky')])
        
        # Populate view files from directory
        self.view_files = sorted([path for path in self.view_files_dir.glob('*.vp')])
        
        # Validate resolution values
        if self.x_res <= 0 or self.y_res <= 0:
            raise ValueError(f"Resolution must be positive: x_res={self.x_res}, y_res={self.y_res}")
        
        # Generate overcast sky rendering commands
        self.overcast_octree_command, self.rpict_low_qual_commands, self.rpict_med_qual_commands = self.__generate_overcast_sky_rendering_commands()

        # Generate sunny sky rendering commands
        self.temp_octree_with_sky_paths, self.oconv_commands, self.rpict_commands, self.pcomb_commands, self.ra_tiff_commands = self.__generate_sunny_sky_rendering_commands()

    def __generate_overcast_sky_rendering_commands(self, aa: float=0.1, ab: int=1, ad: int=4096, ar: int=1024, as_val: int=1024, dj: float=0.7, lr: int=12, lw: float=0.002, pj: int=1, ps: int=4, pt: float=0.05) -> tuple[str, list[str], list[str]]:
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
            aa (float, optional): Ambient accuracy for rpict. Defaults to 0.1. If this value is set to zero then interpolations are not used
            ab (int, optional): Ambient bounces for rpict [low_qual=1, med_qual=2]. Defaults to 1.
            ad (int, optional): Ambient divisions for rpict [low_qual=2048, med_qual=4096]. Defaults to 4096.
            ar (int, optional): Ambient resolution for rpict [low_qual=512, med_qual=1024]. Defaults to 1024.
            as_val (int, optional): Ambient samples for rpict [low_qual=512, med_qual=1024]. Defaults to 1024.
            dj (float, optional): Direct jitter for rpict. Defaults to 0.7.
            lr (int, optional): Limit reflection for rpict. Defaults to 12.
            lw (float, optional): Limit weight for rpict. Defaults to 0.002.
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
                rpict -w -t 2 -vtv -vf view.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 2048 -as 512 -ar 512 -ps 1 -pt 0.06 -af ambient.amb model_overcast_sky.oct
            # subsequent medium quality rendering with the ambient file producing an ouptut indirect image
                rpict -w -t 2 -vtv -vf view.vp -x 2048 -y 2048 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -ab 2 -aa 0.1 -ar 1024 -ad 4096 -as 1024 -lr 12 -lw 0.00200 -af ambient_file.amb model_overcast_sky.oct > output_image.hdr
        """
        
        octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')
        octree_with_overcast_sky_path = self.skyless_octree_path.parent / f"{octree_base_name}_{self.overcast_sky_file_path.stem}.oct"
        overcast_octree_command = str(rf"oconv -i {self.skyless_octree_path} {self.overcast_sky_file_path} > {octree_with_overcast_sky_path}")

        rpict_low_qual_commands, rpict_med_qual_commands = [], []
        x_res_low, y_res_low = 512, 512
        x_res_med, y_res_med = self.x_res, self.y_res

        for octree_with_overcast_sky_path, view_file_path in product([octree_with_overcast_sky_path], self.view_files):
            
            ambient_file_path = self.image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{self.overcast_sky_file_path.stem}.amb"
            output_hdr_path = self.image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{self.overcast_sky_file_path.stem}.hdr"

            # constructed commands that will be executed in parallel from each other untill all are complete.
            rpict_low_qual_command, rpict_med_qual_command = [
                rf"rpict -w -t 2 -vtv -vf {view_file_path} -x {x_res_low} -y {y_res_low} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path}",
                rf"rpict -w -t 2 -vtv -vf {view_file_path} -x {x_res_med} -y {y_res_med} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path} > {output_hdr_path}"
            ]

            rpict_low_qual_commands.append(rpict_low_qual_command)
            rpict_med_qual_commands.append(rpict_med_qual_command)

        return overcast_octree_command, rpict_low_qual_commands, rpict_med_qual_commands   

    def __generate_sunny_sky_rendering_commands(self, ab: int=0, ad: int=128, ar: int=64, as_val: int=64, ps: int=6, lw: float=0.00500) -> tuple[list[Path], list[str], list[str], list[str], list[str]]:
        """
        TODO: update the input variables with type and ranges of allowable inputs given information found online. 
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

        rpict_commands, oconv_commands, temp_octree_with_sky_paths, pcomb_commands, ra_tiff_commands = [], [], [], [], []

        octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')

        for sky_file_path, view_file_path in product(self.sky_files, self.view_files):
            
            sky_file_name = Path(sky_file_path).stem
            view_file_name = Path(view_file_path).stem
            octree_with_sky_path = self.skyless_octree_path.parent / f"{octree_base_name}_{sky_file_name}.oct"
            output_hdr_path = self.image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}.hdr"
            output_hdr_path_combined = self.image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}_combined.hdr"
            overcast_hdr_path = self.image_dir / f"{octree_base_name}_{view_file_name}__TenK_cie_overcast.hdr"

            # constructed commands that will be executed in parallel from each other untill all are complete.
            #FIXME: the -vtv n the rpict command may be redundant as this is already specified in the view file. update the view file code to use vtv instead of vtl and remove -vtv from here and test the results. 
            temp_octree_with_sky_path = self.skyless_octree_path.parent / f'{octree_base_name}_{sky_file_name}_temp.oct'
            oconv_command, rpict_command, pcomb_command, ra_tiff_command = [
                rf"oconv -i {str(temp_octree_with_sky_path).replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}" ,
                rf"rpict -w -vtv -t 3 -vf {view_file_path} -x {self.x_res} -y {self.y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}",
                rf'pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" {overcast_hdr_path} {output_hdr_path} > {output_hdr_path_combined}',
                rf"ra_tiff -e -2 {output_hdr_path_combined} {self.image_dir / f'{output_hdr_path_combined.stem}.tiff'}"
            ]

            temp_octree_with_sky_paths.append(temp_octree_with_sky_path)
            oconv_commands.append(oconv_command)
            rpict_commands.append(rpict_command)
            pcomb_commands.append(pcomb_command)
            ra_tiff_commands.append(ra_tiff_command)
        
        # get rid of duplicate oconv commands while retaining list order
        oconv_commands = list(dict.fromkeys(oconv_commands))

        return temp_octree_with_sky_paths, oconv_commands, rpict_commands, pcomb_commands, ra_tiff_commands

    def render_sequences(self):
        """
        Render images for each combination of sky and view files.
        """

        # Phase 1: Generate ambient lighting foundation using overcast sky conditions
        # Create octree with overcast sky for ambient file generation, establishing the indirect lighting baseline
        utils.execute_new_radiance_commands(self.overcast_octree_command, number_of_workers=1)
        utils.execute_new_radiance_commands(self.rpict_low_qual_commands, number_of_workers=8)
        utils.execute_new_radiance_commands(self.rpict_med_qual_commands, number_of_workers=8)

        # Phase 2: Synthesize octree files for all sky-view combinations
        # Prepare temporary octree structures for comprehensive solar condition analysis
        utils.copy_files(self.skyless_octree_path, self.temp_octree_with_sky_paths)
        utils.execute_new_radiance_commands(self.oconv_commands, number_of_workers=6)
        utils.delete_files(self.temp_octree_with_sky_paths)

        # Phase 3: Execute High-Fidelity Solar Illumination Analysis
        # Perform precision rendering of direct solar conditions across temporal variations
        utils.execute_new_radiance_commands(self.rpict_commands, number_of_workers=10)  # TODO: investigate overture to increase quality of the output image
        
        # Phase 3a: Composite Direct and Ambient Illumination Components
        # Synthesize comprehensive lighting conditions by merging solar and ambient contributions
        utils.execute_new_radiance_commands(self.pcomb_commands, number_of_workers=14)
        
        # Phase 3b: Convert to Industry-Standard TIFF Format
        # Transform HDR data to accessible format with optimized exposure mapping
        utils.execute_new_radiance_commands(self.ra_tiff_commands, number_of_workers=10)  # TODO: automate exposure adjustment based on histogram analysis

        # combined_hdr_files_paths_for_deletion = [Path(cmd.split(' > ')[-1].strip()) for cmd in self.pcomb_commands if ' > ' in cmd]
        # utils.delete_files(combined_hdr_files_paths_for_deletion)

        # Phase 4: Establish Spatial-Temporal Coordinate Framework
        # Create precise pixel-to-world coordinate mapping for analytical accuracy
        utils.create_pixel_to_world_mapping_from_hdr(self.image_dir)

        # Phase 4a: Apply Temporal and Contextual Annotations
        # Embed chronological and meteorological metadata for regulatory compliance verification
        tiff_files_to_stamp = [path for path in self.image_dir.glob('*_combined.tiff')]
        
        # TODO: implement dynamic geospatial coordinate system based on project location
        utils.stamp_tiff_files(
            tiff_files_to_stamp, 
            font_size=24, 
            text_color=(255, 255, 255),  # Professional white annotation
            background_alpha=180, 
            number_of_workers=10
        )

        # Phase 4b: Architectural Space Identification and Compliance Delineation
        # Overlay spatial boundaries with occupancy classifications for regulatory assessment
        # utils.stamp_tiff_files_with_aoi(
        #     tiff_files_to_stamp, 
        #     lineweight              = 1, 
        #     font_size               = 32, 
        #     text_color              = (255, 0, 0), 
        #     background_alpha        = 180, 
        #     number_of_workers       = 10
        #     )

        # Optimization Opportunity: Implement hierarchical stamping methodology for computational efficiency

        # Phase 4c: Quantitative Compliance Analysis and Data Export
        # Calculate illumination metrics per spatial zone with regulatory threshold evaluation
        # TODO: Implement real-world coordinate mapping for processed boundaries
        # TODO: Generate AOI files with geospatial coordinates and validation protocols
        # TODO: Develop interactive interface for dynamic AOI adjustment with persistent configuration

        # Phase 4d: Generate Comprehensive Illumination Analytics Dashboard
        # Produce calibrated visualization showing temporal illumination patterns with ADDG compliance thresholds 


        # Phase 5: Synthesize Multi-Format Temporal Visualizations
        # Create animated sequences demonstrating illumination evolution across temporal cycles
        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='gif', number_of_workers=8)
        utils.combine_tiffs_by_view(self.image_dir, self.view_files, output_format='mp4', number_of_workers=8)


        # Phase 6: Generate Consolidated Multi-Perspective Analytics
        # Produce unified grid visualization integrating all viewpoint analyses for comprehensive assessment
        individual_view_mp4s = [path for path in self.image_dir.glob('animated_results_*.mp4')]
        utils.create_grid_mp4(individual_view_mp4s, self.image_dir, grid_size=(3, 2), target_size=(1024, 1024), fps=2)

        individual_view_gifs = [path for path in self.image_dir.glob('animated_results_*.gif')]
        utils.create_grid_gif(individual_view_gifs, self.image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)

        print("Rendering sequence completed successfully.")
