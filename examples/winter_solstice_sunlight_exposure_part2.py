
"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 
"""

from itertools import product
from archilume import utils
from pathlib import Path

# --- 01. get input files ---
skyless_octree_path = Path(__file__).parent.parent / "outputs" / "octree" / "87cowles_BLD_noWindows_with_site_skyless.oct"
overcast_sky_file_path = Path(__file__).parent.parent / "outputs" / "sky" / "TenK_cie_overcast.rad"
sky_files_dir = Path(__file__).parent.parent / "outputs" / "sky"
view_files_dir = Path(__file__).parent.parent / "outputs" / "views_grids"
image_dir = Path(__file__).parent.parent / "outputs" / "images"
sky_files = [path for path in sky_files_dir.glob('*.sky')]
view_files = [path for path in view_files_dir.glob('*.vp')] 
x_res = 2048 # number of pixels in the x direction
y_res = 2048 # number of pixels in the y direction


def generate_overcast_sky_rendering_commands(
        octree_path: Path, 
        image_dir: Path, 
        sky_file: Path, 
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
            - rpict_low_qual_commands (List[str]): Commands for low quality rendering (ambient file warming).
            - rpict_med_qual_commands (List[str]): Commands for medium quality rendering.
            
    Note:
        # example radiance command warming up the ambient file:
            rpict -w -t 2 -vtv -vf view.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 2048 -as 512 -ar 512 -ps 1 -pt 0.06 -af ambient.amb model_overcast_sky.oct
        # subsequent medium quality rendering with the ambient file producing an ouptut indirect image
            rpict -w -t 2 -vtv -vf view.vp -x 2048 -y 2048 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -ab 2 -aa 0.1 -ar 1024 -ad 4096 -as 1024 -lr 12 -lw 0.00200 -af ambient_file.amb model_overcast_sky.oct > output_image.hdr
    """
    
    octree_base_name = octree_path.stem.replace('_skyless', '')
    octree_with_overcast_sky_path = octree_path.parent / f"{octree_base_name}_{sky_file.stem}.oct"
    overcast_octree_command = str(rf"oconv -i {octree_path} {sky_file} > {octree_with_overcast_sky_path}")

    rpict_low_qual_commands, rpict_med_qual_commands = [], []

    for octree_with_overcast_sky_path, view_file_path in product([octree_with_overcast_sky_path], view_files):
        
        ambient_file_path = image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{sky_file.stem}.amb"
        output_hdr_path = image_dir / f"{octree_base_name}_{Path(view_file_path).stem}__{sky_file.stem}.hdr"

        # constructed commands that will be executed in parallel from each other untill all are complete.
        rpict_low_qual_command, rpict_med_qual_command = [
            rf"rpict -w -t 2 -vtv -vf {view_file_path} -x {x_res[0]} -y {y_res[0]} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path}",
            rf"rpict -w -t 2 -vtv -vf {view_file_path} -x {x_res[1]} -y {y_res[1]} -aa {aa} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -pt {pt} -pj {pj} -dj {dj} -lr {lr} -lw {lw} -af {ambient_file_path} {octree_with_overcast_sky_path} > {output_hdr_path}"
        ]

        rpict_low_qual_commands.append(rpict_low_qual_command)
        rpict_med_qual_commands.append(rpict_med_qual_command)

    return overcast_octree_command, rpict_low_qual_commands, rpict_med_qual_commands

