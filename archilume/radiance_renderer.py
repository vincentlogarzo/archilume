"""
Radiance Renderer Class

This module provides a RadianceRenderer class for handling radiance rendering workflows,
including overcast sky and sunny sky rendering commands generation.

This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 

"""

# Archilume imports
from archilume.sky_generator import SkyFileGenerator

# Standard library imports
import os
import subprocess
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import List, Tuple, Union

# Third-party imports


@dataclass
class RadianceRenderer:
    """
    A class for generating Radiance rendering commands for different sky conditions.
    
    This class handles the generation of oconv, rpict, and ra_tiff commands for
    rendering scenes with both overcast and sunny sky conditions.

    Attributes:
        skyless_octree_path (Path): Path to the base octree file (must be without a sky)

    """

    # User inputs
    skyless_octree_path: Path = None

    # Internal paths (set automatically during processing)
    sky_files_dir = Path(__file__).parent.parent / "outputs" / "sky"
    view_files_dir = Path(__file__).parent.parent / "outputs" / "views_grids"
    image_dir = Path(__file__).parent.parent / "outputs" / "images"
    overcast_sky_file_path = Path(__file__).parent.parent / "outputs" / "sky" / "TenK_cie_overcast.rad"

    
    def __init__(self):
        """
        Initialise the file lists and str variables needed in subsequent steps.
        
        Args:

            image_dir (Path): Directory path for output images.
        """
        
        self.octree_base_name = self.skyless_octree_path.stem.replace('_skyless', '')
        self.sky_files = [path for path in self.sky_files_dir.glob('*.sky')]
        self.view_files = [path for path in self.view_files_dir.glob('*.vp')] 

        if not self.overcast_sky_file_path.exists():
            SkyFileGenerator().generate_overcast_skyfile()
            #FIXME: get the sky generator to create a path variable for the path to the created sky that can be pass into this class. 
            raise FileNotFoundError(f"Overcast sky file not found at {self.overcast_sky_file_path}. Generating now...")

        #TODO: check if overcast_sky_file_path exists and generate one if not.
   
    def generate_overcast_sky_rendering_commands(
            self,   
            view_files: list[Path], 
            x_res: list=[512, 2048], 
            y_res: list=[512, 2048], 
            aa: float=0.1, 
            ab: int=1, 
            ad: int=4096, 
            ar: int=1024, 
            as_val: int=1024,
            dj: float=0.7,
            lr: int=12, 
            lw:float=0.002, 
            pj: int=1, 
            ps: int=4, 
            pt: float=0.05
            ) -> tuple[str, list[str], list[str]]:
        """
        Generates oconv, rpict warming run and rpict medium quality run for overcast sky view_file combinations. 

        Creates all permutations of sky files and view files with a single octree file, generating
        the necessary Radiance commands for the complete rendering pipeline: octree compilation
        with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

        Args:
            octree_path (Path): Path to the base octree file (typically skyless).
            image_dir (Path): Directory path for output images.
            sky_file (Path): Path to sky file (.sky or .rad file).
            view_files (list[Path]): List of view file paths (.vp files).
            x_res (list, optional): X-resolution for rpict rendering [low_qual, med_qual]. Defaults to [512, 2048].
            y_res (list, optional): Y-resolution for rpict rendering [low_qual, med_qual]. Defaults to [512, 2048].
            aa (float, optional): Ambient accuracy for rpict. Defaults to 0.1.
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
                - rpict_low_qual_commands (List[str]): Commands for low quality rendering (ambient file warming).
                - rpict_med_qual_commands (List[str]): Commands for medium quality rendering.
                
        Note:
            # example radiance command warming up the ambient file:
                rpict -w -t 2 -vtl -vf view.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 2048 -as 512 -ar 512 -ps 1 -pt 0.06 -af ambient.amb model_overcast_sky.oct
            # subsequent medium quality rendering with the ambient file producing an ouptut indirect image
                rpict -w -t 2 -vtl -vf view.vp -x 2048 -y 2048 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -ab 2 -aa 0.1 -ar 1024 -ad 4096 -as 1024 -lr 12 -lw 0.00200 -af ambient_file.amb model_overcast_sky.oct > output_image.hdr
        """
        

        octree_with_overcast_sky_path = self.skyless_octree_path.parent / f"{self.octree_base_name}_{self.overcast_sky_file_path.stem}.oct"
        overcast_octree_command = str(rf"oconv -i {octree_path} {sky_file} > {octree_with_overcast_sky_path}")

        rpict_low_qual_commands, rpict_med_qual_commands = [], []

        for octree_with_overcast_sky_path, view_file_path in product([octree_with_overcast_sky_path], view_files):
            
            ambient_file_path = image_dir / f"{octree_base_name}_{sky_file.stem}_{Path(view_file_path).stem}_.amb"
            output_hdr_path = image_dir / f"{octree_base_name}_{sky_file.stem}_{Path(view_file_path).stem}_indirect.hdr"

            # constructed commands that will be executed in parallel from each other untill all are complete.
            rpict_low_qual_command, rpict_med_qual_command = [
                rf"rpict -w -t 2 -vtl -vf {view_file_path} -x {x_res[0]} -y {y_res[0]} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path}",
                rf"rpict -w -t 2 -vtl -vf {view_file_path} -x {x_res[1]} -y {y_res[1]} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path} > {output_hdr_path}"
            ]

            rpict_low_qual_commands.append(rpict_low_qual_command)
            rpict_med_qual_commands.append(rpict_med_qual_command)

        return overcast_octree_command, rpict_low_qual_commands, rpict_med_qual_commands

    def generate_sunny_sky_rendering_commands(
        self, 
        sky_files: List[Path], 
        view_files: List[Path], 
        x_res: int = 1024, 
        y_res: int = 1024, 
        ab: int = 0, 
        ad: int = 128, 
        ar: int = 64, 
        as_val: int = 64, 
        ps: int = 6, 
        lw: float = 0.00500
    ) -> Tuple[List[Path], List[str], List[str], List[str]]:
        """
        TODO: update the input variables with type and ranges of allowable inputs given information found online. 
        Generates oconv, rpict, and ra_tiff commands for rendering combinations of octree, sky, and view files.

        Creates all permutations of sky files and view files with a single octree file, generating
        the necessary Radiance commands for the complete rendering pipeline: octree compilation
        with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

        Args:
            sky_files (List[Path]): List of sky file paths (.sky files).
            view_files (List[Path]): List of view file paths (.vp files).
            x_res (int, optional): X-resolution for rpict rendering. Defaults to 1024.
            y_res (int, optional): Y-resolution for rpict rendering. Defaults to 1024.
            ab (int, optional): Ambient bounces for rpict. Defaults to 2.
            ad (int, optional): Ambient divisions for rpict. Defaults to 128.
            ar (int, optional): Ambient resolution for rpict. Defaults to 64.
            as_val (int, optional): Ambient samples for rpict. Defaults to 64.
            ps (int, optional): Pixel sample spacing for rpict. Defaults to 6.
            lw (float, optional): Limit weight for rpict. Defaults to 0.00500.

        Returns:
            Tuple[List[Path], List[str], List[str], List[str]]: A 4-tuple containing:
                - temp_octree_with_sky_paths (List[Path]): Temporary octree file paths for oconv input.
                - oconv_commands (List[str]): Commands to combine octree with sky files.
                - rpict_commands (List[str]): Commands to render scenes from different viewpoints.
                - ra_tiff_commands (List[str]): Commands to convert HDR output to TIFF format.
                
        Note:
            Output files are named using the pattern: {octree_base}_{view_name}_{sky_name}.{ext}
            Duplicate oconv commands are automatically removed while preserving order.
        """

        rpict_commands, oconv_commands, temp_octree_with_sky_paths, ra_tiff_commands = [], [], [], []

        for sky_file_path, view_file_path in product(sky_files, view_files):
            
            sky_file_name = Path(sky_file_path).stem
            view_file_name = Path(view_file_path).stem
            octree_with_sky_path = Path(self.octree_path).parent / f"{self.octree_base_name}_{sky_file_name}.oct"
            output_hdr_path = self.image_dir / f'{self.octree_base_name}_{view_file_name}_{sky_file_name}.hdr'

            temp_octree_with_sky_path = Path(self.octree_path).parent / f'{self.octree_base_name}_{sky_file_name}_temp.oct'
            oconv_command, rpict_command, ra_tiff_command = [
                rf'oconv -i {str(temp_octree_with_sky_path).replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}' ,
                rf'rpict -w -vtl -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}',
                rf'ra_tiff -e -4 {output_hdr_path} {self.image_dir / f"{output_hdr_path.stem}.tiff"}'
            ]

            temp_octree_with_sky_paths.append(temp_octree_with_sky_path)
            oconv_commands.append(oconv_command)
            rpict_commands.append(rpict_command)
            ra_tiff_commands.append(ra_tiff_command)
        
        oconv_commands = list(dict.fromkeys(oconv_commands))

        return temp_octree_with_sky_paths, oconv_commands, rpict_commands, ra_tiff_commands