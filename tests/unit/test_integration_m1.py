"""M1 integration: real project load -> deck scene build -> save -> reload.

Exercises the seams between the four M1 modules on both example regions:
io.project (load/save), model (Document/SegmentGraph), and deck
(register_all + default_display building every layer group).
"""

from __future__ import annotations

import json
import math

from celeri_builder.deck.display import default_display
from celeri_builder.deck.scene import register_all
from celeri_builder.io.project import load_project, save_project

TOL = 1e-6


def _values_close(a: object, b: object) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, bool) or isinstance(b, bool):
            return a == b
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=TOL)
    return a == b


def _find_layer(descriptors: list[dict], layer_id: str) -> dict:
    matches = [d for d in descriptors if d["id"] == layer_id]
    assert len(matches) == 1, f"expected exactly one {layer_id!r} descriptor"
    return matches[0]


def test_scene_builds_all_groups_from_real_project(example_project):
    doc, _refs = load_project(example_project)
    scene = register_all()
    built = scene.build_all(doc, default_display())

    expected_groups = {
        "graticule",
        "meshes",
        "dip_projection",
        "generic",
        "segments",
        "velocities",
        "vertices",
        "blocks",
        "labels",  # M4 plottableKey text (empty with no plotted value chosen)
        "overlay",  # M2 selection/lasso overlay (empty with no selection)
    }
    assert set(built) == expected_groups
    assert set(scene.group_names()) == expected_groups

    for group, descriptors in built.items():
        assert isinstance(descriptors, list), group
        for desc in descriptors:
            assert isinstance(desc, dict), group
            assert "type" in desc
            assert "id" in desc
            assert "data" in desc
        # Everything must survive the trame state channel.
        json.dumps(descriptors)

    # Segments group carries one row per segment (visible + hit pick layer).
    n_segments = len(doc.segments.segments)
    assert n_segments > 0
    assert len(_find_layer(built["segments"], "segments")["data"]) == n_segments
    assert len(_find_layer(built["segments"], "segments_hit")["data"]) == n_segments

    # Non-empty document slices produce non-empty layer groups.
    assert len(_find_layer(built["vertices"], "vertices")["data"]) == len(
        doc.segments.vertices
    )
    assert built["blocks"] if doc.blocks else True
    assert built["velocities"] if doc.velocities else True
    assert built["meshes"] if doc.meshes else True


def test_save_reload_semantic_equality(example_project):
    doc, refs = load_project(example_project)
    save_project(doc, refs)
    doc2, _refs2 = load_project(example_project)

    # Segment endpoints and remaining columns survive within 1e-6.
    rows1 = doc.segments.expand_rows()
    rows2 = doc2.segments.expand_rows()
    assert len(rows1) == len(rows2)
    for r1, r2 in zip(rows1, rows2, strict=True):
        assert set(r1) == set(r2)
        for key in ("lon1", "lat1", "lon2", "lat2"):
            assert math.isclose(r1[key], r2[key], rel_tol=0.0, abs_tol=TOL), key
        for key in r1:
            assert _values_close(r1[key], r2[key]), key

    # Block and velocity rows survive field-for-field.
    assert len(doc.blocks) == len(doc2.blocks)
    for b1, b2 in zip(doc.blocks, doc2.blocks, strict=True):
        assert set(b1) == set(b2)
        for key in b1:
            assert _values_close(b1[key], b2[key]), key

    assert len(doc.velocities) == len(doc2.velocities)
    for v1, v2 in zip(doc.velocities, doc2.velocities, strict=True):
        assert set(v1) == set(v2)
        for key in v1:
            assert _values_close(v1[key], v2[key]), key

    # Command keys (including unknown ones) and their order fully preserved.
    assert list(doc2.command) == list(doc.command)
    assert doc2.command == doc.command


def test_saved_project_scene_matches_original(example_project):
    """The reloaded document draws the same number of segment rows."""
    doc, refs = load_project(example_project)
    save_project(doc, refs)
    doc2, _ = load_project(example_project)

    scene = register_all()
    display = default_display()
    before = _find_layer(
        scene.build(["segments"], doc, display)["segments"], "segments"
    )
    after = _find_layer(
        scene.build(["segments"], doc2, display)["segments"], "segments"
    )
    assert len(before["data"]) == len(after["data"])