def generate_sunny_sky_rendering_commands(octree_path: Path, image_dir: Path, sky_files: list[Path], view_files: list[Path], x_res: int=1024, y_res: int=1024, ab: int=0, ad: int=128, ar: int=64, 
 as_val: int=64, ps: int=6, lw: float=0.00500) -> tuple[list[Path], list[str], list[str], list[str], list[str]]:
    """
    TODO: update the input variables with type and ranges of allowable inputs given information found online. 
    Generates oconv, rpict, and ra_tiff commands for rendering combinations of octree, sky, and view files.

    Creates all permutations of sky files and view files with a single octree file, generating
    the necessary Radiance commands for the complete rendering pipeline: octree compilation
    with sky (oconv), scene rendering (rpict), and HDR to TIFF conversion (ra_tiff).

    Args:
        octree_path (Path): Path to the base octree file (typically skyless).
        image_dir (Path): Directory path for output images.
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
            - pcomb_commands (list[str]): Commands to combine indirect and direct hdr files.
            - ra_tiff_commands (list[str]): Commands to convert HDR output to tiff format with 8-bit flowting points precision.
            
    Note:
        Output files are named using the pattern: {octree_base}_{view_name}_{sky_name}.{ext}
        Duplicate oconv commands are automatically removed while preserving order.
    """

    rpict_commands, oconv_commands, temp_octree_with_sky_paths, pcomb_commands, ra_tiff_commands = [], [], [], [], []

    octree_base_name = octree_path.stem.replace('_skyless', '')


    for sky_file_path, view_file_path in product(sky_files, view_files):
        
        sky_file_name = Path(sky_file_path).stem
        view_file_name = Path(view_file_path).stem
        octree_with_sky_path = Path(octree_path).parent / f"{octree_base_name}_{sky_file_name}.oct"
        output_hdr_path = image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}.hdr"
        output_hdr_path_combined = image_dir / f"{octree_base_name}_{view_file_name}_{sky_file_name}_combined.hdr"
        overcast_hdr_path = image_dir / f"{octree_base_name}_{view_file_name}__TenK_cie_overcast.hdr"

        # constructed commands that will be executed in parallel from each other untill all are complete.
        #FIXME: the -vtv n the rpict command may be redundant as this is already specified in the view file. update the view file code to use vtv instead of vtl and remove -vtv from here and test the results. 
        temp_octree_with_sky_path = Path(octree_path).parent / f'{octree_base_name}_{sky_file_name}_temp.oct'
        oconv_command, rpict_command, pcomb_command, ra_tiff_command = [
            rf"oconv -i {str(temp_octree_with_sky_path).replace('_skyless', '')} {sky_file_path} > {octree_with_sky_path}" ,
            rf"rpict -w -vtv -t 3 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_hdr_path}",
            rf'pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" {overcast_hdr_path} {output_hdr_path} > {output_hdr_path_combined}',
            rf"ra_tiff -e -2 {output_hdr_path_combined} {image_dir / f'{output_hdr_path_combined.stem}.tiff'}"
        ]

        temp_octree_with_sky_paths.append(temp_octree_with_sky_path)
        oconv_commands.append(oconv_command)
        rpict_commands.append(rpict_command)
        pcomb_commands.append(pcomb_command)
        ra_tiff_commands.append(ra_tiff_command)
    
    # get rid of duplicate oconv commands while retaining list order
    oconv_commands = list(dict.fromkeys(oconv_commands))

    return temp_octree_with_sky_paths, oconv_commands, rpict_commands, pcomb_commands, ra_tiff_commands


# --- 02. Combine skyless octree with the TenK_cie_overcast.rad sky file for ambient file generation, these renderings will be compiled with the sunny sky rendering later. ---
r"""
# 2.1 example frozen skyless octree
    oconv -f outputs\rad\materials.mtl outputs\rad\87cowles_BLD_noWindows.rad outputs\rad\87cowles_site.rad > outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct
# 2.2 example radiance command: 
    oconv -i outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct outputs\sky\TenK_cie_overcast.rad > outputs\octree\87cowles_BLD_noWindows_with_site_skyless_TenK_cie_overcast.oct 
# 2.3 example radiance command warming up the ambient file:
    rpict -w -t 2 -vtv -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 2048 -as 512 -ar 512 -ps 1 -pt 0.06 -af outputs\images\87cowles_BLD_noWindows_with_site_TenK_cie_overcast_plan_L02.amb outputs\octree\87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct > outputs\images\87cowles_BLD_noWindows_with_site_TenK_cie_overcast_plan_L02.hdr
# 2.4 subsequent medium quality rendering with the ambient file producing an ouptut indirect image
    rpict -w -t 2 -vtv -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -aa 0.1 -ab 2 -ad 4096 -as 1024 -ar 1024 -dj 0.7 -lr 12 -lw 0.002 -pj 1 -ps 4 -pt 0.05 -af outputs\images\87cowles_BLD_noWindows_with_site_TenK_cie_overcast.amb outputs\octree\87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct > outputs\images\87cowles_BLD_noWindows_with_site_TenK_cie_overcast_plan_L02.hdr
"""

overcast_octree_command, rpict_low_qual_commands, rpict_med_qual_commands = generate_overcast_sky_rendering_commands(
    skyless_octree_path,
    image_dir, 
    overcast_sky_file_path, 
    view_files, 
    x_res       = [x_res/4, x_res], 
    y_res       = [y_res/4, y_res]
    )

utils.execute_new_radiance_commands(overcast_octree_command, number_of_workers = 1)
utils.execute_new_radiance_commands(rpict_low_qual_commands, number_of_workers = 8)
utils.execute_new_radiance_commands(rpict_med_qual_commands, number_of_workers = 8)


# --- 03. Generate all commands that shall be passsed to radiance programmes in parallel for sunny sky files. --- 
r"""
# 3.1 to combine an skyless octree with a sunny sky
    oconv -i outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct outputs\sky\SS_0621_0900.sky > outputs\octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900.hdr
"""

temp_octree_with_sky_paths, oconv_commands, rpict_commands, pcomb_commands, ra_tiff_commands = generate_sunny_sky_rendering_commands(
    skyless_octree_path,
    image_dir,
    sky_files,
    view_files,
    x_res       = x_res,
    y_res       = y_res
    )

utils.copy_files(skyless_octree_path, temp_octree_with_sky_paths)
utils.execute_new_radiance_commands(oconv_commands, number_of_workers = 6)
utils.delete_files(temp_octree_with_sky_paths)


