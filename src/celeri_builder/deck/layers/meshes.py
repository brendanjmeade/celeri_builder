"""Mesh wireframes: one LineLayer with the unique edges of every mesh.

Edge rows are built from ``Mesh.edges()`` + the vertex array and rendered
with antimeridian-shortest coordinates, matching celeri_ui's mesh-line
sources (SetupLineSources.tsx uses GetShortestLineCoordinates for meshes
too). All meshes share the single ``meshes`` layer id; each row keeps its
mesh ``name``.
"""

from __future__ import annotations

from celeri_builder.deck.layers.segments import shortest_line_coordinates
from celeri_builder.deck.primitives import line_descriptors
from celeri_builder.model.document import Document

GROUP = "meshes"
ORDER = 10


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["mesh"]
    if settings["hide"]:
        return []
    rows = []
    for name, mesh in doc.meshes.items():
        lonlat = mesh.vertices[:, :2]
        for i, j in mesh.edges():
            (slon, slat), (tlon, tlat) = shortest_line_coordinates(
                (float(lonlat[i, 0]), float(lonlat[i, 1])),
                (float(lonlat[j, 0]), float(lonlat[j, 1])),
            )
            rows.append(
                {
                    "name": name,
                    "slon": slon,
                    "slat": slat,
                    "tlon": tlon,
                    "tlat": tlat,
                }
            )
    if not rows:
        return []
    return line_descriptors(
        "meshes",
        rows,
        {
            "getColor": list(settings["color"]),
            "getWidth": settings["width"],
            "widthUnits": "pixels",
        },
    )
