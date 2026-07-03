"""M3 geometry-editing engine tests: drive the real CeleriBuilderApp headless.

Exercises the full interaction pipeline (widget event -> MapController ->
app dispatch) for drag-to-move, click-to-create, and the vertex operations,
asserting document mutations, shared-vertex reuse, auto-merge on drop, and
that every gesture is exactly ONE undo entry that undo restores.
"""

from __future__ import annotations

import uuid

import pytest
from trame.app import get_server

from celeri_builder.app import core, settings
from celeri_builder.model import actions as act


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CELERI_BUILDER_TESTING", "1")
    monkeypatch.setenv("CELERI_BUILDER_NO_BASEMAP", "1")
    monkeypatch.setattr(settings, "load", lambda defaults: defaults)
    monkeypatch.setattr(settings, "save", lambda _display: None)
    server = get_server(f"core-m3-{uuid.uuid4().hex}", client_type="vue3")
    return core.CeleriBuilderApp(server=server, root_dir=tmp_path)


# -- helpers ------------------------------------------------------------------


def click(app, lon, lat, *, picked=False, layer_id=None, index=-1):
    """Route a map click through the widget-event entry point."""
    app.on_map_click(
        {
            "picked": picked,
            "layerId": layer_id,
            "index": index,
            "coordinate": [lon, lat],
        }
    )


def drag_end(app, layer_id, index, lon, lat):
    """Route a widget dragend (drop) through the entry point."""
    app.on_map_dragend(
        {
            "coordinate": [lon, lat],
            "startCoordinate": [0.0, 0.0],
            "layerId": layer_id,
            "index": index,
        }
    )


def undo_depth(app) -> int:
    return app.state.test_probe["undo_depth"]


def two_segments(app):
    """(140,35)-(141,36) and (142,37)-(143,38): vertices 0,1,2,3."""
    app.dispatch(
        act.CreateSegment(start=(140.0, 35.0), end=(141.0, 36.0)), dirty=("segment",)
    )
    app.dispatch(
        act.CreateSegment(start=(142.0, 37.0), end=(143.0, 38.0)), dirty=("segment",)
    )


# -- drag layers track the active edit mode -----------------------------------


def test_drag_layers_track_edit_mode(app):
    assert app.state.deck_drag_layers == ["vertices"]  # default vertex mode
    # The running server fires the edit_mode change watcher; headless we invoke
    # its body directly to prove the mode -> draggable-layer mapping. (The
    # registration is exercised end-to-end by the UI gate.)
    for mode, expected in (
        ("block", ["blocks"]),
        ("velocities", ["velocities"]),
        ("segment", ["vertices"]),  # segments mode drags shared vertices
        ("vertex", ["vertices"]),
    ):
        app.state.edit_mode = mode
        app._on_edit_mode()
        assert app.state.deck_drag_layers == expected
        assert app.state.test_probe["drag_layers"] == expected


# -- two-click segment creation + shared-vertex reuse -------------------------


def test_two_click_segment_creation_and_shared_vertex(app):
    app.arm_new("segment")
    assert app.state.selection_mode == "mapClick"
    assert "start" in app.state.mode_hint.lower()

    click(app, 140.0, 35.0)  # start click re-arms, does not create yet
    assert app.state.selection_mode == "mapClick"
    assert "end" in app.state.mode_hint.lower()
    assert len(app.doc.segments.segments) == 0

    click(app, 141.0, 36.0)  # end click creates the segment
    assert app.state.selection_mode == "normal"
    assert app.state.mode_hint == ""
    assert len(app.doc.segments.segments) == 1
    assert len(app.doc.segments.vertices) == 2
    assert undo_depth(app) == 1  # exactly ONE undo entry

    # second segment: FIRST click lands on the existing endpoint (141,36)
    app.arm_new("segment")
    click(app, 141.0, 36.0)  # reuses the shared vertex
    click(app, 142.0, 37.0)  # only this endpoint is new
    assert len(app.doc.segments.segments) == 2
    assert len(app.doc.segments.vertices) == 3  # +1, not +2 (shared reuse)
    assert undo_depth(app) == 2

    app.on_undo()  # undo restores counts
    assert len(app.doc.segments.segments) == 1
    assert len(app.doc.segments.vertices) == 2


