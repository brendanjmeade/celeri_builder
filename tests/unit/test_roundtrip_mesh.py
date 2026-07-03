"""Gmsh MSH 4.1 parsing vs the files' own declared totals.

Meshes are read-only (never written), so the "round trip" here is
parser output checked against an independent line-walk of the $Nodes /
$Elements headers done inside the test.
"""

from __future__ import annotations

import json

import pytest

from celeri_builder.io.mesh_io import read_mesh_params, read_msh


def _declared_counts(text: str) -> tuple[int, int]:
    """Independently read declared node total and type-2 element total.

    Line-based walk of the section headers — deliberately NOT the
    token-stream strategy used by the parser under test.
    """
    lines = [line.strip() for line in text.splitlines()]

    nodes_at = lines.index("$Nodes")
    n_nodes = int(lines[nodes_at + 1].split()[1])

    elements_at = lines.index("$Elements")
    num_blocks = int(lines[elements_at + 1].split()[0])
    n_triangles = 0
    cursor = elements_at + 2
    for _ in range(num_blocks):
        _dim, _tag, etype, count = (int(v) for v in lines[cursor].split())
        if etype == 2:
            n_triangles += count
        cursor += 1 + count  # one element per line in ASCII output
    return n_nodes, n_triangles


def _node_tag_span(text: str) -> tuple[int, int, int]:
    lines = [line.strip() for line in text.splitlines()]
    header = lines[lines.index("$Nodes") + 1].split()
    return int(header[1]), int(header[2]), int(header[3])


def test_all_example_meshes_parse(data_dir):
    msh_files = sorted((data_dir / "mesh").glob("*.msh"))
    assert len(msh_files) == 5
    for path in msh_files:
        text = path.read_text()
        mesh = read_msh(text, name=path.name)
        n_nodes, n_triangles = _declared_counts(text)

        assert mesh.name == path.name
        assert mesh.vertices.shape == (n_nodes, 3), path.name
        assert mesh.vertices.dtype.kind == "f"
        assert mesh.triangles.shape == (n_triangles, 3), path.name
        assert mesh.triangles.dtype.kind == "i"
        assert n_triangles > 0, path.name

        # every triangle index maps to a real vertex row
        assert mesh.triangles.min() >= 0, path.name
        assert mesh.triangles.max() < n_nodes, path.name

        # celeri convention: longitudes normalized to 0-360
        assert (mesh.vertices[:, 0] >= 0.0).all(), path.name
        assert (mesh.vertices[:, 0] <= 360.0).all(), path.name


def test_japan_tags_are_non_sequential(data_dir):
    """japan.msh is the regression: tags 2..1461 for 1401 nodes.

    celeri_ui's positional parser mis-mapped these; the tag->row map
    must absorb the gaps.
    """
    text = (data_dir / "mesh" / "japan.msh").read_text()
    n_nodes, min_tag, max_tag = _node_tag_span(text)
    assert (min_tag, max_tag) != (1, n_nodes)  # really non-sequential
    mesh = read_msh(text, name="japan.msh")
    assert mesh.vertices.shape[0] == n_nodes
    assert mesh.triangles.max() < n_nodes


def test_japan_mesh_params(data_dir):
    text = (data_dir / "mesh" / "japan_mesh.json").read_text()
    entries = read_mesh_params(text)
    assert len(entries) == 4
    assert all("mesh_filename" in entry for entry in entries)
    names = [entry["mesh_filename"] for entry in entries]
    assert "../mesh/japan.msh" in names
    # opaque passthrough: identical to a raw json.loads
    assert entries == json.loads(text)


def test_wna_mesh_params(data_dir):
    text = (data_dir / "mesh" / "wna_mesh.json").read_text()
    entries = read_mesh_params(text)
    assert len(entries) == 1
    assert entries[0]["mesh_filename"] == "../mesh/cascadia.msh"
    assert entries == json.loads(text)


def test_params_unknown_keys_verbatim():
    entries = [
        {
            "mesh_filename": "../mesh/a.msh",
            "zz_totally_custom": {"deep": [1, 2.5, None]},
            "weird key with spaces": "kept",
            "elastic_constraints_ss": [-90, 90],
        }
    ]
    assert read_mesh_params(json.dumps(entries)) == entries


def test_params_non_array_raises():
    with pytest.raises(ValueError, match="JSON array"):
        read_mesh_params('{"mesh_filename": "x.msh"}')


MINIMAL_22 = "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"
MINIMAL_BINARY = "$MeshFormat\n4.1 1 8\n$EndMeshFormat\n"


def test_non_41_version_raises():
    with pytest.raises(ValueError, match=r"4\.1"):
        read_msh(MINIMAL_22)


def test_binary_raises():
    with pytest.raises(ValueError, match=r"[Bb]inary"):
        read_msh(MINIMAL_BINARY)


def test_non_msh_text_raises():
    with pytest.raises(ValueError, match="MeshFormat"):
        read_msh("lon,lat\n1,2\n")
