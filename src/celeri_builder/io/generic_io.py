"""Generic CSV overlays (celeri_ui GenericSegmentFile).

Raw rows with every column kept verbatim; the user later maps position
columns (start/end lon/lat keys) in the UI. Generic collections are
never written back to disk.
"""

from __future__ import annotations

from celeri_builder.io.tabular import read_table
from celeri_builder.model.document import GenericCollection


def read_generic(text: str, name: str) -> GenericCollection:
    """Parse an arbitrary CSV into a :class:`GenericCollection`.

    Position keys start empty — mapping them is a UI action.
    """
    table = read_table(text)
    if not table.columns:
        msg = f"generic CSV {name!r} has no header row"
        raise ValueError(msg)
    return GenericCollection(
        rows=tuple(dict(row) for row in table.rows),
        columns=tuple(table.columns),
    )
