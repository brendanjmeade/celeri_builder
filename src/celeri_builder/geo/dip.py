"""Fault dip down-dip surface projection.

Line-for-line port of ``projectSegment`` from celeri_ui
``src/State/Segment/State.ts`` (lines 53-110), including the turf.js 6.5
spherical geometry it relies on (``distance``/``bearing``/``destination``
composed by ``along``, earth radius 6 371 008.8 m).

celeri_ui rules preserved exactly:

- Skip (return ``None``) when ``dip == 90`` or ``locking_depth <= 0``.
- The horizontal projection distance is
  ``abs(tan(radians(|90 - dip|)) * locking_depth)`` kilometers — i.e.
  ``locking_depth / tan(dip)`` in magnitude, NOT ``tan(dip) * locking_depth``
  (the TS builds ``dipBase`` from the complement of the dip).
- Endpoints are reordered so ``start`` is the easternmost (``start.lon >=
  end.lon``); the offset direction is the raw degree-space normal
  ``(end.lat - start.lat, -(end.lon - start.lon))``, negated when
  ``dip < 90`` ("dip to the left").
- Each bottom-edge corner is turf ``along`` on the two-point line from the
  vertex to ``vertex + normal``: if the projection distance exceeds that
  line's geodesic length the result clamps to ``vertex + normal``.
"""

from __future__ import annotations

import numpy as np

#: turf.js ``earthRadius`` (@turf/helpers 6.5) expressed in kilometers.
TURF_EARTH_RADIUS_KM = 6371.0088

LonLat = tuple[float, float]


def _distance_km(a: LonLat, b: LonLat) -> float:
    """turf.distance: haversine great-circle distance in kilometers."""
    dlat = np.deg2rad(b[1] - a[1])
    dlon = np.deg2rad(b[0] - a[0])
    lat1 = np.deg2rad(a[1])
    lat2 = np.deg2rad(b[1])
    h = np.sin(dlat / 2.0) ** 2 + np.sin(dlon / 2.0) ** 2 * np.cos(lat1) * np.cos(lat2)
    return float(2.0 * np.arctan2(np.sqrt(h), np.sqrt(1.0 - h)) * TURF_EARTH_RADIUS_KM)


def _bearing_deg(a: LonLat, b: LonLat) -> float:
    """turf.bearing: initial great-circle bearing from ``a`` to ``b``."""
    lon1 = np.deg2rad(a[0])
    lat1 = np.deg2rad(a[1])
    lon2 = np.deg2rad(b[0])
    lat2 = np.deg2rad(b[1])
    y = np.sin(lon2 - lon1) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
    return float(np.rad2deg(np.arctan2(y, x)))


def _destination(origin: LonLat, distance_km: float, bearing_deg: float) -> LonLat:
    """turf.destination: spherical point at distance/bearing from origin."""
    lon1 = np.deg2rad(origin[0])
    lat1 = np.deg2rad(origin[1])
    bearing = np.deg2rad(bearing_deg)
    ang = distance_km / TURF_EARTH_RADIUS_KM
    lat2 = np.arcsin(
        np.sin(lat1) * np.cos(ang) + np.cos(lat1) * np.sin(ang) * np.cos(bearing)
    )
    lon2 = lon1 + np.arctan2(
        np.sin(bearing) * np.sin(ang) * np.cos(lat1),
        np.cos(ang) - np.sin(lat1) * np.sin(lat2),
    )
    return (float(np.rad2deg(lon2)), float(np.rad2deg(lat2)))


def _along(start: LonLat, end: LonLat, distance_km: float) -> LonLat:
    """turf.along on the two-point line ``start -> end``.

    Mirrors turf 6.5 exactly: when the requested distance reaches or
    exceeds the line length the LAST coordinate is returned (clamp);
    otherwise the point is found by stepping BACKWARDS from ``end`` by the
    (negative) overshoot along ``bearing(end, start) - 180``.
    """
    travelled = _distance_km(start, end)
    if distance_km >= travelled:
        return (float(end[0]), float(end[1]))
    overshot = distance_km - travelled  # negative
    direction = _bearing_deg(end, start) - 180.0
    return _destination(end, overshot, direction)


def fault_dip_projection(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    dip: float,
    locking_depth: float,
) -> list[LonLat] | None:
    """Down-dip surface-projection polygon of a fault segment.

    Returns the corner ring ``[(lon1, lat1), (lon2, lat2), proj2, proj1]``
    — the surface trace followed by the projected bottom edge walked back —
    where ``proj_i`` is the down-dip projection of input point ``i``.
    Returns ``None`` when ``dip == 90`` or ``locking_depth <= 0``
    (celeri_ui skip rules).
    """
    if dip == 90 or locking_depth <= 0:
        return None

    dip_to_the_left = dip < 90
    dip_base = 90.0 - dip if dip_to_the_left else dip - 90.0
    dip_angle = np.deg2rad(dip_base)
    projection_distance = abs(float(np.tan(dip_angle)) * locking_depth)

    # TS: start is the easternmost endpoint (start.lon >= end.lon).
    swapped = lon1 < lon2
    if swapped:
        start: LonLat = (lon2, lat2)
        end: LonLat = (lon1, lat1)
    else:
        start = (lon1, lat1)
        end = (lon2, lat2)

    normal_lon = end[1] - start[1]
    normal_lat = -(end[0] - start[0])
    if dip_to_the_left:
        normal_lon = -normal_lon
        normal_lat = -normal_lat

    proj_start = _along(
        start, (start[0] + normal_lon, start[1] + normal_lat), projection_distance
    )
    proj_end = _along(
        end, (end[0] + normal_lon, end[1] + normal_lat), projection_distance
    )

    proj1, proj2 = (proj_end, proj_start) if swapped else (proj_start, proj_end)
    return [(float(lon1), float(lat1)), (float(lon2), float(lat2)), proj2, proj1]
