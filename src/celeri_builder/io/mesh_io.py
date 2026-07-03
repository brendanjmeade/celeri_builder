"""Gmsh MSH 4.1 ASCII reader + mesh-parameters JSON.

This is a real MSH 4.1 parser, intentionally replacing celeri_ui's
positional-regex hack (``MeshFile.ts``), which assumed node tags were
sequential from 1 — they are NOT in the example meshes (japan.msh
declares ``minNodeTag=2 maxNodeTag=1461`` for 1401 nodes). Node tags
are mapped explicitly to row indices.

Only 3-node triangles (element type 2) are kept; points/lines used by
Gmsh for the CAD entities are skipped. Longitudes < 0 gain 360 (celeri
convention). Meshes are read-only: there is no writer.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from celeri_builder.model.document import Mesh

TRIANGLE_TYPE = 2

# Nodes per element for the Gmsh element types we may encounter
# (needed to consume the token stream even for skipped types).
_NODES_PER_ELEMENT: dict[int, int] = {
    1: 2,  # 2-node line
    2: 3,  # 3-node triangle
    3: 4,  # 4-node quadrangle
    4: 4,  # 4-node tetrahedron
    5: 8,  # 8-node hexahedron
    6: 6,  # 6-node prism
    7: 5,  # 5-node pyramid
    8: 3,  # 3-node second-order line
    9: 6,  # 6-node second-order triangle
    10: 9,  # 9-node second-order quadrangle
    11: 10,  # 10-node second-order tetrahedron
    15: 1,  # 1-node point
}


def _section_tokens(text: str, name: str) -> list[str]:
    """Whitespace tokens between ``$name`` and ``$Endname``."""
    start = text.find(f"${name}")
    end = text.find(f"$End{name}")
    if start < 0 or end < 0:
        msg = f"not a Gmsh MSH ASCII file: missing ${name} section"
        raise ValueError(msg)
    return text[start + len(name) + 1 : end].split()


def _check_format(text: str) -> None:
    tokens = _section_tokens(text, "MeshFormat")
    if len(tokens) < 3:
        msg = "malformed $MeshFormat section"
        raise ValueError(msg)
    version, file_type = tokens[0], tokens[1]
    if file_type != "0":
        msg = f"binary MSH files are not supported (file-type {file_type})"
        raise ValueError(msg)
    if version != "4.1":
        msg = f"unsupported MSH version {version} (only 4.1 ASCII is supported)"
        raise ValueError(msg)


def _parse_nodes(text: str) -> tuple[np.ndarray, dict[int, int]]:
    """Parse $Nodes: (n, 3) lon/lat/depth array + node-tag -> row map."""
    tokens = iter(_section_tokens(text, "Nodes"))
    try:
        num_blocks = int(next(tokens))
        num_nodes = int(next(tokens))
        next(tokens)  # minNodeTag
        next(tokens)  # maxNodeTag
        vertices = np.empty((num_nodes, 3), dtype=float)
        tag_to_row: dict[int, int] = {}
        row = 0
        for _ in range(num_blocks):
            next(tokens)  # entityDim
            next(tokens)  # entityTag
            parametric = int(next(tokens))
            if parametric:
                msg = "parametric node blocks are not supported"
                raise ValueError(msg)
            count = int(next(tokens))
            tags = [int(next(tokens)) for _ in range(count)]
            for tag in tags:
                lon = float(next(tokens))
                lat = float(next(tokens))
                depth = float(next(tokens))
                if lon < 0:
                    lon += 360.0
                tag_to_row[tag] = row
                vertices[row] = (lon, lat, depth)
                row += 1
    except StopIteration:
        msg = "truncated $Nodes section"
        raise ValueError(msg) from None
    if row != num_nodes:
        msg = f"$Nodes declared {num_nodes} nodes but blocks held {row}"
        raise ValueError(msg)
    return vertices, tag_to_row


def _parse_triangles(text: str, tag_to_row: dict[int, int]) -> np.ndarray:
    """Parse $Elements keeping type-2 (3-node triangle) rows as row indices."""
    tokens = iter(_section_tokens(text, "Elements"))
    triangles: list[list[int]] = []
    try:
        num_blocks = int(next(tokens))
        next(tokens)  # numElements
        next(tokens)  # minElementTag
        next(tokens)  # maxElementTag
        for _ in range(num_blocks):
            next(tokens)  # entityDim
            next(tokens)  # entityTag
            element_type = int(next(tokens))
            count = int(next(tokens))
            nodes_per = _NODES_PER_ELEMENT.get(element_type)
            if nodes_per is None:
                msg = f"unsupported Gmsh element type {element_type}"
                raise ValueError(msg)
            for _ in range(count):
                next(tokens)  # elementTag
                node_tags = [int(next(tokens)) for _ in range(nodes_per)]
                if element_type == TRIANGLE_TYPE:
                    try:
                        triangles.append([tag_to_row[t] for t in node_tags])
                    except KeyError as exc:
                        msg = f"triangle references unknown node tag {exc.args[0]}"
                        raise ValueError(msg) from None
    except StopIteration:
        msg = "truncated $Elements section"
        raise ValueError(msg) from None
    if not triangles:
        return np.empty((0, 3), dtype=int)
    return np.array(triangles, dtype=int)


def read_msh(text: str, name: str = "", params: dict[str, Any] | None = None) -> Mesh:
    """Parse a Gmsh MSH 4.1 ASCII file into a read-only :class:`Mesh`.

    Raises ``ValueError`` for binary or non-4.1 files.
    """
    _check_format(text)
    vertices, tag_to_row = _parse_nodes(text)
    triangles = _parse_triangles(text, tag_to_row)
    return Mesh(
        name=name,
        vertices=vertices,
        triangles=triangles,
        params=dict(params) if params else {},
    )


def read_mesh_params(text: str) -> list[dict[str, Any]]:
    """Parse a *_mesh.json parameters file: opaque list-of-dicts passthrough.

    Every key is preserved verbatim; nothing is validated beyond the
    outer JSON array shape (celeri_ui parity — parameters ride along
    untouched and are never written back).
    """
    data = json.loads(text)
    if not isinstance(data, list):
        msg = "mesh parameters file must contain a JSON array"
        raise ValueError(msg)
    return data
