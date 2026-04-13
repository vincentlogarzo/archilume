"""Tests for archilume_ui.lib.geometry — pure geometry utilities.

Regression strategy: each test documents a specific geometric invariant.
When a geometry bug is found, add a test here that fails with the old code
and passes with the fix.
"""

import math

import pytest

from archilume_ui.lib.geometry import (
    _find_edge_for_point,
    _min_edge_distance,
    _point_to_segment_dist,
    _signed_edge_distance,
    find_nearest_edge,
    inset_polygon,
    make_unique_name,
    nearest_point_on_edge,
    ortho_constrain,
    point_in_polygon,
    polygon_area,
    polygon_bbox,
    polygon_centroid,
    polygon_label_point,
    ray_polygon_intersection,
    snap_to_vertex,
    split_polygon_by_polyline,
)

# ---------------------------------------------------------------------------
# Shared polygon fixtures
# ---------------------------------------------------------------------------

UNIT_SQUARE: list[list[float]] = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
UNIT_SQUARE_CW: list[list[float]] = [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0]]
RECTANGLE_10x5: list[list[float]] = [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]]
L_SHAPE: list[list[float]] = [
    [0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0], [1.0, 2.0], [0.0, 2.0],
]
TRIANGLE: list[list[float]] = [[0.0, 0.0], [4.0, 0.0], [0.0, 3.0]]
THIN_RECTANGLE: list[list[float]] = [[0.0, 0.0], [100.0, 0.0], [100.0, 1.0], [0.0, 1.0]]


# ===========================================================================
# point_in_polygon
# ===========================================================================

class TestPointInPolygon:
    def test_center_inside_square(self):
        assert point_in_polygon(0.5, 0.5, UNIT_SQUARE)

    def test_outside_square(self):
        assert not point_in_polygon(2.0, 2.0, UNIT_SQUARE)

    def test_on_boundary_corner(self):
        # Corner — boundary behaviour is acceptable either way; just must not crash
        result = point_in_polygon(0.0, 0.0, UNIT_SQUARE)
        assert isinstance(result, bool)

    def test_on_boundary_edge_midpoint(self):
        # Mid-edge — boundary behaviour varies by algorithm; must not crash
        result = point_in_polygon(0.5, 0.0, UNIT_SQUARE)
        assert isinstance(result, bool)

    def test_degenerate_less_than_3_vertices(self):
        assert not point_in_polygon(0.5, 0.5, [[0.0, 0.0], [1.0, 1.0]])

    def test_empty_polygon(self):
        assert not point_in_polygon(0.0, 0.0, [])

    def test_inside_rectangle(self):
        assert point_in_polygon(5.0, 2.5, RECTANGLE_10x5)

    def test_outside_rectangle(self):
        assert not point_in_polygon(11.0, 2.5, RECTANGLE_10x5)

    def test_inside_l_shape(self):
        assert point_in_polygon(0.5, 0.5, L_SHAPE)

    def test_outside_l_shape_concave_pocket(self):
        assert not point_in_polygon(1.5, 1.5, L_SHAPE)

    def test_cw_winding_square(self):
        assert point_in_polygon(0.5, 0.5, UNIT_SQUARE_CW)

    def test_negative_coordinates(self):
        poly: list[list[float]] = [[-5.0, -5.0], [5.0, -5.0], [5.0, 5.0], [-5.0, 5.0]]
        assert point_in_polygon(-2.0, -2.0, poly)
        assert not point_in_polygon(-6.0, 0.0, poly)

    def test_large_coordinates(self):
        poly = [[0, 0], [1e6, 0], [1e6, 1e6], [0, 1e6]]
        assert point_in_polygon(5e5, 5e5, poly)
        assert not point_in_polygon(2e6, 0, poly)

    def test_inside_triangle(self):
        assert point_in_polygon(1.0, 1.0, TRIANGLE)

    def test_outside_triangle(self):
        assert not point_in_polygon(3.0, 2.5, TRIANGLE)