def test_escape_cancels_armed_segment_without_creating(app):
    app.arm_new("segment")
    click(app, 140.0, 35.0)  # first click only
    app.on_map_key({"key": "Escape"})
    assert app.state.selection_mode == "normal"
    assert app.state.mode_hint == ""
    assert len(app.doc.segments.segments) == 0
    assert undo_depth(app) == 0


# -- one-click block / velocity creation --------------------------------------


def test_block_one_click_create(app):
    app.arm_new("block")
    assert app.state.selection_mode == "mapClick"
    click(app, 145.0, 40.0)
    assert app.state.selection_mode == "normal"
    assert len(app.doc.blocks) == 1
    assert app.doc.blocks[0]["interior_lon"] == 145.0
    assert app.doc.blocks[0]["interior_lat"] == 40.0
    assert undo_depth(app) == 1
    app.on_undo()
    assert len(app.doc.blocks) == 0


def test_velocity_one_click_create(app):
    app.arm_new("velocity")
    click(app, 146.0, 41.0)
    assert app.state.selection_mode == "normal"
    assert len(app.doc.velocities) == 1
    assert app.doc.velocities[0]["lon"] == 146.0
    assert app.doc.velocities[0]["lat"] == 41.0
    assert undo_depth(app) == 1
    app.on_undo()
    assert len(app.doc.velocities) == 0


def test_create_normalizes_western_longitude(app):
    app.arm_new("velocity")
    click(app, -170.0, 20.0)  # widget delivers raw lon; controller -> 0..360
    assert app.doc.velocities[0]["lon"] == 190.0


# -- drag vertex: move, endpoint follows, auto-merge on drop ------------------


def test_drag_vertex_moves_endpoint_follows_and_automerges(app):
    two_segments(app)
    assert len(app.doc.segments.vertices) == 4
    depth = undo_depth(app)

    # drag vertex row 0 (id 0) to an empty spot -> plain move
    drag_end(app, "vertices", 0, 150.0, 50.0)
    assert app.doc.segments.vertices[0] == (150.0, 50.0)
    assert len(app.doc.segments.vertices) == 4
    assert undo_depth(app) == depth + 1  # ONE undo entry per drop

    # the attached segment endpoint followed the vertex
    start_lonlat, _ = app.doc.segments.segment_endpoints(app.doc.segments.segments[0])
    assert start_lonlat == (150.0, 50.0)

    # drop vertex 0 onto vertex 1's cell (141,36) -> auto-merge, one fewer vertex
    drag_end(app, "vertices", 0, 141.0, 36.0)
    assert len(app.doc.segments.vertices) == 3  # vertex 1 merged away
    assert 1 not in app.doc.segments.vertices
    # segments repointed onto the surviving vertex
    seg0 = app.doc.segments.segments[0]
    assert seg0["start"] == 0
    assert seg0["end"] == 0
    assert undo_depth(app) == depth + 2

    app.on_undo()  # undo the merge-drop
    assert len(app.doc.segments.vertices) == 4


def test_zero_movement_drop_is_a_noop(app):
    two_segments(app)
    depth = undo_depth(app)
    # a drop whose start cell equals the drop cell is a click, not a drag:
    # deck can fire a zero-movement dragend over an already-hovered point.
    app.on_map_dragend(
        {
            "coordinate": [140.0, 35.0],
            "startCoordinate": [140.0, 35.0],
            "layerId": "vertices",
            "index": 0,
        }
    )
    assert undo_depth(app) == depth  # no spurious undo entry
    assert app.doc.segments.vertices[0] == (140.0, 35.0)


def test_drag_block_and_velocity_move_rows(app):
    app.dispatch(act.CreateBlock(props={"name": "b"}), dirty=("block",))
    app.dispatch(act.CreateVelocity(props={"name": "v"}), dirty=("station",))
    depth = undo_depth(app)

    drag_end(app, "blocks", 0, 155.0, 44.0)
    assert app.doc.blocks[0]["interior_lon"] == 155.0
    assert app.doc.blocks[0]["interior_lat"] == 44.0
    assert undo_depth(app) == depth + 1

    drag_end(app, "velocities", 0, 156.0, 45.0)
    assert app.doc.velocities[0]["lon"] == 156.0
    assert app.doc.velocities[0]["lat"] == 45.0
    assert undo_depth(app) == depth + 2


