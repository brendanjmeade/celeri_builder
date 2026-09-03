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

import io

import pandas as pd

from celeri_builder.model.schema import SEGMENT_FIELDS
from celeri_builder.model.vertex_graph import SegmentGraph, build_graph


def read_segments(text: str) -> SegmentGraph:
    """Read segment data from CSV text and return a SegmentGraph."""
    # Read CSV into pandas DataFrame using standard library StringIO
    segment_df = pd.read_csv(io.StringIO(text))

    # Fill missing values with read defaults only for existing columns
    for field in SEGMENT_FIELDS:
        if field in segment_df.columns:
            if field == "name":
                segment_df[field] = segment_df[field].fillna("")
            else:
                segment_df[field] = segment_df[field].fillna(0)

    # Convert to list of dicts for build_graph
    rows = segment_df.to_dict("records")
    return build_graph(rows)


def write_segments(graph: SegmentGraph) -> str:
    """Convert SegmentGraph to CSV text with canonical column order."""
    # Get expanded rows from graph
    rows = graph.expand_rows()

    # Create DataFrame with canonical columns first
    segment_df = pd.DataFrame(rows)

    # Ensure canonical columns are first in the DataFrame
    canonical_cols = [col for col in SEGMENT_FIELDS if col in segment_df.columns]
    other_cols = [col for col in segment_df.columns if col not in SEGMENT_FIELDS]
    segment_df = segment_df[canonical_cols + other_cols]

    # Convert to CSV text
    return segment_df.to_csv(index=False)
