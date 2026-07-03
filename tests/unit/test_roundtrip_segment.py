"""Segment CSV round-trip invariants (japan + wna examples)."""

from __future__ import annotations

import pytest

from celeri_builder.io.segment_io import read_segments, write_segments
from celeri_builder.io.tabular import read_table
from celeri_builder.model.schema import SEGMENT_FIELDS
from celeri_builder.model.vertex_graph import normalize_lon

# The example files are 29-column; canonical is 33.
MISSING_IN_EXAMPLES = (
    "ss_reg_flag",
    "ds_reg_flag",
    "ts_reg_flag",
    "slip_rate_bound_sigma",
)


def _assert_rows_equal(rows1, rows2):
    assert len(rows1) == len(rows2)
    for r1, r2 in zip(rows1, rows2, strict=True):
        assert set(r1) == set(r2)
        for key, v1 in r1.items():
            v2 = r2[key]
            if isinstance(v1, int | float) or isinstance(v2, int | float):
                tol = 1e-6 if ("lon" in key or "lat" in key) else 1e-9
                assert float(v2) == pytest.approx(float(v1), abs=tol), key
            else:
                assert v1 == v2, key


def test_semantic_roundtrip(raw_text, region):
    text = raw_text("segment", region)
    g1 = read_segments(text)
    g2 = read_segments(write_segments(g1))
    assert len(g2.segments) == len(g1.segments)
    assert len(g2.vertices) == len(g1.vertices)
    _assert_rows_equal(g1.expand_rows(), g2.expand_rows())


def test_second_generation_byte_idempotent(raw_text, region):
    text = raw_text("segment", region)
    gen1 = write_segments(read_segments(text))
    gen2 = write_segments(read_segments(gen1))
    assert gen2 == gen1
    assert gen1.endswith("\n")


def test_expand_rows_match_file_coordinates(raw_text, region):
    text = raw_text("segment", region)
    table = read_table(text)
    rows = read_segments(text).expand_rows()
    assert len(rows) == len(table.rows)
    for raw, row in zip(table.rows, rows, strict=True):
        for key in ("lon1", "lon2"):
            expected = normalize_lon(float(raw[key]))
            assert row[key] == pytest.approx(expected, abs=1e-6), key
        for key in ("lat1", "lat2"):
            assert row[key] == pytest.approx(float(raw[key]), abs=1e-6), key


def test_canonical_order_and_gained_columns(raw_text, region):
    text = raw_text("segment", region)
    original_cols = read_table(text).columns
    for col in MISSING_IN_EXAMPLES:
        assert col not in original_cols
    out = write_segments(read_segments(text))
    table = read_table(out)
    assert table.columns[: len(SEGMENT_FIELDS)] == list(SEGMENT_FIELDS)
    assert len(table.columns) == len(original_cols) + len(MISSING_IN_EXAMPLES)
    for row in table.rows:
        for col in MISSING_IN_EXAMPLES:
            assert row[col] == 0


def test_japan_numeric_name_2_stable_across_generations(raw_text):
    text = raw_text("segment", "japan")
    graph = read_segments(text)
    assert 2 in [seg["name"] for seg in graph.segments]
    gen1 = write_segments(graph)
    gen2 = write_segments(read_segments(gen1))
    first_data_line = gen1.split("\n")[1]
    assert first_data_line.startswith("2,")
    assert gen2.split("\n")[1] == first_data_line
