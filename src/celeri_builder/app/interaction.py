"""MapController: the (event x edit_mode x selection_mode) dispatch table.

Faithful port of celeri_ui's selection routing:

- ``select_dispatch`` is the pure port of ``SelectionModeSelector``
  (src/Selectors/SelectionMode.ts): 'normal'/'lasso' selects replace the
  single-kind selection; 'override' routes picks of the armed kind to a
  callback; 'mapClick' ignores entity picks and delivers raw coordinates.
- ``MapController`` receives celeri-deck widget events and applies the
  keyboard/click behavior of celeri_ui App.tsx:307-440 through the frozen
  app-method contract (``app.select`` etc.). Coordinates are normalized to
  the 0-360 longitude convention on receipt.

M2 scope is SELECTION ONLY, but the table is shaped so M3/M4 slot in:
creation flows arm 'mapClick', vertex merge/bridge arm 'override' (see
``arm``), drag handlers (keyed by ``edit_mode``) will sit beside the click
table, and ``close_lasso`` is the M4 point-in-polygon hook.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celeri_builder.deck.primitives import SHIFT_SUFFIX
from celeri_builder.model.vertex_graph import normalize_lon

#: Pickable base layer id -> entity kind (celeri_ui Setup*Sources click map).
LAYER_KINDS: dict[str, str] = {
    "segments_hit": "segment",
    "vertices": "vertex",
    "blocks": "block",
    "velocities": "velocity",
}

#: Selection modes that update the selection on a select call.
SELECT_MODES = ("normal", "lasso")

#: Selection modes armed with a callback via :meth:`MapController.arm`.
ARM_MODES = ("mapClick", "override")

#: Enter closes a lasso only when the polygon has >2 points (App.tsx:320).
LASSO_CLOSE_MIN_POINTS = 3

LonLat = list[float]


def select_dispatch(
    mode: str,
    kind: str,
    indices: Any,
    current: dict,
    additive: bool = False,
) -> dict:
    """Pure port of SelectionModeSelector (SelectionMode.ts:64-85).

    Returns the new selection dict for a ``select(kind, indices)`` call under
    the given selection mode. The selection is single-kind, so selecting one
    kind implicitly clears the others (celeri_ui calls every other setter
    with ``[]``). ``additive`` (shift-click, a sanctioned M2 extension —
    celeri_ui has no shift-click) unions with the current same-kind
    selection. 'override' and 'mapClick' never change the selection here;
    their armed callbacks are invoked by :class:`MapController` instead.
    """
    if mode in SELECT_MODES:
        ids = list(indices)
        if additive and current.get("kind") == kind:
            previous = list(current.get("ids") or [])
            ids = previous + [i for i in ids if i not in previous]
        return {"kind": kind, "ids": ids}
    return {"kind": current.get("kind"), "ids": list(current.get("ids") or [])}


class MapController:
    """Routes celeri-deck events by ``state.selection_mode`` (x edit_mode).

    ``app`` follows the CeleriBuilderApp contract: ``app.state`` (plain
    key access + optional ``flush()``), ``app.doc`` (Document), and
    ``app.select(kind, ids, additive=False)``.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._armed: dict | None = None
        self._click_table: dict[str, Callable[[dict], None]] = {
            "normal": self._click_normal,
            "lasso": self._click_lasso,
            "mapClick": self._click_armed_map_click,
            "override": self._click_armed_override,
        }
        # M3 slots in here: per-edit_mode drag tables
        # (handle_dragstart/drag/dragend -> MoveVertex/Block/Velocity), the
        # segment two-click + block/velocity one-click creation flows via
        # arm("mapClick", ...), and merge/bridge/extrude via arm("override"/
        # "mapClick", ...).

    # -- introspection ------------------------------------------------------

    @property
    def armed(self) -> dict | None:
        """Armed ``{mode, payload, callback}`` record (mode banner reads it)."""
        return self._armed

    # -- widget event entry points -------------------------------------------

    def handle_click(self, event: dict) -> None:
        """Dispatch a celeri-deck click event by the current selection mode."""
        handler = self._click_table.get(self.app.state.selection_mode)
        if handler is not None:
            handler(event or {})

    def handle_key(self, event: dict) -> None:
        """App.tsx:312-369 keyboard behavior (Escape / Enter)."""
        key = (event or {}).get("key")
        if key == "Escape":
            self.cancel()
        elif key == "Enter" and self.app.state.selection_mode == "lasso":
            points = list(self.app.state.lasso_points or [])
            if len(points) >= LASSO_CLOSE_MIN_POINTS:
                self.close_lasso(points)
            self.cancel()

    # -- mode arming (creation / merge / bridge flows land in M3) -------------

    def arm(self, mode: str, payload: dict | None, callback: Callable) -> None:
        """Arm a 'mapClick' or 'override' flow.

        ``payload`` carries the banner metadata (``label``/``subtitle``,
        celeri_ui SelectionModeDetails) plus, for 'override', the entity
        ``kind`` the callback accepts. 'mapClick' callbacks receive a
        ``[lon, lat]`` coordinate; 'override' callbacks receive a list of
        picked ids (celeri_ui parity).
        """
        if mode not in ARM_MODES:
            msg = f"cannot arm selection mode {mode!r}"
            raise ValueError(msg)
        self._armed = {
            "mode": mode,
            "payload": dict(payload or {}),
            "callback": callback,
        }
        self._set_state(selection_mode=mode)

    def cancel(self) -> None:
        """Escape: back to 'normal', drop the lasso polygon + armed callback."""
        self._armed = None
        self._set_state(selection_mode="normal", lasso_points=[])

    def close_lasso(self, polygon: list[LonLat]) -> None:
        """Enter on a >2-point lasso polygon.

        TODO(M4): point-in-polygon over the active edit mode's candidates
        (block interiors / velocity stations / vertices / segment MIDPOINTS,
        App.tsx:320-367) then select the hits via ``app.select``.
        """

    # -- per-mode click handlers ----------------------------------------------

    def _click_normal(self, event: dict) -> None:
        kind, ident = self._pick(event)
        if kind is None or ident is None:
            return  # background click: no-op (celeri_ui parity)
        self.app.select(kind, [ident], additive=bool(event.get("shiftKey")))
        # SelectionMode.ts:66-75: selecting also switches the inspector tab.
        self._set_state(inspector_tab=kind, inspector_open=True)

    def _click_lasso(self, event: dict) -> None:
        # celeri_ui App.tsx:427-435: every click (picked or not) appends its
        # coordinate to the in-progress polygon.
        coordinate = self._coordinate(event)
        if coordinate is None:
            return
        points = [*(self.app.state.lasso_points or []), coordinate]
        self._set_state(lasso_points=points)

    def _click_armed_map_click(self, event: dict) -> None:
        armed = self._armed
        if armed is None or armed["mode"] != "mapClick":
            return
        # mapClick ignores entity picks: any click delivers coordinates
        # (App.tsx:421-426 + SelectionMode.spec.ts "ignores select calls").
        coordinate = self._coordinate(event)
        if coordinate is None:
            return
        armed["callback"](coordinate)

    def _click_armed_override(self, event: dict) -> None:
        armed = self._armed
        if armed is None or armed["mode"] != "override":
            return
        kind, ident = self._pick(event)
        if kind is None or ident is None:
            return
        # SelectionMode.ts:77-83: only the armed kind reaches the callback.
        if kind == armed["payload"].get("kind"):
            armed["callback"]([ident])

    # -- event decoding helpers ----------------------------------------------

    def _coordinate(self, event: dict) -> LonLat | None:
        coordinate = event.get("coordinate")
        if not coordinate:
            return None
        return [normalize_lon(float(coordinate[0])), float(coordinate[1])]

    def _pick(self, event: dict) -> tuple[str | None, int | None]:
        """(kind, id) of an entity pick, or (None, None) for background."""
        if not event.get("picked"):
            return None, None
        layer_id = str(event.get("layerId") or "").removesuffix(SHIFT_SUFFIX)
        kind = LAYER_KINDS.get(layer_id)
        index = event.get("index")
        if kind is None or index is None or index < 0:
            return None, None
        if kind == "vertex":
            return kind, self._vertex_id_at_row(int(index))
        return kind, int(index)

    def _vertex_id_at_row(self, row: int) -> int | None:
        """Vertex layer rows follow dict insertion order; ids are sparse."""
        ids = list(self.app.doc.segments.vertices)
        if 0 <= row < len(ids):
            return ids[row]
        return None

    def _set_state(self, **values: Any) -> None:
        state = self.app.state
        for key, value in values.items():
            setattr(state, key, value)
        flush = getattr(state, "flush", None)
        if callable(flush):
            flush()
