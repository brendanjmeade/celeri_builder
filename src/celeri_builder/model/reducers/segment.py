"""Segment reducers — faithful ports of celeri_ui ``src/State/Segment/*``.

Rows in the graph never carry lon1/lat1/lon2/lat2 columns; endpoints are
the vertex ids ``start`` and ``end`` (re-expanded on save/render), so new
segments merge ``DEFAULT_SEGMENT`` minus the lon/lat keys.
"""

from __future__ import annotations

from typing import Any

from celeri_builder.model.actions import (
    BridgeVertices,
    CreateSegment,
    DeleteSegments,
    EditSegments,
    ExtrudeSegment,
    LoadSegments,
    MergeVertices,
    MoveVertex,
    SplitSegments,
)
from celeri_builder.model.document import Document
from celeri_builder.model.schema import DEFAULT_SEGMENT

_LONLAT_KEYS = ("lon1", "lat1", "lon2", "lat2")


def _default_segment_row() -> dict[str, Any]:
    """``defaultSegment`` minus the lon/lat columns (graph uses vertex ids)."""
    return {k: v for k, v in DEFAULT_SEGMENT.items() if k not in _LONLAT_KEYS}


def create_segment(doc: Document, action: CreateSegment) -> Document:
    """CreateSegment.tsx: get-or-insert both endpoints, append default+props."""
    graph, start = doc.segments.get_or_insert(*action.start)
    graph, end = graph.get_or_insert(*action.end)
    seg = {**_default_segment_row(), **action.props, "start": start, "end": end}
    return doc.with_(segments=graph.with_segments((*graph.segments, seg)))


def delete_segments(doc: Document, action: DeleteSegments) -> Document:
    """DeleteSegment.tsx: drop indexed rows, then GC each removed row's
    endpoints (start first, then end)."""
    drop = set(action.indices)
    kept: list[dict] = []
    removed: list[dict] = []
    for i, seg in enumerate(doc.segments.segments):
        (removed if i in drop else kept).append(seg)
    if not removed:
        return doc
    graph = doc.segments.with_segments(tuple(kept))
    for seg in removed:
        graph = graph.try_remove_vertex(seg["start"])
        graph = graph.try_remove_vertex(seg["end"])
    return doc.with_(segments=graph)


def edit_segments(doc: Document, action: EditSegments) -> Document:
    """EditSegmentData.tsx: shallow-merge the patch into every indexed row."""
    if not action.indices:
        return doc
    segments = list(doc.segments.segments)
    for i in action.indices:
        segments[i] = {**segments[i], **action.patch}
    return doc.with_(segments=doc.segments.with_segments(tuple(segments)))


def split_segments(doc: Document, action: SplitSegments) -> Document:
    """SplitSegment.tsx: per index, insert the arithmetic midpoint vertex
    ``((lon1+lon2)/2, (lat1+lat2)/2)``, replace the original row in place
    with a copy ending at the midpoint (name + ``_a``) and append the second
    half starting at the midpoint (name + ``_b``) at the array end.

    Lookups use the ORIGINAL rows, so a repeated index re-splits the
    original segment exactly as the TS does.
    """
    if not action.indices:
        return doc
    graph = doc.segments
    original = graph.segments
    segments = list(original)
    for index in action.indices:
        old = original[index]
        lon1, lat1 = graph.vertices[old["start"]]
        lon2, lat2 = graph.vertices[old["end"]]
        graph, mid = graph.get_or_insert((lon1 + lon2) / 2, (lat1 + lat2) / 2)
        segments[index] = {**old, "end": mid, "name": f"{old['name']}_a"}
        segments.append({**old, "start": mid, "name": f"{old['name']}_b"})
    return doc.with_(segments=graph.with_segments(tuple(segments)))


def merge_vertices(doc: Document, action: MergeVertices) -> Document:
    """MergeVertices.tsx: delegate to the graph (self-merge is a no-op)."""
    graph = doc.segments.merge_vertices(action.keep, action.remove)
    return doc if graph is doc.segments else doc.with_(segments=graph)


def move_vertex(doc: Document, action: MoveVertex) -> Document:
    """MoveVertex.tsx: delegate to the graph (auto-merges on landing key)."""
    graph = doc.segments.move_vertex(action.vertex_id, action.lon, action.lat)
    return doc if graph is doc.segments else doc.with_(segments=graph)


def extrude_segment(doc: Document, action: ExtrudeSegment) -> Document:
    """ExtrudeSegment.tsx: new default segment from an existing vertex to a
    (possibly new) target vertex."""
    if action.vertex_id not in doc.segments.vertices:
        return doc
    graph, end = doc.segments.get_or_insert(*action.target)
    seg = {**_default_segment_row(), "start": action.vertex_id, "end": end}
    return doc.with_(segments=graph.with_segments((*graph.segments, seg)))


def bridge_vertices(doc: Document, action: BridgeVertices) -> Document:
    """BridgeVertices.tsx: new default segment between two EXISTING vertex
    ids — no new vertices; ``a == b`` or a missing id is a no-op."""
    vertices = doc.segments.vertices
    if action.a == action.b or action.a not in vertices or action.b not in vertices:
        return doc
    seg = {**_default_segment_row(), "start": action.a, "end": action.b}
    graph = doc.segments.with_segments((*doc.segments.segments, seg))
    return doc.with_(segments=graph)


def load_segments(doc: Document, action: LoadSegments) -> Document:
    """LoadNewSegmentData.tsx: replace the whole slice."""
    return doc.with_(segments=action.graph)
