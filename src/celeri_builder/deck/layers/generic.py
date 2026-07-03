"""Generic CSV line overlays: one LineLayer per collection.

Mirrors celeri_ui SetupLineSources.tsx generic-segment handling: a
collection renders only when all four mapped position keys are set; rows
whose mapped coordinates are not numeric are skipped; lines use
antimeridian-shortest coordinates.
"""

from __future__ import annotations

from celeri_builder.deck.layers.segments import shortest_line_coordinates
from celeri_builder.deck.primitives import line_descriptors
from celeri_builder.model.document import Document, GenericCollection

GROUP = "generic"
ORDER = 30


def _collection_rows(collection: GenericCollection) -> list[dict]:
    rows = []
    for index, row in enumerate(collection.rows):
        try:
            start = (
                float(row[collection.start_lon_key]),
                float(row[collection.start_lat_key]),
            )
            end = (
                float(row[collection.end_lon_key]),
                float(row[collection.end_lat_key]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        (slon, slat), (tlon, tlat) = shortest_line_coordinates(start, end)
        rows.append(
            {"index": index, "slon": slon, "slat": slat, "tlon": tlon, "tlat": tlat}
        )
    return rows


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["generic"]
    if settings["hide"]:
        return []
    descriptors: list[dict] = []
    for name, collection in doc.generic.items():
        keys = (
            collection.start_lon_key,
            collection.start_lat_key,
            collection.end_lon_key,
            collection.end_lat_key,
        )
        if not all(keys):
            continue
        rows = _collection_rows(collection)
        if not rows:
            continue
        descriptors += line_descriptors(
            f"generic_{name}",
            rows,
            {
                "getColor": list(settings["color"]),
                "getWidth": settings["width"],
                "widthUnits": "pixels",
            },
        )
    return descriptors
