"""Tabular utilities (ports celeri_ui ``Table.ts``)."""

from __future__ import annotations

import io
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

# Use the actual field lists instead of the Field type
Field = str  # Define Field as string type since we're using field names


def read_table(text: str) -> list[dict[str, Any]]:
    """Read CSV text into a list of dicts."""
    table_df = pd.read_csv(io.StringIO(text))
    return table_df.to_dict("records")


def write_table(rows: Iterable[Mapping[str, Any]]) -> str:
    """Write rows to CSV text."""
    table_df = pd.DataFrame(rows)
    return table_df.to_csv(index=False)


def fill_rows(
    rows: Iterable[Mapping[str, Any]],
    fields: Iterable[Field],
    default: Any,
) -> list[dict[str, Any]]:
    """Fill missing fields with default."""
    table_df = pd.DataFrame(rows)
    for field in fields:
        if field in table_df.columns:
            table_df[field] = table_df[field].fillna(default)
    return table_df.to_dict("records")


def canonical_table(
    rows: Iterable[Mapping[str, Any]],
    fields: Iterable[Field],
) -> list[dict[str, Any]]:
    """Reorder rows so canonical fields come first."""
    table_df = pd.DataFrame(rows)
    canonical_cols = [col for col in fields if col in table_df.columns]
    other_cols = [col for col in table_df.columns if col not in fields]
    table_df = table_df[canonical_cols + other_cols]
    return table_df.to_dict("records")
