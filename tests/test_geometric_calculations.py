# Archilume imports
from archilume.geometry_utils import (
    calc_centroid_of_points,
    calculate_dimensions_from_points,
    get_center_of_bounding_box,
    get_bounding_box_from_point_coordinates,
)

# Third-party imports
import numpy as np
import pandas as pd
import pytest


# Test fixtures
@pytest.fixture
def sample_points_3d():
    """Sample 3D coordinate DataFrame for testing"""
    return pd.DataFrame(
        {
            "x_coords": [1.0, 3.0, 1.0, 3.0],
            "y_coords": [2.0, 2.0, 4.0, 4.0],
            "z_coords": [0.0, 0.0, 1.0, 1.0],
        }
    )


@pytest.fixture
def sample_points_2d():
    """Sample 2D coordinate DataFrame for testing"""
    return pd.DataFrame({"x_coords": [0.0, 5.0, 2.5], "y_coords": [0.0, 0.0, 4.0]})


@pytest.fixture
def single_point():
    """Single point DataFrame for edge case testing"""
    return pd.DataFrame({"x_coords": [1.5], "y_coords": [2.5], "z_coords": [3.5]})


@pytest.fixture
def empty_dataframe():
    """Empty DataFrame for testing edge cases"""
    return pd.DataFrame()


@pytest.fixture
def invalid_columns_df():
    """DataFrame with wrong column names"""
    return pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0], "z": [5.0, 6.0]})


@pytest.fixture
def non_numeric_df():
    """DataFrame with non-numeric data"""
    return pd.DataFrame(
        {"x_coords": ["a", "b", "c"], "y_coords": [1.0, 2.0, 3.0], "z_coords": [4.0, 5.0, 6.0]}
    )


@pytest.fixture
def mixed_data_df():
    """DataFrame with mixed numeric/string data that could be converted"""
    return pd.DataFrame(
        {
            "x_coords": ["1.5", "2.5", "3.5"],
            "y_coords": [1.0, 2.0, 3.0],
            "z_coords": [0.0, 1.0, 2.0],
        }
    )


@pytest.fixture
def nan_data_df():
    """DataFrame with NaN values"""
    return pd.DataFrame(
        {
            "x_coords": [1.0, np.nan, 3.0],
            "y_coords": [2.0, 2.0, np.nan],
            "z_coords": [0.0, 1.0, 2.0],
        }
    )


@pytest.fixture
def bounding_box_corners():
    """Sample bounding box corners DataFrame"""
    return pd.DataFrame(
        {
            "x_coords": [0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0],
            "y_coords": [0.0, 0.0, 5.0, 5.0, 0.0, 0.0, 5.0, 5.0],
            "z_coords": [0.0, 0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 3.0],
        }
    )


class TestGeometricCalculations:
    """Test suite for geometric calculation functions in geometry_utils.py"""


class TestGetBoundingBoxFromPointCoordinates:
    """Tests for get_bounding_box_from_point_coordinates function"""

    def test_valid_input_returns_correct_bounding_box(self, sample_points_3d):
        """Test that valid input produces correct 8-corner bounding box"""
        result = get_bounding_box_from_point_coordinates(sample_points_3d)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 8
        assert list(result.columns) == ["x_coords", "y_coords", "z_coords"]

        # Check min/max values are correct
        assert result["x_coords"].min() == 1.0
        assert result["x_coords"].max() == 3.0
        assert result["y_coords"].min() == 2.0
        assert result["y_coords"].max() == 4.0
        assert result["z_coords"].min() == 0.0
        assert result["z_coords"].max() == 1.0

    def test_single_point_returns_degenerate_box(self, single_point):
        """Test that single point creates degenerate bounding box (all corners same)"""
        result = get_bounding_box_from_point_coordinates(single_point)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 8
        # All corners should be the same point
        assert all(result["x_coords"] == 1.5)
        assert all(result["y_coords"] == 2.5)
        assert all(result["z_coords"] == 3.5)

    def test_non_dataframe_input_returns_empty(self):
        """Test that non-DataFrame input returns empty DataFrame"""
        result = get_bounding_box_from_point_coordinates("not a dataframe")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_empty_dataframe_returns_empty(self, empty_dataframe):
        """Test that empty DataFrame returns empty DataFrame"""
        result = get_bounding_box_from_point_coordinates(empty_dataframe)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_missing_columns_returns_empty(self, invalid_columns_df):
        """Test that DataFrame with wrong columns returns empty DataFrame"""
        result = get_bounding_box_from_point_coordinates(invalid_columns_df)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_non_numeric_data_returns_empty(self, non_numeric_df):
        """Test that non-numeric data returns empty DataFrame"""
        result = get_bounding_box_from_point_coordinates(non_numeric_df)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_nan_values_handled_correctly(self, nan_data_df):
        """Test that NaN values are handled appropriately"""
        result = get_bounding_box_from_point_coordinates(nan_data_df)

        # Should still return valid bounding box, ignoring NaN values
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 8
        assert not result["x_coords"].isna().any()
        assert not result["y_coords"].isna().any()
        assert not result["z_coords"].isna().any()


