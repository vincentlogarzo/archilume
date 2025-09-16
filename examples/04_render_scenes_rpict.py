
"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

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
            rf'oconv -i {str(temp_octree_with_sky_path).replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}' ,
            rf'rpict -w -vtl -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}',
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
overcast_sky_path = Path(__file__).parent.parent / "outputs" / "sky" / "TenK_cie_overcast.rad"

sky_files = [path for path in sky_files_dir.glob('*.sky')]
view_files = [path for path in view_files_dir.glob('*.vp')]
# FIXME: this code breaks when only one view file is present. An input of a singular view file must be allowable. 



# --- 2. Combine skyless octree with the TenK_cie_overcast.rad sky file for ambient file generation
"""
# example frozen skyless octree
oconv -f outputs\rad\materials.mtl outputs\rad\87cowles_BLD_noWindows.rad outputs\rad\87cowles_site.rad > outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct
FIXME: the above command is not correctly executed when running the example winter solstice file for the octree generation. 

# example radiance command: 
oconv -i outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct outputs\sky\TenK_cie_overcast.rad > outputs\octree\87cowles_BLD_noWindows_with_site_skyless_TenK_cie_overcast.oct 
"""
octree_with_overcast_sky_path = Path(octree_path).parent / f'{octree_path.stem}_TenK_cie_overcast.oct'
overcast_octree_command = str(rf'oconv -i {octree_path} {overcast_sky_path} > {octree_with_overcast_sky_path}')
utils.execute_new_radiance_commands(overcast_octree_command)

# --- 3. Rendering overcast sky octree with each view_file to generate a warmed ambient file to speed up the rendering process.
"""
# example radiance command warming up the ambient file:
rpict -w -t 2 -vtl -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 2048 -as 512 -ar 512 -ps 1 -pt 0.06 -af outputs\images\87cowles_BLD_noWindows_with_site_plan_L02.amb outputs\octree\87cowles_BLD_noWindows_with_site_skyless_TenK_cie_overcast.oct > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_indirect.hdr

# subsequent medium quality rendering with the ambient file producing an ouptut indirect image
rpict -w -t 2 -vtl -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -ab 2 -aa 0.1 -ar 1024 -ad 4096 -as 1024 -lr 12 -lw 0.00200 -af outputs\images\87cowles_BLD_noWindows_with_site_plan_L02.amb outputs\octree\87cowles_BLD_noWindows_with_site_skyless_TenK_cie_overcast.oct > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_indirect.hdr

"""
#TODO: setup actual execution section of this example code above. 

# --- 2. Generate all commands that shall be passsed to radiance programmes in parallel for sunny sky files. --- 
"""
# to combine an skyless octree with a sunny sky
    oconv -i outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct outputs\sky\SS_0621_0900.sky > outputs\octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct
# example radiance rpict command for direct sun image:
    rpict -w -vtl -t 2 -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -ab 0 -ad 1024 -as 64 -ar 64 -ps 5 -lw 0.001 outputs\octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900.hdr
"""
temp_octree_with_sky_paths, oconv_commands, rpict_commands, ra_tiff_commands = generate_commands(
    octree_path,
    sky_files,
    view_files,
    x_res       =2048, #1024
    y_res       =2048, #1024
    ab          =0,
    ad          =1024,
    ar          =64,
    as_val      =64,
    ps          =5, 
    lw          =0.001, # 0.005
)


# --- 3. generate temp files for oconv, combine these with sky files, then delete the temp files.
utils.copy_files(octree_path, temp_octree_with_sky_paths)
utils.execute_new_radiance_commands(oconv_commands, number_of_workers = 6)
utils.delete_files(temp_octree_with_sky_paths)

# --- 6. rendering octrees with a given view files input ---
utils.execute_new_radiance_commands(rpict_commands, number_of_workers = 8)

#TODO: run pcomb to comine the indirect hdr file with the direct sunlight hdr for each timestep to create a hdr file that can be convert to a tiff and then to a .giff with a higher quality look and feel. This gif cannot be used for results generation, results will be generated form the direct .hdr files only, as they represent the sunlit are
# 
"""
pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_indirect.hdr outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900.hdr > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900_combined.hdr
"""

# --- 7. run ra_tiff to convert output hdr files to .tiff ---
"""
ra_tiff -e -4 outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900_combined.hdr outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900_combined.tiff
"""
utils.execute_new_radiance_commands(ra_tiff_commands, number_of_workers = 10)


# ---8. Overlay room boundaries with the apartment numbers and room identifier of interest with an instant area of compliance for that timestep, place timestamp on image, simulated on: X and sunny sky winter solstice June 21 : 09:00 



# --- 9. turn tiff files into a giff file. 
