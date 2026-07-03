"""The immutable document: everything undoable lives here.

NOT part of the document (and therefore not undoable): selection, edit
mode, display settings, camera, lasso polygon, and file handles/dirty
flags — matching the plan's intentional differences from celeri_ui.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from celeri_builder.model.vertex_graph import SegmentGraph


@dataclass(frozen=True)
class Mesh:
    """A read-only triangulated fault surface (Gmsh MSH 4.1).

    ``vertices``: float array (n, 3) of lon (0-360), lat, depth.
    ``triangles``: int array (m, 3) of row indices into ``vertices``.
    ``params``: the opaque per-mesh parameter dict from *_mesh.json.
    """

    name: str
    vertices: np.ndarray
    triangles: np.ndarray
    params: dict[str, Any] = field(default_factory=dict)

    def edges(self) -> np.ndarray:
        """Unique undirected edges as an (e, 2) int array."""
        tri = self.triangles
        e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        e.sort(axis=1)
        return np.unique(e, axis=0)


@dataclass(frozen=True)
class GenericCollection:
    """An arbitrary CSV overlay with user-mapped position columns."""

    rows: tuple[dict, ...]
    columns: tuple[str, ...]
    start_lon_key: str = ""
    start_lat_key: str = ""
    end_lon_key: str = ""
    end_lat_key: str = ""
    plot_key: str = ""


@dataclass(frozen=True)
class Document:
    segments: SegmentGraph = field(default_factory=SegmentGraph)
    blocks: tuple[dict, ...] = ()
    velocities: tuple[dict, ...] = ()
    meshes: dict[str, Mesh] = field(default_factory=dict)
    generic: dict[str, GenericCollection] = field(default_factory=dict)
    command: dict[str, Any] = field(default_factory=dict)

    def with_(self, **changes) -> Document:
        return replace(self, **changes)