class TestCalculateDimensionsFromPoints:
    """Tests for calculate_dimensions_from_points function"""

    def test_valid_input_returns_correct_dimensions(self, sample_points_2d):
        """Test that valid input returns correct width and depth"""
        width, depth = calculate_dimensions_from_points(sample_points_2d)

        assert width == 5.0  # 5.0 - 0.0
        assert depth == 4.0  # 4.0 - 0.0

    def test_single_point_returns_zero_dimensions(self):
        """Test that single point returns zero dimensions"""
        single_point_2d = pd.DataFrame({"x_coords": [1.0], "y_coords": [2.0]})
        width, depth = calculate_dimensions_from_points(single_point_2d)

        assert width == 0.0
        assert depth == 0.0

    def test_empty_dataframe_returns_none(self, empty_dataframe):
        """Test that empty DataFrame returns None values"""
        width, depth = calculate_dimensions_from_points(empty_dataframe)

        assert width is None
        assert depth is None

    def test_missing_columns_returns_none(self, invalid_columns_df):
        """Test that missing columns returns None values"""
        width, depth = calculate_dimensions_from_points(invalid_columns_df)

        assert width is None
        assert depth is None

    def test_custom_column_names(self):
        """Test function with custom column names"""
        df = pd.DataFrame({"longitude": [0.0, 10.0], "latitude": [0.0, 5.0]})
        width, depth = calculate_dimensions_from_points(df, "longitude", "latitude")

        assert width == 10.0
        assert depth == 5.0

    def test_non_numeric_data_conversion(self, mixed_data_df):
        """Test that string numbers are converted correctly"""
        width, depth = calculate_dimensions_from_points(mixed_data_df)

        assert width == 2.0  # 3.5 - 1.5
        assert depth == 2.0  # 3.0 - 1.0

    def test_all_nan_returns_none(self):
        """Test that all NaN values return None"""
        all_nan_df = pd.DataFrame({"x_coords": [np.nan, np.nan], "y_coords": [np.nan, np.nan]})
        width, depth = calculate_dimensions_from_points(all_nan_df)

        assert width is None
        assert depth is None


class TestCalcCentroidOfPoints:
    """Tests for calc_centroid_of_points function"""

    def test_valid_input_returns_correct_centroid(self, sample_points_2d):
        """Test that valid input returns correct centroid"""
        result = calc_centroid_of_points(sample_points_2d)

        assert result is not None
        x_centroid, y_centroid = result
        assert x_centroid == pytest.approx(2.5)  # (0 + 5 + 2.5) / 3
        assert y_centroid == pytest.approx(4.0 / 3)  # (0 + 0 + 4) / 3

    def test_single_point_returns_same_point(self):
        """Test that single point returns itself as centroid"""
        single_point_2d = pd.DataFrame({"x_coords": [3.0], "y_coords": [4.0]})
        result = calc_centroid_of_points(single_point_2d)

        assert result is not None
        x_centroid, y_centroid = result
        assert x_centroid == 3.0
        assert y_centroid == 4.0

    def test_empty_dataframe_returns_none(self, empty_dataframe):
        """Test that empty DataFrame returns None"""
        result = calc_centroid_of_points(empty_dataframe)
        assert result is None

    def test_custom_column_names(self):
        """Test function with custom column names"""
        df = pd.DataFrame({"longitude": [0.0, 10.0], "latitude": [0.0, 4.0]})
        result = calc_centroid_of_points(df, "longitude", "latitude")

        assert result is not None
        x_centroid, y_centroid = result
        assert x_centroid == 5.0
        assert y_centroid == 2.0


class TestGetBoundingBoxCenterDf:
    """Tests for get_center_of_bounding_box function"""

    def test_valid_input_returns_correct_center(self, bounding_box_corners):
        """Test that valid bounding box returns correct center coordinates"""
        result = get_center_of_bounding_box(bounding_box_corners)

        assert isinstance(result, tuple)
        assert len(result) == 3
        x, y, z = result
        assert x == 5.0
        assert y == 2.5
        assert z == 1.5

    def test_empty_dataframe_returns_none(self, empty_dataframe):
        """Test that empty DataFrame returns None"""
        result = get_center_of_bounding_box(empty_dataframe)
        assert result is None

    def test_invalid_input_returns_none(self):
        """Test that invalid input returns None"""
        result = get_center_of_bounding_box("not a dataframe")
        assert result is None


class TestIntegrationWorkflows:
    """Integration tests for geometric function workflows"""

    def test_point_to_bounding_box_to_center_workflow(self, sample_points_3d):
        """Test complete workflow from points to bounding box to center"""
        # Step 1: Get bounding box from points
        bounding_box = get_bounding_box_from_point_coordinates(sample_points_3d)
        assert not bounding_box.empty

        # Step 2: Get center from bounding box
        center = get_center_of_bounding_box(bounding_box)

        assert isinstance(center, tuple)
        assert len(center) == 3
        x, y, z = center
        assert x == 2.0  # (1+3)/2
        assert y == 3.0  # (2+4)/2
        assert z == 0.5  # (0+1)/2

    def test_points_to_dimensions_and_centroid(self, sample_points_2d):
        """Test calculating both dimensions and centroid from same points"""
        width, depth = calculate_dimensions_from_points(sample_points_2d)
        centroid = calc_centroid_of_points(sample_points_2d)

        assert width == 5.0
        assert depth == 4.0
        assert centroid is not None

        x_centroid, y_centroid = centroid
        assert x_centroid == pytest.approx(2.5)
        assert y_centroid == pytest.approx(4.0 / 3)
