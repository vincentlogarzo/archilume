
"""
This code uses three main radiance programmes: 
oconv - compile an octree which is a file ready to be rendered
rpict - rendering a scene using a view and the above octree
ra_tiff - convert output hdr file format to tiff or simple viewing. 

rpict defauls inputs are seen below, not all are utilised, but could be useful in future iteration of this code. 
rpict -w -vtv -t 15 -vf views_grids/plan_L02.vp -x 1024 -y 1024 -ab 1 -ad 1028 -ar 256 -as 256 -ps 5 octrees/87cowles_Jun21_1030_ss_temp.oct > results/87cowles_Jun21_1030_ss.hdr

rpict -defaults # to get defaults

-vp 0.000000 0.000000 0.000000      # irradiance calculation point
-vt 0.000000 0.000000 1.000000      # view type perspective
-vup 0.000000 1.000000 0.000000     # view point
-vdu 0.000000 0.000000 1.000000     # view up
-vh 45.000000                       # view horizontal size
-vv 45.000000                       # view vertical size
-vo 0.000000                        # view fore clipping plane
-va 0.000000                        # view aft clipping plane
-vl 0.000000                        # view left
-vr 0.000000                        # view right
-x 512                              # x resolution
-y 512                              # y resolution
-pa 1.000000                        # pixel aspect ratio
-pj 0.670000                        # pixel jitter
-ps 1.000000                        # pixel sample
-pt 0.050000                        # pixel threshold
-bv                                 # back face visibility, on
-dt 0.050000                        # direct threshold
-dc 1.000000                        # direct certainty
-dj 0.000000                        # direct jitter
-ds 0.250000                        # direct sample density
-dr 1                               # direct relay
-dp 512                             # direct pixel density
-st 0.150000                        # specular filter
-sj 1.000000                        # specular threshold
-av 0.000000 0.000000 0.000000      # ambient value
-aw 0                               # ambient value weight
-ab 0                               # ambient bounces
-aa 0.200000                        # ambient accuracy
-ar 96                              # ambient resolution
-as 0                               # ambient division
-ad 0                               # ambient super-samples
-e 0.00e+00 0.00e+00 0.00e+00       # extinction coefficient
-ss 0.000000 0.000000 0.000000      # scattering albedo
-se 0.000000                        # scattering eccentricity
-sm 4.000000                        # max sampling distance
-st 0                               # time weight
-lw 0.005000                        # limit weight
-t 0                                # time between reports
-n 1                                # number of rays

"""

import os
from itertools import product
import utils
import sys

def generate_commands(octree,sky_files, view_files, x_res=1024, y_res=1024, ab=2, ad=128, ar=64, as_val=64, ps=6, lw=0.00500,output_dir='results'):
    """
    Generates rpict and ra_tiff commands for a list of input files.

    Args:
        input_files: A list of input octree file paths.
        sky_files: 
        view_file: The path to the view file.
        x_res: The x-resolution for rpict.
        y_res: The y-resolution for rpict.
        ab: Ambient bounces for rpict.
        ad: Ambient divisions for rpict.
        ar: Ambient resolution for rpict.
        as_val: Ambient samples for rpict.
        ps: Pixel size for rpict.
        output_dir: The directory to store output files.

    Returns:
        A tuple containing:
            - A list of file names without extensions.
            - A list of rpict commands.
            - A list of ra_tiff commands.
    """

    octree_base_name = os.path.basename(octree)
    octree_no_ext = octree_base_name.replace('_skyless.oct', '')

    rpict_commands = []
    oconv_commands = []
    temp_file_names = []
    ra_tiff_commands = []

    for sky_file_path, view_file_path in product(sky_files, view_files):
        
        sky_file_base_name = os.path.basename(sky_file_path)
        sky_file_no_ext = os.path.splitext(sky_file_base_name)[0]
        view_file_base_name = os.path.basename(view_file_path)
        view_file_no_ext = os.path.splitext(view_file_base_name)[0]
        output_file_path = os.path.join(output_dir, f'{octree_no_ext}_{view_file_no_ext}_{sky_file_no_ext}.hdr')
        output_file_path_no_ext = os.path.splitext(output_file_path)[0]
        octree_with_sky_path = rf'octrees/{octree_no_ext}_{sky_file_no_ext}.oct'
        octree_with_sky_path_temp = rf'octrees/{octree_no_ext}_{sky_file_no_ext}_temp.oct'

        temp_file_name = octree_with_sky_path_temp
        # shutil.copy(rf'octrees/{octree_base_name}', octree_with_sky_path_temp) # copy original octree
        oconv_command = rf'oconv -i {octree_with_sky_path_temp} {sky_file_path} > {octree_with_sky_path}' # substitute original input file with copied file name
        rpict_command = rf'rpict -w -vtv -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_file_path}'
        # Halve the exposure and retain dynamic range in a compressed tiff files a the options. 
        ra_tiff_command = rf'ra_tiff -e -4 {output_file_path} {output_file_path_no_ext}.tiff'

        temp_file_names.append(temp_file_name)
        oconv_commands.append(oconv_command)
        rpict_commands.append(rpict_command)
        ra_tiff_commands.append(ra_tiff_command)
    
    # get rid of duplicate oconv commands
    oconv_commands = list(dict.fromkeys(oconv_commands))

    return temp_file_names, oconv_commands, rpict_commands, ra_tiff_commands

