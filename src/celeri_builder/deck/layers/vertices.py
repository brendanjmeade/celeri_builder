"""Segment-graph vertices as pickable points.

Row order follows the graph's vertex-dict insertion order and each row
carries its vertex ``id`` (ids are not contiguous after deletions, so the
picked row index must be mapped back through the row's ``id``).
"""

from __future__ import annotations

from celeri_builder.deck.primitives import scatter_descriptors
from celeri_builder.model.document import Document

GROUP = "vertices"
ORDER = 60

RADIUS_MAX_PIXELS = 10


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["vertex"]
    if settings["hide"]:
        return []
    rows = [
        {
            "id": vertex_id,
            "lon": lon,
            "lat": lat,
            "tooltip": (
                f"<strong>vertex {vertex_id}</strong>"
                f"<br/>lon: {lon:.6f}<br/>lat: {lat:.6f}"
            ),
        }
        for vertex_id, (lon, lat) in doc.segments.vertices.items()
    ]
    return scatter_descriptors(
        "vertices",
        rows,
        {
            "getFillColor": list(settings["color"]),
            "getRadius": settings["radius"],
            "radiusMinPixels": settings["radius"],
            "radiusMaxPixels": max(RADIUS_MAX_PIXELS, settings["radius"]),
            "pickable": True,
        },
    )
