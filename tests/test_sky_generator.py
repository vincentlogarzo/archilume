# Standard library imports
import os
import tempfile
import shutil
from datetime import datetime

# Third-party imports
import pytest

# Archilume imports
from archilume.sky_generator import SkyGenerator


class TestSkyGenerator:
    """Test suite for SkyGenerator class in sky_generator.py"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup after test
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def basic_generator(self):
        """Basic SkyGenerator instance for testing"""
        return SkyGenerator(lat=-37.8136)  # Melbourne latitude

    @pytest.fixture
    def generator_with_defaults(self):
        """SkyGenerator with default values"""
        return SkyGenerator(lat=40.7128)  # New York latitude

    def test_basic_instantiation(self, basic_generator):
        """Test that SkyGenerator can be instantiated with basic parameters"""
        assert basic_generator.lat == -37.8136
        assert basic_generator.str_lat == "-37.8136"

    def test_output_directory_creation(self, basic_generator):
        """Test that output directory is created during initialization"""
        # Directory should be created during __post_init__
        assert os.path.exists(basic_generator.sky_file_dir)

    def test_positive_latitude(self):
        """Test with positive latitude (Northern Hemisphere)"""
        generator = SkyGenerator(lat=51.5074)  # London latitude
        assert generator.lat == 51.5074
        assert generator.str_lat == "51.5074"

    def test_negative_latitude(self, basic_generator):
        """Test with negative latitude (Southern Hemisphere)"""
        assert basic_generator.lat == -37.8136
        assert basic_generator.str_lat == "-37.8136"

    def test_zero_latitude(self):
        """Test with zero latitude (equator)"""
        generator = SkyGenerator(lat=0.0)
        assert generator.lat == 0.0
        assert generator.str_lat == "0.0"

    def test_sky_file_generation_creates_files(self, basic_generator, temp_dir):
        """Test that sky file generation creates the expected files"""
        # Override output directory for testing
        basic_generator.sky_file_dir = temp_dir

        # Generate files
        basic_generator.generate_sunny_sky_series(
            month=6,
            day=21,
            start_hour_24hr_format=10,
            end_hour_24hr_format=12,
            minute_increment=60
        )

        # Check that files were created
        expected_files = ["SS_0621_1000.sky", "SS_0621_1100.sky", "SS_0621_1200.sky"]

        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath), f"Expected file {filename} was not created"
            assert os.path.getsize(filepath) > 0, f"File {filename} is empty"

    def test_generated_file_content_structure(self, basic_generator, temp_dir):
        """Test that generated sky files have the correct content structure"""
        # Override output directory for testing
        basic_generator.sky_file_dir = temp_dir

        # Generate a single file
        basic_generator.generate_sunny_sky_series(
            month=6, day=21, start_hour_24hr_format=10, end_hour_24hr_format=12, minute_increment=60
        )

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
        basic_generator.sky_file_dir = temp_dir

        # Generate files
        basic_generator.generate_sunny_sky_series(
            month=6, day=21, start_hour_24hr_format=10, end_hour_24hr_format=12, minute_increment=60
        )

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
        basic_generator.sky_file_dir = temp_dir

        # Generate files
        basic_generator.generate_sunny_sky_series(
            month=6, day=21, start_hour_24hr_format=10, end_hour_24hr_format=12, minute_increment=60
        )

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
        generator = SkyGenerator(lat=0.0)
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=12, day=1, start_hour_24hr_format=14, end_hour_24hr_format=15, minute_increment=30
        )

        # Should create files at 14:00, 14:30, 15:00
        expected_files = ["SS_1201_1400.sky", "SS_1201_1430.sky", "SS_1201_1500.sky"]
        for filename in expected_files:
            filepath = os.path.join(temp_dir, filename)
            assert os.path.exists(filepath)

    def test_minute_increment_functionality(self, temp_dir):
        """Test that minute increment works correctly"""
        generator = SkyGenerator(lat=45.0)
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=1, day=1, start_hour_24hr_format=12, end_hour_24hr_format=13, minute_increment=15
        )

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
        generator = SkyGenerator(lat=30.0)
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=7, day=4, start_hour_24hr_format=15, end_hour_24hr_format=15, minute_increment=60
        )

        # Should create only one file
        expected_file = "SS_0704_1500.sky"
        filepath = os.path.join(temp_dir, expected_file)
        assert os.path.exists(filepath)

        # Verify no other files were created
        all_files = [f for f in os.listdir(temp_dir) if f.endswith('.sky')]
        assert len(all_files) == 1

    def test_latitude_precision_in_gensky_command(self, temp_dir):
        """Test that latitude precision is maintained in gensky command"""
        generator = SkyGenerator(lat=37.123456789)  # High precision latitude
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=6, day=15, start_hour_24hr_format=12, end_hour_24hr_format=12, minute_increment=60
        )

        filepath = os.path.join(temp_dir, "SS_0615_1200.sky")
        with open(filepath, 'r') as f:
            content = f.read()

        # Check that the full precision latitude is included
        assert "37.123456789" in content

    def test_edge_case_hours(self, temp_dir):
        """Test edge cases for hour values (0 and 23)"""
        generator = SkyGenerator(lat=0.0)
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=6, day=21, start_hour_24hr_format=0, end_hour_24hr_format=1, minute_increment=60
        )

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
        generator = SkyGenerator(lat=40.0)
        generator.sky_file_dir = temp_dir

        generator.generate_sunny_sky_series(
            month=2, day=29, start_hour_24hr_format=12, end_hour_24hr_format=12,
            minute_increment=60, year=2024  # 2024 is a leap year
        )

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
        basic_generator.sky_file_dir = temp_dir

        # Generate files and capture output
        basic_generator.generate_sunny_sky_series(
            month=6, day=21, start_hour_24hr_format=10, end_hour_24hr_format=12, minute_increment=60
        )
        captured = capsys.readouterr()

        # Check that key information is displayed
        assert "Starting sky generation" in captured.out
        assert "6/21/" in captured.out  # Date
        assert "10:00 to 12:00" in captured.out  # Time range
        assert "-37.8136 lat" in captured.out  # Latitude
        assert "Sky generation series complete" in captured.out


class TestSkyGeneratorEdgeCases:
    """Test edge cases and error conditions for SkyGenerator"""

    def test_extreme_latitudes(self):
        """Test with extreme latitude values"""
        # North Pole
        generator_north = SkyGenerator(lat=90.0)
        assert generator_north.str_lat == "90.0"

        # South Pole
        generator_south = SkyGenerator(lat=-90.0)
        assert generator_south.str_lat == "-90.0"