"""Selection + lasso overlay group (drawn on top of everything).

Highlights the current selection with the owning panel's ``selectedColor``
(celeri_ui recolors rows in-layer via Mapbox feature state; here the
highlight is a separate overlay group so only this small group rebuilds on
selection changes):

- kind 'segment': the selected segments re-drawn as a LineLayer with
  ``selectedColor``/``selectedWidth`` (antimeridian-shortest coordinates,
  reusing ``segments.shortest_line_coordinates``).
- kind 'vertex' / 'block' / 'velocity': ScatterplotLayer points at the
  selected coordinates with the panel's ``selectedColor`` and a slightly
  larger radius than the base layer.

The in-progress lasso polygon (celeri_ui SetupPolygonSource.tsx
'selection_polygon') renders as a translucent yellow fill + outline.

``selection`` is ``{"kind": str | None, "ids": set()}`` and may carry
``"lasso": [[lon, lat], ...]`` with the in-progress polygon points.
A hidden panel suppresses its highlight (a hidden celeri_ui source shows
no selected features either).
"""

from __future__ import annotations

from celeri_builder.deck.layers.blocks import RADIUS_MAX_PIXELS as BLOCK_RADIUS_MAX
from celeri_builder.deck.layers.segments import shortest_line_coordinates
from celeri_builder.deck.layers.velocities import ANCHOR_RADIUS_PIXELS
from celeri_builder.deck.layers.vertices import RADIUS_MAX_PIXELS as VERTEX_RADIUS_MAX
from celeri_builder.deck.primitives import (
    line_descriptors,
    path_descriptors,
    polygon_descriptors,
    scatter_descriptors,
)
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import normalize_lon

GROUP = "overlay"
ORDER = 90

#: Highlight points render slightly larger than their base layer.
HIGHLIGHT_RADIUS_BONUS = 2

LASSO_FILL_COLOR = [255, 255, 0, 60]
LASSO_LINE_COLOR = [255, 255, 0, 200]
LASSO_MIN_OUTLINE_POINTS = 2
LASSO_MIN_FILL_POINTS = 3


def _highlight_points(
    layer_id: str, rows: list[dict], color, radius: float, radius_max: float
) -> list[dict]:
    if not rows:
        return []
    radius = radius + HIGHLIGHT_RADIUS_BONUS
    return scatter_descriptors(
        layer_id,
        rows,
        {
            "getFillColor": list(color),
            "getRadius": radius,
            "radiusMinPixels": radius,
            "radiusMaxPixels": max(radius_max, radius),
        },
    )


def _segment_highlight(doc: Document, display: dict, ids) -> list[dict]:
    settings = display["segment"]
    if settings["hide"]:
        return []
    graph = doc.segments
    rows = []
    for index in sorted(ids):
        if not 0 <= index < len(graph.segments):
            continue
        start, end = graph.segment_endpoints(graph.segments[index])
        (slon, slat), (tlon, tlat) = shortest_line_coordinates(start, end)
        rows.append(
            {"index": index, "slon": slon, "slat": slat, "tlon": tlon, "tlat": tlat}
        )
    if not rows:
        return []
    return line_descriptors(
        "selection_segments",
        rows,
        {
            "getColor": list(settings["selectedColor"]),
            "getWidth": settings["selectedWidth"],
            "widthUnits": "pixels",
            "widthMinPixels": settings["selectedWidth"],
        },
    )


def _vertex_highlight(doc: Document, display: dict, ids) -> list[dict]:
    settings = display["vertex"]
    if settings["hide"]:
        return []
    rows = []
    for vertex_id in sorted(ids):
        lonlat = doc.segments.vertices.get(vertex_id)
        if lonlat is None:
            continue
        rows.append({"id": vertex_id, "lon": lonlat[0], "lat": lonlat[1]})
    return _highlight_points(
        "selection_vertices",
        rows,
        settings["selectedColor"],
        settings["radius"],
        VERTEX_RADIUS_MAX,
    )


def _block_highlight(doc: Document, display: dict, ids) -> list[dict]:
    settings = display["block"]
    if settings["hide"]:
        return []
    rows = []
    for index in sorted(ids):
        if not 0 <= index < len(doc.blocks):
            continue
        block = doc.blocks[index]
        rows.append(
            {
                "index": index,
                "lon": normalize_lon(float(block.get("interior_lon", 0.0))),
                "lat": float(block.get("interior_lat", 0.0)),
            }
        )
    return _highlight_points(
        "selection_blocks",
        rows,
        settings["selectedColor"],
        settings["radius"],
        BLOCK_RADIUS_MAX,
    )


def _velocity_highlight(doc: Document, display: dict, ids) -> list[dict]:
    settings = display["velocity"]
    if settings["hide"]:
        return []
    rows = []
    for index in sorted(ids):
        if not 0 <= index < len(doc.velocities):
            continue
        velocity = doc.velocities[index]
        rows.append(
            {
                "index": index,
                "lon": normalize_lon(float(velocity.get("lon", 0.0))),
                "lat": float(velocity.get("lat", 0.0)),
            }
        )
    return _highlight_points(
        "selection_velocities",
        rows,
        settings["selectedColor"],
        ANCHOR_RADIUS_PIXELS,
        ANCHOR_RADIUS_PIXELS + HIGHLIGHT_RADIUS_BONUS,
    )


_HIGHLIGHTS = {
    "segment": _segment_highlight,
    "vertex": _vertex_highlight,
    "block": _block_highlight,
    "velocity": _velocity_highlight,
}


def _lasso_descriptors(points: list) -> list[dict]:
    polygon = [[float(point[0]), float(point[1])] for point in points]
    descriptors = []
    if len(polygon) >= LASSO_MIN_FILL_POINTS:
        descriptors += polygon_descriptors(
            "lasso_fill",
            [{"polygon": polygon}],
            {
                "getFillColor": LASSO_FILL_COLOR,
                "filled": True,
                "stroked": False,
            },
        )
    if len(polygon) >= LASSO_MIN_OUTLINE_POINTS:
        descriptors += path_descriptors(
            "lasso_outline",
            [{"path": polygon}],
            {
                "getColor": LASSO_LINE_COLOR,
                "getWidth": 1,
                "widthUnits": "pixels",
                "widthMinPixels": 1,
            },
        )
    return descriptors


def build(doc: Document, display: dict, selection: dict) -> list[dict]:
    descriptors = []
    kind = selection.get("kind")
    ids = selection.get("ids") or ()
    highlight = _HIGHLIGHTS.get(kind) if kind else None
    if highlight is not None and ids:
        descriptors += highlight(doc, display, ids)
    descriptors += _lasso_descriptors(selection.get("lasso") or [])
    return descriptors
