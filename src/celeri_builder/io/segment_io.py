"""Segment CSV <-> :class:`SegmentGraph` (ports celeri_ui ``SegmentFile.ts``).

Read: every canonical segment field is materialized (missing/empty cells
get the read default — ``0``, or ``""`` for ``name`` — matching celeri_ui's
``row[field] || 0`` which also zeroes empty values); unknown columns are
kept verbatim. The flat rows are then folded into the shared-vertex graph
(``lon1/lat1/lon2/lat2`` become vertex ids).

Write: the graph is re-expanded to flat rows and emitted with the canonical
column order first, unknown columns after.
"""

from __future__ import annotations

from celeri_builder.io.tabular import (
    canonical_table,
    fill_rows,
    read_table,
    write_table,
)
from celeri_builder.model.schema import SEGMENT_FIELDS, read_default
from celeri_builder.model.vertex_graph import SegmentGraph, build_graph


def read_segments(text: str) -> SegmentGraph:
    rows = fill_rows(read_table(text), SEGMENT_FIELDS, read_default)
    return build_graph(rows)


def write_segments(graph: SegmentGraph) -> str:
    return write_table(canonical_table(graph.expand_rows(), SEGMENT_FIELDS))
