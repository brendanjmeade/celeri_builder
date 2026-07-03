"""Replay an abstract edit script against the celeri_builder ENGINE.

This is the runnable core of the parity harness. It imports the pure model
layer directly -- no trame, no browser -- so it runs anywhere:

    load_project -> Store -> resolve abstract ops to actions -> reduce
                 -> save_project (writes CSV/JSON back into a workspace dir)

Abstract-op resolution is the whole point: segment *names* are resolved to
row indices and coordinates to vertex ids against the CURRENT document, so
indices that shift after a delete/split still resolve correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from celeri_builder.io.project import FileRefs, load_project, save_project
from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.store import Store
from celeri_builder.model.vertex_graph import normalize_lon, vertex_key

Op = tuple[str, dict]


@dataclass
class BuilderRun:
    """Result of replaying a script against the engine and saving it."""

    config_path: Path
    workspace: Path
    refs: FileRefs
    baseline: Document  # the pristine load, before any edits
    document: Document  # the final document, after edits
    saved: dict[str, Path] = field(default_factory=dict)

    def text(self, kind: str) -> str:
        """Read back a saved file's text (``segment``/``block``/``station``/
        ``command``)."""
        return self.saved[kind].read_text()


# -- abstract-op resolution ---------------------------------------------------


def _segment_indices(doc: Document, names: list) -> tuple[int, ...]:
    """Row indices of every segment whose name matches one of ``names``.

    Names are compared as strings so a numeric-looking name (japan has a
    segment literally named ``2``, parsed to the int ``2``) still matches
    its string spelling in the script.
    """
    wanted = [str(n) for n in names]
    return tuple(
        i
        for i, seg in enumerate(doc.segments.segments)
        if str(seg.get("name")) in wanted
    )


def _vertex_at(doc: Document, coordinate: list) -> int:
    """Vertex id occupying ``coordinate``'s micro-degree cell (0-360 keyed)."""
    lon, lat = coordinate
    key = vertex_key(normalize_lon(lon), lat)
    vid = doc.segments.vertex_index.get(key)
    if vid is None:
        msg = f"no vertex at coordinate {coordinate!r} (cell {key})"
        raise KeyError(msg)
    return vid


def apply_op(store: Store, op: str, params: dict) -> None:
    """Resolve one abstract op against ``store.doc`` and dispatch it."""
    doc = store.doc
    if op == "edit_segments":
        indices = _segment_indices(doc, params["names"])
        if len(indices) != len(params["names"]):
            msg = f"edit_segments: {params['names']} resolved to {indices}"
            raise ValueError(msg)
        store.dispatch(act.EditSegments(indices=indices, patch=dict(params["patch"])))
    elif op == "create_segment":
        store.dispatch(
            act.CreateSegment(
                start=tuple(params["start"]),
                end=tuple(params["end"]),
                props=dict(params.get("props", {})),
            )
        )
    elif op == "move_vertex":
        vid = _vertex_at(doc, params["at"])
        to_lon, to_lat = params["to"]
        store.dispatch(act.MoveVertex(vertex_id=vid, lon=to_lon, lat=to_lat))
    elif op == "delete_segments":
        indices = _segment_indices(doc, params["names"])
        if len(indices) != len(params["names"]):
            msg = f"delete_segments: {params['names']} resolved to {indices}"
            raise ValueError(msg)
        store.dispatch(act.DeleteSegments(indices=indices))
    elif op == "split_segment":
        indices = _segment_indices(doc, [params["name"]])
        if len(indices) != 1:
            msg = f"split_segment: {params['name']!r} resolved to {indices}"
            raise ValueError(msg)
        store.dispatch(act.SplitSegments(indices=indices))
    elif op == "undo_all":
        while store.can_undo:
            store.undo()
    else:
        msg = f"unknown parity op {op!r}"
        raise ValueError(msg)


# -- replay -------------------------------------------------------------------

#: Kinds save_project actually writes back (mesh/generic are read-only).
_SAVED_KINDS: tuple[str, ...] = ("segment", "block", "station", "command")


def replay(config_path: Path, ops: list[Op] | tuple[Op, ...]) -> BuilderRun:
    """Load ``config_path``, apply ``ops``, save in place, return the run.

    ``config_path`` must point at a WRITABLE project copy: ``save_project``
    overwrites the referenced CSV/JSON files (the workspace fixture hands us
    a throwaway copy of the region tree). The pristine originals are still
    available from the source data dir for canonicalization comparisons.
    """
    config_path = Path(config_path)
    baseline, refs = load_project(config_path)
    store = Store(baseline)
    for op, params in ops:
        apply_op(store, op, params)

    save_project(store.doc, refs)

    saved: dict[str, Path] = {"command": refs.config_path}
    for kind in ("segment", "block", "station"):
        if kind in refs.paths:
            saved[kind] = refs.paths[kind]

    return BuilderRun(
        config_path=config_path,
        workspace=config_path.parents[1],
        refs=refs,
        baseline=baseline,
        document=store.doc,
        saved=saved,
    )
