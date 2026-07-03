"""Fault-segment lines + the fat invisible pick layer.

Rows come from ``SegmentGraph.expand_rows()`` and are rendered with
antimeridian-shortest coordinates (port of ``GetShortestLineCoordinates``
from celeri_ui src/State/Segment/Vertex.ts): when the longitudinal gap
exceeds 180° the segment is drawn across the shorter wrap, which may place
an endpoint beyond lon 360 — the primitives' ``__shift`` twin then covers
the -180..0 view.
"""

from __future__ import annotations

from celeri_builder.deck.primitives import line_descriptors
from celeri_builder.model.document import Document

GROUP = "segments"
ORDER = 40

LON_HALF = 180.0
LON_MAX = 360.0

#: Fat pick layer: alpha 1 (not 0) for reliable GPU picking (plan).
HIT_WIDTH_PIXELS = 12


def _transform_lon(lon: float) -> float:
    """Port of TransformVertexCoordinates: wrap into 0..360."""
    while lon < 0:
        lon += LON_MAX
    while lon > LON_MAX:
        lon -= LON_MAX
    return lon


def shortest_line_coordinates(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Port of celeri_ui GetShortestLineCoordinates (Vertex.ts:38-56)."""
    a_lon, a_lat = _transform_lon(start[0]), start[1]
    b_lon, b_lat = _transform_lon(end[0]), end[1]
    balt_lon = b_lon - LON_MAX if b_lon - a_lon >= LON_HALF else b_lon + LON_MAX
    if abs(a_lon - b_lon) > abs(a_lon - balt_lon):
        return (a_lon, a_lat), (balt_lon, b_lat)
    return (a_lon, a_lat), (b_lon, b_lat)


def _tooltip(seg: dict) -> str:
    """Row hover HTML (name + the facts celeri_ui shows in the segment popup)."""
    name = seg.get("name", "")
    dip = seg.get("dip", "")
    locking_depth = seg.get("locking_depth", "")
    return f"<strong>{name}</strong><br/>dip: {dip}<br/>locking_depth: {locking_depth}"


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["segment"]
    if settings["hide"]:
        return []
    rows = []
    for index, seg in enumerate(doc.segments.expand_rows()):
        (slon, slat), (tlon, tlat) = shortest_line_coordinates(
            (seg["lon1"], seg["lat1"]), (seg["lon2"], seg["lat2"])
        )
        rows.append(
            {
                "index": index,
                "name": seg.get("name", ""),
                "tooltip": _tooltip(seg),
                "slon": slon,
                "slat": slat,
                "tlon": tlon,
                "tlat": tlat,
            }
        )
    color = list(settings["color"])
    descriptors = line_descriptors(
        "segments",
        rows,
        {
            "getColor": color,
            "getWidth": settings["width"],
            "widthUnits": "pixels",
            "widthMinPixels": 1,
        },
    )
    descriptors += line_descriptors(
        "segments_hit",
        rows,
        {
            "getColor": [*color[:3], 1],
            "getWidth": HIT_WIDTH_PIXELS,
            "widthUnits": "pixels",
            "widthMinPixels": HIT_WIDTH_PIXELS,
            "pickable": True,
        },
    )
    return descriptors
