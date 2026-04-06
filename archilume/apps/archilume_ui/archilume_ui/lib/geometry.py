"""Geometry utilities for the AOI editor: snapping, point-in-polygon, polygon splitting, ortho."""

import math
from typing import Optional


def point_in_polygon(px: float, py: float, vertices: list[list[float]]) -> bool:
    """Winding-number point-in-polygon test."""
    n = len(vertices)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def polygon_centroid(vertices: list[list[float]]) -> tuple[float, float]:
    """Compute centroid of a polygon using the shoelace formula."""
    n = len(vertices)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        cx = sum(v[0] for v in vertices) / n
        cy = sum(v[1] for v in vertices) / n
        return (cx, cy)

    signed_area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        signed_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    signed_area *= 0.5
    if abs(signed_area) < 1e-10:
        cx = sum(v[0] for v in vertices) / n
        cy = sum(v[1] for v in vertices) / n
        return (cx, cy)

    cx /= 6.0 * signed_area
    cy /= 6.0 * signed_area
    return (cx, cy)


def polygon_label_point(vertices: list[list[float]]) -> tuple[float, float]:
    """Find an interior point suitable for label placement.

    Uses centroid if inside; falls back to grid search for concave polygons.
    """
    cx, cy = polygon_centroid(vertices)
    if point_in_polygon(cx, cy, vertices):
        return (cx, cy)

    # Grid-search fallback for concave polygons
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    best_point = (cx, cy)
    best_dist = -1.0
    steps = 20
    dx = (max_x - min_x) / steps
    dy = (max_y - min_y) / steps

    for i in range(steps + 1):
        for j in range(steps + 1):
            px = min_x + i * dx
            py = min_y + j * dy
            if point_in_polygon(px, py, vertices):
                d = _min_edge_distance(px, py, vertices)
                if d > best_dist:
                    best_dist = d
                    best_point = (px, py)

    return best_point


def _min_edge_distance(px: float, py: float, vertices: list[list[float]]) -> float:
    """Minimum distance from point to any polygon edge."""
    min_d = float("inf")
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        d = _point_to_segment_dist(px, py, x1, y1, x2, y2)
        if d < min_d:
            min_d = d
    return min_d


