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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# Third-party imports


# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)

@dataclass
class SkyGenerator:
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
        >>> generator = SkyFileGenerator(lat=-37.8136)  # Melbourne latitude
        >>> generator.generate_sunny_sky_series(
        ...     month=6,  # June (winter solstice)
        ...     day=21,
        ...     start_hour_24hr_format=8,
        ...     end_hour_24hr_format=17,
        ...     minute_increment=5
        ... )

    Parameters:
        lat: Latitude in decimal degrees (positive = North, negative = South)

    Output:
        Creates .sky files named as SS_MMDD_HHMM.sky in the output directory.
        Each file contains gensky command and sky/ground glow definitions.
        Sky orientation is aligned to true north with solar time positioning.
    """

    # Required user input
    lat: float

    # Fixed - not user configurable but accessible from instance
    sky_file_dir: Path = field(init = False, default = Path(__file__).parent.parent / "outputs" / "sky")
    TenK_cie_overcast_sky_file_path: Path = field(init=False, default=Path(__file__).parent.parent / "outputs" / "sky" / "TenK_cie_overcast.rad")

    def __post_init__(self):
        """
        Performs post-initialization setup:
        - Creates output directory if needed.
        """

        if not os.path.exists(self.sky_file_dir):
            try:
                os.makedirs(self.sky_file_dir)
                print(f"Created output directory: {self.sky_file_dir}")
            except OSError as e:
                print(f"Error creating directory {self.sky_file_dir}: {e}")

    def generate_TenK_cie_overcast_skyfile(self):
        """
        Generates a CIE overcast sky file using gensky.

        Creates a single overcast sky file suitable for lighting simulation under
        uniform cloudy conditions. The sky uses the CIE overcast sky model (+c)
        which provides even luminance distribution appropriate for overcast days.
        >>> example: gensky -ang 45 0 -c -B 55.8659217877 > "outputs/sky/TenK_cie_overcast.sky"

        Returns:
            None: Sky file is written to disk at outputs/sky
        """

        print(f"Outputting to: {self.TenK_cie_overcast_sky_file_path}")

        try:
            with open(self.TenK_cie_overcast_sky_file_path, "w") as outfile:
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

    def generate_sunny_sky_series(self, month: int, day: int, start_hour_24hr_format: int, end_hour_24hr_format: int, minute_increment: int = 5) -> None:
        """
        Execute sky file generation for the configured time series.

        Creates individual .sky files for each time step from start_hour to end_hour
        at the specified minute_increment intervals. Files are saved to sky_file_dir.

        Parameters:
            month: Month (1-12)
            day: Day of month (1-31)
            start_hour_24hr_format: Start hour in 24-hour format (0-23) - solar time
            end_hour_24hr_format: End hour in 24-hour format (0-23) - solar time
            minute_increment: Time increment in minutes (default: 5)

        Returns:
            None: Files are written to disk, status printed to console.
        """
        year = datetime.now().year

        print(
            f"\nStarting sky generation for {month}/{day}/{year} from {start_hour_24hr_format}:00 to {end_hour_24hr_format}:00 "
            f"at {str(self.lat)} lat.\n"
        )
        
        # Create the output directory if it doesn't exist
        if not os.path.exists(self.sky_file_dir):
            os.makedirs(self.sky_file_dir)
            print(f"Created output directory: {self.sky_file_dir}")

        start_dt = datetime(
            year, month, day, start_hour_24hr_format, 0
        )
        end_dt = datetime(year, month, day, end_hour_24hr_format, 0)
        time_delta = timedelta(minutes=minute_increment)
        current_dt = start_dt

        while current_dt <= end_dt:
            formatted_time_for_gensky = current_dt.strftime("%H:%M")  # e.g., "09:00"
            formatted_time_for_filename = current_dt.strftime("%H%M")  # e.g., "0900"

            self._generate_single_sunny_skyfile(
                lat                 =str(self.lat),
                month               =current_dt.month,
                day                 =current_dt.day,
                time_hhmm           =formatted_time_for_gensky,
                output_time_suffix  =formatted_time_for_filename,
            )
            current_dt += time_delta
        
        print("\nSky generation series complete.\n")
    
    def _generate_single_sunny_skyfile(self, lat: str, month: int, day: int, time_hhmm: str, output_time_suffix: str) -> None:
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
        output_filename = f"SS_{month_str}{day_str}_{output_time_suffix}.sky"
        output_filepath = self.sky_file_dir / output_filename

        print(f"Outputting to: {output_filepath}")

        try:
            # Append skyfunc lines that create more realistic sky
            with open(output_filepath, "w") as outfile:
                skyfunc_description = textwrap.dedent(f"""\
                    #Radiance Sky file: Ark Resources Pty Ltd

                    !gensky {str(month)} {str(day)} +{time_hhmm} +s -a {lat}

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
            print(f"Error running gensky for {time_hhmm}")


