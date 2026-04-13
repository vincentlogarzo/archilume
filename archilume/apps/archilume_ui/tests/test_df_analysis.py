"""Tests for archilume_ui.lib.df_analysis — DF% computation logic.

All tests use synthetic numpy arrays — no HDR file I/O needed.
Regression strategy: when a DF% bug is found, add a test here.
"""

import numpy as np
import pytest

from archilume_ui.lib.df_analysis import (
    DF_THRESHOLDS,
    _polygon_mask,
    compute_room_df,
    read_df_at_pixel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_uniform_image(h: int, w: int, value: float) -> np.ndarray:
    """Return a HxW float32 array filled with a constant DF% value."""
    return np.full((h, w), value, dtype=np.float32)


def make_gradient_image(h: int, w: int) -> np.ndarray:
    """Return a HxW array where value = x (column index) as float32."""
    return np.tile(np.arange(w, dtype=np.float32), (h, 1))


# Polygon covering entire 10x10 image
FULL_POLY_10: list[list[float]] = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
# Polygon covering entire 20x20 image
FULL_POLY_20: list[list[float]] = [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]
# Small polygon inside a 20x20 image (centre quarter)
CENTRE_POLY: list[list[float]] = [[5.0, 5.0], [15.0, 5.0], [15.0, 15.0], [5.0, 15.0]]
# Left half of 10x10
LEFT_HALF_POLY: list[list[float]] = [[0.0, 0.0], [5.0, 0.0], [5.0, 10.0], [0.0, 10.0]]


# ===========================================================================
# DF_THRESHOLDS sanity
# ===========================================================================

class TestDFThresholds:
    def test_bed_threshold(self):
        assert DF_THRESHOLDS["BED"] == 0.5

    def test_living_threshold(self):
        assert DF_THRESHOLDS["LIVING"] == 1.0

    def test_non_resi_threshold(self):
        assert DF_THRESHOLDS["NON-RESI"] == 2.0

    def test_none_type_no_threshold(self):
        assert DF_THRESHOLDS["NONE"] is None

    def test_circ_no_threshold(self):
        assert DF_THRESHOLDS["CIRC"] is None


# ===========================================================================
# _polygon_mask
# ===========================================================================

class TestPolygonMask:
    def test_full_polygon_covers_image(self):
        mask = _polygon_mask(FULL_POLY_10, 10, 10)
        assert mask.shape == (10, 10)
        # Most interior pixels should be True
        assert np.sum(mask) > 50

    def test_small_polygon_partial_coverage(self):
        mask = _polygon_mask(CENTRE_POLY, 20, 20)
        total = np.sum(mask)
        # Should cover roughly 10x10=100 pixels, not the full 20x20=400
        assert 50 < total < 200

    def test_triangle_mask(self):
        tri: list[list[float]] = [[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]]
        mask = _polygon_mask(tri, 10, 10)
        # Triangle area is 50 → roughly 50 pixels
        assert 20 < np.sum(mask) < 80

    def test_degenerate_polygon_near_zero_coverage(self):
        mask = _polygon_mask([[5.0, 5.0], [5.0, 5.0], [5.0, 5.0]], 10, 10)
        # Degenerate polygon (zero area) — rasterizer may mark 0 or 1 pixel
        assert np.sum(mask) <= 1

    def test_mask_is_boolean(self):
        mask = _polygon_mask(FULL_POLY_10, 10, 10)
        assert mask.dtype == bool


# ===========================================================================
# compute_room_df — basic
# ===========================================================================

class TestComputeRoomDfBasic:
    def test_returns_none_for_none_image(self):
        assert compute_room_df(None, FULL_POLY_10) is None

    def test_returns_none_for_degenerate_polygon(self):
        img = make_uniform_image(10, 10, 1.0)
        assert compute_room_df(img, [[0.0, 0.0], [1.0, 1.0]]) is None

    def test_uniform_image_mean_equals_value(self):
        img = make_uniform_image(10, 10, 2.5)
        result = compute_room_df(img, FULL_POLY_10)
        assert result is not None
        assert abs(result["mean_df"] - 2.5) < 0.1

    def test_uniform_image_median_equals_value(self):
        img = make_uniform_image(10, 10, 2.5)
        result = compute_room_df(img, FULL_POLY_10)
        assert result is not None
        assert abs(result["median_df"] - 2.5) < 0.1

    def test_returns_expected_keys(self):
        img = make_uniform_image(10, 10, 1.0)
        result = compute_room_df(img, FULL_POLY_10)
        assert result is not None
        for key in ("mean_df", "median_df", "pct_above", "threshold", "pass_status", "result_lines"):
            assert key in result

    def test_partial_polygon_uses_only_masked_pixels(self):
        """A polygon covering only part of the image should only average those pixels."""
        img = np.zeros((20, 20), dtype=np.float32)
        img[5:15, 5:15] = 3.0  # Only centre has DF
        result = compute_room_df(img, CENTRE_POLY)
        assert result is not None
        assert result["mean_df"] > 2.0  # Most masked pixels are in the 3.0 area

    def test_explicit_image_dimensions(self):
        img = make_uniform_image(10, 10, 1.5)
        result = compute_room_df(img, FULL_POLY_10, image_width=10, image_height=10)
        assert result is not None
        assert abs(result["mean_df"] - 1.5) < 0.1

    def test_polygon_outside_image_returns_none(self):
        """Polygon entirely outside image bounds should return None (no masked pixels)."""
        img = make_uniform_image(10, 10, 1.0)
        far_poly: list[list[float]] = [[50.0, 50.0], [60.0, 50.0], [60.0, 60.0], [50.0, 60.0]]
        assert compute_room_df(img, far_poly) is None

    def test_left_half_has_lower_mean_on_gradient(self):
        """On a gradient image, the left-half polygon should have lower mean than the full."""
        img = make_gradient_image(10, 10)
        result_left = compute_room_df(img, LEFT_HALF_POLY)
        result_full = compute_room_df(img, FULL_POLY_10)
        assert result_left is not None and result_full is not None
        assert result_left["mean_df"] < result_full["mean_df"]


# ===========================================================================
# compute_room_df — pass / marginal / fail thresholds
# ===========================================================================

class TestComputeRoomDfPassFail:
    """Verify pass/fail logic against each room type."""

    def _run(self, value: float, room_type: str) -> dict:
        img = make_uniform_image(20, 20, value)
        result = compute_room_df(img, FULL_POLY_20, room_type=room_type)
        assert result is not None
        return result

    # --- BED (threshold 0.5) ---
    def test_bed_pass_above_threshold(self):
        r = self._run(1.0, "BED")
        assert r["pass_status"] == "pass"
        assert r["pct_above"] > 90.0

    def test_bed_fail_below_threshold(self):
        r = self._run(0.1, "BED")
        assert r["pass_status"] == "fail"
        assert r["pct_above"] < 50.0

    # --- LIVING (threshold 1.0) ---
    def test_living_pass(self):
        assert self._run(2.0, "LIVING")["pass_status"] == "pass"

    def test_living_fail(self):
        assert self._run(0.5, "LIVING")["pass_status"] == "fail"

    # --- NON-RESI (threshold 2.0) ---
    def test_non_resi_pass(self):
        assert self._run(3.0, "NON-RESI")["pass_status"] == "pass"

    def test_non_resi_fail(self):
        assert self._run(1.0, "NON-RESI")["pass_status"] == "fail"

    # --- NONE / CIRC (no threshold) ---
    def test_none_type_status_is_none(self):
        r = self._run(5.0, "NONE")
        assert r["pass_status"] == "none"
        assert r["threshold"] is None

    def test_circ_type_status_is_none(self):
        assert self._run(5.0, "CIRC")["pass_status"] == "none"

    # --- Marginal boundary ---
    def test_marginal_between_50_and_90_pct(self):
        h, w = 10, 10
        img = np.zeros((h, w), dtype=np.float32)
        img[:7, :] = 1.0
        img[7:, :] = 0.1
        r = compute_room_df(img, FULL_POLY_10, room_type="BED")
        assert r is not None
        assert r["pass_status"] == "marginal"

    def test_pass_exactly_at_90pct_boundary(self):
        h, w = 10, 10
        img = np.zeros((h, w), dtype=np.float32)
        img[:9, :] = 1.0
        img[9, :] = 0.1
        r = compute_room_df(img, FULL_POLY_10, room_type="BED")
        assert r is not None
        assert r["pass_status"] == "pass"

    def test_fail_exactly_at_50pct_boundary(self):
        """Exactly 50% above → marginal, not fail."""
        h, w = 10, 10
        img = np.zeros((h, w), dtype=np.float32)
        img[:5, :] = 1.0
        img[5:, :] = 0.1
        r = compute_room_df(img, FULL_POLY_10, room_type="BED")
        assert r is not None
        assert r["pass_status"] == "marginal"

    def test_unknown_room_type_has_no_threshold(self):
        """Room type not in DF_THRESHOLDS falls back to threshold=None."""
        r = self._run(1.0, "UNKNOWN_TYPE")
        assert r["threshold"] is None
        assert r["pass_status"] == "none"


# ===========================================================================
# compute_room_df — result_lines format
# ===========================================================================

class TestComputeRoomDfResultLines:
    def test_no_result_lines_for_none_type(self):
        img = make_uniform_image(10, 10, 1.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="NONE")
        assert r is not None
        assert r["result_lines"] == []

    def test_result_lines_present_for_typed_room(self):
        img = make_uniform_image(10, 10, 2.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="BED")
        assert r is not None
        assert len(r["result_lines"]) == 2

    def test_result_lines_include_threshold_label(self):
        img = make_uniform_image(10, 10, 2.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="LIVING")
        assert r is not None
        # Second line: "@ 1% DF"
        assert "1" in r["result_lines"][1]
        assert "DF" in r["result_lines"][1]

    def test_result_lines_area_format_with_area_per_pixel(self):
        img = make_uniform_image(10, 10, 2.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="BED", area_per_pixel_m2=0.01)
        assert r is not None
        assert "m\u00b2" in r["result_lines"][0]

    def test_result_lines_percent_format_without_area(self):
        img = make_uniform_image(10, 10, 2.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="BED", area_per_pixel_m2=0.0)
        assert r is not None
        assert "%" in r["result_lines"][0]
        assert "above" in r["result_lines"][0]

    def test_result_lines_circ_empty(self):
        img = make_uniform_image(10, 10, 1.0)
        r = compute_room_df(img, FULL_POLY_10, room_type="CIRC")
        assert r is not None
        assert r["result_lines"] == []


# ===========================================================================
# read_df_at_pixel
# ===========================================================================

class TestReadDfAtPixel:
    def test_reads_known_value(self):
        img = make_gradient_image(5, 10)
        val = read_df_at_pixel(img, 3.0, 0.0)
        assert val is not None
        assert abs(val - 3.0) < 1e-6

    def test_returns_none_for_out_of_bounds(self):
        img = make_uniform_image(5, 5, 1.0)
        assert read_df_at_pixel(img, 10.0, 10.0) is None

    def test_returns_none_for_none_image(self):
        assert read_df_at_pixel(None, 0.0, 0.0) is None

    def test_rounds_to_nearest_pixel(self):
        img = make_gradient_image(5, 10)
        val = read_df_at_pixel(img, 3.4, 0.0)
        assert val is not None
        assert abs(val - 3.0) < 1e-6

    def test_negative_coords_out_of_bounds(self):
        img = make_uniform_image(5, 5, 1.0)
        assert read_df_at_pixel(img, -1.0, -1.0) is None

    def test_origin_pixel(self):
        img = make_uniform_image(5, 5, 7.0)
        val = read_df_at_pixel(img, 0.0, 0.0)
        assert val is not None
        assert abs(val - 7.0) < 1e-6

    def test_last_pixel(self):
        img = make_uniform_image(5, 10, 7.0)
        val = read_df_at_pixel(img, 9.0, 4.0)
        assert val is not None
        assert abs(val - 7.0) < 1e-6

    def test_boundary_just_outside_width(self):
        img = make_uniform_image(5, 10, 1.0)
        # x=10 is out of bounds for width=10 (valid: 0..9)
        assert read_df_at_pixel(img, 10.0, 0.0) is None

    def test_boundary_just_outside_height(self):
        img = make_uniform_image(5, 10, 1.0)
        assert read_df_at_pixel(img, 0.0, 5.0) is None
