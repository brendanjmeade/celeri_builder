"""Block CSV round-trip invariants (japan + wna examples)."""

from __future__ import annotations

import pytest

from celeri_builder.io.block_io import read_blocks, write_blocks
from celeri_builder.io.tabular import read_table
from celeri_builder.model.schema import BLOCK_FIELDS

# The example files are 13-column (+ trailing comma in japan); canonical is 20.
MISSING_IN_EXAMPLES = (
    "other1",
    "other2",
    "other3",
    "other4",
    "other5",
    "other6",
    "apriori_flag",
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
    text = raw_text("block", region)
    rows1 = read_blocks(text)
    rows2 = read_blocks(write_blocks(rows1))
    _assert_rows_equal(rows1, rows2)


def test_second_generation_byte_idempotent(raw_text, region):
    text = raw_text("block", region)
    gen1 = write_blocks(read_blocks(text))
    gen2 = write_blocks(read_blocks(gen1))
    assert gen2 == gen1
    assert gen1.endswith("\n")


def test_canonical_order_and_gained_columns(raw_text, region):
    text = raw_text("block", region)
    original_cols = read_table(text).columns
    for col in MISSING_IN_EXAMPLES:
        assert col not in original_cols
    out = write_blocks(read_blocks(text))
    table = read_table(out)
    assert table.columns[: len(BLOCK_FIELDS)] == list(BLOCK_FIELDS)
    assert len(table.columns) == len(original_cols) + len(MISSING_IN_EXAMPLES)
    for row in table.rows:
        for col in MISSING_IN_EXAMPLES:
            assert row[col] == 0


def test_japan_trailing_empty_column_kept(raw_text):
    out = write_blocks(read_blocks(raw_text("block", "japan")))
    lines = [line for line in out.split("\n") if line]
    assert all(line.endswith(",") for line in lines)
    assert lines[0].split(",")[-1] == ""


def test_wna_gains_no_trailing_empty_column(raw_text):
    out = write_blocks(read_blocks(raw_text("block", "wna")))
    lines = [line for line in out.split("\n") if line]
    assert not any(line.endswith(",") for line in lines)
    assert lines[0].split(",")[-1] == BLOCK_FIELDS[-1]
