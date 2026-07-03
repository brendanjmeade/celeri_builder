"""Lon/lat graticule (PathLayer), shown when the grid display toggle is on.

Meridians every ``spacing`` degrees across 0..360 (spanning lat -80..80)
and parallels every ``spacing`` degrees across -80..80 (spanning lon
0..360). Line style follows celeri_ui MapGrid.ts (rgba(0,0,0,0.2), 1 px).
"""

from __future__ import annotations

from celeri_builder.deck.primitives import path_descriptors
from celeri_builder.model.document import Document

GROUP = "graticule"
ORDER = 0

LON_MIN, LON_MAX = 0.0, 360.0
LAT_MIN, LAT_MAX = -80.0, 80.0
GRID_COLOR = [0, 0, 0, 51]  # rgba(0,0,0,0.2)


def _steps(start: float, stop: float, spacing: float) -> list[float]:
    values = []
    value = start
    while value <= stop + 1e-9:
        values.append(round(value, 9))
        value += spacing
    return values


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["grid"]
    if not settings["show"]:
        return []
    spacing = float(settings["spacing"]) or 10.0
    rows = [
        {"label": f"Lon: {lon:g}", "path": [[lon, LAT_MIN], [lon, LAT_MAX]]}
        for lon in _steps(LON_MIN, LON_MAX, spacing)
    ]
    rows += [
        {"label": f"Lat: {lat:g}", "path": [[LON_MIN, lat], [LON_MAX, lat]]}
        for lat in _steps(LAT_MIN, LAT_MAX, spacing)
    ]
    return path_descriptors(
        "graticule",
        rows,
        {
            "getColor": GRID_COLOR,
            "getWidth": 1,
            "widthUnits": "pixels",
        },
    )
