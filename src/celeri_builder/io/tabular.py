"""Tabular utilities (ports celeri_ui ``Table.ts``)."""

from __future__ import annotations

import io
import pandas as pd
from typing import Any, Iterable, Mapping

# Check what's available in schema module
from celeri_builder.model.schema import SEGMENT_FIELDS, BLOCK_FIELDS, VELOCITY_FIELDS, read_default

# Use the actual field lists instead of the Field type
Field = str  # Define Field as string type since we're using field names

def read_table(text: str) -> list[dict[str, Any]]:
    """Read CSV text into a list of dicts."""
    df = pd.read_csv(io.StringIO(text))
    return df.to_dict('records')

def write_table(rows: Iterable[Mapping[str, Any]]) -> str:
    """Write rows to CSV text."""
    df = pd.DataFrame(rows)
    return df.to_csv(index=False)

def fill_rows(
    rows: Iterable[Mapping[str, Any]],
    fields: Iterable[Field],
    default: Any,
) -> list[dict[str, Any]]:
    """Fill missing fields with default."""
    df = pd.DataFrame(rows)
    for field in fields:
        df[field] = df[field].fillna(default)
    return df.to_dict('records')

def canonical_table(
    rows: Iterable[Mapping[str, Any]],
    fields: Iterable[Field],
) -> list[dict[str, Any]]:
    """Reorder rows so canonical fields come first."""
    df = pd.DataFrame(rows)
    canonical_cols = [col for col in fields if col in df.columns]
    other_cols = [col for col in df.columns if col not in fields]
    df = df[canonical_cols + other_cols]
    return df.to_dict('records')
