import datetime
import os
import logging
import os
from datetime import datetime

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)

def generate_commands(
    octree,
    sky_files,
    view_files,
    x_res=1024,
    y_res=1024,
    ab=2,
    ad=128,
    ar=64,
    as_val=64,
    ps=6,
    lw=0.00500,
    output_dir="results"):

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
    octree_no_ext = octree_base_name.replace("_skyless.oct", "")

    rpict_commands = []
    oconv_commands = []
    temp_file_names = []
    ra_tiff_commands = []

    for sky_file_path, view_file_path in product(sky_files, view_files):

        sky_file_base_name = os.path.basename(sky_file_path)
        sky_file_no_ext = os.path.splitext(sky_file_base_name)[0]
        view_file_base_name = os.path.basename(view_file_path)
        view_file_no_ext = os.path.splitext(view_file_base_name)[0]
        output_file_path = os.path.join(
            output_dir, f"{octree_no_ext}_{view_file_no_ext}_{sky_file_no_ext}.hdr"
        )
        output_file_path_no_ext = os.path.splitext(output_file_path)[0]
        octree_with_sky_path = rf"octrees/{octree_no_ext}_{sky_file_no_ext}.oct"
        octree_with_sky_path_temp = rf"octrees/{octree_no_ext}_{sky_file_no_ext}_temp.oct"

        temp_file_name = octree_with_sky_path_temp
        # shutil.copy(rf'octrees/{octree_base_name}', octree_with_sky_path_temp) # copy original octree
        oconv_command = rf"oconv -i {octree_with_sky_path_temp} {sky_file_path} > {octree_with_sky_path}"  # substitute original input file with copied file name
        rpict_command = rf"rpict -w -vtv -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_file_path}"
        # Halve the exposure and retain dynamic range in a compressed tiff files a the options.
        ra_tiff_command = rf"ra_tiff -e -4 {output_file_path} {output_file_path_no_ext}.tiff"

        temp_file_names.append(temp_file_name)
        oconv_commands.append(oconv_command)
        rpict_commands.append(rpict_command)
        ra_tiff_commands.append(ra_tiff_command)

    # get rid of duplicate oconv commands
    oconv_commands = list(dict.fromkeys(oconv_commands))

    return temp_file_names, oconv_commands, rpict_commands, ra_tiff_commands
    """
    Generates Radiance sky files for a specific date, time range, and location.

    The generator is configured with all necessary parameters upon initialization.
    The generate_sunny_sky_series() method then executes the sky file creation.

    Args (for the auto-generated __init__):
        lat (float): The latitude for the sky generation.
        lon (float): The longitude for the sky generation.
        year (int): The year for the sky generation series.
        month (int): The month for the series.
        day (int): The day of the month for the series.
        start_hour (int): The starting hour for the series (0-23).
        end_hour (int): The ending hour for the series (0-23).
        output_dir (str, optional): Directory to save sky files. Defaults to "sky".
        minute_increment (int, optional): Increment in minutes. Defaults to 5.

    Attributes (available after object creation):
        str_lat (str): Latitude stored as a string.
        str_lon (str): Longitude stored as a string.
        # Plus all the __init__ args are stored as attributes.
    """

    # Core location parameters
    lat: float
    lon: float
    std_meridian: float

    # Parameters for the specific sky series
    year: int
    month: int
    day: int
    start_hour_24hr_format: int
    end_hour_24hr_format: int

    # Optional parameters with defaults
    output_dir: str = "sky"
    minute_increment: int = 5

    def __post_init__(self):
        """
        Performs post-initialization setup:
        - Converts lat/lon to strings for use with gensky.
        - Creates the output directory if it doesn't exist.
        """
        self.str_lat = str(self.lat)
        self.str_lon = str(self.lon)
        self.str_std_meridian = str(self.std_meridian)

        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                print(f"Created output directory: {self.output_dir}")
            except OSError as e:
                print(f"Error creating directory {self.output_dir}: {e}")

    def __generate_single_sunny_skyfile(self, month, day, time_hhmm_str, output_time_suffix_str):
        """
        Generates a single sky file for a specific date and time using gensky.

        This method assumes a sunny sky (+s) and specific meridian for gensky.
        It also appends a standard skyfunc glow definition.

        Args:
            month (int): The month (1-12).
            day (int): The day of the month.
            time_hhmm_str (str): The time in "HH:MM" format (e.g., "09:00").
            output_time_suffix_str (str): A string used in the output filename (e.g., "0900" for 9 AM).
        """

        # Construct a descriptive filename using month and day arguments
        month_str = f"{month:02d}"
        day_str = f"{day:02d}"
        output_filename_base = f"SS_{month_str}{day_str}_{output_time_suffix_str}.sky"
        output_filepath = os.path.join(self.output_dir, output_filename_base)

        print(f"Outputting to: {output_filepath}")

        try:
            # Append skyfunc lines that create more realistic sky
            with open(output_filepath, "w") as outfile:
                skyfunc_description = f"""#Radiance Sky file: Ark Resources Pty Ltd

!gensky {str(month)} {str(day)} {time_hhmm_str} +s -a {self.str_lat} -o {self.str_lon} -m {self.str_std_meridian}

skyfunc glow skyglow
0 0
4 0.7 0.8 1.0 0
skyglow source sky
0 0
4 0 0 1 180

skyfunc glow grndglow
0 0
4 0.20 0.20 0.20 0
grndglow source ground
0 0
4 0 0 -1 180
"""
                outfile.write(skyfunc_description)
                print(f"Successfully generated: {output_filepath}")
        except:
            print(f"Error running gensky for {time_hhmm_str}")

    def generate_sunny_sky_series(self):
        """
        Generates a series of sky files based on the parameters
        set during object initialization.
        """
        print(
            f"\nStarting sky generation for {self.month}/{self.day}/{self.year} from {self.start_hour_24hr_format}:00 to {self.end_hour_24hr_format}:00 "
            f"at {self.str_lat} lat, {self.str_lon} lon."
        )

        # Create the output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created output directory: {self.output_dir}")

        start_dt = datetime.datetime(
            self.year, self.month, self.day, self.start_hour_24hr_format, 0
        )
        end_dt = datetime.datetime(self.year, self.month, self.day, self.end_hour_24hr_format, 0)
        time_delta = datetime.timedelta(minutes=self.minute_increment)
        current_dt = start_dt

        while current_dt <= end_dt:
            formatted_time_for_gensky = current_dt.strftime("%H:%M")  # e.g., "09:00"
            formatted_time_for_filename = current_dt.strftime("%H%M")  # e.g., "0900"

            self.__generate_single_sunny_skyfile(
                month=current_dt.month,
                day=current_dt.day,
                time_hhmm_str=formatted_time_for_gensky,
                output_time_suffix_str=formatted_time_for_filename,
            )
            current_dt += time_delta
        print("\nSky generation series complete.")

    octree,
    sky_files,
    view_files,
    x_res=1024,
    y_res=1024,
    ab=2,
    ad=128,
    ar=64,
    as_val=64,
    ps=6,
    lw=0.00500,
    output_dir="results"):

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
    octree_no_ext = octree_base_name.replace("_skyless.oct", "")

    rpict_commands = []
    oconv_commands = []
    temp_file_names = []
    ra_tiff_commands = []

    for sky_file_path, view_file_path in product(sky_files, view_files):

        sky_file_base_name = os.path.basename(sky_file_path)
        sky_file_no_ext = os.path.splitext(sky_file_base_name)[0]
        view_file_base_name = os.path.basename(view_file_path)
        view_file_no_ext = os.path.splitext(view_file_base_name)[0]
        output_file_path = os.path.join(
            output_dir, f"{octree_no_ext}_{view_file_no_ext}_{sky_file_no_ext}.hdr"
        )
        output_file_path_no_ext = os.path.splitext(output_file_path)[0]
        octree_with_sky_path = rf"octrees/{octree_no_ext}_{sky_file_no_ext}.oct"
        octree_with_sky_path_temp = rf"octrees/{octree_no_ext}_{sky_file_no_ext}_temp.oct"

        temp_file_name = octree_with_sky_path_temp
        # shutil.copy(rf'octrees/{octree_base_name}', octree_with_sky_path_temp) # copy original octree
        oconv_command = rf"oconv -i {octree_with_sky_path_temp} {sky_file_path} > {octree_with_sky_path}"  # substitute original input file with copied file name
        rpict_command = rf"rpict -w -vtv -t 15 -vf {view_file_path} -x {x_res} -y {y_res} -ab {ab} -ad {ad} -ar {ar} -as {as_val} -ps {ps} -lw {lw} {octree_with_sky_path} > {output_file_path}"
        # Halve the exposure and retain dynamic range in a compressed tiff files a the options.
        ra_tiff_command = rf"ra_tiff -e -4 {output_file_path} {output_file_path_no_ext}.tiff"

        temp_file_names.append(temp_file_name)
        oconv_commands.append(oconv_command)
        rpict_commands.append(rpict_command)
        ra_tiff_commands.append(ra_tiff_command)

    # get rid of duplicate oconv commands
    oconv_commands = list(dict.fromkeys(oconv_commands))

    return temp_file_names, oconv_commands, rpict_commands, ra_tiff_commands