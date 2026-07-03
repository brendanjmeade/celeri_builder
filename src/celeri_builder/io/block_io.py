"""Block CSV <-> row dicts (ports celeri_ui ``BlockFile.ts``).

Same fill policy as segments against ``BLOCK_FIELDS``; a trailing
empty-string column (trailing-comma file, e.g. japan_block.csv) is kept in
the row dicts so ``canonical_table`` re-emits it.
"""

from __future__ import annotations

from collections.abc import Sequence

from celeri_builder.io.tabular import (
    Row,
    canonical_table,
    fill_rows,
    read_table,
    write_table,
)
from celeri_builder.model.schema import BLOCK_FIELDS, read_default


def read_blocks(text: str) -> tuple[Row, ...]:
    return tuple(fill_rows(read_table(text), BLOCK_FIELDS, read_default))


def write_blocks(rows: Sequence[Row]) -> str:
    return write_table(canonical_table(list(rows), BLOCK_FIELDS))
