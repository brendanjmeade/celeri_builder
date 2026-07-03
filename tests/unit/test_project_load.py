"""Whole-project load/save via the config file."""

from __future__ import annotations

import json

import pytest

# segment/block/velocity io are authored by a parallel M1 task; skip
# cleanly if they have not landed yet (the integrate stage re-runs all).
pytest.importorskip("celeri_builder.io.segment_io")
pytest.importorskip("celeri_builder.io.block_io")
pytest.importorskip("celeri_builder.io.velocity_io")

from celeri_builder.io.project import (
    load_project,
    save_project,
)

# japan_mesh.json references 4 meshes (nankai, japan, sagami,
# japan_mock_cmi); wna_mesh.json references cascadia only.
EXPECTED_MESH_COUNT = {"japan": 4, "wna": 1}


def _assert_rows_equal(rows_a, rows_b):
    """Semantic row equality: floats within 1e-6, everything else exact."""
    assert len(rows_a) == len(rows_b)
    for row_a, row_b in zip(rows_a, rows_b, strict=True):
        assert set(row_a) == set(row_b)
        for key, value_a in row_a.items():
            value_b = row_b[key]
            numeric = all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in (value_a, value_b)
            )
            if numeric:
                assert value_b == pytest.approx(value_a, abs=1e-6), key
            else:
                assert value_b == value_a, key


def test_load_document(example_project, region, raw_text):
    document, refs = load_project(example_project)

    assert len(document.segments.segments) > 0
    assert len(document.blocks) > 0
    assert len(document.velocities) > 0

    assert len(document.meshes) == EXPECTED_MESH_COUNT[region]
    for name, mesh in document.meshes.items():
        assert name.endswith(".msh")  # keyed by mesh_filename basename
        assert mesh.params["mesh_filename"].endswith(name)  # params verbatim
        assert mesh.triangles.shape[0] > 0

    # vertex sharing happened: strictly fewer vertices than endpoints
    n_segments = len(document.segments.segments)
    assert len(document.segments.vertices) < 2 * n_segments

    # command keeps ALL original keys, in original order
    original = json.loads(raw_text("config", region))
    assert list(document.command) == list(original)
    assert document.command == original

    assert refs.config_path == example_project.resolve()
    assert set(refs.paths) == {"segment", "block", "station", "mesh_params"}
    assert all(path.is_file() for path in refs.paths.values())
    assert refs.dirty == set()


def test_missing_reference_raises(tmp_path):
    config = {"segment_file_name": "../segment/does_not_exist.csv"}
    config_path = tmp_path / "broken_config.json"
    config_path.write_text(json.dumps(config))
    with pytest.raises(FileNotFoundError, match="does_not_exist"):
        load_project(config_path)


def test_null_and_absent_references_skipped(tmp_path):
    config = {"segment_file_name": None, "station_file_name": ""}
    config_path = tmp_path / "empty_config.json"
    config_path.write_text(json.dumps(config))
    document, refs = load_project(config_path)
    assert document.segments.segments == ()
    assert document.blocks == ()
    assert document.velocities == ()
    assert document.meshes == {}
    assert refs.paths == {}


def test_save_project_reloads_equal(example_project):
    document, refs = load_project(example_project)
    save_project(document, refs)
    reloaded, _ = load_project(example_project)

    assert reloaded.command == document.command
    assert list(reloaded.command) == list(document.command)
    _assert_rows_equal(document.blocks, reloaded.blocks)
    _assert_rows_equal(document.velocities, reloaded.velocities)
    _assert_rows_equal(document.segments.expand_rows(), reloaded.segments.expand_rows())
    assert len(reloaded.segments.vertices) == len(document.segments.vertices)
    assert set(reloaded.meshes) == set(document.meshes)


def test_saved_command_keeps_relative_paths(example_project, region):
    document, refs = load_project(example_project)
    save_project(document, refs, kinds=["command"])
    saved = json.loads(example_project.read_text())
    assert saved["segment_file_name"] == f"../segment/{region}_segment.csv"
    assert saved["block_file_name"] == f"../block/{region}_block.csv"
    assert saved["station_file_name"] == f"../station/{region}_station.csv"
    assert saved["mesh_parameters_file_name"] == f"../mesh/{region}_mesh.json"


def test_save_clears_dirty_for_saved_kinds_only(example_project):
    document, refs = load_project(example_project)
    refs.dirty = {"segment", "command"}
    save_project(document, refs, kinds=["segment"])
    assert refs.dirty == {"command"}


def test_save_unknown_kind_raises(example_project):
    document, refs = load_project(example_project)
    with pytest.raises(ValueError, match="unknown save kind"):
        save_project(document, refs, kinds=["mesh"])
