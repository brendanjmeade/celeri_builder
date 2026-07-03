"""Point-in-polygon test — the lasso-select geometry primitive.

Pure geometry (no matplotlib, no turf): an even-odd ray cast that mirrors
celeri_ui's turf-based ``PointsInPolygon`` (src/Utilities/PointUtilities.ts).
The polygon is treated as CLOSED — the last vertex connects back to the
first — so callers do not repeat the opening point (celeri_ui appends
``polygon[0]`` before handing the ring to turf; here the wrap-around edge in
the loop closes it implicitly).

Longitude convention is the caller's responsibility: pass candidate points
and polygon vertices in the SAME frame (celeri_builder normalizes both to the
0-360 convention before calling in :meth:`MapController.close_lasso`). The
test itself is a planar even-odd cast, matching turf's ``booleanPointInPolygon``
on the flat lon/lat plane.
"""

from __future__ import annotations

from collections.abc import Sequence

Point = Sequence[float]
Polygon = Sequence[Point]

#: A polygon needs at least a triangle to enclose any area.
MIN_POLYGON_POINTS = 3


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """True when ``point`` falls inside the closed ``polygon`` (ray casting).

    Boundary points are intentionally left undefined (the even-odd rule gives
    them no stable answer); callers keep candidates clear of polygon edges.
    """
    if len(polygon) < MIN_POLYGON_POINTS:
        return False
    x = float(point[0])
    y = float(point[1])
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        # Does the horizontal ray at ``y`` cross edge (j -> i)? The strict
        # inequality on exactly one endpoint keeps shared vertices from being
        # counted twice (the standard even-odd guard); it also guarantees
        # ``yj != yi`` here, so the crossing division never hits zero.
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def points_in_polygon(points: Sequence[Point], polygon: Polygon) -> list[bool]:
    """Vectorized :func:`point_in_polygon` — one bool per input point."""
    if len(polygon) < MIN_POLYGON_POINTS:
        return [False] * len(points)
    return [point_in_polygon(p, polygon) for p in points]


def enclosed_indices(points: Sequence[Point], polygon: Polygon) -> list[int]:
    """Indices (ascending) of the points enclosed by ``polygon``."""
    return [i for i, inside in enumerate(points_in_polygon(points, polygon)) if inside]
