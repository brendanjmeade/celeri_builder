"""Block CSV <-> row dicts (ports celeri_ui ``BlockFile.ts``).

Same fill policy as segments against ``BLOCK_FIELDS``; a trailing
empty-string column (trailing-comma file, e.g. japan_block.csv) is kept in
the row dicts so ``canonical_table`` re-emits it.
"""

from __future__ import annotations

import io
import pandas as pd
from collections.abc import Sequence

from celeri_builder.model.schema import BLOCK_FIELDS, read_default

def read_blocks(text: str) -> tuple[dict, ...]:
    """Read block data from CSV text and return tuple of dicts."""
    df = pd.read_csv(io.StringIO(text))

    # Fill missing values with read defaults only for existing columns
    for field in BLOCK_FIELDS:
        if field in df.columns:
            df[field] = df[field].fillna(read_default)

    # Convert to tuple of dicts
    return tuple(df.to_dict('records'))

def write_blocks(rows: Sequence[dict]) -> str:
    """Convert block rows to CSV text with canonical column order."""
    df = pd.DataFrame(rows)

    # Ensure canonical columns are first in the DataFrame
    canonical_cols = [col for col in BLOCK_FIELDS if col in df.columns]
    other_cols = [col for col in df.columns if col not in BLOCK_FIELDS]
    df = df[canonical_cols + other_cols]

    # Convert to CSV text
    return df.to_csv(index=False)
