"""Project-level load/save: a config file plus everything it references.

Intentional differences from celeri_ui (documented in the plan):

- Referenced paths are resolved relative to the CONFIG FILE's directory
  (celeri_ui's ``GetProjectFile`` munging could not resolve ``../``).
- A referenced-but-missing file raises ``FileNotFoundError`` instead of
  silently creating an empty file.
- Unknown command keys are preserved (see :mod:`command_io`).

celeri_ui parity that IS kept: ``mogi_file_name``/``sar_file_name`` are
not loaded; meshes, mesh parameters, and generic overlays are read-only
and never written by :func:`save_project`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from celeri_builder.io.block_io import read_blocks, write_blocks
from celeri_builder.io.command_io import read_command, write_command
from celeri_builder.io.mesh_io import read_mesh_params, read_msh
from celeri_builder.io.segment_io import read_segments, write_segments
from celeri_builder.io.velocity_io import read_velocities, write_velocities
from celeri_builder.model.document import Document, Mesh
from celeri_builder.model.vertex_graph import SegmentGraph

#: Kinds save_project can write (everything else is read-only).
SAVABLE_KINDS: tuple[str, ...] = ("segment", "block", "station", "command")

#: FileRefs.paths key -> command key that references the file.
FILE_NAME_KEYS: dict[str, str] = {
    "segment": "segment_file_name",
    "block": "block_file_name",
    "station": "station_file_name",
    "mesh_params": "mesh_parameters_file_name",
}


@dataclass
class FileRefs:
    """Where the project's files live on disk + which kinds are unsaved.

    NOT part of the undoable :class:`Document` — file handles and dirty
    flags are session state (intentional difference from celeri_ui).
    """

    config_path: Path
    paths: dict[str, Path] = field(default_factory=dict)
    dirty: set[str] = field(default_factory=set)


def _resolve_ref(parent: Path, value: str, key: str) -> Path:
    path = (parent / value).resolve()
    if not path.is_file():
        msg = f"{key} references a missing file: {path}"
        raise FileNotFoundError(msg)
    return path


def _load_meshes(params_path: Path) -> dict[str, Mesh]:
    meshes: dict[str, Mesh] = {}
    for entry in read_mesh_params(params_path.read_text()):
        mesh_filename = entry.get("mesh_filename")
        if not mesh_filename:
            continue
        name = PurePosixPath(mesh_filename).name
        mesh_path = (params_path.parent / mesh_filename).resolve()
        if not mesh_path.is_file():
            msg = f"mesh_filename references a missing file: {mesh_path}"
            raise FileNotFoundError(msg)
        meshes[name] = read_msh(mesh_path.read_text(), name=name, params=entry)
    return meshes


def load_project(config_path: Path | str) -> tuple[Document, FileRefs]:
    """Read a config JSON and every file it references into a Document.

    Null/absent/empty file references are skipped (celeri_ui parity);
    referenced-but-missing files raise ``FileNotFoundError``.
    """
    config_path = Path(config_path).resolve()
    command = read_command(config_path.read_text())
    parent = config_path.parent

    paths: dict[str, Path] = {}
    for kind, key in FILE_NAME_KEYS.items():
        value = command.get(key)
        if not value:
            continue
        paths[kind] = _resolve_ref(parent, value, key)

    segments = SegmentGraph()
    if "segment" in paths:
        segments = read_segments(paths["segment"].read_text())
    blocks: tuple[dict, ...] = ()
    if "block" in paths:
        blocks = tuple(read_blocks(paths["block"].read_text()))
    velocities: tuple[dict, ...] = ()
    if "station" in paths:
        velocities = tuple(read_velocities(paths["station"].read_text()))
    meshes: dict[str, Mesh] = {}
    if "mesh_params" in paths:
        meshes = _load_meshes(paths["mesh_params"])

    document = Document(
        segments=segments,
        blocks=blocks,
        velocities=velocities,
        meshes=meshes,
        command=command,
    )
    return document, FileRefs(config_path=config_path, paths=paths)


def save_project(
    document: Document,
    refs: FileRefs,
    kinds: Iterable[str] | None = None,
) -> None:
    """Write the requested kinds back to their original paths.

    ``kinds`` defaults to all of :data:`SAVABLE_KINDS`. The command JSON
    is written with its ORIGINAL relative file-name values unchanged
    (``document.command`` is never path-munged). Kinds whose file was
    never referenced are skipped. Meshes/mesh-params/generic overlays
    are never written.
    """
    selected = tuple(SAVABLE_KINDS if kinds is None else kinds)
    for kind in selected:
        if kind not in SAVABLE_KINDS:
            msg = f"unknown save kind {kind!r}; expected one of {SAVABLE_KINDS}"
            raise ValueError(msg)
        if kind == "command":
            refs.config_path.write_text(write_command(document.command))
        elif kind == "segment" and "segment" in refs.paths:
            refs.paths["segment"].write_text(write_segments(document.segments))
        elif kind == "block" and "block" in refs.paths:
            refs.paths["block"].write_text(write_blocks(document.blocks))
        elif kind == "station" and "station" in refs.paths:
            refs.paths["station"].write_text(write_velocities(document.velocities))
        refs.dirty.discard(kind)
