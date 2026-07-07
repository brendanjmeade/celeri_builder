"""CeleriBuilderApp: trame application shell.

M2 wiring: the undoable :class:`Store` owns the Document; every mutation
funnels through :meth:`dispatch`; selection lives in plain trame state
(``selection`` / ``selection_fields``); the inspector panels talk to the
app-method contract implemented here (``select`` / ``edit_selection`` /
``edit_command`` / ``open_kind`` / ``save_kind`` / ...); the
:class:`MapController` routes widget clicks/keys by selection mode.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from pathlib import Path
from typing import Any, ClassVar

from trame.app import TrameApp
from trame.ui.vuetify3 import VAppLayout
from trame.widgets import html

from celeri_builder.app import settings
from celeri_builder.app.interaction import MapController, select_dispatch
from celeri_builder.app.ui import (
    edit_mode_panel,
    inspector,
    mode_banner,
    top_bar,
)
from celeri_builder.app.ui.file_explorer import FileExplorer
from celeri_builder.deck import mapbox
from celeri_builder.deck.display import default_display
from celeri_builder.deck.scene import register_all
from celeri_builder.io import project as project_io
from celeri_builder.io.block_io import read_blocks, write_blocks
from celeri_builder.io.command_io import read_command, write_command
from celeri_builder.io.generic_io import read_generic
from celeri_builder.io.mesh_io import read_msh
from celeri_builder.io.segment_io import read_segments, write_segments
from celeri_builder.io.velocity_io import read_velocities, write_velocities
from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.schema import (
    BLOCK_FIELDS,
    SEGMENT_FIELDS,
    SEGMENT_HIDDEN_FIELDS,
    VELOCITY_FIELDS,
)
from celeri_builder.model.store import Store
from celeri_builder.widgets import DeckEditor

# Bottom-to-top z-order of scene layer groups (celeri_ui layering).
# 'overlay' (selection highlight + lasso polygon) always draws on top.
GROUPS = (
    "graticule",
    "meshes",
    "generic",
    "dip_projection",
    "segments",
    "blocks",
    "velocities",
    "vertices",
    "labels",
    "overlay",
)

DEFAULT_VIEW = {"longitude": 180.0, "latitude": 30.0, "zoom": 2}
TEST_VIEW = {"longitude": 140.0, "latitude": 37.5, "zoom": 5}

#: selection kind -> inspector tab name (celeri_ui Inspector windows).
KIND_TABS = {
    "segment": "segment",
    "vertex": "vertex",
    "block": "block",
    "velocity": "velocities",
}

#: file/dirty kind -> scene layer groups it invalidates. ``labels`` re-syncs
#: with the entity groups so a plottableKey text follows its entity's edits.
KIND_GROUPS: dict[str, tuple[str, ...]] = {
    "segment": ("segments", "dip_projection", "vertices", "labels", "overlay"),
    "block": ("blocks", "labels", "overlay"),
    "station": ("velocities", "labels", "overlay"),
    "command": (),
    "mesh": ("meshes",),
    "mesh_params": ("meshes",),
    "generic": ("generic",),
}

#: selection kind -> the file kind its edits make dirty.
SELECTION_DIRTY = {
    "segment": "segment",
    "vertex": "segment",
    "block": "block",
    "velocity": "station",
}

#: open_kind file-dialog metadata: kind -> (extension, dialog title).
OPEN_SPECS: dict[str, tuple[str, str]] = {
    "segment": (".csv", "Open segment file"),
    "block": (".csv", "Open block file"),
    "station": (".csv", "Open station (velocity) file"),
    "command": (".json", "Open command file"),
    "mesh": (".msh", "Open mesh file"),
    "mesh_params": (".json", "Open mesh parameters file"),
    "generic": (".csv", "Open generic segments CSV"),
}

#: selection kind -> (canonical field order, fields hidden from the editor).
SELECTION_SCHEMA: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "segment": (SEGMENT_FIELDS, SEGMENT_HIDDEN_FIELDS),
    "block": (BLOCK_FIELDS, ()),
    "velocity": (VELOCITY_FIELDS, ()),
}

#: Active edit mode -> the layer(s) the widget lets the user drag. Segments
#: mode drags the shared vertices layer (celeri_ui SetupDrawnPointSource).
EDIT_MODE_DRAG_LAYERS: dict[str, list[str]] = {
    "vertex": ["vertices"],
    "segment": ["vertices"],
    "block": ["blocks"],
    "velocities": ["velocities"],
}

#: Drag/commit kind -> the file kind its Move* action makes dirty.
MOVE_DIRTY = {"vertex": "segment", "block": "block", "velocity": "station"}

#: New-entity mapClick flows: kind -> the file kind CreateX makes dirty.
CREATE_DIRTY = {"segment": "segment", "block": "block", "velocity": "station"}

VERTEX_OP_HINTS = {
    "merge": "Merge: click the vertex to merge into",
    "bridge": "Bridge: click the vertex to connect to",
    "extrude": "Extrude: click the target location",
}
NEW_ENTITY_HINTS = {
    "segment": "New segment: click the start point",
    "block": "New block: click a location inside the block",
    "velocity": "New velocity: click the station location",
}

#: Numeric property edits commit after 1 s of quiet (celeri_ui parity).
EDIT_DEBOUNCE_S = 1.0
PROBE_FIELD_SAMPLE = 8

_SKIP = object()
_MISSING = object()


def _coerce(value: Any, template: Any) -> Any:
    """Coerce a UI edit to the type of the value it replaces.

    Ports celeri_ui EditableItem's ``typeof`` switch: numeric fields parse
    numbers (``_SKIP`` on unparsable input instead of NaN), everything else
    stays a string. int templates keep integral results as int (dtype
    fidelity on save: write ``1`` not ``1.0``). list/dict templates (command
    ``tri_edge`` etc.) are not editable in M2.
    """
    if isinstance(template, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(template, int | float):
        if value is None or isinstance(value, bool):
            return _SKIP
        if isinstance(value, int | float):
            number = float(value)
        else:
            try:
                number = float(str(value).strip())
            except ValueError:
                return _SKIP
        if isinstance(template, int) and number.is_integer():
            return int(number)
        return number
    if isinstance(template, list | dict):
        return _SKIP
    if isinstance(template, str):
        return str(value)
    return value


class CeleriBuilderApp(TrameApp):
    def __init__(self, server=None, root_dir: Path | None = None):
        super().__init__(server, client_type="vue3")
        self.scene = register_all()

        self.testing = os.environ.get("CELERI_BUILDER_TESTING") == "1"
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.store = Store(Document())
        self.refs: project_io.FileRefs | None = None
        self.controller = MapController(self)
        self._save_task: asyncio.Task | None = None
        self._edit_task: asyncio.Task | None = None
        self._pending_edit: dict | None = None
        self._last_pick: dict | None = None

        state = self.state
        state.trame__title = "celeri_builder"
        # Testing mode uses pristine defaults: persisted settings would leak
        # state between test runs.
        state.display = (
            default_display() if self.testing else settings.load(default_display())
        )
        for group in GROUPS:
            state[f"deck_layers_{group}"] = []
        state.deck_map_style = self._resolve_map_style(
            state.display["map"].get("styleName", "default")
        )
        state.deck_view_state = dict(TEST_VIEW if self.testing else DEFAULT_VIEW)
        state.deck_view_state_rev = 0
        state.deck_cursor_mode = "normal"
        state.folder_label = ""
        state.dirty_kinds = []
        state.can_undo = False
        state.can_redo = False
        state.edit_mode = "vertex"
        state.deck_drag_layers = list(EDIT_MODE_DRAG_LAYERS.get("vertex", []))
        state.selection_mode = "normal"
        state.mode_hint = ""
        state.hover_lonlat = None
        state.selection = {"kind": None, "ids": []}
        state.selection_fields = {}
        state.command_fields = {}
        state.lasso_points = []
        state.inspector_tab = "command"
        state.inspector_open = False
        state.mesh_names = []
        state.generic_collections = []
        state.test_probe = {}

        state.change("lasso_points")(self._on_lasso_points)
        state.change("selection_mode")(self._on_selection_mode)
        # The active edit mode decides which layer the widget lets us drag.
        state.change("edit_mode")(self._on_edit_mode)
        # inspector_tab/inspector_open change client-side (tab-strip JS).
        state.change("inspector_tab", "inspector_open")(self._on_probe_keys)

        if self.server.hot_reload:
            self.server.controller.on_server_reload.add(self._build_ui)
        self._build_ui()

    # -- document / store ------------------------------------------------------

    @property
    def doc(self) -> Document:
        return self.store.doc

    def dispatch(self, action: act.Action, dirty=(), groups=None) -> bool:
        """Store dispatch + dirty marking + layer refresh.

        ``dirty`` are file kinds (segment/block/station/command/...); the
        affected layer groups default to :data:`KIND_GROUPS` for those kinds
        (``groups`` overrides, e.g. Load* actions that are not dirty).
        Returns True when the action changed the document.
        """
        before = self.store.doc
        after = self.store.dispatch(action)
        if after is before:
            self._update_probe()
            return False
        self.mark_dirty(*dirty)
        self._sync_derived()
        self._sanitize_selection()
        self._refresh(self._groups_for(dirty) if groups is None else groups)
        return True

    def _groups_for(self, dirty) -> tuple[str, ...]:
        wanted: set[str] = set()
        for kind in dirty:
            wanted.update(KIND_GROUPS.get(kind, GROUPS))
        return tuple(g for g in GROUPS if g in wanted)

    def _sync_derived(self):
        """Mirror store/doc-derived values into plain trame state."""
        doc = self.doc
        file_ref_keys = set(project_io.FILE_NAME_KEYS.values())
        with self.state as state:
            state.can_undo = self.store.can_undo
            state.can_redo = self.store.can_redo
            state.command_fields = {
                key: value
                for key, value in doc.command.items()
                if key not in file_ref_keys
            }
            state.mesh_names = list(doc.meshes)
            state.generic_collections = [
                {
                    "name": name,
                    "columns": list(col.columns),
                    "keys": {
                        "start_lon_key": col.start_lon_key,
                        "start_lat_key": col.start_lat_key,
                        "end_lon_key": col.end_lon_key,
                        "end_lat_key": col.end_lat_key,
                        "plot_key": col.plot_key,
                    },
                }
                for name, col in doc.generic.items()
            ]

    # -- layer refresh ----------------------------------------------------------

    def _refresh(self, groups=None):
        """Rebuild layer-group descriptors from the document into state.

        ``None`` rebuilds every group; an empty iterable only refreshes the
        test probe.
        """
        names = GROUPS if groups is None else tuple(g for g in groups if g in GROUPS)
        if names:
            built = self.scene.build(
                names, self.doc, self.state.display, self._scene_selection()
            )
            with self.state as state:
                for name in names:
                    state[f"deck_layers_{name}"] = built.get(name, [])
        self._update_probe()

    def _scene_selection(self) -> dict:
        selection = self.state.selection or {}
        return {
            "kind": selection.get("kind"),
            "ids": set(selection.get("ids") or ()),
            "lasso": list(self.state.lasso_points or []),
        }

    def _update_probe(self):
        if not self.testing:
            return
        graph = self.doc.segments
        with self.state as state:
            selection = state.selection or {"kind": None, "ids": []}
            state.test_probe = {
                "counts": {
                    "segments": len(graph.segments),
                    "vertices": len(graph.vertices),
                    "blocks": len(self.doc.blocks),
                    "velocities": len(self.doc.velocities),
                    "meshes": len(self.doc.meshes),
                },
                "mode": state.edit_mode,
                "selection_mode": state.selection_mode,
                "mode_hint": state.mode_hint,
                "lasso_points": [list(p) for p in (state.lasso_points or [])],
                "drag_layers": list(state.deck_drag_layers or []),
                "segment_names": [s.get("name") for s in graph.segments],
                "dirty": sorted(state.dirty_kinds),
                "selection": {
                    "kind": selection.get("kind"),
                    "ids": list(selection.get("ids") or []),
                },
                "selection_fields": dict(
                    itertools.islice(
                        (state.selection_fields or {}).items(), PROBE_FIELD_SAMPLE
                    )
                ),
                "command_fields_count": len(state.command_fields or {}),
                "inspector_tab": state.inspector_tab,
                "inspector_open": state.inspector_open,
                "undo_depth": len(self.store._past),
                "redo_depth": len(self.store._future),
                "last_pick": self._last_pick,
                "layer_rows": {
                    g: sum(len(d.get("data", [])) for d in state[f"deck_layers_{g}"])
                    for g in GROUPS
                },
            }

    def _fly_to_data(self):
        vertices = list(self.doc.segments.vertices.values())
        lons = [v[0] for v in vertices] + [
            b.get("interior_lon", 0) for b in self.doc.blocks
        ]
        lats = [v[1] for v in vertices] + [
            b.get("interior_lat", 0) for b in self.doc.blocks
        ]
        if not lons:
            return
        with self.state as state:
            state.deck_view_state = {
                "longitude": (min(lons) + max(lons)) / 2,
                "latitude": (min(lats) + max(lats)) / 2,
                "zoom": 5,
            }
            state.deck_view_state_rev += 1

    # -- selection ---------------------------------------------------------------

    def select(self, kind: str, ids, additive: bool = False):
        """Set the (single-kind) selection; routed by the selection mode."""
        self.flush_pending_edits()
        with self.state as state:
            current = state.selection or {"kind": None, "ids": []}
            mode = state.selection_mode or "normal"
            new = select_dispatch(mode, kind, list(ids), current, additive=additive)
            if not new["ids"]:
                new = {"kind": None, "ids": []}
            changed = new != current
            state.selection = new
            state.selection_fields = (
                self._selection_fields(new["kind"], new["ids"]) if new["ids"] else {}
            )
            if changed and new["kind"] in KIND_TABS:
                state.inspector_tab = KIND_TABS[new["kind"]]
                state.inspector_open = True
        self._refresh(("overlay",))

    def _rows(self, kind: str) -> tuple[dict, ...]:
        doc = self.doc
        return {
            "segment": doc.segments.segments,
            "block": doc.blocks,
            "velocity": doc.velocities,
        }.get(kind, ())

    def _id_valid(self, kind: str, ident) -> bool:
        if kind == "vertex":
            return ident in self.doc.segments.vertices
        rows = self._rows(kind)
        return isinstance(ident, int) and 0 <= ident < len(rows)

    def _selection_fields(self, kind: str | None, ids) -> dict:
        """Merged editor fields; ``"-"`` marks mixed values (EditableItem)."""
        if kind == "vertex":
            if len(ids) == 1:
                lonlat = self.doc.segments.vertices.get(ids[0])
                if lonlat is None:
                    return {}
                return {"lon": lonlat[0], "lat": lonlat[1]}
            return {"lon": "-", "lat": "-"}
        schema = SELECTION_SCHEMA.get(kind or "")
        if schema is None:
            return {}
        fields, hidden = schema
        rows = self._rows(kind)  # type: ignore[arg-type]
        selected = [rows[i] for i in ids if 0 <= i < len(rows)]
        if not selected:
            return {}
        ordered = [f for f in fields if f not in hidden]
        for row in selected:  # unknown columns after, first-seen order
            for key in row:
                if key not in fields and key not in hidden and key not in ordered:
                    ordered.append(key)
        merged: dict[str, Any] = {}
        for key in ordered:
            values = [row.get(key, _MISSING) for row in selected]
            if all(value is _MISSING for value in values):
                continue
            first = values[0]
            merged[key] = (
                first
                if first is not _MISSING and all(v == first for v in values[1:])
                else "-"
            )
        return merged

    def _sanitize_selection(self):
        """Drop stale ids after doc changes; recompute the merged fields."""
        selection = self.state.selection or {"kind": None, "ids": []}
        kind, ids = selection.get("kind"), list(selection.get("ids") or [])
        if not kind or not ids:
            return
        valid = [i for i in ids if self._id_valid(kind, i)]
        with self.state as state:
            if not valid:
                state.selection = {"kind": None, "ids": []}
                state.selection_fields = {}
            else:
                if valid != ids:
                    state.selection = {"kind": kind, "ids": valid}
                state.selection_fields = self._selection_fields(kind, valid)

    # -- property editing (1 s numeric debounce, celeri_ui parity) --------------

    def edit_selection(self, key: str, value):
        selection = self.state.selection or {}
        kind = selection.get("kind")
        ids = tuple(selection.get("ids") or ())
        if not kind or not ids:
            return
        if kind == "vertex" and len(ids) != 1:
            return  # merged vertex editor only applies to a single vertex
        coerced = _coerce(value, self._selection_template(kind, ids, key))
        if coerced is _SKIP:
            return
        if self._selection_field_unchanged(kind, ids, key, coerced):
            return  # value echo (e.g. an input re-emitting on render): no-op
        self._stage_edit(("selection", kind, ids), key, coerced)

    def edit_command(self, key: str, value):
        current = self.doc.command.get(key)
        coerced = _coerce(value, current)
        if coerced is _SKIP or coerced == current:
            return  # unchanged value: don't stage a no-op edit
        self._stage_edit(("command",), key, coerced)

    def _selection_field_unchanged(self, kind: str, ids, key: str, coerced) -> bool:
        """True when every selected entity already holds ``coerced`` for ``key``.

        Selecting an entity renders its inspector inputs, which can re-emit
        their current value; committing that as an Edit*/Move* would be a
        no-op that still lands as an undo entry, so it is dropped here.
        """
        if kind == "vertex":
            lonlat = self.doc.segments.vertices.get(ids[0])
            if lonlat is None:
                return False
            return (lonlat[0] if key == "lon" else lonlat[1]) == coerced
        rows = self._rows(kind)
        selected = [rows[i] for i in ids if 0 <= i < len(rows)]
        return bool(selected) and all(
            row.get(key, _MISSING) == coerced for row in selected
        )

    def _selection_template(self, kind: str, ids, key: str):
        if kind == "vertex":
            return 0.0
        rows = self._rows(kind)
        for i in ids:
            if 0 <= i < len(rows) and key in rows[i]:
                return rows[i][key]
        return None

    def _stage_edit(self, target: tuple, key: str, value):
        if self._pending_edit and self._pending_edit["target"] != target:
            self.flush_pending_edits()
        pending = self._pending_edit or {"target": target, "patch": {}}
        pending["patch"][key] = value
        self._pending_edit = pending
        with self.state as state:  # optimistic echo while the debounce runs
            if target[0] == "selection":
                state.selection_fields = {**(state.selection_fields or {}), key: value}
            else:
                state.command_fields = {**(state.command_fields or {}), key: value}
        if isinstance(value, int | float) and not isinstance(value, bool):
            self._schedule_edit_flush()
        else:
            self.flush_pending_edits()

    def _schedule_edit_flush(self):
        async def _later():
            await asyncio.sleep(EDIT_DEBOUNCE_S)
            self.flush_pending_edits()

        self._cancel_edit_task()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # headless (tests): apply immediately
            self.flush_pending_edits()
            return
        self._edit_task = loop.create_task(_later())

    def _cancel_edit_task(self):
        if self._edit_task and not self._edit_task.done():
            self._edit_task.cancel()
        self._edit_task = None

    def flush_pending_edits(self):
        """Commit the staged patch as ONE undoable Edit*/Move* action."""
        self._cancel_edit_task()
        pending, self._pending_edit = self._pending_edit, None
        if not pending:
            return
        target, patch = pending["target"], pending["patch"]
        if target[0] == "command":
            self.dispatch(act.EditCommand(patch=patch), dirty=("command",))
            return
        _, kind, ids = target
        if kind == "vertex":
            vertex_id = ids[0]
            lonlat = self.doc.segments.vertices.get(vertex_id)
            if lonlat is None:
                return
            self.dispatch(
                act.MoveVertex(
                    vertex_id=vertex_id,
                    lon=float(patch.get("lon", lonlat[0])),
                    lat=float(patch.get("lat", lonlat[1])),
                ),
                dirty=("segment",),
            )
            return
        action_type = {
            "segment": act.EditSegments,
            "block": act.EditBlocks,
            "velocity": act.EditVelocities,
        }.get(kind)
        if action_type is None:
            return
        self.dispatch(
            action_type(indices=ids, patch=patch),
            dirty=(SELECTION_DIRTY[kind],),
        )

    def delete_selection(self):
        self._pending_edit = None  # rows are going away; drop staged edits
        self._cancel_edit_task()
        selection = self.state.selection or {}
        kind = selection.get("kind")
        ids = tuple(sorted(selection.get("ids") or ()))
        action_type = {
            "segment": act.DeleteSegments,
            "block": act.DeleteBlocks,
            "velocity": act.DeleteVelocities,
        }.get(kind or "")
        if action_type is None or not ids:
            return
        with self.state as state:
            state.selection = {"kind": None, "ids": []}
            state.selection_fields = {}
        self.dispatch(action_type(indices=ids), dirty=(SELECTION_DIRTY[kind],))

    def split_selection(self):
        """Split every selected segment at its midpoint (SegmentsPanel)."""
        self.flush_pending_edits()
        selection = self.state.selection or {}
        if selection.get("kind") != "segment" or not selection.get("ids"):
            return
        self.dispatch(
            act.SplitSegments(indices=tuple(sorted(selection["ids"]))),
            dirty=("segment",),
        )

    # -- geometry editing: drag / creation / vertex ops -------------------------

    def commit_move(self, kind: str, ident: int, lon: float, lat: float):
        """Commit a drag as ONE undoable Move* action (dragend only).

        ``kind`` is vertex/block/velocity, ``ident`` the vertex id (already
        resolved from the row) or the block/velocity row index. A vertex move
        auto-merges in the reducer when it lands on an occupied cell.
        """
        self.flush_pending_edits()
        dirty = MOVE_DIRTY.get(kind)
        if dirty is None:
            return
        action: act.Action
        if kind == "vertex":
            action = act.MoveVertex(vertex_id=ident, lon=lon, lat=lat)
        elif kind == "block":
            action = act.MoveBlock(index=ident, lon=lon, lat=lat)
        else:
            action = act.MoveVelocity(index=ident, lon=lon, lat=lat)
        self.dispatch(action, dirty=(dirty,))

    def arm_new(self, kind: str):
        """Arm a new-entity mapClick flow (SegmentsPanel / BlockPanel / ...).

        Segment creation takes TWO clicks (start then end); block and velocity
        take one. The mapClick callback receives a normalized ``[lon, lat]``.
        """
        self.flush_pending_edits()
        if kind == "segment":
            self._arm_segment_start()
        elif kind in ("block", "velocity"):
            self.controller.arm(
                "mapClick",
                {"label": f"New {kind}"},
                lambda coord, kind=kind: self._place_entity(kind, coord),
            )
            self._set_mode_hint(NEW_ENTITY_HINTS[kind])

    def _arm_segment_start(self):
        self.controller.arm(
            "mapClick", {"label": "New Segment"}, self._segment_start_click
        )
        self._set_mode_hint(NEW_ENTITY_HINTS["segment"])

    def _segment_start_click(self, coordinate):
        start = (coordinate[0], coordinate[1])
        # Re-arm for the second click, remembering the start point.
        self.controller.arm(
            "mapClick",
            {"label": "New Segment"},
            lambda coord, start=start: self._segment_end_click(start, coord),
        )
        self._set_mode_hint("New segment: click the end point")

    def _segment_end_click(self, start, coordinate):
        end = (coordinate[0], coordinate[1])
        self.controller.cancel()
        self.dispatch(
            act.CreateSegment(start=start, end=end, props={}), dirty=("segment",)
        )

    def _place_entity(self, kind: str, coordinate):
        self.controller.cancel()
        lon, lat = coordinate[0], coordinate[1]
        if kind == "block":
            action: act.Action = act.CreateBlock(
                props={"interior_lon": lon, "interior_lat": lat}
            )
        else:
            action = act.CreateVelocity(props={"lon": lon, "lat": lat})
        self.dispatch(action, dirty=(CREATE_DIRTY[kind],))

    def arm_vertex_op(self, op: str):
        """Arm merge/bridge/extrude — each needs a single selected vertex.

        Merge/bridge arm 'override' and route the SECOND picked vertex to the
        op; extrude arms 'mapClick' and takes the target coordinate. With no
        single vertex selected the call is a no-op (a hint, no crash).
        """
        self.flush_pending_edits()
        keep = self._selected_single_vertex()
        if keep is None:
            self._set_mode_hint("Select a single vertex first")
            return
        if op == "extrude":
            self.controller.arm(
                "mapClick",
                {"label": "Extrude"},
                lambda coord, vid=keep: self._do_extrude(vid, coord),
            )
        elif op == "merge":
            self.controller.arm(
                "override",
                {"label": "Merge", "kind": "vertex"},
                lambda ids, vid=keep: self._do_merge(vid, ids),
            )
        elif op == "bridge":
            self.controller.arm(
                "override",
                {"label": "Bridge", "kind": "vertex"},
                lambda ids, vid=keep: self._do_bridge(vid, ids),
            )
        else:
            return
        self._set_mode_hint(VERTEX_OP_HINTS[op])

    def _selected_single_vertex(self) -> int | None:
        selection = self.state.selection or {}
        if selection.get("kind") != "vertex":
            return None
        ids = list(selection.get("ids") or [])
        return ids[0] if len(ids) == 1 else None

    def _do_extrude(self, vertex_id: int, coordinate):
        self.controller.cancel()
        self.dispatch(
            act.ExtrudeSegment(
                vertex_id=vertex_id, target=(coordinate[0], coordinate[1])
            ),
            dirty=("segment",),
        )

    def _do_merge(self, keep: int, picked_ids):
        self.controller.cancel()
        remove = picked_ids[0] if picked_ids else None
        if remove is None:
            return
        self.dispatch(act.MergeVertices(keep=keep, remove=remove), dirty=("segment",))

    def _do_bridge(self, a: int, picked_ids):
        self.controller.cancel()
        b = picked_ids[0] if picked_ids else None
        if b is None:
            return
        self.dispatch(act.BridgeVertices(a=a, b=b), dirty=("segment",))

    def _set_mode_hint(self, text: str):
        with self.state as state:
            state.mode_hint = text
        self._update_probe()

    # -- mesh / generic collection handlers --------------------------------------

    def remove_mesh(self, name: str):
        self.dispatch(act.RemoveMesh(name=name), dirty=("mesh",))

    def remove_generic(self, name: str):
        self.dispatch(act.RemoveGeneric(name=name), dirty=("generic",))

    def set_generic_keys(self, name: str, key: str, value):
        self.dispatch(
            act.SetGenericKeys(name=name, keys={key: str(value)}),
            dirty=("generic",),
        )

    # -- project / file actions ---------------------------------------------------

    def on_open_config(self):
        self.file_explorer.open(
            self.open_config, extension=".json", title="Open config file"
        )

    def open_config(self, path: Path):
        self.flush_pending_edits()
        doc, refs = project_io.load_project(Path(path))
        self.refs = refs
        self.store.reset(doc)
        with self.state as state:
            state.folder_label = Path(path).parent.name + "/" + Path(path).name
            state.dirty_kinds = []
            state.selection = {"kind": None, "ids": []}
            state.selection_fields = {}
            state.lasso_points = []
        self._sync_derived()
        self._refresh()
        if not self.testing:
            self._fly_to_data()

    def on_save_all(self):
        self.flush_pending_edits()
        if self.refs is None:
            return
        kinds = set(self.state.dirty_kinds) & set(project_io.SAVABLE_KINDS)
        if not kinds:
            return
        project_io.save_project(self.doc, self.refs, kinds)
        with self.state as state:
            state.dirty_kinds = sorted(set(state.dirty_kinds) - kinds)
        self._update_probe()

    def mark_dirty(self, *kinds: str):
        saveable = set(kinds) & set(project_io.SAVABLE_KINDS)
        if not saveable:
            return
        with self.state as state:
            state.dirty_kinds = sorted(set(state.dirty_kinds) | saveable)

    # -- per-kind open / save (inspector panel file buttons) ----------------------

    def open_kind(self, kind: str):
        extension, title = OPEN_SPECS[kind]
        self.file_explorer.open(
            lambda path, kind=kind: self._load_kind(kind, Path(path)),
            extension=extension,
            mode="open",
            title=title,
        )

    def _load_kind(self, kind: str, path: Path):
        """Read one file into the document (undoable Load* dispatch)."""
        self.flush_pending_edits()
        text = path.read_text()
        if kind == "segment":
            self.dispatch(
                act.LoadSegments(graph=read_segments(text)),
                groups=KIND_GROUPS["segment"],
            )
        elif kind == "block":
            self.dispatch(
                act.LoadBlocks(rows=read_blocks(text)), groups=KIND_GROUPS["block"]
            )
        elif kind == "station":
            self.dispatch(
                act.LoadVelocities(rows=read_velocities(text)),
                groups=KIND_GROUPS["station"],
            )
        elif kind == "command":
            self.dispatch(act.LoadCommand(data=read_command(text)), groups=())
        elif kind == "mesh":
            mesh = read_msh(text, name=path.name)
            self.dispatch(
                act.LoadMesh(name=path.name, mesh=mesh), groups=KIND_GROUPS["mesh"]
            )
        elif kind == "mesh_params":
            meshes = project_io._load_meshes(path)
            self.dispatch(
                act.Batch(
                    actions=tuple(
                        act.LoadMesh(name=name, mesh=mesh)
                        for name, mesh in meshes.items()
                    )
                ),
                groups=KIND_GROUPS["mesh"],
            )
        elif kind == "generic":
            self.dispatch(
                act.LoadGeneric(
                    name=path.name, collection=read_generic(text, path.name)
                ),
                groups=KIND_GROUPS["generic"],
            )
        self._remember_path(kind, path)

    def _remember_path(self, kind: str, path: Path):
        if kind in ("mesh", "generic"):
            return  # read-only kinds are never written back
        refs = self._ensure_refs(path)
        if kind == "command":
            refs.config_path = path
        else:
            refs.paths[kind] = path

    def _ensure_refs(self, near: Path | None = None) -> project_io.FileRefs:
        if self.refs is None:
            base = Path(near).parent if near is not None else self.root_dir
            self.refs = project_io.FileRefs(config_path=base / "untitled_config.json")
        return self.refs

    def save_kind(self, kind: str):
        self.flush_pending_edits()
        path = self._kind_path(kind)
        if path is None:
            self.save_kind_as(kind)
            return
        self._write_kind(kind, path)

    def save_kind_as(self, kind: str):
        if kind not in project_io.SAVABLE_KINDS:
            return
        extension = ".json" if kind == "command" else ".csv"
        self.file_explorer.open(
            lambda path, kind=kind: self._save_as(kind, Path(path)),
            extension=extension,
            mode="save",
            title=f"Save {kind} file as",
        )

    def _kind_path(self, kind: str) -> Path | None:
        if self.refs is None:
            return None
        if kind == "command":
            path = self.refs.config_path
            return path if path.is_file() else None
        return self.refs.paths.get(kind)

    def _save_as(self, kind: str, path: Path):
        self.flush_pending_edits()
        refs = self._ensure_refs(path)
        if kind == "command":
            refs.config_path = path
        else:
            refs.paths[kind] = path
            key = project_io.FILE_NAME_KEYS.get(kind)
            if key and self.doc.command:
                # Keep the command's file reference pointing at the new file.
                rel = os.path.relpath(path, refs.config_path.parent)
                self.dispatch(act.EditCommand(patch={key: rel}), dirty=("command",))
        self._write_kind(kind, path)

    def _write_kind(self, kind: str, path: Path):
        doc = self.doc
        if kind == "command":
            path.write_text(write_command(doc.command))
        elif kind == "segment":
            path.write_text(write_segments(doc.segments))
        elif kind == "block":
            path.write_text(write_blocks(doc.blocks))
        elif kind == "station":
            path.write_text(write_velocities(doc.velocities))
        else:
            return  # mesh/mesh_params/generic are read-only
        with self.state as state:
            state.dirty_kinds = sorted(set(state.dirty_kinds) - {kind})
        if self.refs is not None:
            self.refs.dirty.discard(kind)
        self._update_probe()

    # -- undo / redo ---------------------------------------------------------------

    def on_undo(self):
        self.flush_pending_edits()
        if self.store.undo() is None:
            return
        self._after_history_step()

    def on_redo(self):
        self.flush_pending_edits()
        if self.store.redo() is None:
            return
        self._after_history_step()

    def _after_history_step(self):
        self._sync_derived()
        self._sanitize_selection()
        self._refresh()

    # -- display / mode handlers -----------------------------------------------

    PANEL_GROUPS: ClassVar[dict[str, tuple[str, ...]]] = {
        "segment": ("segments", "dip_projection", "labels", "overlay"),
        "vertex": ("vertices", "overlay"),
        "block": ("blocks", "labels", "overlay"),
        "velocity": ("velocities", "labels", "overlay"),
        "mesh": ("meshes",),
        "generic": ("generic",),
        "grid": ("graticule",),
        "map": (),
    }

    def on_toggle_display(self, panel: str):
        display = json.loads(json.dumps(self.state.display))
        key = "show" if panel == "grid" else "hide"
        display[panel][key] = not display[panel][key]
        self.set_display(display, groups=self.PANEL_GROUPS.get(panel))

    def update_display(self, panel: str, key: str, value):
        """Single funnel for every nested display edit (reassigns the dict)."""
        display = json.loads(json.dumps(self.state.display))
        display[panel][key] = value
        self.set_display(display, groups=self.PANEL_GROUPS.get(panel))
        if panel == "map" and key == "styleName":
            with self.state as state:
                state.deck_map_style = self._resolve_map_style(value)

    def set_display(self, display: dict, groups=None):
        with self.state as state:
            state.display = display
        self._refresh(groups)
        self._schedule_settings_save()

    @staticmethod
    def _resolve_map_style(name: str):
        if name == "none":
            return None
        if name == "carto":
            return mapbox.CARTO_POSITRON_STYLE_URL
        return mapbox.resolve_style()  # 'default' / 'monochrome' ladder

    def _schedule_settings_save(self):
        async def _save_later():
            await asyncio.sleep(1.0)
            settings.save(self.state.display)

        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            settings.save(self.state.display)
            return
        self._save_task = loop.create_task(_save_later())

    def on_toggle_lasso(self):
        if self.state.selection_mode == "lasso":
            self.controller.cancel()
        else:
            with self.state as state:
                state.selection_mode = "lasso"
        self._update_probe()

    # -- state watchers -----------------------------------------------------------

    def _on_lasso_points(self, **_):
        self._refresh(("overlay",))

    def _on_selection_mode(self, selection_mode, **_):
        if selection_mode == "normal" and self.state.mode_hint:
            self.state.mode_hint = ""
        self._update_probe()

    def _on_edit_mode(self, **_):
        self._sync_drag_layers()
        self._update_probe()

    def _sync_drag_layers(self):
        """Mirror the active edit mode into the widget's draggable-layer set."""
        layers = list(EDIT_MODE_DRAG_LAYERS.get(self.state.edit_mode, []))
        if list(self.state.deck_drag_layers or []) != layers:
            self.state.deck_drag_layers = layers

    def _on_probe_keys(self, **_):
        self._update_probe()

    # -- widget events --------------------------------------------------------------

    def on_map_hover(self, event):
        with self.state as state:
            state.hover_lonlat = (event or {}).get("coordinate")

    def on_map_click(self, event):
        event = event or {}
        if self.testing:
            self._last_pick = {
                "picked": event.get("picked"),
                "layerId": event.get("layerId"),
                "index": event.get("index"),
                "coordinate": event.get("coordinate"),
            }
        self.controller.handle_click(event)
        with self.state as state:
            # MapController writes the raw kind; map it to the tab name
            # ('velocity' -> 'velocities').
            tab = state.inspector_tab
            fixed = KIND_TABS.get(tab, tab)
            if fixed != tab:
                state.inspector_tab = fixed
        self._update_probe()

    def on_map_viewstate(self, event):
        with self.state as state:
            state.deck_view_state = {
                "longitude": event.get("longitude"),
                "latitude": event.get("latitude"),
                "zoom": event.get("zoom"),
            }

    def on_map_dragstart(self, event):
        self.controller.handle_dragstart(event or {})

    def on_map_drag(self, event):
        self.controller.handle_drag(event or {})

    def on_map_dragend(self, event):
        self.controller.handle_dragend(event or {})
        self._update_probe()

    def on_map_key(self, event):
        self.controller.handle_key(event or {})
        self._update_probe()

    # -- ui ------------------------------------------------------------------------

    def _build_ui(self):
        with VAppLayout(self.server, fill_height=True) as layout:
            self.ui = layout
            top_bar.build(self)
            with html.Div(
                style="position: fixed; inset: 48px 0 0 0;",
            ):
                DeckEditor(
                    groups=GROUPS,
                    map_style=("deck_map_style",),
                    view_state=("deck_view_state",),
                    view_state_revision=("deck_view_state_rev",),
                    drag_layers=("deck_drag_layers",),
                    cursor_mode=("deck_cursor_mode",),
                    click=(self.on_map_click, "[$event]"),
                    hover=(self.on_map_hover, "[$event]"),
                    dragstart=(self.on_map_dragstart, "[$event]"),
                    drag=(self.on_map_drag, "[$event]"),
                    dragend=(self.on_map_dragend, "[$event]"),
                    viewstate=(self.on_map_viewstate, "[$event]"),
                    mapkey=(self.on_map_key, "[$event]"),
                )
            edit_mode_panel.build(self)
            mode_banner.build(self)
            inspector.build(self)
            self.file_explorer = FileExplorer(self, self.root_dir)
            self.file_explorer.build()
            if self.testing:
                html.Div(
                    "{{ JSON.stringify(test_probe) }}",
                    classes="test-probe",
                    style="display: none;",
                )
