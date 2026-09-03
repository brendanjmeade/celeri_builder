"""Block CSV <-> row dicts (ports celeri_ui ``BlockFile.ts``).

Same fill policy as segments against ``BLOCK_FIELDS``; a trailing
empty-string column (trailing-comma file, e.g. japan_block.csv) is kept in
the row dicts so ``canonical_table`` re-emits it.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pandas as pd

from celeri_builder.model.schema import BLOCK_FIELDS, read_default


def read_blocks(text: str) -> tuple[dict, ...]:
    """Read block data from CSV text and return tuple of dicts."""
    block_df = pd.read_csv(io.StringIO(text))

    # Fill missing values with read defaults only for existing columns
    for field in BLOCK_FIELDS:
        if field in block_df.columns:
            block_df[field] = block_df[field].fillna(read_default)

    # Convert to tuple of dicts
    return tuple(block_df.to_dict("records"))


def write_blocks(rows: Sequence[dict]) -> str:
    """Convert block rows to CSV text with canonical column order."""
    block_df = pd.DataFrame(rows)

    # Ensure canonical columns are first in the DataFrame
    canonical_cols = [col for col in BLOCK_FIELDS if col in block_df.columns]
    other_cols = [col for col in block_df.columns if col not in BLOCK_FIELDS]
    block_df = block_df[canonical_cols + other_cols]

    # Convert to CSV text
    return block_df.to_csv(index=False)
