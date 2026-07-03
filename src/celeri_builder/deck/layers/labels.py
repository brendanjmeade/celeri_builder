"""Numeric-field text labels (celeri_ui per-layer ``plottableKey``).

Each of the segment / block / velocity panels has a "Plotted Value" select
(``display.<panel>.plottableKey``). When it names a field, celeri_ui prints
that field's value as text at every entity position; here that becomes a
deck.gl ``TextLayer`` per panel:

- segment -> the segment MIDPOINT (same point the lasso tests against),
- block   -> the block interior point,
- velocity-> the station location.

A panel whose layer is hidden shows no labels, and an empty ``plottableKey``
(the default) emits nothing — so the group is empty until a value is chosen.
"""

from __future__ import annotations

from celeri_builder.deck.primitives import (
    ANTIMERIDIAN_LON,
    SHIFT_LON,
    SHIFT_SUFFIX,
)
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import normalize_lon

GROUP = "labels"
ORDER = 80

LABEL_SIZE_PIXELS = 13
LABEL_PIXEL_OFFSET = [0, -12]
LABEL_BACKGROUND_COLOR = [0, 0, 0, 140]
LABEL_BACKGROUND_PADDING = [3, 1]


def _format_value(value) -> str:
    """Render a field value as compact label text."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def _text_descriptors(layer_id: str, rows: list[dict], color) -> list[dict]:
    """TextLayer descriptor(s) for rows with ``lon/lat/text`` (+ twin)."""
    if not rows:
        return []
    base = {
        "type": "TextLayer",
        "id": layer_id,
        "data": rows,
        "getPosition": ["@lon", "@lat"],
        "getText": "@text",
        "getColor": list(color),
        "getSize": LABEL_SIZE_PIXELS,
        "sizeUnits": "pixels",
        "getTextAnchor": "middle",
        "getAlignmentBaseline": "center",
        "getPixelOffset": list(LABEL_PIXEL_OFFSET),
        "background": True,
        "getBackgroundColor": list(LABEL_BACKGROUND_COLOR),
        "backgroundPadding": list(LABEL_BACKGROUND_PADDING),
        "pickable": False,
    }
    if not any(row["lon"] > ANTIMERIDIAN_LON for row in rows):
        return [base]
    shifted = [{**row, "lon": row["lon"] + SHIFT_LON} for row in rows]
    return [base, {**base, "id": layer_id + SHIFT_SUFFIX, "data": shifted}]


def _plottable_key(settings: dict) -> str:
    return "" if settings["hide"] else str(settings.get("plottableKey") or "")


def _segment_labels(doc: Document, display: dict) -> list[dict]:
    settings = display["segment"]
    key = _plottable_key(settings)
    if not key:
        return []
    rows = []
    for row in doc.segments.expand_rows():
        if key not in row:
            continue
        lon = (
            normalize_lon(float(row["lon1"])) + normalize_lon(float(row["lon2"]))
        ) / 2
        lat = (float(row["lat1"]) + float(row["lat2"])) / 2
        rows.append({"lon": lon, "lat": lat, "text": _format_value(row[key])})
    return _text_descriptors("labels_segment", rows, settings["color"])


def _block_labels(doc: Document, display: dict) -> list[dict]:
    settings = display["block"]
    key = _plottable_key(settings)
    if not key:
        return []
    rows = [
        {
            "lon": normalize_lon(float(block.get("interior_lon", 0.0))),
            "lat": float(block.get("interior_lat", 0.0)),
            "text": _format_value(block[key]),
        }
        for block in doc.blocks
        if key in block
    ]
    return _text_descriptors("labels_block", rows, settings["color"])


def _velocity_labels(doc: Document, display: dict) -> list[dict]:
    settings = display["velocity"]
    key = _plottable_key(settings)
    if not key:
        return []
    rows = [
        {
            "lon": normalize_lon(float(velocity.get("lon", 0.0))),
            "lat": float(velocity.get("lat", 0.0)),
            "text": _format_value(velocity[key]),
        }
        for velocity in doc.velocities
        if key in velocity
    ]
    return _text_descriptors("labels_velocity", rows, settings["color"])


def build(doc: Document, display: dict, selection: dict) -> list[dict]:  # noqa: ARG001
    return [
        *_segment_labels(doc, display),
        *_block_labels(doc, display),
        *_velocity_labels(doc, display),
    ]
