"""Shared-vertex graph for fault segments.

Ports celeri_ui's vertex model (src/State/Segment/Vertex.ts) exactly:

- Longitudes are normalized to 0-360 (``lon < 0`` gains 360) before keying.
- Vertex identity is the FLOORED micro-degree cell
  ``(floor(lon * 1e6), floor(lat * 1e6))`` — floor, not round or trunc,
  which differs for negative coordinates.
- Inserting a coordinate whose cell is already occupied reuses the existing
  vertex id; the first occurrence's exact coordinates win (load-time snap).
- Ids are sequential integers in first-seen order.

``SegmentGraph`` is immutable; every operation returns a new graph that
structurally shares untouched containers (the undo stack relies on this).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

VERTEX_PRECISION_MULTIPLIER = 1_000_000

VertexKey = tuple[int, int]
LonLat = tuple[float, float]


def normalize_lon(lon: float) -> float:
    """celeri convention: western-hemisphere longitudes are stored 0-360."""
    return lon + 360.0 if lon < 0 else lon


def vertex_key(lon: float, lat: float) -> VertexKey:
    return (
        math.floor(lon * VERTEX_PRECISION_MULTIPLIER),
        math.floor(lat * VERTEX_PRECISION_MULTIPLIER),
    )


@dataclass(frozen=True)
class SegmentGraph:
    """Immutable segment/vertex graph.

    ``segments`` rows are plain dicts holding every known/unknown segment
    column EXCEPT lon1/lat1/lon2/lat2, which are represented by the vertex
    ids ``start`` and ``end`` and re-expanded on save/render.
    """

    vertices: dict[int, LonLat] = field(default_factory=dict)
    vertex_index: dict[VertexKey, int] = field(default_factory=dict)
    next_id: int = 0
    segments: tuple[dict, ...] = ()

    # -- queries ---------------------------------------------------------

    def vertex_lonlat(self, vertex_id: int) -> LonLat:
        return self.vertices[vertex_id]

    def segment_endpoints(self, seg: dict) -> tuple[LonLat, LonLat]:
        return self.vertices[seg["start"]], self.vertices[seg["end"]]

    def expand_rows(self) -> list[dict]:
        """Re-expand segments to flat rows with lon1/lat1/lon2/lat2."""
        rows = []
        for seg in self.segments:
            (lon1, lat1), (lon2, lat2) = self.segment_endpoints(seg)
            row = {k: v for k, v in seg.items() if k not in ("start", "end")}
            row["lon1"] = lon1
            row["lat1"] = lat1
            row["lon2"] = lon2
            row["lat2"] = lat2
            rows.append(row)
        return rows

    def orphaned(self, vertex_id: int, ignoring: tuple[int, ...] = ()) -> bool:
        """True when no segment (outside ``ignoring`` indices) uses the vertex."""
        return not any(
            (seg["start"] == vertex_id or seg["end"] == vertex_id)
            for i, seg in enumerate(self.segments)
            if i not in ignoring
        )

    # -- construction ------------------------------------------------------

    def get_or_insert(self, lon: float, lat: float) -> tuple[SegmentGraph, int]:
        """Return (graph, vertex id) for the coordinate, inserting if new.

        First-occurrence coordinates win: a later coordinate landing in an
        occupied cell adopts the existing vertex unchanged.
        """
        lon = normalize_lon(lon)
        key = vertex_key(lon, lat)
        existing = self.vertex_index.get(key)
        if existing is not None:
            return self, existing
        vid = self.next_id
        graph = replace(
            self,
            vertices={**self.vertices, vid: (lon, lat)},
            vertex_index={**self.vertex_index, key: vid},
            next_id=vid + 1,
        )
        return graph, vid

    def with_segments(self, segments: tuple[dict, ...]) -> SegmentGraph:
        return replace(self, segments=segments)

    # -- mutation helpers (used by reducers; all return new graphs) --------

    def try_remove_vertex(self, vertex_id: int) -> SegmentGraph:
        """Drop the vertex if no segment references it (celeri_ui GC)."""
        if vertex_id not in self.vertices or not self.orphaned(vertex_id):
            return self
        lon, lat = self.vertices[vertex_id]
        vertices = dict(self.vertices)
        del vertices[vertex_id]
        vertex_index = dict(self.vertex_index)
        vertex_index.pop(vertex_key(lon, lat), None)
        return replace(self, vertices=vertices, vertex_index=vertex_index)

    def move_vertex(self, vertex_id: int, lon: float, lat: float) -> SegmentGraph:
        """Move a vertex; auto-merge when landing in an occupied cell.

        Ports celeri_ui MoveVertex.tsx: if the destination cell maps to
        another vertex, all segments pointing at that OTHER vertex are
        repointed to ``vertex_id`` and the other vertex is deleted.
        """
        if vertex_id not in self.vertices:
            return self
        lon = normalize_lon(lon)
        old_lon, old_lat = self.vertices[vertex_id]
        new_key = vertex_key(lon, lat)
        old_key = vertex_key(old_lon, old_lat)

        vertices = dict(self.vertices)
        vertex_index = dict(self.vertex_index)
        segments = self.segments

        occupant = vertex_index.get(new_key)
        if occupant is not None and occupant != vertex_id:
            segments = tuple(
                {
                    **seg,
                    "start": vertex_id if seg["start"] == occupant else seg["start"],
                    "end": vertex_id if seg["end"] == occupant else seg["end"],
                }
                for seg in segments
            )
            del vertices[occupant]

        vertices[vertex_id] = (lon, lat)
        if old_key != new_key:
            vertex_index.pop(old_key, None)
        vertex_index[new_key] = vertex_id
        return replace(
            self, vertices=vertices, vertex_index=vertex_index, segments=segments
        )

    def merge_vertices(self, keep: int, remove: int) -> SegmentGraph:
        """Repoint segments from ``remove`` to ``keep``; drop zero-length
        segments; delete ``remove``. No-op when ids match (celeri_ui
        MergeVertices.tsx)."""
        if keep == remove or keep not in self.vertices or remove not in self.vertices:
            return self
        repointed = tuple(
            {
                **seg,
                "start": keep if seg["start"] == remove else seg["start"],
                "end": keep if seg["end"] == remove else seg["end"],
            }
            for seg in self.segments
        )
        segments = tuple(s for s in repointed if s["start"] != s["end"])
        lon, lat = self.vertices[remove]
        vertices = dict(self.vertices)
        del vertices[remove]
        vertex_index = dict(self.vertex_index)
        vertex_index.pop(vertex_key(lon, lat), None)
        return replace(
            self, vertices=vertices, vertex_index=vertex_index, segments=segments
        )


def build_graph(rows: list[dict]) -> SegmentGraph:
    """Build a graph from flat parsed segment rows (mutable fast path).

    Same semantics as repeated ``get_or_insert`` — cell dedup, first
    occurrence wins, sequential ids — without per-row copying.
    """
    vertices: dict[int, LonLat] = {}
    vertex_index: dict[VertexKey, int] = {}
    next_id = 0
    segments: list[dict] = []

    def insert(lon: float, lat: float) -> int:
        nonlocal next_id
        lon = normalize_lon(lon)
        key = vertex_key(lon, lat)
        existing = vertex_index.get(key)
        if existing is not None:
            return existing
        vid = next_id
        vertices[vid] = (lon, lat)
        vertex_index[key] = vid
        next_id += 1
        return vid

    for row in rows:
        seg = {
            k: v for k, v in row.items() if k not in ("lon1", "lat1", "lon2", "lat2")
        }
        seg["start"] = insert(row["lon1"], row["lat1"])
        seg["end"] = insert(row["lon2"], row["lat2"])
        segments.append(seg)

    return SegmentGraph(
        vertices=vertices,
        vertex_index=vertex_index,
        next_id=next_id,
        segments=tuple(segments),
    )