# -- vertex operations: extrude / merge / bridge ------------------------------


def test_extrude_from_selected_vertex(app):
    app.dispatch(
        act.CreateSegment(start=(140.0, 35.0), end=(141.0, 36.0)), dirty=("segment",)
    )
    app.select("vertex", [0])
    app.arm_vertex_op("extrude")
    assert app.state.selection_mode == "mapClick"
    depth = undo_depth(app)

    click(app, 150.0, 45.0)  # extrude target
    assert app.state.selection_mode == "normal"
    assert len(app.doc.segments.segments) == 2
    assert len(app.doc.segments.vertices) == 3
    new_seg = app.doc.segments.segments[-1]
    assert new_seg["start"] == 0
    assert app.doc.segments.vertices[new_seg["end"]] == (150.0, 45.0)
    assert undo_depth(app) == depth + 1

    app.on_undo()
    assert len(app.doc.segments.segments) == 1
    assert len(app.doc.segments.vertices) == 2


def test_merge_via_override_second_pick(app):
    two_segments(app)
    app.select("vertex", [0])  # keep
    app.arm_vertex_op("merge")
    assert app.state.selection_mode == "override"
    depth = undo_depth(app)

    # pick vertex row 2 (id 2) as the vertex to merge away
    click(app, 142.0, 37.0, picked=True, layer_id="vertices", index=2)
    assert app.state.selection_mode == "normal"
    assert len(app.doc.segments.vertices) == 3  # vertex 2 merged into 0
    assert app.doc.segments.segments[1]["start"] == 0  # repointed from 2
    assert undo_depth(app) == depth + 1

    app.on_undo()
    assert len(app.doc.segments.vertices) == 4


def test_bridge_via_override_second_pick(app):
    two_segments(app)
    app.select("vertex", [0])  # a
    app.arm_vertex_op("bridge")
    assert app.state.selection_mode == "override"
    depth = undo_depth(app)

    click(app, 143.0, 38.0, picked=True, layer_id="vertices", index=3)  # b = id 3
    assert app.state.selection_mode == "normal"
    assert len(app.doc.segments.segments) == 3  # bridge segment added
    assert len(app.doc.segments.vertices) == 4  # no new vertices
    new_seg = app.doc.segments.segments[-1]
    assert {new_seg["start"], new_seg["end"]} == {0, 3}
    assert undo_depth(app) == depth + 1

    app.on_undo()
    assert len(app.doc.segments.segments) == 2


def test_vertex_op_without_selection_is_noop(app):
    two_segments(app)
    for op in ("merge", "bridge", "extrude"):
        app.arm_vertex_op(op)
        assert app.state.selection_mode == "normal"  # nothing armed
        assert app.controller.armed is None


def test_override_ignores_wrong_kind_pick(app):
    two_segments(app)
    app.select("vertex", [0])
    app.arm_vertex_op("merge")
    # a block pick must not reach the merge callback
    click(app, 150.0, 40.0, picked=True, layer_id="blocks", index=0)
    assert app.state.selection_mode == "override"  # still armed, no merge
    assert len(app.doc.segments.vertices) == 4


# -- split (already wired) still one entry with _a/_b names -------------------


def test_split_produces_a_b_names_and_one_entry(app):
    app.dispatch(
        act.CreateSegment(
            start=(140.0, 35.0), end=(141.0, 36.0), props={"name": "seg"}
        ),
        dirty=("segment",),
    )
    app.select("segment", [0])
    depth = undo_depth(app)
    app.split_selection()
    assert len(app.doc.segments.segments) == 2
    names = app.state.test_probe["segment_names"]
    assert any(n.endswith("_a") for n in names)
    assert any(n.endswith("_b") for n in names)
    assert undo_depth(app) == depth + 1
