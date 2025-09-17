"""
Radiance Sky File Generator

Generates series of Radiance sky files for daylight analysis using the gensky utility.
Supports sunny sky conditions with configurable time ranges and geographic locations.

IMPORTANT: This generator produces sky files oriented to true north using solar time 
for sun positioning calculations. The generated files use Radiance's gensky utility 
which calculates sun positions based on solar time rather than local standard time.
"""

# Archilume imports

# Standard library imports
import logging
import os
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Third-party imports


# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)

@dataclass
class SkyFileGenerator:
    """
    Generates Radiance sky files for daylight analysis.
    
    Creates a series of sunny sky files using the gensky utility for specified
    date/time ranges and geographic locations. Files are saved in Radiance format
    suitable for lighting simulation.
    
    IMPORTANT: Sky files are generated with true north orientation using solar time
    for sun positioning. The gensky utility calculates sun positions based on solar
    time (apparent solar time) rather than local standard time or daylight saving time.
    This ensures accurate solar positioning for lighting analysis but requires users
    to account for time zone differences when interpreting results.
    
    Example:
        >>> generator = SkyFileGenerator(
        ...     lat=-37.8136,  # Melbourne latitude
        ...     month=6,  # June (winter solstice)
        ...     day=21,
        ...     start_hour_24hr_format=8,
        ...     end_hour_24hr_format=17,
        ...     minute_increment=5
        ... )
        >>> generator.generate_sunny_sky_series()
    
    Parameters:
        lat: Latitude in decimal degrees (positive = North, negative = South)
        year: Year for sky generation (e.g., 2024)
        month: Month (1-12)
        day: Day of month (1-31)
        start_hour_24hr_format: Start hour in 24-hour format (0-23) - solar time
        end_hour_24hr_format: End hour in 24-hour format (0-23) - solar time
        minute_increment: Time increment in minutes (default: 5)
        
    Output:
        Creates .sky files named as SS_MMDD_HHMM.sky in the output directory.
        Each file contains gensky command and sky/ground glow definitions.
        Sky orientation is aligned to true north with solar time positioning.
    """

    # Core location parameters
    lat: float

    # Parameters for the specific sky series
    month: int
    day: int
    start_hour_24hr_format: int
    end_hour_24hr_format: int

    # Optional parameters with defaults
    year: int = datetime.now().year
    minute_increment: int = 5

    def __post_init__(self):
        """
        Performs post-initialization setup:
        - Converts lat to string for use with gensky.
        - Sets fixed output directory and creates it if needed.
        """
        self.str_lat = str(self.lat)
        
        # Fixed output directory - not user configurable
        self.output_dir = Path(__file__).parent.parent / "outputs"/  "sky"
        #FIXME use relative references and update this to use pathlib.

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
        output_filename = f"SS_{month_str}{day_str}_{output_time_suffix_str}.sky"
        output_filepath = self.output_dir / output_filename

        print(f"Outputting to: {output_filepath}")

        try:
            # Append skyfunc lines that create more realistic sky
            with open(output_filepath, "w") as outfile:
                skyfunc_description = textwrap.dedent(f"""\
                    #Radiance Sky file: Ark Resources Pty Ltd

                    !gensky {str(month)} {str(day)} +{time_hhmm_str} +s -a {self.str_lat}

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
                    """)
                outfile.write(skyfunc_description)
                # print(f"Successfully generated: {output_filepath}")
        except:
            print(f"Error running gensky for {time_hhmm_str}")

    def generate_sunny_sky_series(self):
        """
        Execute sky file generation for the configured time series.
        
        Creates individual .sky files for each time step from start_hour to end_hour
        at the specified minute_increment intervals. Files are saved to output_dir.
        
        Returns:
            None: Files are written to disk, status printed to console.
        """
        print(
            f"\nStarting sky generation for {self.month}/{self.day}/{self.year} from {self.start_hour_24hr_format}:00 to {self.end_hour_24hr_format}:00 "
            f"at {self.str_lat} lat."
        )

        # Create the output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created output directory: {self.output_dir}")

        start_dt = datetime(
            self.year, self.month, self.day, self.start_hour_24hr_format, 0
        )
        end_dt = datetime(self.year, self.month, self.day, self.end_hour_24hr_format, 0)
        time_delta = timedelta(minutes=self.minute_increment)
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
    
    def generate_overcast_skyfile(self):
        """
        Generates a CIE overcast sky file using gensky.

        Creates a single overcast sky file suitable for lighting simulation under
        uniform cloudy conditions. The sky uses the CIE overcast sky model (+c)
        which provides even luminance distribution appropriate for overcast days.
        >>> example: gensky -ang 45 0 -c -B 55.8659217877 > outputs\sky\TenK_cie_overcast.sky

        Returns:
            None: Sky file is written to disk at outputs/sky
        """
        
        output_filepath = self.output_dir / "TenK_cie_overcast.rad"

        print(f"Outputting to: {output_filepath}")

        try:
            with open(output_filepath, "w") as outfile:
                skyfunc_description = textwrap.dedent(f"""\
                    #Radiance Sky file: Ark Resources Pty Ltd

                    !gensky -ang 45 0 -c -B 55.8659217877

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
                    """)
                outfile.write(skyfunc_description)
        except Exception as e:
            print(f"Error generating overcast sky file: {e}")