def execute_new_radiance_commands(commands, number_of_workers=1):
    """ 
    This code is running the below line in the terminal with various combinations of inputs .oct and .sky files. 
    oconv -i octrees/87cowles_skyless.oct sky/sunny_sky_0621_0900.sky > octrees/87cowles_sunny_sky_0621_0900.oct
    rpict -vf views_grids/plan_L01.vp -x 1024 -y 1024 -ab 3 -ad 128 -ar 64 -as 64 -ps 6 octrees/87cowles_SS_0621_1030.oct > results/87cowles_plan_L01_SS_0621_1030.hdr
    ra_tiff results/87cowles_SS_0621_1030.hdr results/87cowles_SS_0621_1030.tiff

    # Accelerad rpict
    must set cuda enable GPU prior to executing the accelerad_rpict command below. 
    check CUDA GPUs
    nvidia-smi 
    Command
    med | accelerad_rpict -vf views_grids\floorplate_view_L1.vp -x 1024 -y 1024 -ab 1 -ad 1024 -ar 256 -as 256 -ps 5 octrees/untitled_Jun21_0940.oct > results/untitled_floor_plate_Jun21_0940_med_accelerad.hdr

    high |  rpict -vf views_grids\view.vp -x 1024 -y 1024 -ab 2 -ad 1024 -ar 256 -as 256 -ps 5 octrees/untitled_Jun21_0940.oct > results/untitled_floor_plate_Jun21_0940_high.hdr 
    """ 
    filtered_commands = []
    for command in commands:
        try:
            # First, try splitting by the '>' operator
            output_path = command.split(' > ')[1].strip()
        except IndexError:
            # If that fails, it's likely a command like ra_tiff.
            # Split by spaces and take the last element.
            output_path = command.split()[-1].strip()

        # Now, check if the extracted path exists
        if not os.path.exists(output_path):
            filtered_commands.append(command)

    utils.run_commands_parallel(
        filtered_commands,
        number_of_workers = number_of_workers # number of workers should not go over 6 for oconv
        )

    print('All new commands have successfully completed')

    return 

# --- 1. get input files ---
octree = 'octrees/87cowles_noWindows_skyless.oct'
octree_base_name = os.path.basename(octree)

if not octree:
    print("Error: No octree file selected. Exiting program.")
    sys.exit(1) # Exit with status code 1 to indicate an error

sky_files = utils.get_files_from_dir('sky','.sky')
view_files = utils.get_files_from_dir('views_grids','.vp')
# TODO: this code breaks when only one view file is presented. An input of a singular view file must be allowable. 

# --- 2. Generate all commands that shall be passsed to radiance programmes in parallel --- 
temp_file_names, oconv_commands, rpict_commands, ra_tiff_commands = generate_commands(
    octree,
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

# for oconv_command in oconv_commands:
#     print(oconv_command)

# --- 3. generate temp files for oconv to use.
utils.copy_files_concurrently(rf'octrees/{octree_base_name}',temp_file_names)

# TODO: run code to run daylihgt sim on each level using overcast sky, and then very low quality sunny sky simulations for each time increment, and them pcomb the high quality dayihgt sim together with each low qaulity sunny sky simulation to create a high quality end result for every image. 

# --- 4. run oconv commands if octree does not exist ---
execute_new_radiance_commands(oconv_commands, number_of_workers = 6)

# TODO: Find and delete all files ending in '_temp' in the specified directory.

# --- 5. rendering octrees with a given view files input ---
execute_new_radiance_commands(rpict_commands, number_of_workers = 8)

# --- 6. run ra_tiff to convert output hdr files to .tiff ---
execute_new_radiance_commands(ra_tiff_commands, number_of_workers = 10)
