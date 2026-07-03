"""Station (velocity) CSV round-trip invariants (japan + wna examples)."""

from __future__ import annotations

import pytest

from celeri_builder.io.tabular import read_table
from celeri_builder.io.velocity_io import read_velocities, write_velocities
from celeri_builder.model.schema import VELOCITY_FIELDS

# The example files are 10-column + trailing comma; canonical is 15.
MISSING_IN_EXAMPLES = (
    "corr",
    "other1",
    "east_adjust",
    "north_adjust",
    "up_adjust",
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
    text = raw_text("station", region)
    rows1 = read_velocities(text)
    rows2 = read_velocities(write_velocities(rows1))
    _assert_rows_equal(rows1, rows2)


def test_second_generation_byte_idempotent(raw_text, region):
    text = raw_text("station", region)
    gen1 = write_velocities(read_velocities(text))
    gen2 = write_velocities(read_velocities(gen1))
    assert gen2 == gen1
    assert gen1.endswith("\n")


def test_canonical_order_and_gained_columns(raw_text, region):
    text = raw_text("station", region)
    original_cols = read_table(text).columns
    for col in MISSING_IN_EXAMPLES:
        assert col not in original_cols
    out = write_velocities(read_velocities(text))
    table = read_table(out)
    assert table.columns[: len(VELOCITY_FIELDS)] == list(VELOCITY_FIELDS)
    # original trailing "" column is kept, canonical gains the 5 new fields
    assert len(table.columns) == len(original_cols) + len(MISSING_IN_EXAMPLES)
    for row in table.rows:
        for col in MISSING_IN_EXAMPLES:
            assert row[col] == 0


def test_trailing_empty_column_kept(raw_text, region):
    # both japan_station.csv and wna_station.csv end every line with a comma
    out = write_velocities(read_velocities(raw_text("station", region)))
    lines = [line for line in out.split("\n") if line]
    assert all(line.endswith(",") for line in lines)
    assert lines[0].split(",")[-1] == ""
