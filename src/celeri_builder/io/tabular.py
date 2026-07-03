"""Lossless CSV layer — port of celeri_ui ``CsvUtils.ts`` with intentional fixes.

Read side (``parse``): lines split tolerating CRLF, blank lines skipped,
cells split on comma, trimmed, surrounding double quotes stripped then
trimmed again. Cells are coerced to ``int``/``float`` only when the
coercion is lossless, so identifiers like ``"007"`` survive (celeri_ui's
``parseFloat`` would mangle them). Empty cells stay ``""`` — callers apply
column defaults. A trailing empty header (from a trailing comma) is
preserved as an ``""`` column in both ``columns`` and every row.

Write side (``stringify``): numbers in columns whose NAME contains ``lon``
or ``lat`` are formatted with exactly 6 decimals (celeri_ui
``key.includes('lon')`` parity — so ``euler_lon_sig`` counts); other ints
as ``str(int)``, other floats as ``repr(float)``; strings containing
whitespace or a comma are double-quoted (trimmed). Intentional differences
from celeri_ui: output ends with a trailing newline, and comma-bearing
strings are quoted too.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

Cell = int | float | str
Row = dict[str, Cell]

_INT_RE = re.compile(r"^-?[0-9]+$")
_NEEDS_QUOTE_RE = re.compile(r"[\s,]")


@dataclass
class Table:
    """Parsed CSV: header order + one dict per data row."""

    columns: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)


def _clean(cell: str) -> str:
    cell = cell.strip()
    if len(cell) >= 2 and cell.startswith('"') and cell.endswith('"'):
        cell = cell[1:-1].strip()
    return cell


def _coerce(cell: str) -> Cell:
    if cell == "":
        return ""
    if _INT_RE.fullmatch(cell):
        value = int(cell)
        # Lossless only: "007" / "-0" are identifiers, not numbers.
        return value if str(value) == cell else cell
    if "_" in cell:
        # float() tolerates "1_0"; underscore cells are identifiers.
        return cell
    try:
        number = float(cell)
    except ValueError:
        return cell
    # float() accepts "inf"/"nan" spellings that must stay strings.
    return number if math.isfinite(number) else cell


def read_table(text: str) -> Table:
    """Parse CSV text into a :class:`Table` (see module docstring)."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    lines = [line for line in lines if line.strip() != ""]
    if not lines:
        return Table()
    columns = [header.strip() for header in lines[0].split(",")]
    rows: list[Row] = []
    for line in lines[1:]:
        cells = [_clean(cell) for cell in line.split(",")]
        row: Row = {}
        for index, column in enumerate(columns):
            raw = cells[index] if index < len(cells) else ""
            row[column] = _coerce(raw)
        rows.append(row)
    return Table(columns=columns, rows=rows)


def _format_cell(value: Cell, column: str) -> str:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int | float):
        if "lon" in column or "lat" in column:
            return f"{value:.6f}"
        if isinstance(value, int):
            return str(value)
        return repr(value)
    text = str(value)
    if _NEEDS_QUOTE_RE.search(text):
        return f'"{text.strip()}"'
    return text


def write_table(table: Table) -> str:
    """Serialize a :class:`Table`; ends with a trailing newline."""
    if not table.columns and not table.rows:
        return ""
    lines = [",".join(table.columns)]
    lines.extend(
        ",".join(_format_cell(row.get(column, ""), column) for column in table.columns)
        for row in table.rows
    )
    return "\n".join(lines) + "\n"


def canonical_table(rows: Sequence[Row], canonical_fields: Sequence[str]) -> Table:
    """Columns = canonical fields first, then any other row keys in
    first-seen order; a trailing empty-string column (trailing-comma file)
    is kept and kept LAST."""
    columns = list(canonical_fields)
    seen = set(columns)
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    if "" in seen and columns and columns[-1] != "":
        columns.remove("")
        columns.append("")
    return Table(columns=columns, rows=list(rows))


def fill_rows(
    table: Table,
    known_fields: Sequence[str],
    default: Callable[[str], Cell],
) -> list[Row]:
    """celeri_ui read fill policy (``row[field] || default``): every known
    field present, missing or EMPTY known cells replaced by the field
    default; unknown columns kept verbatim (including a trailing
    empty-string column)."""
    known = list(known_fields)
    known_set = set(known)
    rows: list[Row] = []
    for raw in table.rows:
        row: Row = {}
        for name in known:
            value = raw.get(name, "")
            row[name] = default(name) if value == "" else value
        for key, value in raw.items():
            if key not in known_set:
                row[key] = value
        rows.append(row)
    return rows
