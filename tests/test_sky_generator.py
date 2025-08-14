# Standard library imports
import os
import tempfile
import shutil
from datetime import datetime

# Third-party imports
import pytest

# Archilume imports
from archilume.sky_generator import SkyFileGenerator


class TestSkyFileGenerator:
    """Test suite for SkyFileGenerator class in sky_generator.py"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup after test
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def basic_generator(self):
        """Basic SkyFileGenerator instance for testing"""
        return SkyFileGenerator(
            lat=-37.8136,  # Melbourne latitude
            month=6,
            day=21,
            start_hour_24hr_format=10,
            end_hour_24hr_format=12,
            minute_increment=60
        )

    @pytest.fixture
    def generator_with_defaults(self):
        """SkyFileGenerator with default values"""
        return SkyFileGenerator(
            lat=40.7128,  # New York latitude
            month=12,
            day=21,
            start_hour_24hr_format=9,
            end_hour_24hr_format=15
        )

    def test_basic_instantiation(self, basic_generator):
        """Test that SkyFileGenerator can be instantiated with basic parameters"""
        assert basic_generator.lat == -37.8136
        assert basic_generator.str_lat == "-37.8136"
        assert basic_generator.month == 6
        assert basic_generator.day == 21
        assert basic_generator.start_hour_24hr_format == 10
        assert basic_generator.end_hour_24hr_format == 12
        assert basic_generator.minute_increment == 60

    def test_default_year_is_current(self, basic_generator):
        """Test that default year is set to current year"""
        assert basic_generator.year == datetime.now().year

    def test_default_minute_increment(self, generator_with_defaults):
        """Test that default minute increment is 5"""
        assert generator_with_defaults.minute_increment == 5

    def test_custom_year(self):
        """Test setting custom year"""
        generator = SkyFileGenerator(
            lat=51.5074,  # London latitude
            month=3,
            day=20,
            start_hour_24hr_format=8,
            end_hour_24hr_format=18,
            year=2023
        )
        assert generator.year == 2023

    def test_output_directory_creation(self, basic_generator):
        """Test that output directory is created during initialization"""
        assert basic_generator.output_dir == "intermediates/sky"
        # Directory should be created during __post_init__
        assert os.path.exists(basic_generator.output_dir)

    def test_positive_latitude(self):
        """Test with positive latitude (Northern Hemisphere)"""
        generator = SkyFileGenerator(
            lat=51.5074,  # London latitude
            month=6,
            day=21,
            start_hour_24hr_format=6,
            end_hour_24hr_format=20
        )
        assert generator.lat == 51.5074
        assert generator.str_lat == "51.5074"

    def test_negative_latitude(self, basic_generator):
        """Test with negative latitude (Southern Hemisphere)"""
        assert basic_generator.lat == -37.8136
        assert basic_generator.str_lat == "-37.8136"

    def test_zero_latitude(self):
        """Test with zero latitude (equator)"""
        generator = SkyFileGenerator(
            lat=0.0,
            month=3,
            day=20,
            start_hour_24hr_format=6,
            end_hour_24hr_format=18
        )
        assert generator.lat == 0.0
        assert generator.str_lat == "0.0"

    def test_sky_file_generation_creates_files(self, basic_generator, temp_dir):
        """Test that sky file generation creates the expected files"""
        # Override output directory for testing
        basic_generator.output_dir = temp_dir
        
        # Generate files
        basic_generator.generate_sunny_sky_series()
        
        # Check that files were created
        expected_files = ["SS_0621_1000.sky", "SS_0621_1100.sky", "SS_0621_1200.sky"]
        
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath), f"Expected file {filename} was not created"
            assert os.path.getsize(filepath) > 0, f"File {filename} is empty"

    def test_generated_file_content_structure(self, basic_generator, temp_dir):
        """Test that generated sky files have the correct content structure"""
        # Override output directory for testing
        basic_generator.output_dir = temp_dir
        
        # Generate a single file
        basic_generator.generate_sunny_sky_series()
        
        # Read the first generated file
        filepath = os.path.join(temp_dir, "SS_0621_1000.sky")
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check for required content
        assert "#Radiance Sky file: Ark Resources Pty Ltd" in content
        assert "!gensky 6 21 +10:00 +s -a -37.8136" in content
        assert "skyfunc glow skyglow" in content
        assert "skyglow source sky" in content
        assert "skyfunc glow grndglow" in content
        assert "grndglow source ground" in content

    def test_gensky_command_format(self, basic_generator, temp_dir):
        """Test that gensky command is formatted correctly"""
        # Override output directory for testing
        basic_generator.output_dir = temp_dir
        
        # Generate files
        basic_generator.generate_sunny_sky_series()
        
        # Check each generated file
        expected_commands = [
            "!gensky 6 21 +10:00 +s -a -37.8136",
            "!gensky 6 21 +11:00 +s -a -37.8136",
            "!gensky 6 21 +12:00 +s -a -37.8136"
        ]
        
        filenames = ["SS_0621_1000.sky", "SS_0621_1100.sky", "SS_0621_1200.sky"]
        
        for filename, expected_cmd in zip(filenames, expected_commands):
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'r') as f:
                content = f.read()
            assert expected_cmd in content

    def test_filename_format(self, basic_generator, temp_dir):
        """Test that sky files are named correctly"""
        # Override output directory for testing
        basic_generator.output_dir = temp_dir
        
        # Generate files
        basic_generator.generate_sunny_sky_series()
        
        # Check filename format: SS_MMDD_HHMM.sky
        expected_files = ["SS_0621_1000.sky", "SS_0621_1100.sky", "SS_0621_1200.sky"]
        
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath)
            
            # Check filename parts
            base_name = filename.replace(".sky", "")
            parts = base_name.split("_")
            assert len(parts) == 3
            assert parts[0] == "SS"  # Sunny Sky prefix
            assert len(parts[1]) == 4  # MMDD format
            assert len(parts[2]) == 4  # HHMM format

    def test_different_date_formats(self, temp_dir):
        """Test sky generation with different dates"""
        generator = SkyFileGenerator(
            lat=0.0,
            month=12,
            day=1,
            start_hour_24hr_format=14,
            end_hour_24hr_format=15,  # Span two hours
            minute_increment=30
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        # Should create files at 14:00, 14:30, 15:00
        expected_files = ["SS_1201_1400.sky", "SS_1201_1430.sky", "SS_1201_1500.sky"]
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath)

    def test_minute_increment_functionality(self, temp_dir):
        """Test that minute increment works correctly"""
        generator = SkyFileGenerator(
            lat=45.0,
            month=1,
            day=1,
            start_hour_24hr_format=12,
            end_hour_24hr_format=13,
            minute_increment=15
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        # Should create files at 15-minute intervals
        expected_files = [
            "SS_0101_1200.sky",
            "SS_0101_1215.sky", 
            "SS_0101_1230.sky",
            "SS_0101_1245.sky",
            "SS_0101_1300.sky"
        ]
        
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath)

    def test_single_time_point(self, temp_dir):
        """Test generation with start and end hour being the same"""
        generator = SkyFileGenerator(
            lat=30.0,
            month=7,
            day=4,
            start_hour_24hr_format=15,
            end_hour_24hr_format=15,
            minute_increment=60
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        # Should create only one file
        expected_file = "SS_0704_1500.sky"
        filepath = os.path.join(temp_dir, expected_file)
        assert os.path.exists(filepath)
        
        # Verify no other files were created
        all_files = [f for f in os.listdir(temp_dir) if f.endswith('.sky')]
        assert len(all_files) == 1

    def test_latitude_precision_in_gensky_command(self, temp_dir):
        """Test that latitude precision is maintained in gensky command"""
        generator = SkyFileGenerator(
            lat=37.123456789,  # High precision latitude
            month=6,
            day=15,
            start_hour_24hr_format=12,
            end_hour_24hr_format=12,
            minute_increment=60
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        filepath = os.path.join(temp_dir, "SS_0615_1200.sky")
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check that the full precision latitude is included
        assert "37.123456789" in content

    def test_edge_case_hours(self, temp_dir):
        """Test edge cases for hour values (0 and 23)"""
        generator = SkyFileGenerator(
            lat=0.0,
            month=6,
            day=21,
            start_hour_24hr_format=0,
            end_hour_24hr_format=1,
            minute_increment=60
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        # Should handle midnight and 1 AM correctly
        expected_files = ["SS_0621_0000.sky", "SS_0621_0100.sky"]
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath)
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            if "0000" in filename:
                assert "+00:00" in content
            else:
                assert "+01:00" in content

    def test_leap_year_february(self, temp_dir):
        """Test generation for February 29th in a leap year"""
        generator = SkyFileGenerator(
            lat=40.0,
            month=2,
            day=29,
            start_hour_24hr_format=12,
            end_hour_24hr_format=12,
            year=2024,  # 2024 is a leap year
            minute_increment=60
        )
        generator.output_dir = temp_dir
        
        generator.generate_sunny_sky_series()
        
        # Should handle leap year date correctly
        expected_file = "SS_0229_1200.sky"
        filepath = os.path.join(temp_dir, expected_file)
        assert os.path.exists(filepath)
        
        with open(filepath, 'r') as f:
            content = f.read()
        assert "!gensky 2 29" in content

    def test_console_output_format(self, basic_generator, temp_dir, capsys):
        """Test that console output contains expected information"""
        # Override output directory for testing
        basic_generator.output_dir = temp_dir
        
        # Generate files and capture output
        basic_generator.generate_sunny_sky_series()
        captured = capsys.readouterr()
        
        # Check that key information is displayed
        assert "Starting sky generation" in captured.out
        assert "6/21/" in captured.out  # Date
        assert "10:00 to 12:00" in captured.out  # Time range
        assert "-37.8136 lat" in captured.out  # Latitude
        assert "Sky generation series complete" in captured.out


class TestSkyFileGeneratorEdgeCases:
    """Test edge cases and error conditions for SkyFileGenerator"""
    
    def test_extreme_latitudes(self):
        """Test with extreme latitude values"""
        # North Pole
        generator_north = SkyFileGenerator(
            lat=90.0,
            month=6,
            day=21,
            start_hour_24hr_format=12,
            end_hour_24hr_format=12
        )
        assert generator_north.str_lat == "90.0"
        
        # South Pole
        generator_south = SkyFileGenerator(
            lat=-90.0,
            month=12,
            day=21,
            start_hour_24hr_format=12,
            end_hour_24hr_format=12
        )
        assert generator_south.str_lat == "-90.0"

    def test_month_day_combinations(self):
        """Test various month/day combinations"""
        test_cases = [
            (1, 1),    # New Year's Day
            (2, 28),   # February (non-leap year)
            (4, 30),   # April (30-day month)
            (12, 31),  # New Year's Eve
        ]
        
        for month, day in test_cases:
            generator = SkyFileGenerator(
                lat=0.0,
                month=month,
                day=day,
                start_hour_24hr_format=12,
                end_hour_24hr_format=12
            )
            assert generator.month == month
            assert generator.day == day

    def test_various_time_ranges(self):
        """Test different time range configurations"""
        # Early morning
        generator_early = SkyFileGenerator(
            lat=0.0, month=6, day=21,
            start_hour_24hr_format=5, end_hour_24hr_format=7
        )
        assert generator_early.start_hour_24hr_format == 5
        assert generator_early.end_hour_24hr_format == 7
        
        # Evening
        generator_evening = SkyFileGenerator(
            lat=0.0, month=6, day=21,
            start_hour_24hr_format=18, end_hour_24hr_format=22
        )
        assert generator_evening.start_hour_24hr_format == 18
        assert generator_evening.end_hour_24hr_format == 22
        
        # All day
        generator_all_day = SkyFileGenerator(
            lat=0.0, month=6, day=21,
            start_hour_24hr_format=0, end_hour_24hr_format=23
        )
        assert generator_all_day.start_hour_24hr_format == 0
        assert generator_all_day.end_hour_24hr_format == 23

    def test_various_minute_increments(self):
        """Test different minute increment values"""
        test_increments = [1, 5, 10, 15, 30, 60, 120]
        
        for increment in test_increments:
            generator = SkyFileGenerator(
                lat=0.0, month=6, day=21,
                start_hour_24hr_format=12, end_hour_24hr_format=12,
                minute_increment=increment
            )
            assert generator.minute_increment == increment