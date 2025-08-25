# Archilume imports

# Standard library imports
from typing import Optional, Tuple

# Third-party imports
import pandas as pd

def get_bounding_box_from_point_coordinates(point_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Generates a Pandas DataFrame containing the 8 corner coordinates of a 3D bounding box
    from an input Pandas DataFrame containing 'x_coords', 'y_coords', and 'z_coords' columns.

    Args:
        point_dataframe (pd.DataFrame): A Pandas DataFrame that must include
                                        'x_coords', 'y_coords', and 'z_coords' columns
                                        representing the coordinates of the points.

    Returns:
        pd.DataFrame: A Pandas DataFrame with 8 rows (one for each corner) and
                      columns ['x_coords', 'y_coords', 'z_coords'].
                      Returns an empty DataFrame if the input DataFrame is empty, doesn't
                      have the required columns, is not a DataFrame, or if an error occurs
                      during min/max calculation.
    """
    # --- 1. Input Validation ---
    # Check if the input is a Pandas DataFrame
    if not isinstance(point_dataframe, pd.DataFrame):
        print("Error: Input must be a Pandas DataFrame.")
        return pd.DataFrame()  # Return an empty DataFrame

    # Check if the DataFrame is empty
    if point_dataframe.empty:
        print("Warning: Input DataFrame is empty. Returning an empty DataFrame.")
        return pd.DataFrame()  # Return an empty DataFrame

    # Check for required columns
    required_columns = ["x_coords", "y_coords", "z_coords"]
    for col in required_columns:
        if col not in point_dataframe.columns:
            print(f"Error: DataFrame is missing the required column '{col}'.")
            return pd.DataFrame()  # Return an empty DataFrame

    # --- 2. Check for numeric data and Find Min/Max Coordinates ---
    try:
        # Check if all required columns contain numeric data
        for col in required_columns:
            if not pd.api.types.is_numeric_dtype(point_dataframe[col]):
                print(f"Error: Column '{col}' must contain numeric data.")
                return pd.DataFrame()

        min_x = point_dataframe["x_coords"].min()
        max_x = point_dataframe["x_coords"].max()
        min_y = point_dataframe["y_coords"].min()
        max_y = point_dataframe["y_coords"].max()
        min_z = point_dataframe["z_coords"].min()
        max_z = point_dataframe["z_coords"].max()
    except TypeError:
        # This can happen if columns are not numeric
        print("Error: Columns 'x_coords', 'y_coords', 'z_coords' must contain numeric data.")
        return pd.DataFrame()  # Return an empty DataFrame
    except Exception as e:
        print(f"Error during min/max calculation: {e}")
        return pd.DataFrame()  # Return an empty DataFrame

    # --- 3. Construct Corner Points ---
    # Based on the min/max values extracted, define the 8 corners.
    corners_list = [
        (min_x, min_y, min_z),  # Bottom-left-front
        (max_x, min_y, min_z),  # Bottom-right-front
        (min_x, max_y, min_z),  # Top-left-front
        (max_x, max_y, min_z),  # Top-right-front
        (min_x, min_y, max_z),  # Bottom-left-back
        (max_x, min_y, max_z),  # Bottom-right-back
        (min_x, max_y, max_z),  # Top-left-back
        (max_x, max_y, max_z),  # Top-right-back
    ]

    # --- 4. Convert list of corners to DataFrame ---
    # The DataFrame will have the same column names as the input for consistency.
    corners_df = pd.DataFrame(corners_list, columns=["x_coords", "y_coords", "z_coords"])

    return corners_df

def get_center_of_bounding_box(box_corners_df: pd.DataFrame) -> Optional[Tuple[float, float, float]]:
    """
    Calculates the center coordinate of a 3D bounding box and returns it as a tuple.

    Args:
        box_corners_df (pd.DataFrame): A Pandas DataFrame with columns
                                       ['x_coords', 'y_coords', 'z_coords']
                                       representing the corner coordinates.

    Returns:
        tuple: A tuple (x, y, z) representing the center coordinate.
               Returns None if input is invalid.
    """
    # --- 1. Input Validation ---
    if (
        not isinstance(box_corners_df, pd.DataFrame)
        or box_corners_df.empty
        or not all(col in box_corners_df.columns for col in ["x_coords", "y_coords", "z_coords"])
    ):
        # print("Error or Warning: Input DataFrame invalid, empty, or missing required columns.") # Optional: keep print for debugging
        return None

    # --- 2. Calculate Min/Max Coordinates ---
    try:
        min_x = box_corners_df["x_coords"].min()
        max_x = box_corners_df["x_coords"].max()
        min_y = box_corners_df["y_coords"].min()
        max_y = box_corners_df["y_coords"].max()
        min_z = box_corners_df["z_coords"].min()
        max_z = box_corners_df["z_coords"].max()
    except (TypeError, Exception):
        # print("Error: Non-numeric data or other issue during min/max calculation.") # Optional
        return None

    # --- 3. Calculate Center Coordinates ---
    x_coord_center = (min_x + max_x) / 2
    y_coord_center = (min_y + max_y) / 2
    z_coord_center = (min_z + max_z) / 2

    # --- 4. Return as tuple ---
    return (x_coord_center, y_coord_center, z_coord_center)

def calculate_dimensions_from_points(
    df_points: pd.DataFrame, 
    x_col: str = "x_coords", 
    y_col: str = "y_coords"
    ) -> tuple[float | None, float | None]:
    """
    Calculates the width (x_max - x_min) and depth (y_max - y_min)
    from a DataFrame of points.

    Args:
        df_points (pd.DataFrame): DataFrame containing the point coordinates.
                                  It must have columns for x and y values.
        x_col (str): The name of the column containing the x-coordinates.
                     Defaults to 'x'.
        y_col (str): The name of the column containing the y-coordinates.
                     Defaults to 'y'.

    Returns:
        tuple[float | None, float | None]: A tuple containing two float values:
                                           (width, depth).
                                           Returns (None, None) if the input
                                           DataFrame is empty, if specified
                                           columns are not found, or if an
                                           error occurs during calculation.
    """
    if df_points.empty:
        return None, None

    if x_col not in df_points.columns or y_col not in df_points.columns:
        return None, None

    try:
        # Ensure columns are numeric and handle potential NaNs that could arise from non-numeric data
        # If min/max is called on an entirely non-numeric or empty (after dropping NaNs) series, it can raise.
        if not pd.api.types.is_numeric_dtype(
            df_points[x_col]
        ) or not pd.api.types.is_numeric_dtype(df_points[y_col]):
            # Attempt to convert to numeric, coercing errors to NaN
            x_series = pd.to_numeric(df_points[x_col], errors="coerce")
            y_series = pd.to_numeric(df_points[y_col], errors="coerce")
            if x_series.isnull().all() or y_series.isnull().all():  # if all values became NaN
                return None, None
        else:
            x_series = df_points[x_col]
            y_series = df_points[y_col]

        x_min = x_series.min()
        x_max = x_series.max()
        y_min = y_series.min()
        y_max = y_series.max()

        # If min or max returned NaN (e.g., if all values were NaN after coercion)
        if pd.isna(x_min) or pd.isna(x_max) or pd.isna(y_min) or pd.isna(y_max):
            return None, None

        width = x_max - x_min
        depth = y_max - y_min

        return float(width), float(depth)

    except Exception:
        return None, None

def calc_centroid_of_points(
        df: pd.DataFrame, 
        x_col: str = "x_coords", 
        y_col: str = "y_coords") -> Optional[Tuple[float, float]]:
    """
    Calculates the centroid from coordinates in a pandas DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame containing the coordinates.
        x_col (str): The name of the column containing x-coordinates.
        y_col (str): The name of the column containing y-coordinates.

    Returns:
        tuple or None: A tuple (x, y) for the centroid, or None if the DataFrame is empty.
    """
    if df.empty:
        return None

    # Use the built-in .mean() method for efficiency
    centroid_x = df[x_col].mean()
    centroid_y = df[y_col].mean()

    return (centroid_x, centroid_y)