# --- 04. rendering sunny sky octrees for each view_file ---
r"""
4.1:
    rpict -w -vtv -t 3 -vf view_file.vp -x 2048 -y 2048 -ab 0 -ad 1024 -as 64 -ar 64 -ps 5 -lw 0.001 scene_with_sky.oct > output.hdr
"""
utils.execute_new_radiance_commands(rpict_commands, number_of_workers = 10)
#TODO invesitgate overture to increase quality of the output simage. 

# --- 05. Add the direct sunlight and indrect daylighting renderings together. 
r"""
5.1:
    pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" image_overcast.hdr image_sunny_sky.hdr > combined.hdr
    pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" outputs\images\87cowles_BLD_noWindows_with_site_plan_L02__TenK_cie_overcast.hdr outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_1400.hdr > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_1400_combined.hdr
"""
utils.execute_new_radiance_commands(pcomb_commands, number_of_workers = 14)


# --- 06. run ra_tiff to convert output hdr files and retain dynamic range ---
r"""
7.1: 8-bit floating point, use [f] or [w] options for either 32 bit or 16 bit tiff files respectively. They are much larger files but retain the dynamic range of the hdr file.
    ra_tiff -e -2 outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_1400_combined.hdr outputs\images\87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_1400_combined.tiff
"""
# TODO: automate exposure adjustment based on image histogram analysis to avoid overexposure or underexposure in the tiff outputs.

utils.execute_new_radiance_commands(ra_tiff_commands, number_of_workers = 10)
# combined_hdr_files_paths_for_deletion = [Path(cmd.split(' > ')[-1].strip()) for cmd in pcomb_commands if ' > ' in cmd]
# utils.delete_files(combined_hdr_files_paths_for_deletion)


# --- 07. Stamp images with relevant information ---

# --- 07.1 create a pixel to real world coordiante map.txt ---
utils.create_pixel_to_world_mapping_from_hdr(self.image_dir)

# --- 07.2 First pass overlay to each .gif file to stamp with "Simulated on YYMMDD HH:MM for June 21 09:00 latitude: -37.8136" ---
tiff_files_to_stamp = [path for path in image_dir.glob('*_combined.tiff')]

# Extract timestamps from filenames
#TODO: fix up the lat long to be dependent on project location inputs.
utils.stamp_tiff_files(
    tiff_files_to_stamp, 
    font_size           = 24, 
    text_color          = (255, 255, 255), # yellow text RGB 
    background_alpha    = 180, 
    number_of_workers   = 10
    )

# --- 07.3 Second pass overlay to stamp each .gif with area of interest (.AOI) including the "APT: apartment_name, ROOM: room_name" in the centre of room. Bedrooms will be quantitied for information and shown differently to the rest as they do not form part of compliance. e.g. if the relocation of a living space to the current location of the bedroom would affect compliance or allow it to pass. ---
# utils.stamp_tiff_files_with_aoi(
#     tiff_files_to_stamp, 
#     lineweight              = 1, 
#     font_size               = 32, 
#     text_color              = (255, 0, 0), 
#     background_alpha        = 180, 
#     number_of_workers       = 10
#     )

# FIXME: Optimize stamping by creating one stamp per level and reusing for all images on that level

# --- 07.4 Third pass overlay of the results of each time step on each .gif gile for each aoi, there may need to be work to exclude full height or determine of % of compliant area. If its an absolute amount of area, then discrpancies between the AOI and say kitchen joinery does not need ot be considere , it is is a % of compliance area, then excluding part of the aoi that are acually our of bounds is important.Also output a csv file with the results of each aoi
# TODO: Add real world coordinate mapping to processed boundaries CSV after HDR rendering
# TODO: Regenerate AOI files with real world coordinates and cross-check against final images
# TODO: Create interactive UI for AOI adjustment with persistent storage per room

# --- 07.5 Create summary image that shows a scale with each pixel to determine the combined area that is illuminanted in each aoi at each time step, and draw a chart of each data point to show the real area illuminanted and the period of time it occurs over. Then determine then place the ADDG sunlihgt access thresholds of compliance, i. .e 1m2 for at least 15 mins in either the living, or open private space. 


# --- 08. combine individual gif files with overlays into animated gif with a results table on the side
utils.combine_tiffs_by_view(image_dir, view_files, output_format='gif', number_of_workers=8)
utils.combine_tiffs_by_view(image_dir, view_files, output_format='mp4', number_of_workers=8)

# --- 9. Create final MP4 combining all the individual MP4s at lower quality into a grid
individual_view_mp4s = [path for path in image_dir.glob('animated_results_*.mp4')]
utils.create_grid_mp4(individual_view_mp4s, image_dir, grid_size=(3, 2), target_size=(1024, 1024), fps=2)

individual_view_gifs = [path for path in image_dir.glob('animated_results_*.gif')]
utils.create_grid_gif(individual_view_gifs, image_dir, grid_size=(3, 2), target_size=(2048, 2048), fps=2)