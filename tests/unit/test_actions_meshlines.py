"""Mesh action reducers — port of celeri_ui ``mocha/tests/MeshLineState.spec.ts``
("Mesh Lines"). celeri_builder stores real Mesh objects (vertices/triangles
arrays + opaque params) instead of pre-flattened line lists, so the
scenarios assert the equivalent outcomes on the keyed ``Document.meshes``
dict."""

from __future__ import annotations

import numpy as np

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document, Mesh
from celeri_builder.model.reducers import reduce


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


def make_mesh(name: str = "mesh", params: dict | None = None) -> Mesh:
    return Mesh(
        name=name,
        vertices=np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [1.0, 0.0, -5.0]]),
        triangles=np.array([[0, 1, 2]]),
        params=params or {},
    )


def test_can_load_new_data_into_a_keyed_mesh_dict():
    doc = apply(act.LoadMesh(name="mesh", mesh=make_mesh()))
    assert "mesh" in doc.meshes
    mesh = doc.meshes["mesh"]
    assert mesh.vertices.shape == (3, 3)
    assert mesh.vertices[0, 0] == 0
    assert len(mesh.edges()) == 3


def test_can_load_new_data_with_parameters_into_a_keyed_mesh_dict():
    params = {
        "mesh_filename": "test",
        "smoothing_weight": 3,
        "edge_constraints": [0, 1, 0],
        "n_eigenvalues": 20,
        "a_priori_slip_filename": "me",
    }
    doc = apply(act.LoadMesh(name="mesh", mesh=make_mesh(params=params)))
    assert "mesh" in doc.meshes
    assert doc.meshes["mesh"].vertices[0, 0] == 0
    assert doc.meshes["mesh"].params["mesh_filename"] == "test"


def test_can_remove_a_mesh_from_state():
    doc = apply(
        act.LoadMesh(name="mesh", mesh=make_mesh()),
        act.RemoveMesh(name="mesh"),
    )
    assert "mesh" not in doc.meshes


def test_remove_keeps_the_other_meshes():
    other = make_mesh(name="other")
    doc = apply(
        act.LoadMesh(name="mesh", mesh=make_mesh()),
        act.LoadMesh(name="other", mesh=other),
        act.RemoveMesh(name="mesh"),
    )
    assert list(doc.meshes) == ["other"]
    assert doc.meshes["other"] is other


def test_load_replaces_an_existing_mesh_of_the_same_name():
    replacement = make_mesh(params={"mesh_filename": "v2"})
    doc = apply(
        act.LoadMesh(name="mesh", mesh=make_mesh()),
        act.LoadMesh(name="mesh", mesh=replacement),
    )
    assert len(doc.meshes) == 1
    assert doc.meshes["mesh"] is replacement


def test_clear_meshes_empties_the_dict():
    doc = apply(
        act.LoadMesh(name="a", mesh=make_mesh(name="a")),
        act.LoadMesh(name="b", mesh=make_mesh(name="b")),
        act.ClearMeshes(),
    )
    assert doc.meshes == {}


def test_removing_a_missing_mesh_is_a_noop():
    before = apply(act.LoadMesh(name="mesh", mesh=make_mesh()))
    assert reduce(before, act.RemoveMesh(name="missing")) is before