# ===========================================================================
# _point_to_segment_dist
# ===========================================================================

class TestPointToSegmentDist:
    def test_perpendicular_to_horizontal(self):
        d = _point_to_segment_dist(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d - 3.0) < 1e-9

    def test_perpendicular_to_vertical(self):
        d = _point_to_segment_dist(3.0, 5.0, 0.0, 0.0, 0.0, 10.0)
        assert abs(d - 3.0) < 1e-9

    def test_clamped_past_start(self):
        d = _point_to_segment_dist(-3.0, 4.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d - 5.0) < 1e-9  # distance to (0,0)

    def test_clamped_past_end(self):
        d = _point_to_segment_dist(13.0, 4.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d - 5.0) < 1e-9  # distance to (10,0)

    def test_zero_length_segment(self):
        d = _point_to_segment_dist(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(d - 5.0) < 1e-9  # hypotenuse 3-4-5

    def test_point_on_segment(self):
        d = _point_to_segment_dist(5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d) < 1e-9

    def test_diagonal_segment(self):
        # 45-degree segment from (0,0) to (10,10), point at (0,10)
        d = _point_to_segment_dist(0.0, 10.0, 0.0, 0.0, 10.0, 10.0)
        expected = 10.0 * math.sqrt(2) / 2  # ≈ 7.071
        assert abs(d - expected) < 1e-6


# ===========================================================================
# _min_edge_distance
# ===========================================================================

class TestMinEdgeDistance:
    def test_centre_of_square(self):
        d = _min_edge_distance(0.5, 0.5, UNIT_SQUARE)
        assert abs(d - 0.5) < 1e-9

    def test_near_corner(self):
        d = _min_edge_distance(0.1, 0.1, UNIT_SQUARE)
        assert abs(d - 0.1) < 1e-9

    def test_on_edge(self):
        d = _min_edge_distance(0.5, 0.0, UNIT_SQUARE)
        assert abs(d) < 1e-9


# ===========================================================================
# polygon_centroid
# ===========================================================================

class TestPolygonCentroid:
    def test_unit_square_centroid(self):
        cx, cy = polygon_centroid(UNIT_SQUARE)
        assert abs(cx - 0.5) < 1e-9
        assert abs(cy - 0.5) < 1e-9

    def test_rectangle_centroid(self):
        cx, cy = polygon_centroid(RECTANGLE_10x5)
        assert abs(cx - 5.0) < 1e-9
        assert abs(cy - 2.5) < 1e-9

    def test_empty_polygon(self):
        cx, cy = polygon_centroid([])
        assert cx == 0.0 and cy == 0.0

    def test_single_vertex(self):
        cx, cy = polygon_centroid([[3.0, 7.0]])
        assert cx == 3.0 and cy == 7.0

    def test_two_vertices(self):
        cx, cy = polygon_centroid([[0.0, 0.0], [4.0, 0.0]])
        assert abs(cx - 2.0) < 1e-9
        assert abs(cy - 0.0) < 1e-9

    def test_degenerate_collinear(self):
        verts: list[list[float]] = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
        cx, cy = polygon_centroid(verts)
        assert isinstance(cx, float)
        assert isinstance(cy, float)

    def test_triangle_centroid(self):
        cx, cy = polygon_centroid(TRIANGLE)
        assert abs(cx - 4.0 / 3.0) < 1e-6
        assert abs(cy - 1.0) < 1e-6

    def test_cw_winding_centroid(self):
        # Centroid should be the same regardless of winding
        cx_ccw, cy_ccw = polygon_centroid(UNIT_SQUARE)
        cx_cw, cy_cw = polygon_centroid(UNIT_SQUARE_CW)
        assert abs(cx_ccw - cx_cw) < 1e-9
        assert abs(cy_ccw - cy_cw) < 1e-9


# ===========================================================================
# polygon_area
# ===========================================================================

class TestPolygonArea:
    def test_unit_square_area(self):
        assert abs(polygon_area(UNIT_SQUARE) - 1.0) < 1e-9

    def test_rectangle_area(self):
        assert abs(polygon_area(RECTANGLE_10x5) - 50.0) < 1e-9

    def test_cw_winding_negative_area(self):
        area = polygon_area(UNIT_SQUARE_CW)
        assert area < 0

    def test_area_sign_flips_with_winding(self):
        ccw_area = polygon_area(UNIT_SQUARE)
        cw_area = polygon_area(list(reversed(UNIT_SQUARE)))
        assert abs(ccw_area + cw_area) < 1e-9

    def test_triangle_area(self):
        assert abs(abs(polygon_area(TRIANGLE)) - 6.0) < 1e-9

    def test_empty_polygon(self):
        assert polygon_area([]) == 0.0

    def test_l_shape_area(self):
        # L-shape: 2x2 square minus 1x1 corner = 3.0
        assert abs(abs(polygon_area(L_SHAPE)) - 3.0) < 1e-9


# ===========================================================================
# polygon_bbox
# ===========================================================================

class TestPolygonBbox:
    def test_unit_square(self):
        assert polygon_bbox(UNIT_SQUARE) == (0, 0, 1, 1)

    def test_rectangle(self):
        assert polygon_bbox(RECTANGLE_10x5) == (0, 0, 10, 5)

    def test_l_shape(self):
        min_x, min_y, max_x, max_y = polygon_bbox(L_SHAPE)
        assert (min_x, min_y, max_x, max_y) == (0, 0, 2, 2)

    def test_negative_coordinates(self):
        poly: list[list[float]] = [[-10.0, -20.0], [5.0, -20.0], [5.0, 10.0], [-10.0, 10.0]]
        assert polygon_bbox(poly) == (-10.0, -20.0, 5.0, 10.0)

    def test_single_vertex(self):
        assert polygon_bbox([[7.0, 3.0]]) == (7.0, 3.0, 7.0, 3.0)


# ===========================================================================
# snap_to_vertex
# ===========================================================================

class TestSnapToVertex:
    def test_snaps_to_exact_vertex(self):
        verts = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]
        sx, sy, did_snap = snap_to_vertex(10.1, 0.1, verts, threshold=1.0)
        assert did_snap
        assert sx == 10.0 and sy == 0.0

    def test_no_snap_when_too_far(self):
        verts = [[0.0, 0.0], [10.0, 0.0]]
        sx, sy, did_snap = snap_to_vertex(5.0, 5.0, verts, threshold=1.0)
        assert not did_snap
        assert sx == 5.0 and sy == 5.0

    def test_snaps_to_nearest_among_multiple(self):
        verts = [[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]]
        sx, sy, did_snap = snap_to_vertex(5.3, 0.2, verts, threshold=1.0)
        assert did_snap
        assert sx == 5.0 and sy == 0.0

    def test_default_threshold(self):
        verts = [[0.0, 0.0]]
        _, _, did_snap = snap_to_vertex(9.9, 0.0, verts)
        assert did_snap

    def test_empty_vertex_list(self):
        sx, sy, did_snap = snap_to_vertex(1.0, 1.0, [])
        assert not did_snap
        assert sx == 1.0 and sy == 1.0

    def test_exact_on_vertex_zero_distance(self):
        verts = [[5.0, 5.0]]
        sx, sy, did_snap = snap_to_vertex(5.0, 5.0, verts, threshold=1.0)
        assert did_snap
        assert sx == 5.0 and sy == 5.0

    def test_threshold_boundary_just_inside(self):
        verts = [[0.0, 0.0]]
        # Distance = sqrt(0.5^2 + 0.5^2) ≈ 0.707 < 1.0
        _, _, did_snap = snap_to_vertex(0.5, 0.5, verts, threshold=1.0)
        assert did_snap

    def test_threshold_boundary_just_outside(self):
        verts = [[0.0, 0.0]]
        # Distance = sqrt(1.0^2 + 1.0^2) ≈ 1.414 > 1.0
        _, _, did_snap = snap_to_vertex(1.0, 1.0, verts, threshold=1.0)
        assert not did_snap


