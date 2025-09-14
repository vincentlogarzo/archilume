
"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

import os
from itertools import product
from archilume import utils
from pathlib import Path

def generate_commands(octree_path: Path, sky_files: list[Path], view_files: list[Path], x_res=1024, y_res=1024, ab=2, ad=128, ar=64, 
 as_val=64, ps=6, lw=0.00500) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Generates oconv, rpict, and ra_tiff commands for rendering combinations of octree, sky, and view files.

    Creates all permutations of sky files and view files with a single octree file, generating
    the necessary Radiance commands for the complete rendering pipeline: octree compilation
    with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

    Args:
        octree_path (Path): Path to the base octree file (typically skyless).
        sky_files (list[Path]): List of sky file paths (.sky files).
        view_files (list[Path]): List of view file paths (.vp files).
        x_res (int, optional): X-resolution for rpict rendering. Defaults to 1024.
        y_res (int, optional): Y-resolution for rpict rendering. Defaults to 1024.
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
            - ra_tiff_commands (list[str]): Commands to convert HDR output to TIFF format.
            
    Note:
        Output files are named using the pattern: {octree_base}_{view_name}_{sky_name}.{ext}
        Duplicate oconv commands are automatically removed while preserving order.
    """

    rpict_commands = []
    oconv_commands = []
    temp_octree_with_sky_paths = []
    ra_tiff_commands = []

    octree_base_name = str(octree_path.stem).replace('_skyless', '')
    image_dir = Path(__file__).parent.parent / "outputs" / "images"

    for sky_file_path, view_file_path in product(sky_files, view_files):
        
        sky_file_name = Path(sky_file_path).stem
        view_file_name = Path(view_file_path).stem
        octree_with_sky_path = Path(octree_path).parent / f'{octree_path.stem}_{sky_file_name}.oct'
        output_hdr_path = image_dir / f'{octree_base_name}_{view_file_name}_{sky_file_name}.hdr'

        # constructed commands that will be executed in parallel from each other untill all are complete.
        temp_octree_with_sky_path = Path(octree_path).parent / f'{octree_base_name}_{sky_file_name}_temp.oct'
        oconv_command, rpict_command, ra_tiff_command = [
            rf'oconv -i {temp_octree_with_sky_path.replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}' ,
            rf'rpict -w -vtv -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}',
            rf'ra_tiff -e -4 {output_hdr_path} {image_dir / f"{output_hdr_path.stem}.tiff"}' # Half exposure of image and retain dynamic range
        ]

        temp_octree_with_sky_paths.append(temp_octree_with_sky_path)
        oconv_commands.append(oconv_command)
        rpict_commands.append(rpict_command)
        ra_tiff_commands.append(ra_tiff_command)
    
    # get rid of duplicate oconv commands while retaining list order
    oconv_commands = list(dict.fromkeys(oconv_commands))

    return temp_octree_with_sky_paths, oconv_commands, rpict_commands, ra_tiff_commands


# --- 1. get input files ---
octree_path = Path(__file__).parent.parent / "outputs" / "octree" / "87cowles_BLD_noWindows_with_site_skyless.oct"
sky_files_dir = Path(__file__).parent.parent / "outputs" / "sky"
view_files_dir = Path(__file__).parent.parent / "outputs" / "views_grids"
overcast_sky_path = Path(__file__).parent.parent / "outputs" / "sky" / "TenK_cie_overcast.sky"

sky_files = [path for path in sky_files_dir.glob('*.sky')]
view_files = [path for path in view_files_dir.glob('*.vp')]
# FIXME: this code breaks when only one view file is present. An input of a singular view file must be allowable. 

# --- 2. Combine skyless octree with the TenK_cie_overcast.rad sky file for ambient file generation
octree_with_overcast_sky_path = Path(octree_path).parent / f'{octree_path.stem}_TenK_cie_overcast.oct'
overcast_octree_command = str(rf'oconv -i {octree_path} {overcast_sky_path} > {octree_with_overcast_sky_path}')
utils.execute_new_radiance_commands(overcast_octree_command)

# --- 3. Rendering overcast sky octree with each view_file to generate an ambient file.
#TODO: setup this new execution to only generate new ambient files. 


# --- 2. Generate all commands that shall be passsed to radiance programmes in parallel --- 
temp_octree_with_sky_paths, oconv_commands, rpict_commands, ra_tiff_commands = generate_commands(
    octree_path,
    sky_files,
    view_files,
    x_res       =2048, #1024
    y_res       =2048, #1024
    ab          =2,
    ad          =1024,
    ar          =64,
    as_val      =64,
    ps          =5, 
    lw          =0.001, # 0.005
)


# --- 3. generate temp files for oconv to use.
utils.copy_files(octree_path, temp_octree_with_sky_paths)


# --- 4. run oconv commands to combine the skyless octree with its respective sky file. ---
utils.execute_new_radiance_commands(oconv_commands, number_of_workers = 6)


# --- 5. delete temp files after use to reduce storage load ---
utils.delete_files(temp_octree_with_sky_paths)


# --- 6. rendering octrees with a given view files input ---
utils.execute_new_radiance_commands(rpict_commands, number_of_workers = 8)
#TODO: update this rpict command to have an input of the ambient file in each subequent simulation. This should be split into direct only calcualtions that will be used for results extraction (i.e. # hrs each pixel is illuminated, and an direct simulation with an ambient file input that will serve as a more high quality rendering in order to put together a .gif file of the results.

# TODO: run code to run daylihgt sim on each level using overcast sky, and then very low quality sunny sky simulations for each time increment, and them pcomb the high quality daylight sim together with each low qaulity sunny sky simulation to create a high quality end result for every image that can then be combined into a giff for the day for each level, and then utlimately a results summary can be drawn from the original source files.


# --- 7. run ra_tiff to convert output hdr files to .tiff ---
utils.execute_new_radiance_commands(ra_tiff_commands, number_of_workers = 10)
