"""Station velocity arrows + pickable station anchors.

Faithful port of the arrow math in celeri_ui
src/Components/Map/MapArrows.ts + src/Utilities/SetupArrowSources.tsx:

- ``direction`` is the unit (east, north) vector of the velocity.
- The drawn shaft length (degrees) is ``magnitude * display scale``.
- Two head strokes leave the tip at ±pi/6 off the reversed direction, each
  ``display scale * arrowHead`` degrees long (the head length factor comes
  from the source settings, NOT from the velocity magnitude).

Each velocity emits 3 LineLayer rows (shaft + 2 head strokes) in
``velocity_arrows`` plus one pickable ScatterplotLayer anchor at the
station in ``velocities`` (the anchor's row index IS the velocity index).
Zero-magnitude velocities get no arrow rows (celeri_ui would produce NaN
geometry there) but keep their anchor.
"""

from __future__ import annotations

import math

from celeri_builder.deck.primitives import line_descriptors, scatter_descriptors
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import normalize_lon

GROUP = "velocities"
ORDER = 50

ARROW_ANGLE_1 = math.pi / 6
ARROW_ANGLE_2 = 2 * math.pi - ARROW_ANGLE_1

ANCHOR_RADIUS_PIXELS = 3


def _head_point(
    tip: tuple[float, float],
    direction: tuple[float, float],
    angle: float,
    head_scale: float,
) -> tuple[float, float]:
    """Rotate the reversed unit direction by ``angle`` and step from the tip."""
    back_e, back_n = -direction[0], -direction[1]
    return (
        tip[0] + (math.cos(angle) * back_e - math.sin(angle) * back_n) * head_scale,
        tip[1] + (math.sin(angle) * back_e + math.cos(angle) * back_n) * head_scale,
    )


def arrow_rows(
    lon: float, lat: float, east_vel: float, north_vel: float, settings: dict
) -> list[dict]:
    """Shaft + two head strokes as slon/slat/tlon/tlat rows (may be empty)."""
    magnitude = math.hypot(east_vel, north_vel)
    if magnitude == 0:
        return []
    direction = (east_vel / magnitude, north_vel / magnitude)
    scale = magnitude * settings["scale"]
    head_scale = settings["scale"] * settings["arrowHead"]
    tip = (lon + direction[0] * scale, lat + direction[1] * scale)
    head_1 = _head_point(tip, direction, ARROW_ANGLE_1, head_scale)
    head_2 = _head_point(tip, direction, ARROW_ANGLE_2, head_scale)
    return [
        {"slon": lon, "slat": lat, "tlon": tip[0], "tlat": tip[1]},
        {"slon": tip[0], "slat": tip[1], "tlon": head_1[0], "tlat": head_1[1]},
        {"slon": tip[0], "slat": tip[1], "tlon": head_2[0], "tlat": head_2[1]},
    ]


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["velocity"]
    if settings["hide"]:
        return []
    line_rows: list[dict] = []
    anchor_rows: list[dict] = []
    for index, velocity in enumerate(doc.velocities):
        lon = normalize_lon(float(velocity.get("lon", 0.0)))
        lat = float(velocity.get("lat", 0.0))
        east_vel = float(velocity.get("east_vel", 0.0))
        north_vel = float(velocity.get("north_vel", 0.0))
        name = str(velocity.get("name", ""))
        anchor_rows.append(
            {
                "index": index,
                "name": name,
                "lon": lon,
                "lat": lat,
                "tooltip": (
                    f"<strong>{name}</strong>"
                    f"<p>north: {north_vel}, east: {east_vel}</p>"
                ),
            }
        )
        for row in arrow_rows(lon, lat, east_vel, north_vel, settings):
            line_rows.append({"index": index, **row})
    color = list(settings["color"])
    descriptors = line_descriptors(
        "velocity_arrows",
        line_rows,
        {
            "getColor": color,
            "getWidth": settings["width"],
            "widthUnits": "pixels",
            "widthMinPixels": 1,
        },
    )
    descriptors += scatter_descriptors(
        "velocities",
        anchor_rows,
        {
            "getFillColor": color,
            "getRadius": ANCHOR_RADIUS_PIXELS,
            "radiusMinPixels": ANCHOR_RADIUS_PIXELS,
            "radiusMaxPixels": 10,
            "pickable": True,
        },
    )
    return descriptors
