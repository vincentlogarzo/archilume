"""Geometry utilities for the AOI editor: snapping, point-in-polygon, polygon splitting, ortho."""

import heapq
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


def polygon_label_point(
    vertices: list[list[float]], precision: float = 1.0
) -> tuple[float, float]:
    """Find an interior point suitable for label placement.

    Rule is aspect-dependent:

    * **Landscape rooms** (bbox width > height) → shoelace centroid
      (equivalent to the centre of mass of a uniformly-filled polygon).
      Keeps labels visually balanced in rooms that are already wide
      enough to comfortably fit horizontal text.
    * **Portrait or square rooms** (bbox height ≥ width) → pole of
      inaccessibility (centre of the largest inscribed circle). Biases
      labels toward the thickest interior region, so tall narrow rooms
      with a bulge get the anchor in the bulge rather than the cramped
      stem.

    Either branch falls back to the pole of inaccessibility if the
    centroid is not inside the polygon (concave shapes), so the
    returned point is always interior.
    """
    n = len(vertices)
    if n < 3:
        if n == 0:
            return (0.0, 0.0)
        return (vertices[0][0], vertices[0][1])

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    if width > height:
        cx, cy = polygon_centroid(vertices)
        if point_in_polygon(cx, cy, vertices):
            return (cx, cy)
        # Concave landscape polygon with exterior centroid — fall through

    return _polygon_pole_of_inaccessibility(vertices, precision)


def _polygon_pole_of_inaccessibility(
    vertices: list[list[float]], precision: float = 1.0
) -> tuple[float, float]:
    """Interior point maximising distance to the polygon boundary.

    Uses the Mapbox `polylabel` algorithm: priority-queue-driven quadtree
    subdivision of the polygon bbox using signed distance-to-edge as the
    cell score, with the cell half-diagonal as the pruning upper bound.
    Assumes `len(vertices) >= 3`.
    """
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    cell_size = min(width, height)
    if cell_size < 1e-9:
        return (min_x, min_y)

    h = cell_size / 2.0

    # Seed with centroid as a cheap starting best
    cx, cy = polygon_centroid(vertices)
    best_x, best_y = cx, cy
    best_d = _signed_edge_distance(cx, cy, vertices)

    # Also try bbox centre as a second seed
    bcx, bcy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    bcd = _signed_edge_distance(bcx, bcy, vertices)
    if bcd > best_d:
        best_d = bcd
        best_x, best_y = bcx, bcy

    # Priority queue of cells: (-max_possible_distance, counter, x, y, h)
    # Negated so heapq (min-heap) yields the most promising cell first.
    queue: list[tuple[float, int, float, float, float]] = []
    counter = 0

    def _push_cell(x: float, y: float, half: float) -> None:
        nonlocal counter
        d = _signed_edge_distance(x, y, vertices)
        # Upper bound: any point within this square cell is at most
        # half * sqrt(2) farther from the polygon boundary than its centre.
        upper = d + half * math.sqrt(2.0)
        heapq.heappush(queue, (-upper, counter, x, y, half))
        counter += 1
        nonlocal best_d, best_x, best_y
        if d > best_d:
            best_d = d
            best_x, best_y = x, y

    # Tile the bbox with cells of side `cell_size`
    x = min_x
    while x < max_x:
        y = min_y
        while y < max_y:
            _push_cell(x + h, y + h, h)
            y += cell_size
        x += cell_size

    while queue:
        neg_upper, _, x, y, half = heapq.heappop(queue)
        upper = -neg_upper
        # Prune: this cell can't beat the current best by more than `precision`
        if upper - best_d <= precision:
            continue
        # Subdivide into four children
        sub_h = half / 2.0
        _push_cell(x - sub_h, y - sub_h, sub_h)
        _push_cell(x + sub_h, y - sub_h, sub_h)
        _push_cell(x - sub_h, y + sub_h, sub_h)
        _push_cell(x + sub_h, y + sub_h, sub_h)

    # Guarantee the returned point is inside the polygon. For degenerate
    # or numerically pathological inputs the search may still score a
    # near-boundary point — fall back to the seeded centroid if it was
    # interior.
    if not point_in_polygon(best_x, best_y, vertices) and point_in_polygon(cx, cy, vertices):
        return (cx, cy)
    return (best_x, best_y)


