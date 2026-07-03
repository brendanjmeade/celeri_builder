"""Pure reducers: ``(Document, action) -> Document`` with structural sharing.

Each reducer is a faithful port of the matching celeri_ui per-action file
(``src/State/{Segment,Block,Velocity,MeshLines,GenericSegments,Command}``).
Reducers replace only the Document slices they touch and return the SAME
Document object when an action changes nothing (the Store uses identity to
decide whether a history entry is warranted).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import (
    block,
    command,
    generic,
    mesh,
    segment,
    velocity,
)

Reducer = Callable[[Document, Any], Document]


def _reduce_batch(doc: Document, action: act.Batch) -> Document:
    """Batch: fold the actions left-to-right (ONE undoable entry)."""
    for sub in action.actions:
        doc = reduce(doc, sub)
    return doc


REDUCERS: dict[type[act.Action], Reducer] = {
    # segments
    act.CreateSegment: segment.create_segment,
    act.DeleteSegments: segment.delete_segments,
    act.EditSegments: segment.edit_segments,
    act.SplitSegments: segment.split_segments,
    act.MergeVertices: segment.merge_vertices,
    act.MoveVertex: segment.move_vertex,
    act.ExtrudeSegment: segment.extrude_segment,
    act.BridgeVertices: segment.bridge_vertices,
    act.LoadSegments: segment.load_segments,
    # blocks
    act.CreateBlock: block.create_block,
    act.EditBlocks: block.edit_blocks,
    act.DeleteBlocks: block.delete_blocks,
    act.MoveBlock: block.move_block,
    act.LoadBlocks: block.load_blocks,
    # velocities
    act.CreateVelocity: velocity.create_velocity,
    act.EditVelocities: velocity.edit_velocities,
    act.DeleteVelocities: velocity.delete_velocities,
    act.MoveVelocity: velocity.move_velocity,
    act.LoadVelocities: velocity.load_velocities,
    # meshes
    act.LoadMesh: mesh.load_mesh,
    act.RemoveMesh: mesh.remove_mesh,
    act.ClearMeshes: mesh.clear_meshes,
    # generic segment collections
    act.LoadGeneric: generic.load_generic,
    act.SetGenericKeys: generic.set_generic_keys,
    act.RemoveGeneric: generic.remove_generic,
    # command / config
    act.LoadCommand: command.load_command,
    act.NewCommand: command.new_command,
    act.EditCommand: command.edit_command,
    # composition
    act.Batch: _reduce_batch,
}


def reduce(doc: Document, action: act.Action) -> Document:
    """Apply one action to the document; unknown types raise ``TypeError``."""
    try:
        reducer = REDUCERS[type(action)]
    except KeyError:
        msg = f"no reducer registered for action type {type(action).__name__!r}"
        raise TypeError(msg) from None
    return reducer(doc, action)