def _point_to_segment_dist(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """Distance from point (px, py) to line segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def snap_to_vertex(
    x: float,
    y: float,
    all_vertices: list[list[float]],
    threshold: float = 10.0,
) -> tuple[float, float, bool]:
    """Snap (x, y) to nearest existing vertex if within threshold.

    Returns (snapped_x, snapped_y, did_snap).
    """
    best_d = threshold
    sx, sy = x, y
    snapped = False
    for vx, vy in all_vertices:
        d = math.hypot(x - vx, y - vy)
        if d < best_d:
            best_d = d
            sx, sy = vx, vy
            snapped = True
    return (sx, sy, snapped)


def ortho_constrain(
    x: float, y: float, ref_x: float, ref_y: float
) -> tuple[float, float]:
    """Constrain (x, y) to nearest horizontal or vertical line from (ref_x, ref_y)."""
    dx = abs(x - ref_x)
    dy = abs(y - ref_y)
    if dx >= dy:
        return (x, ref_y)
    else:
        return (ref_x, y)


def nearest_point_on_edge(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> tuple[float, float, float]:
    """Find nearest point on edge (x1,y1)-(x2,y2) to (px,py).

    Returns (nearest_x, nearest_y, distance).
    """
    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (x1, y1, math.hypot(px - x1, py - y1))
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    nx = x1 + t * dx
    ny = y1 + t * dy
    return (nx, ny, math.hypot(px - nx, py - ny))


def find_nearest_edge(
    px: float,
    py: float,
    vertices: list[list[float]],
    threshold: float = 10.0,
) -> Optional[tuple[int, float, float, float]]:
    """Find nearest edge of polygon to point.

    Returns (edge_index, nearest_x, nearest_y, distance) or None.
    """
    n = len(vertices)
    best = None
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        nx, ny, d = nearest_point_on_edge(px, py, x1, y1, x2, y2)
        if d <= threshold and (best is None or d < best[3]):
            best = (i, nx, ny, d)
    return best


def ray_polygon_intersection(
    origin: tuple[float, float],
    direction: tuple[float, float],
    vertices: list[list[float]],
) -> Optional[tuple[float, float]]:
    """Find first intersection of ray from origin in direction with polygon boundary.

    Ray: P(t) = origin + t * direction, t > 0.
    """
    ox, oy = origin
    rdx, rdy = direction
    best_t = float("inf")
    best_pt = None
    n = len(vertices)

    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        edge_dx = x2 - x1
        edge_dy = y2 - y1
        denom = rdx * edge_dy - rdy * edge_dx
        if abs(denom) < 1e-12:
            continue
        t = ((x1 - ox) * edge_dy - (y1 - oy) * edge_dx) / denom
        u = ((x1 - ox) * rdy - (y1 - oy) * rdx) / denom
        if t > 1e-6 and -1e-10 <= u <= 1.0 + 1e-10 and t < best_t:
            best_t = t
            hit_x = ox + t * rdx
            hit_y = oy + t * rdy
            # Snap to vertex if very close
            if u < 1e-6:
                hit_x, hit_y = x1, y1
            elif u > 1.0 - 1e-6:
                hit_x, hit_y = x2, y2
            best_pt = (hit_x, hit_y)

    return best_pt


def split_polygon_by_polyline(
    polygon: list[list[float]],
    polyline: list[tuple[float, float]],
) -> tuple[Optional[list[list[float]]], Optional[list[list[float]]]]:
    """Split a closed polygon along a multi-segment polyline.

    The polyline's first and last points must lie on the polygon boundary.
    Returns (poly_a, poly_b) or (None, None) on failure.
    """
    n = len(polygon)
    if n < 3 or len(polyline) < 2:
        return (None, None)

    entry = polyline[0]
    exit_pt = polyline[-1]

    # Find which edges entry/exit fall on
    entry_edge = _find_edge_for_point(entry, polygon)
    exit_edge = _find_edge_for_point(exit_pt, polygon)

    if entry_edge is None or exit_edge is None:
        return (None, None)

    # Build augmented boundary with entry/exit inserted
    augmented = []
    entry_idx = -1
    exit_idx = -1

    for i in range(n):
        augmented.append(list(polygon[i]))
        next_i = (i + 1) % n
        # Insert entry point after this vertex if on this edge
        if i == entry_edge:
            augmented.append(list(entry))
            entry_idx = len(augmented) - 1
        if i == exit_edge:
            augmented.append(list(exit_pt))
            exit_idx = len(augmented) - 1

    if entry_idx < 0 or exit_idx < 0:
        return (None, None)

    # Walk boundary entry→exit for side A
    m = len(augmented)
    bnd_a = []
    idx = entry_idx
    while True:
        bnd_a.append(augmented[idx])
        if idx == exit_idx:
            break
        idx = (idx + 1) % m

    # Walk boundary exit→entry for side B
    bnd_b = []
    idx = exit_idx
    while True:
        bnd_b.append(augmented[idx])
        if idx == entry_idx:
            break
        idx = (idx + 1) % m

    # Interior polyline points (excluding first/last which are on boundary)
    interior = [list(p) for p in polyline[1:-1]]

    poly_a = bnd_a + list(reversed(interior))
    poly_b = bnd_b + interior

    if len(poly_a) < 3 or len(poly_b) < 3:
        return (None, None)

    return (poly_a, poly_b)


def _find_edge_for_point(
    pt: tuple[float, float], polygon: list[list[float]], tol: float = 5.0
) -> Optional[int]:
    """Find which edge of polygon a point lies on (within tolerance)."""
    px, py = pt
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        _, _, d = nearest_point_on_edge(px, py, x1, y1, x2, y2)
        if d < tol:
            return i
    return None


def inset_polygon(vertices: list[list[float]], amount: float) -> list[list[float]]:
    """Return a copy of the polygon with each vertex moved inward by `amount` pixels.

    Uses per-vertex bisector inset: each vertex is shifted along the average
    inward normal of its two adjacent edges.  Works for convex polygons and
    reasonably well for mildly concave ones.
    """
    n = len(vertices)
    if n < 3:
        return vertices

    # Ensure counter-clockwise winding (positive area) so "inward" is correct
    area = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    if area < 0:
        vertices = list(reversed(vertices))

    result = []
    for i in range(n):
        xp, yp = vertices[(i - 1) % n]
        xc, yc = vertices[i]
        xn, yn = vertices[(i + 1) % n]

        # Inward normals of the two edges meeting at this vertex
        # Edge prev→cur: normal pointing inward (leftward for CCW) = (dy, -dx) normalised
        dx1, dy1 = xc - xp, yc - yp
        l1 = math.hypot(dx1, dy1)
        if l1 < 1e-10:
            n1x, n1y = 0.0, 0.0
        else:
            n1x, n1y = dy1 / l1, -dx1 / l1

        # Edge cur→next
        dx2, dy2 = xn - xc, yn - yc
        l2 = math.hypot(dx2, dy2)
        if l2 < 1e-10:
            n2x, n2y = 0.0, 0.0
        else:
            n2x, n2y = dy2 / l2, -dx2 / l2

        # Bisector direction (average of the two normals)
        bx = n1x + n2x
        by = n1y + n2y
        bl = math.hypot(bx, by)
        if bl < 1e-10:
            result.append([xc, yc])
            continue

        # Scale so the inset distance measured perpendicularly to each edge is `amount`
        # dot(bisector_unit, n1) = cos(half-angle); divide by that to get correct offset
        cos_half = (bx * n1x + by * n1y) / bl
        if abs(cos_half) < 1e-6:
            scale = amount
        else:
            scale = amount / cos_half

        result.append([xc + (bx / bl) * scale, yc + (by / bl) * scale])

    return result


def polygon_area(vertices: list[list[float]]) -> float:
    """Compute signed area of polygon (positive = CCW)."""
    n = len(vertices)
    area = 0.0
    for i in range(n):
        x0, y0 = vertices[i]
        x1, y1 = vertices[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return area / 2.0


def polygon_bbox(vertices: list[list[float]]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) bounding box."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return (min(xs), min(ys), max(xs), max(ys))


def make_unique_name(name: str, existing_names: list[str]) -> str:
    """Ensure name is unique by appending _2, _3, etc."""
    if name not in existing_names:
        return name
    base = name
    counter = 2
    while f"{base}_{counter}" in existing_names:
        counter += 1
    return f"{base}_{counter}"
