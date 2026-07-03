"""Plain-JSON layer descriptors for the celeri-deck widget.

Port of fennil ``app/deck/primitives.py`` with pydeck removed: each helper
returns a list of descriptor dicts that the celeri-deck client turns into
deck.gl layers. Descriptor contract (see widgets/module/serve/celeri_deck.js):

- ``type`` is the deck.gl layer class name, ``id`` the layer id, ``data``
  a list of plain row dicts; every other key passes through as a prop.
- Props starting with ``get`` whose value is ``"@field"`` (or a list of
  ``"@field"`` strings) become per-row accessors on the client.

Antimeridian twins: fennil always emitted a second, -360°-shifted copy of
every layer so features drawn past lon 180 stay visible on the western
(-180..0) side of the map. Here the twin — same descriptor with the id
suffixed ``"__shift"`` and every longitude shifted by -360 — is emitted
ONLY when some longitude in the data exceeds 180, since layers fully inside
0..180 render identically on both sides and the copy would double the
payload for nothing. The client reports events against the base id.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

SHIFT_SUFFIX = "__shift"
SHIFT_LON = -360.0
ANTIMERIDIAN_LON = 180.0

# Standard row keys used across builders.
LINE_LON_KEYS = ("slon", "tlon")
SCATTER_LON_KEYS = ("lon",)


def _descriptor(
    layer_type: str,
    layer_id: str,
    rows: list[dict],
    defaults: dict,
    props: dict | None,
) -> dict:
    desc = {"type": layer_type, "id": layer_id, "data": rows}
    desc.update(defaults)
    if props:
        desc.update(props)
    return desc


def _needs_twin_fields(rows: Iterable[dict], lon_keys: Sequence[str]) -> bool:
    return any(row[key] > ANTIMERIDIAN_LON for row in rows for key in lon_keys)


def _shift_fields(rows: Iterable[dict], lon_keys: Sequence[str]) -> list[dict]:
    return [{**row, **{key: row[key] + SHIFT_LON for key in lon_keys}} for row in rows]


def _needs_twin_coords(rows: Iterable[dict], coords_key: str) -> bool:
    return any(point[0] > ANTIMERIDIAN_LON for row in rows for point in row[coords_key])


def _shift_coords(rows: Iterable[dict], coords_key: str) -> list[dict]:
    return [
        {
            **row,
            coords_key: [[point[0] + SHIFT_LON, point[1]] for point in row[coords_key]],
        }
        for row in rows
    ]


def _with_twin(base: dict, needs_twin: bool, shifted_rows) -> list[dict]:
    if not needs_twin:
        return [base]
    return [base, {**base, "id": base["id"] + SHIFT_SUFFIX, "data": shifted_rows()}]


def line_descriptors(
    layer_id: str, rows: list[dict], props: dict | None = None
) -> list[dict]:
    """LineLayer descriptor(s) for rows with ``slon/slat/tlon/tlat``."""
    base = _descriptor(
        "LineLayer",
        layer_id,
        rows,
        {
            "getSourcePosition": ["@slon", "@slat"],
            "getTargetPosition": ["@tlon", "@tlat"],
        },
        props,
    )
    return _with_twin(
        base,
        _needs_twin_fields(rows, LINE_LON_KEYS),
        lambda: _shift_fields(rows, LINE_LON_KEYS),
    )


def scatter_descriptors(
    layer_id: str, rows: list[dict], props: dict | None = None
) -> list[dict]:
    """ScatterplotLayer descriptor(s) for rows with ``lon/lat``."""
    base = _descriptor(
        "ScatterplotLayer",
        layer_id,
        rows,
        {"getPosition": ["@lon", "@lat"]},
        props,
    )
    return _with_twin(
        base,
        _needs_twin_fields(rows, SCATTER_LON_KEYS),
        lambda: _shift_fields(rows, SCATTER_LON_KEYS),
    )


def path_descriptors(
    layer_id: str, rows: list[dict], props: dict | None = None
) -> list[dict]:
    """PathLayer descriptor(s) for rows with ``path`` = [[lon, lat], ...]."""
    base = _descriptor("PathLayer", layer_id, rows, {"getPath": "@path"}, props)
    return _with_twin(
        base,
        _needs_twin_coords(rows, "path"),
        lambda: _shift_coords(rows, "path"),
    )


def polygon_descriptors(
    layer_id: str, rows: list[dict], props: dict | None = None
) -> list[dict]:
    """PolygonLayer descriptor(s) for rows with ``polygon`` = [[lon, lat], ...]."""
    base = _descriptor(
        "PolygonLayer", layer_id, rows, {"getPolygon": "@polygon"}, props
    )
    return _with_twin(
        base,
        _needs_twin_coords(rows, "polygon"),
        lambda: _shift_coords(rows, "polygon"),
    )
