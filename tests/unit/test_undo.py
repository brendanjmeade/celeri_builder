"""Store history semantics.

- EVERY action type round-trips undo/redo to a deep-equal Document
  (identity, in fact — snapshots are shared, not copied).
- A dispatch that changes nothing adds no history entry.
- ``batch(...)`` is exactly one entry.
- The redo stack is cleared by a fresh dispatch.
- The past stack is bounded by ``limit`` (oldest entries dropped).
- ``reset`` replaces the document and clears all history.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from celeri_builder.model import actions as act
from celeri_builder.model.command_defaults import DEFAULT_COMMAND
from celeri_builder.model.document import Document, GenericCollection, Mesh
from celeri_builder.model.reducers import reduce
from celeri_builder.model.store import Store
from celeri_builder.model.vertex_graph import SegmentGraph

# -- fixtures -----------------------------------------------------------------


def make_mesh(name: str = "m") -> Mesh:
    return Mesh(
        name=name,
        vertices=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, -5.0], [1.0, 1.0, -10.0]]),
        triangles=np.array([[0, 1, 2]]),
        params={"mesh_filename": f"{name}.msh"},
    )


def make_collection() -> GenericCollection:
    return GenericCollection(
        rows=({"lon": 0, "lat": 0, "elon": 1, "elat": 1},),
        columns=("lon", "lat", "elon", "elat"),
    )


def make_base_doc() -> Document:
    """A document exercising every slice: 2 chained segments (vertices
    0,1,2), one block, one velocity, one mesh, one generic collection,
    the default command."""
    doc = Document()
    for action in (
        act.LoadCommand(data=dict(DEFAULT_COMMAND)),
        act.CreateSegment(start=(0.0, 0.0), end=(1.0, 1.0)),
        act.CreateSegment(start=(1.0, 1.0), end=(2.0, 2.0)),
        act.CreateBlock(props={"name": "b0"}),
        act.CreateVelocity(props={"name": "v0"}),
        act.LoadMesh(name="m", mesh=make_mesh()),
        act.LoadGeneric(name="g", collection=make_collection()),
    ):
        doc = reduce(doc, action)
    return doc


def doc_equal(a: Document, b: Document) -> bool:
    """Deep equality; meshes hold numpy arrays so compare them explicitly."""
    if (
        a.segments != b.segments
        or a.blocks != b.blocks
        or a.velocities != b.velocities
        or a.generic != b.generic
        or a.command != b.command
        or set(a.meshes) != set(b.meshes)
    ):
        return False
    for key, mesh_a in a.meshes.items():
        mesh_b = b.meshes[key]
        if (
            mesh_a.name != mesh_b.name
            or mesh_a.params != mesh_b.params
            or not np.array_equal(mesh_a.vertices, mesh_b.vertices)
            or not np.array_equal(mesh_a.triangles, mesh_b.triangles)
        ):
            return False
    return True


# -- every action type round-trips -----------------------------------------------

ROUND_TRIP_ACTIONS = [
    # segments
    act.CreateSegment(start=(5.0, 5.0), end=(6.0, 6.0)),
    act.DeleteSegments(indices=(0,)),
    act.EditSegments(indices=(0,), patch={"dip": 45.0}),
    act.SplitSegments(indices=(0,)),
    act.MergeVertices(keep=0, remove=1),
    act.MoveVertex(vertex_id=0, lon=9.0, lat=9.0),
    act.ExtrudeSegment(vertex_id=0, target=(7.0, 7.0)),
    act.BridgeVertices(a=0, b=2),
    act.LoadSegments(graph=SegmentGraph()),
    # blocks
    act.CreateBlock(props={"name": "new"}),
    act.EditBlocks(indices=(0,), patch={"name": "edited"}),
    act.DeleteBlocks(indices=(0,)),
    act.MoveBlock(index=0, lon=3.0, lat=4.0),
    act.LoadBlocks(rows=()),
    # velocities
    act.CreateVelocity(props={"name": "new"}),
    act.EditVelocities(indices=(0,), patch={"name": "edited"}),
    act.DeleteVelocities(indices=(0,)),
    act.MoveVelocity(index=0, lon=3.0, lat=4.0),
    act.LoadVelocities(rows=()),
    # meshes
    act.LoadMesh(name="m2", mesh=make_mesh("m2")),
    act.RemoveMesh(name="m"),
    act.ClearMeshes(),
    # generic collections
    act.LoadGeneric(name="g2", collection=make_collection()),
    act.SetGenericKeys(
        name="g",
        keys={
            "start_lon_key": "lon",
            "start_lat_key": "lat",
            "end_lon_key": "elon",
            "end_lat_key": "elat",
            "plot_key": "",
        },
    ),
    act.RemoveGeneric(name="g"),
    # command
    act.LoadCommand(data={"file_name": "other"}),
    act.NewCommand(),
    act.EditCommand(patch={"n_iterations": 9}),
    # composition
    act.Batch(
        actions=(
            act.CreateBlock(props={"name": "in_batch"}),
            act.CreateVelocity(props={"name": "in_batch"}),
        )
    ),
]


def test_round_trip_list_covers_every_action_type():
    tested = {type(a) for a in ROUND_TRIP_ACTIONS}
    all_types = {
        obj
        for _, obj in inspect.getmembers(act, inspect.isclass)
        if issubclass(obj, act.Action) and obj is not act.Action
    }
    assert tested == all_types


@pytest.mark.parametrize("action", ROUND_TRIP_ACTIONS, ids=lambda a: type(a).__name__)
def test_every_action_type_round_trips_through_undo_redo(action):
    base = make_base_doc()
    store = Store(base)
    after = store.dispatch(action)
    assert after is not base
    assert store.doc is after
    assert store.can_undo

    assert store.undo() is base
    assert doc_equal(store.doc, base)
    assert store.can_redo

    assert store.redo() is after
    assert doc_equal(store.doc, after)
    assert not store.can_redo


# -- no-op dispatches -------------------------------------------------------------

NOOP_ACTIONS = [
    act.MergeVertices(keep=0, remove=0),
    act.BridgeVertices(a=0, b=0),
    act.BridgeVertices(a=0, b=99),
    act.MoveVertex(vertex_id=99, lon=1.0, lat=1.0),
    act.ExtrudeSegment(vertex_id=99, target=(1.0, 1.0)),
    act.DeleteSegments(indices=()),
    act.EditSegments(indices=(), patch={"dip": 1.0}),
    act.DeleteBlocks(indices=(99,)),
    act.DeleteVelocities(indices=(99,)),
    act.RemoveMesh(name="missing"),
    act.RemoveGeneric(name="missing"),
    act.SetGenericKeys(name="missing", keys={"plot_key": "x"}),
    act.Batch(actions=()),
    act.Batch(actions=(act.MergeVertices(keep=0, remove=0),)),
]


@pytest.mark.parametrize("action", NOOP_ACTIONS, ids=lambda a: type(a).__name__)
def test_dispatch_that_changes_nothing_adds_no_history_entry(action):
    base = make_base_doc()
    store = Store(base)
    assert store.dispatch(action) is base
    assert store.doc is base
    assert not store.can_undo
    assert store.undo() is None


# -- history mechanics ----------------------------------------------------------


def test_batch_is_a_single_history_entry():
    base = make_base_doc()
    store = Store(base)
    store.batch(
        act.CreateBlock(props={"name": "x"}),
        act.CreateVelocity(props={"name": "y"}),
    )
    assert len(store.doc.blocks) == 2
    assert len(store.doc.velocities) == 2
    assert store.undo() is base
    assert not store.can_undo


def test_redo_is_cleared_by_a_new_dispatch():
    store = Store(make_base_doc())
    store.dispatch(act.CreateBlock(props={"name": "a"}))
    store.undo()
    assert store.can_redo
    store.dispatch(act.CreateBlock(props={"name": "b"}))
    assert not store.can_redo
    assert store.redo() is None
    assert store.doc.blocks[-1]["name"] == "b"


def test_undo_redo_return_none_at_history_ends():
    store = Store(Document())
    assert store.undo() is None
    assert store.redo() is None
    assert not store.can_undo
    assert not store.can_redo


def test_history_is_bounded_by_limit():
    store = Store(Document(), limit=5)
    for i in range(8):
        store.dispatch(act.CreateBlock(props={"name": f"b{i}"}))
    assert len(store.doc.blocks) == 8
    undone = 0
    while store.undo() is not None:
        undone += 1
    assert undone == 5
    # the 3 oldest entries were dropped: their edits are baked in
    assert len(store.doc.blocks) == 3


def test_reset_replaces_the_document_and_clears_history():
    store = Store(make_base_doc())
    store.dispatch(act.CreateBlock(props={"name": "x"}))
    store.dispatch(act.CreateBlock(props={"name": "y"}))
    store.undo()
    assert store.can_undo
    assert store.can_redo

    fresh = Document()
    store.reset(fresh)
    assert store.doc is fresh
    assert not store.can_undo
    assert not store.can_redo
    assert store.undo() is None
    assert store.redo() is None


def test_subscribers_see_dispatch_undo_redo_and_can_unsubscribe():
    base = make_base_doc()
    store = Store(base)
    events: list[tuple[Document, Document, act.Action | None]] = []
    unsubscribe = store.subscribe(
        lambda old, new, action: events.append((old, new, action))
    )

    # a no-op dispatch does not notify
    store.dispatch(act.MergeVertices(keep=0, remove=0))
    assert events == []

    action = act.CreateBlock(props={"name": "x"})
    after = store.dispatch(action)
    assert events[-1] == (base, after, action)

    store.undo()
    assert events[-1] == (after, base, None)
    store.redo()
    assert events[-1] == (base, after, None)

    # a failed undo at the end of history does not notify
    store.undo()
    count = len(events)
    store.undo()
    assert len(events) == count

    unsubscribe()
    store.dispatch(act.CreateBlock(props={"name": "z"}))
    assert len(events) == count


def test_dispatching_an_unknown_action_type_raises():
    class Rogue(act.Action):
        pass

    store = Store(Document())
    with pytest.raises(TypeError, match="no reducer registered"):
        store.dispatch(Rogue())
