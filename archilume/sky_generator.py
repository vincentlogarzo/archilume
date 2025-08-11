"""
Radiance Sky File Generator

Generates series of Radiance sky files for daylight analysis using the gensky utility.
Supports sunny sky conditions with configurable time ranges and geographic locations.
"""

# Standard library imports
import logging
import os
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta


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
    
    Example:
        >>> generator = SkyFileGenerator(
        ...     lat=-37.8136,  # Melbourne latitude
        ...     lon=144.9631,  # Melbourne longitude
        ...     std_meridian=145.0,  # Australian EST
        ...     year=2024,
        ...     month=6,  # June (winter solstice)
        ...     day=21,
        ...     start_hour_24hr_format=8,
        ...     end_hour_24hr_format=17
        ... )
        >>> generator.generate_sunny_sky_series()
    
    Parameters:
        lat: Latitude in decimal degrees (positive = North, negative = South)
        lon: Longitude in decimal degrees (positive = East, negative = West) 
        std_meridian: Standard meridian for timezone in decimal degrees
        year: Year for sky generation (e.g., 2024)
        month: Month (1-12)
        day: Day of month (1-31)
        start_hour_24hr_format: Start hour in 24-hour format (0-23)
        end_hour_24hr_format: End hour in 24-hour format (0-23)
        minute_increment: Time increment in minutes (default: 5)
        
    Output:
        Creates .sky files named as SS_MMDD_HHMM.sky in the output directory.
        Each file contains gensky command and sky/ground glow definitions.
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
    minute_increment: int = 5

    def __post_init__(self):
        """
        Performs post-initialization setup:
        - Converts lat/lon to strings for use with gensky.
        - Sets fixed output directory and creates it if needed.
        """
        self.str_lat = str(self.lat)
        self.str_lon = str(self.lon)
        self.str_std_meridian = str(self.std_meridian)
        
        # Fixed output directory - not user configurable
        self.output_dir = "intermediates/sky"

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
                skyfunc_description = textwrap.dedent(f"""\
                    #Radiance Sky file: Ark Resources Pty Ltd

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
                    """)
                outfile.write(skyfunc_description)
                print(f"Successfully generated: {output_filepath}")
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
            f"at {self.str_lat} lat, {self.str_lon} lon."
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