def _min_edge_distance(px: float, py: float, vertices: list[list[float]]) -> float:
    """Minimum unsigned distance from point to any polygon edge."""
    min_d = float("inf")
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        d = _point_to_segment_dist(px, py, x1, y1, x2, y2)
        if d < min_d:
            min_d = d
    return min_d


def _signed_edge_distance(
    px: float, py: float, vertices: list[list[float]]
) -> float:
    """Signed distance to polygon boundary — positive inside, negative outside."""
    d = _min_edge_distance(px, py, vertices)
    return d if point_in_polygon(px, py, vertices) else -d


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


def _ray_to_edge(
    cx: float, cy: float, dx: float, dy: float,
    vertices: list[list[float]],
) -> float:
    """Distance from (cx,cy) along direction (dx,dy) to nearest polygon edge.

    Uses ray-segment intersection. Returns a large value if no intersection.
    """
    best = 1e9
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        denom = dx * ey - dy * ex
        if abs(denom) < 1e-12:
            continue
        t = ((x1 - cx) * ey - (y1 - cy) * ex) / denom
        u = ((x1 - cx) * dy - (y1 - cy) * dx) / denom
        if t > 1e-9 and 0.0 <= u <= 1.0 and t < best:
            best = t
    return best


def max_inscribed_rect(
    cx: float, cy: float, vertices: list[list[float]],
) -> tuple[float, float]:
    """Max axis-aligned rectangle centred at (cx, cy) inside polygon.

    Returns (half_width, half_height). Cardinal-ray bound only; corners
    may extend outside polygon for concave shapes — use
    `max_inscribed_rect_aspect()` for corner-safe sizing.
    """
    if len(vertices) < 3:
        return (0.0, 0.0)
    dist_left = _ray_to_edge(cx, cy, -1, 0, vertices)
    dist_right = _ray_to_edge(cx, cy, 1, 0, vertices)
    dist_up = _ray_to_edge(cx, cy, 0, -1, vertices)
    dist_down = _ray_to_edge(cx, cy, 0, 1, vertices)
    return (min(dist_left, dist_right), min(dist_up, dist_down))


def max_inscribed_rect_aspect(
    cx: float, cy: float, ratio_w: float, ratio_h: float,
    vertices: list[list[float]], samples_per_edge: int = 3,
) -> tuple[float, float]:
    """Max rectangle with aspect (ratio_w:ratio_h) centred at (cx, cy)
    where all corners and edge samples lie inside polygon.

    Binary search on scale factor. Tests rect corners + midpoints to
    catch concave-edge intrusions.

    Returns (half_width, half_height).
    """
    if len(vertices) < 3 or ratio_w <= 0 or ratio_h <= 0:
        return (0.0, 0.0)

    # Upper bound: cardinal rays
    cw, ch = max_inscribed_rect(cx, cy, vertices)
    if cw <= 0 or ch <= 0:
        return (0.0, 0.0)

    s_hi = min(2 * cw / ratio_w, 2 * ch / ratio_h)
    s_lo = 0.0

    def _fits(s: float) -> bool:
        hw = ratio_w * s / 2
        hh = ratio_h * s / 2
        # Sample rect perimeter — corners and midpoints
        n = max(1, samples_per_edge)
        pts: list[tuple[float, float]] = []
        for k in range(n + 1):
            t = k / n
            x = -hw + t * 2 * hw
            pts.append((x, -hh))
            pts.append((x, hh))
            y = -hh + t * 2 * hh
            pts.append((-hw, y))
            pts.append((hw, y))
        for dx, dy in pts:
            if not point_in_polygon(cx + dx, cy + dy, vertices):
                return False
        return True

    # Binary search ~20 iterations → 1e-6 relative precision
    for _ in range(20):
        s_mid = (s_lo + s_hi) / 2
        if _fits(s_mid):
            s_lo = s_mid
        else:
            s_hi = s_mid
    return (ratio_w * s_lo / 2, ratio_h * s_lo / 2)


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
