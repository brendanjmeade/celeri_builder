"""Mesh reducers — faithful ports of celeri_ui ``src/State/MeshLines/*``.

celeri_ui keys meshes by name in a plain record; celeri_builder does the
same with ``Document.meshes`` (name -> ``Mesh``).
"""

from __future__ import annotations

from celeri_builder.model.actions import ClearMeshes, LoadMesh, RemoveMesh
from celeri_builder.model.document import Document


def load_mesh(doc: Document, action: LoadMesh) -> Document:
    """LoadMeshLineData.ts: insert/replace the named mesh."""
    return doc.with_(meshes={**doc.meshes, action.name: action.mesh})


def remove_mesh(doc: Document, action: RemoveMesh) -> Document:
    """RemoveMesh.ts: drop the named mesh, keeping the others."""
    if action.name not in doc.meshes:
        return doc
    return doc.with_(meshes={k: v for k, v in doc.meshes.items() if k != action.name})


def clear_meshes(doc: Document, _action: ClearMeshes) -> Document:
    """clearMeshes: back to the initial (empty) mesh state."""
    if not doc.meshes:
        return doc
    return doc.with_(meshes={})