# ===========================================================================
# ortho_constrain
# ===========================================================================

class TestOrthoConstrain:
    def test_more_horizontal_movement(self):
        x, y = ortho_constrain(10.0, 6.0, 5.0, 5.0)
        assert x == 10.0 and y == 5.0

    def test_more_vertical_movement(self):
        x, y = ortho_constrain(6.0, 10.0, 5.0, 5.0)
        assert x == 5.0 and y == 10.0

    def test_equal_movement_goes_horizontal(self):
        x, y = ortho_constrain(8.0, 8.0, 5.0, 5.0)
        assert x == 8.0 and y == 5.0

    def test_no_movement(self):
        x, y = ortho_constrain(5.0, 5.0, 5.0, 5.0)
        assert x == 5.0 and y == 5.0

    def test_negative_direction(self):
        x, y = ortho_constrain(0.0, 4.5, 5.0, 5.0)
        assert x == 0.0 and y == 5.0  # dx=5 > dy=0.5


# ===========================================================================
# nearest_point_on_edge
# ===========================================================================

class TestNearestPointOnEdge:
    def test_midpoint_of_horizontal_edge(self):
        nx, ny, d = nearest_point_on_edge(5.0, 3.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(nx - 5.0) < 1e-9
        assert abs(ny - 0.0) < 1e-9
        assert abs(d - 3.0) < 1e-9

    def test_clamped_to_start(self):
        nx, _ny, _d = nearest_point_on_edge(-5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(nx - 0.0) < 1e-9

    def test_clamped_to_end(self):
        nx, _ny, _d = nearest_point_on_edge(15.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(nx - 10.0) < 1e-9

    def test_degenerate_zero_length_edge(self):
        nx, ny, d = nearest_point_on_edge(3.0, 4.0, 0.0, 0.0, 0.0, 0.0)
        assert nx == 0.0 and ny == 0.0
        assert abs(d - 5.0) < 1e-9

    def test_point_exactly_on_edge(self):
        nx, _ny, d = nearest_point_on_edge(5.0, 0.0, 0.0, 0.0, 10.0, 0.0)
        assert abs(d) < 1e-9
        assert abs(nx - 5.0) < 1e-9

    def test_diagonal_edge(self):
        # Edge from (0,0) to (10,10), point at (10,0)
        nx, ny, d = nearest_point_on_edge(10.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        assert abs(nx - 5.0) < 1e-6
        assert abs(ny - 5.0) < 1e-6
        expected_d = math.hypot(5.0, 5.0)
        assert abs(d - expected_d) < 1e-6

    def test_vertical_edge(self):
        nx, ny, d = nearest_point_on_edge(3.0, 5.0, 0.0, 0.0, 0.0, 10.0)
        assert abs(nx - 0.0) < 1e-9
        assert abs(ny - 5.0) < 1e-9
        assert abs(d - 3.0) < 1e-9


# ===========================================================================
# find_nearest_edge
# ===========================================================================

class TestFindNearestEdge:
    def test_finds_bottom_edge_of_square(self):
        result = find_nearest_edge(0.5, 0.1, UNIT_SQUARE, threshold=1.0)
        assert result is not None
        edge_idx, _nx, _ny, d = result
        assert edge_idx == 0
        assert d < 1.0

    def test_returns_none_when_too_far(self):
        result = find_nearest_edge(5.0, 5.0, UNIT_SQUARE, threshold=1.0)
        assert result is None

    def test_returns_closest_edge_not_first(self):
        result = find_nearest_edge(1.05, 0.5, UNIT_SQUARE, threshold=1.0)
        assert result is not None
        assert result[0] == 1  # right edge

    def test_empty_polygon(self):
        result = find_nearest_edge(0.0, 0.0, [], threshold=1.0)
        assert result is None

    def test_returned_point_is_on_edge(self):
        result = find_nearest_edge(0.5, 0.3, UNIT_SQUARE, threshold=1.0)
        assert result is not None
        _, nx, ny, _ = result
        # nearest point should be on bottom edge at y=0
        assert abs(ny - 0.0) < 1e-9
        assert abs(nx - 0.5) < 1e-9


# ===========================================================================
# _find_edge_for_point
# ===========================================================================

class TestFindEdgeForPoint:
    def test_point_on_bottom_edge(self):
        idx = _find_edge_for_point((0.5, 0.0), UNIT_SQUARE)
        assert idx == 0

    def test_point_on_right_edge(self):
        # (1.0, 0.5) is on edge 1 ([1,0]-[1,1]) but also within default tol=5
        # of other edges. _find_edge_for_point returns the first edge found.
        idx = _find_edge_for_point((1.0, 0.5), UNIT_SQUARE)
        assert idx is not None
        assert idx in (0, 1)  # iteration order may find edge 0 first

    def test_point_far_from_boundary(self):
        idx = _find_edge_for_point((50.0, 50.0), UNIT_SQUARE)
        assert idx is None

    def test_point_at_vertex(self):
        # Vertex (1,0) is shared by edges 0 and 1; either is valid
        idx = _find_edge_for_point((1.0, 0.0), UNIT_SQUARE)
        assert idx is not None
        assert idx in (0, 1)

    def test_custom_tolerance(self):
        # 0.5 units away from bottom edge — within tol=1 but outside tol=0.1
        assert _find_edge_for_point((0.5, 0.5), UNIT_SQUARE, tol=1.0) is not None
        assert _find_edge_for_point((0.5, 0.5), UNIT_SQUARE, tol=0.1) is None


# ===========================================================================
# ray_polygon_intersection
# ===========================================================================

class TestRayPolygonIntersection:
    def test_ray_hits_right_edge(self):
        pt = ray_polygon_intersection((0.5, 0.5), (1.0, 0.0), UNIT_SQUARE)
        assert pt is not None
        assert abs(pt[0] - 1.0) < 1e-6
        assert abs(pt[1] - 0.5) < 1e-6

    def test_ray_hits_top_edge(self):
        pt = ray_polygon_intersection((0.5, 0.5), (0.0, 1.0), UNIT_SQUARE)
        assert pt is not None
        assert abs(pt[1] - 1.0) < 1e-6

    def test_ray_hits_left_edge(self):
        pt = ray_polygon_intersection((0.5, 0.5), (-1.0, 0.0), UNIT_SQUARE)
        assert pt is not None
        assert abs(pt[0] - 0.0) < 1e-6

    def test_ray_hits_bottom_edge(self):
        pt = ray_polygon_intersection((0.5, 0.5), (0.0, -1.0), UNIT_SQUARE)
        assert pt is not None
        assert abs(pt[1] - 0.0) < 1e-6

    def test_diagonal_ray(self):
        pt = ray_polygon_intersection((0.5, 0.5), (1.0, 1.0), UNIT_SQUARE)
        assert pt is not None
        # Should hit corner (1,1) or near it
        assert pt[0] >= 0.99
        assert pt[1] >= 0.99

    def test_no_intersection_parallel_ray_outside(self):
        pt = ray_polygon_intersection((0.5, 2.0), (1.0, 0.0), UNIT_SQUARE)
        assert pt is None

    def test_ray_from_outside_toward_polygon(self):
        pt = ray_polygon_intersection((-1.0, 0.5), (1.0, 0.0), UNIT_SQUARE)
        assert pt is not None
        assert abs(pt[0] - 0.0) < 1e-6

    def test_ray_from_outside_away_from_polygon(self):
        pt = ray_polygon_intersection((-1.0, 0.5), (-1.0, 0.0), UNIT_SQUARE)
        assert pt is None


# ===========================================================================
# split_polygon_by_polyline
# ===========================================================================

class TestSplitPolygonByPolyline:
    @pytest.fixture
    def square_10(self):
        return [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]

    def test_horizontal_split(self, square_10):
        polyline = [(0.0, 5.0), (10.0, 5.0)]
        a, b = split_polygon_by_polyline(square_10, polyline)
        assert a is not None and b is not None
        assert len(a) >= 3 and len(b) >= 3

    def test_vertical_split(self, square_10):
        polyline = [(5.0, 0.0), (5.0, 10.0)]
        a, b = split_polygon_by_polyline(square_10, polyline)
        assert a is not None and b is not None
        assert len(a) >= 3 and len(b) >= 3

    def test_split_preserves_total_area(self, square_10):
        polyline = [(0.0, 5.0), (10.0, 5.0)]
        a, b = split_polygon_by_polyline(square_10, polyline)
        assert a is not None and b is not None
        original = abs(polygon_area(square_10))
        total = abs(polygon_area(a)) + abs(polygon_area(b))
        assert abs(total - original) < 1.0

    def test_multi_segment_polyline(self, square_10):
        """Polyline with an interior waypoint."""
        polyline = [(0.0, 5.0), (5.0, 7.0), (10.0, 5.0)]
        a, b = split_polygon_by_polyline(square_10, polyline)
        assert a is not None and b is not None
        original = abs(polygon_area(square_10))
        total = abs(polygon_area(a)) + abs(polygon_area(b))
        assert abs(total - original) < 1.0

    def test_returns_none_for_degenerate_polygon(self):
        a, b = split_polygon_by_polyline([[0.0, 0.0], [1.0, 0.0]], [(0.0, 0.0), (1.0, 0.0)])
        assert a is None and b is None

    def test_returns_none_for_short_polyline(self):
        a, b = split_polygon_by_polyline(UNIT_SQUARE, [(0.5, 0.5)])
        assert a is None and b is None

    def test_entry_exit_not_on_boundary(self):
        a, b = split_polygon_by_polyline(UNIT_SQUARE, [(50.0, 50.0), (100.0, 100.0)])
        assert a is None and b is None

    def test_empty_polygon(self):
        a, b = split_polygon_by_polyline([], [(0, 0), (1, 1)])
        assert a is None and b is None


# ===========================================================================
# inset_polygon
# ===========================================================================

class TestInsetPolygon:
    @pytest.mark.xfail(
        reason="BUG: inset_polygon bisector normal direction is inverted for CCW winding",
        strict=True,
    )
    def test_inset_reduces_area(self):
        inset = inset_polygon(RECTANGLE_10x5, 1.0)
        orig_area = abs(polygon_area(RECTANGLE_10x5))
        inset_area = abs(polygon_area(inset))
        assert inset_area < orig_area

    def test_inset_centroid_stays_close(self):
        inset = inset_polygon(RECTANGLE_10x5, 1.0)
        cx_orig, cy_orig = polygon_centroid(RECTANGLE_10x5)
        cx_in, cy_in = polygon_centroid(inset)
        assert abs(cx_orig - cx_in) < 0.5
        assert abs(cy_orig - cy_in) < 0.5

    def test_inset_preserves_vertex_count(self):
        inset = inset_polygon(RECTANGLE_10x5, 0.5)
        assert len(inset) == len(RECTANGLE_10x5)

    def test_degenerate_less_than_3_vertices_returned_unchanged(self):
        verts: list[list[float]] = [[0.0, 0.0], [1.0, 1.0]]
        result = inset_polygon(verts, 1.0)
        assert result == verts

    def test_zero_inset_unchanged(self):
        inset = inset_polygon(RECTANGLE_10x5, 0.0)
        for orig, ins in zip(RECTANGLE_10x5, inset):
            assert abs(orig[0] - ins[0]) < 1e-9
            assert abs(orig[1] - ins[1]) < 1e-9

    def test_all_vertices_shifted(self):
        """With nonzero inset, no vertex should stay in the original position."""
        inset = inset_polygon(RECTANGLE_10x5, 1.0)
        for orig, ins in zip(RECTANGLE_10x5, inset):
            moved = abs(orig[0] - ins[0]) > 0.01 or abs(orig[1] - ins[1]) > 0.01
            assert moved


# ===========================================================================
# make_unique_name
# ===========================================================================

class TestMakeUniqueName:
    def test_no_conflict(self):
        assert make_unique_name("Room A", ["Room B", "Room C"]) == "Room A"

    def test_conflict_appends_2(self):
        assert make_unique_name("Room A", ["Room A"]) == "Room A_2"

    def test_conflict_skips_existing(self):
        existing = ["Room A", "Room A_2", "Room A_3"]
        assert make_unique_name("Room A", existing) == "Room A_4"

    def test_empty_existing(self):
        assert make_unique_name("X", []) == "X"

    def test_only_conflict_is_numbered(self):
        assert make_unique_name("Room A_2", ["Room A_2"]) == "Room A_2_2"

    def test_empty_name(self):
        assert make_unique_name("", [""]) == "_2"

    def test_many_conflicts(self):
        existing = ["R"] + [f"R_{i}" for i in range(2, 102)]
        assert make_unique_name("R", existing) == "R_102"


# ===========================================================================
# polygon_label_point
# ===========================================================================

class TestPolygonLabelPoint:
    def test_convex_polygon_label_inside(self):
        lx, ly = polygon_label_point(RECTANGLE_10x5)
        assert point_in_polygon(lx, ly, RECTANGLE_10x5)

    def test_l_shape_label_inside(self):
        lx, ly = polygon_label_point(L_SHAPE)
        assert point_in_polygon(lx, ly, L_SHAPE)

    def test_triangle_label_inside(self):
        lx, ly = polygon_label_point(TRIANGLE)
        assert point_in_polygon(lx, ly, TRIANGLE)

    def test_thin_rectangle_label_inside(self):
        lx, ly = polygon_label_point(THIN_RECTANGLE)
        assert point_in_polygon(lx, ly, THIN_RECTANGLE)

    def test_unit_square_anchors_at_centre(self):
        """Pole of inaccessibility for a square is its centre."""
        lx, ly = polygon_label_point(UNIT_SQUARE)
        assert abs(lx - 0.5) < 0.05
        assert abs(ly - 0.5) < 0.05

    def test_rectangle_anchors_at_centre(self):
        """Uniform rectangle → anchor at geometric centre (known limitation)."""
        lx, ly = polygon_label_point(RECTANGLE_10x5)
        assert abs(lx - 5.0) < 0.2
        assert abs(ly - 2.5) < 0.1

    def test_l_shape_anchors_in_thicker_arm(self):
        """L-shape bulk is along the bottom (0..2 x 0..1) and left (0..1 x 0..2).
        Pole of inaccessibility should sit near one of those arms' centres,
        well clear of the concave pocket around (1.5, 1.5)."""
        lx, ly = polygon_label_point(L_SHAPE)
        # Anchor must not fall into the concave pocket (the missing 1..2 x 1..2 quadrant)
        assert not (lx > 1.0 and ly > 1.0)
        # Anchor should be at least as far from any edge as the arm half-thickness
        assert _signed_edge_distance(lx, ly, L_SHAPE) >= 0.4

    def test_portrait_stem_with_bulge_anchors_in_bulge(self):
        """Portrait-bbox polygon: narrow stem with wider bulge on top.
        Height > width triggers pole-of-inaccessibility → anchor in bulge."""
        # Stem: x in [4, 6], y in [0, 10]; bulge: x in [0, 10], y in [10, 14].
        # bbox 10 x 14 — portrait → polylabel branch.
        poly: list[list[float]] = [
            [4.0, 0.0], [6.0, 0.0], [6.0, 10.0],
            [10.0, 10.0], [10.0, 14.0], [0.0, 14.0], [0.0, 10.0], [4.0, 10.0],
        ]
        lx, ly = polygon_label_point(poly)
        assert point_in_polygon(lx, ly, poly)
        # Label should land inside the bulge (y >= 10), not in the stem.
        assert ly >= 10.0
        # Should be notably closer to the bulge centre (5, 12) than the stem.
        assert abs(lx - 5.0) < 1.5

    def test_landscape_uses_centroid_even_with_fat_region(self):
        """Landscape-bbox polygon: thin stem extending sideways from a fat
        square. Rule: width > height → shoelace centroid (not polylabel),
        so the anchor sits near the centroid — not planted in the fat square."""
        # Fat square x in [0, 4], y in [0, 4]; thin stem x in [4, 14], y in [1, 2].
        # bbox 14 x 4 — landscape → centroid branch.
        poly: list[list[float]] = [
            [0.0, 0.0], [4.0, 0.0],
            [4.0, 1.0], [14.0, 1.0], [14.0, 2.0], [4.0, 2.0],
            [4.0, 4.0], [0.0, 4.0],
        ]
        lx, ly = polygon_label_point(poly)
        # Must be interior
        assert point_in_polygon(lx, ly, poly)
        # Centroid lands roughly between the square and stem — NOT at the
        # fat-square centre (2, 2) that polylabel would choose.
        from archilume_ui.lib.geometry import polygon_centroid
        cx, cy = polygon_centroid(poly)
        assert abs(lx - cx) < 1e-6
        assert abs(ly - cy) < 1e-6

    def test_landscape_concave_falls_back_to_polylabel(self):
        """Landscape-bbox concave polygon whose centroid lies outside the
        shape still gets an interior anchor via fallback."""
        # Landscape C-shape: bbox 10 x 6, mouth on the right.
        poly: list[list[float]] = [
            [0.0, 0.0], [10.0, 0.0], [10.0, 2.0], [3.0, 2.0],
            [3.0, 4.0], [10.0, 4.0], [10.0, 6.0], [0.0, 6.0],
        ]
        lx, ly = polygon_label_point(poly)
        assert point_in_polygon(lx, ly, poly)

    def test_concave_polygon_centroid_outside_returns_interior(self):
        """Strongly concave C-shape whose shoelace centroid falls outside the polygon."""
        c_shape: list[list[float]] = [
            [0.0, 0.0], [10.0, 0.0], [10.0, 2.0], [2.0, 2.0],
            [2.0, 8.0], [10.0, 8.0], [10.0, 10.0], [0.0, 10.0],
        ]
        lx, ly = polygon_label_point(c_shape)
        assert point_in_polygon(lx, ly, c_shape)

    def test_degenerate_two_vertices(self):
        lx, ly = polygon_label_point([[3.0, 7.0], [4.0, 8.0]])
        assert lx == 3.0 and ly == 7.0

    def test_empty_polygon(self):
        lx, ly = polygon_label_point([])
        assert lx == 0.0 and ly == 0.0


# ===========================================================================
# _signed_edge_distance
# ===========================================================================

class TestSignedEdgeDistance:
    def test_inside_positive(self):
        assert _signed_edge_distance(0.5, 0.5, UNIT_SQUARE) > 0

    def test_outside_negative(self):
        assert _signed_edge_distance(2.0, 2.0, UNIT_SQUARE) < 0

    def test_magnitude_matches_unsigned(self):
        d_signed = _signed_edge_distance(0.5, 0.5, UNIT_SQUARE)
        d_unsigned = _min_edge_distance(0.5, 0.5, UNIT_SQUARE)
        assert abs(abs(d_signed) - d_unsigned) < 1e-9

    def test_concave_pocket_negative(self):
        # The L_SHAPE concave pocket at (1.5, 1.5) is outside
        assert _signed_edge_distance(1.5, 1.5, L_SHAPE) < 0
