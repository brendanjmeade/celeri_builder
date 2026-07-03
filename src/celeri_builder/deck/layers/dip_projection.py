"""Down-dip surface-projection polygons for dipping segments.

Per expanded segment row this calls
``celeri_builder.geo.dip.fault_dip_projection`` (the celeri_ui
``projectSegment`` port) and skips ``None`` results (vertical dip or
non-positive locking depth). Polygons fill with the segment panel's
``projectionColor`` at half opacity; the whole group is empty when
``hideProjection`` is set.
"""

from __future__ import annotations

from celeri_builder.deck.primitives import polygon_descriptors
from celeri_builder.geo.dip import fault_dip_projection
from celeri_builder.model.document import Document

GROUP = "dip_projection"
ORDER = 20


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    settings = display["segment"]
    if settings["hideProjection"]:
        return []
    rows = []
    for index, seg in enumerate(doc.segments.expand_rows()):
        polygon = fault_dip_projection(
            seg["lon1"],
            seg["lat1"],
            seg["lon2"],
            seg["lat2"],
            float(seg.get("dip", 90.0)),
            float(seg.get("locking_depth", 0.0)),
        )
        if polygon is None:
            continue
        rows.append(
            {
                "index": index,
                "polygon": [[float(lon), float(lat)] for lon, lat in polygon],
            }
        )
    if not rows:
        return []
    color = list(settings["projectionColor"])
    fill = [*color[:3], color[3] // 2]
    return polygon_descriptors(
        "dip_projection",
        rows,
        {
            "getFillColor": fill,
            "filled": True,
            "stroked": False,
        },
    )
