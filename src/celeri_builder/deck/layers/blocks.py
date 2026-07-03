"""Block interior points (pickable, block name in the hover tooltip)."""

from __future__ import annotations

from celeri_builder.deck.primitives import scatter_descriptors
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import normalize_lon

GROUP = "blocks"
ORDER = 70

RADIUS_MAX_PIXELS = 12


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["block"]
    if settings["hide"]:
        return []
    rows = []
    for index, block in enumerate(doc.blocks):
        name = str(block.get("name", ""))
        rows.append(
            {
                "index": index,
                "name": name,
                "tooltip": name,
                "lon": normalize_lon(float(block.get("interior_lon", 0.0))),
                "lat": float(block.get("interior_lat", 0.0)),
            }
        )
    return scatter_descriptors(
        "blocks",
        rows,
        {
            "getFillColor": list(settings["color"]),
            "getRadius": settings["radius"],
            "radiusMinPixels": settings["radius"],
            "radiusMaxPixels": max(RADIUS_MAX_PIXELS, settings["radius"]),
            "pickable": True,
        },
    )
