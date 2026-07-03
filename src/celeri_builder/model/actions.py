"""Action dataclasses — the app's full command set (celeri_ui parity).

Every action is a frozen dataclass; reducers are pure functions
``(Document, action) -> Document`` registered in ``model.reducers``.
All actions are undoable via the Store's snapshot stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from celeri_builder.model.document import GenericCollection, Mesh
from celeri_builder.model.vertex_graph import SegmentGraph

LonLat = tuple[float, float]


class Action:
    """Marker base class."""


# -- segments (celeri_ui State/Segment) --------------------------------------


@dataclass(frozen=True)
class CreateSegment(Action):
    start: LonLat
    end: LonLat
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeleteSegments(Action):
    indices: tuple[int, ...]


@dataclass(frozen=True)
class EditSegments(Action):
    indices: tuple[int, ...]
    patch: dict[str, Any]


@dataclass(frozen=True)
class SplitSegments(Action):
    indices: tuple[int, ...]


@dataclass(frozen=True)
class MergeVertices(Action):
    keep: int
    remove: int


@dataclass(frozen=True)
class MoveVertex(Action):
    vertex_id: int
    lon: float
    lat: float


@dataclass(frozen=True)
class ExtrudeSegment(Action):
    vertex_id: int
    target: LonLat


@dataclass(frozen=True)
class BridgeVertices(Action):
    a: int
    b: int


@dataclass(frozen=True)
class LoadSegments(Action):
    graph: SegmentGraph


# -- blocks -------------------------------------------------------------------


@dataclass(frozen=True)
class CreateBlock(Action):
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EditBlocks(Action):
    indices: tuple[int, ...]
    patch: dict[str, Any]


@dataclass(frozen=True)
class DeleteBlocks(Action):
    indices: tuple[int, ...]


@dataclass(frozen=True)
class MoveBlock(Action):
    index: int
    lon: float
    lat: float


@dataclass(frozen=True)
class LoadBlocks(Action):
    rows: tuple[dict, ...]


# -- velocities ------------------------------------------------------------------


@dataclass(frozen=True)
class CreateVelocity(Action):
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EditVelocities(Action):
    indices: tuple[int, ...]
    patch: dict[str, Any]


@dataclass(frozen=True)
class DeleteVelocities(Action):
    indices: tuple[int, ...]


@dataclass(frozen=True)
class MoveVelocity(Action):
    index: int
    lon: float
    lat: float


@dataclass(frozen=True)
class LoadVelocities(Action):
    rows: tuple[dict, ...]


# -- meshes ------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadMesh(Action):
    name: str
    mesh: Mesh


@dataclass(frozen=True)
class RemoveMesh(Action):
    name: str


@dataclass(frozen=True)
class ClearMeshes(Action):
    pass


# -- generic segment collections ----------------------------------------------------


@dataclass(frozen=True)
class LoadGeneric(Action):
    name: str
    collection: GenericCollection


@dataclass(frozen=True)
class SetGenericKeys(Action):
    name: str
    keys: dict[str, str]  # start_lon_key / start_lat_key / end_* / plot_key


@dataclass(frozen=True)
class RemoveGeneric(Action):
    name: str


# -- command / config -----------------------------------------------------------------


@dataclass(frozen=True)
class LoadCommand(Action):
    data: dict[str, Any]


@dataclass(frozen=True)
class NewCommand(Action):
    pass


@dataclass(frozen=True)
class EditCommand(Action):
    patch: dict[str, Any]


# -- composition -------------------------------------------------------------------------


@dataclass(frozen=True)
class Batch(Action):
    """Apply several actions as ONE undoable history entry."""

    actions: tuple[Action, ...]
