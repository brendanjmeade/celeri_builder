"""M2 integration: CeleriBuilderApp wiring of Store, selection, panels, files.

Runs the real app headless (no server start): dispatch/undo/redo through the
Store, selection -> merged ``selection_fields``, debounced property edits,
map-click routing through MapController, and per-kind open/save.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from trame.app import get_server

from celeri_builder.app import core, settings
from celeri_builder.deck.display import default_display
from celeri_builder.io.segment_io import read_segments
from celeri_builder.model import actions as act


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CELERI_BUILDER_TESTING", "1")
    monkeypatch.setenv("CELERI_BUILDER_NO_BASEMAP", "1")
    # Keep the user's persisted display settings out of the tests.
    monkeypatch.setattr(settings, "load", lambda defaults: defaults)
    monkeypatch.setattr(settings, "save", lambda _display: None)
    server = get_server(f"core-m2-{uuid.uuid4().hex}", client_type="vue3")
    return core.CeleriBuilderApp(server=server, root_dir=tmp_path)


def _make_two_segments(app):
    app.dispatch(
        act.CreateSegment(start=(10.0, 10.0), end=(20.0, 20.0)), dirty=("segment",)
    )
    app.dispatch(
        act.CreateSegment(start=(20.0, 20.0), end=(30.0, 30.0), props={"name": "b"}),
        dirty=("segment",),
    )


# -- boot ---------------------------------------------------------------------


def test_boot_defaults(app):
    state = app.state
    assert state.selection == {"kind": None, "ids": []}
    assert state.selection_fields == {}
    assert state.command_fields == {}
    assert state.lasso_points == []
    assert state.inspector_tab == "command"
    assert state.inspector_open is False
    assert state.can_undo is False
    assert state.can_redo is False
    assert "overlay" in core.GROUPS
    assert state["deck_layers_overlay"] == []


# -- store wiring ----------------------------------------------------------------


def test_dispatch_marks_dirty_and_history(app):
    changed = app.dispatch(act.CreateBlock(props={"name": "blk"}), dirty=("block",))
    assert changed is True
    assert len(app.doc.blocks) == 1
    assert app.state.can_undo is True
    assert app.state.dirty_kinds == ["block"]
    probe = app.state.test_probe
    assert probe["undo_depth"] == 1
    assert probe["redo_depth"] == 0
    assert probe["counts"]["blocks"] == 1


def test_noop_dispatch_adds_no_history(app):
    assert app.dispatch(act.DeleteBlocks(indices=(5,)), dirty=("block",)) is False
    assert app.state.can_undo is False
    assert app.state.dirty_kinds == []


def test_undo_redo_roundtrip(app):
    app.dispatch(act.CreateVelocity(props={"name": "v"}), dirty=("station",))
    assert len(app.doc.velocities) == 1
    app.on_undo()
    assert len(app.doc.velocities) == 0
    assert app.state.can_undo is False
    assert app.state.can_redo is True
    app.on_redo()
    assert len(app.doc.velocities) == 1
    assert app.state.test_probe["undo_depth"] == 1


def test_undo_prunes_stale_selection(app):
    _make_two_segments(app)
    app.select("segment", [1])
    app.on_undo()  # second segment gone
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.state.selection_fields == {}


# -- selection -> merged fields ----------------------------------------------------


def test_select_single_segment_fields(app):
    _make_two_segments(app)
    app.select("segment", [1])
    state = app.state
    assert state.selection == {"kind": "segment", "ids": [1]}
    fields = state.selection_fields
    assert fields["name"] == "b"
    assert fields["dip"] == 90.0
    for hidden in ("lon1", "lat1", "lon2", "lat2", "start", "end"):
        assert hidden not in fields
    assert next(iter(fields)) == "name"
    assert state.inspector_tab == "segment"
    assert state.inspector_open is True
    # highlight overlay carries the selected segment
    assert state["deck_layers_overlay"]


def test_select_multi_mixed_marker(app):
    _make_two_segments(app)
    app.select("segment", [0, 1])
    fields = app.state.selection_fields
    assert fields["name"] == "-"  # 'new_segment' vs 'b'
    assert fields["dip"] == 90.0  # equal values stay merged


def test_select_additive_union(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.select("segment", [1], additive=True)
    assert app.state.selection == {"kind": "segment", "ids": [0, 1]}


def test_select_vertex_fields(app):
    _make_two_segments(app)
    vid = next(iter(app.doc.segments.vertices))
    app.select("vertex", [vid])
    lon, lat = app.doc.segments.vertices[vid]
    assert app.state.selection_fields == {"lon": lon, "lat": lat}
    ids = list(app.doc.segments.vertices)[:2]
    app.select("vertex", ids)
    assert app.state.selection_fields == {"lon": "-", "lat": "-"}


def test_select_empty_clears(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.select("segment", [])
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.state.selection_fields == {}


# -- property editing --------------------------------------------------------------


def test_edit_selection_numeric_flushes_headless(app):
    _make_two_segments(app)
    app.select("segment", [0, 1])
    depth_before = app.state.test_probe["undo_depth"]
    app.edit_selection("dip", 45)  # no running loop -> immediate flush
    assert all(seg["dip"] == 45 for seg in app.doc.segments.segments)
    assert app.state.selection_fields["dip"] == 45
    assert app.state.test_probe["undo_depth"] == depth_before + 1
    assert "segment" in app.state.dirty_kinds


def test_edit_selection_string_immediate(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.edit_selection("name", "renamed")
    assert app.doc.segments.segments[0]["name"] == "renamed"
    assert app.state.selection_fields["name"] == "renamed"


def test_edit_selection_coerces_string_number(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.edit_selection("locking_depth", "25.5")
    assert app.doc.segments.segments[0]["locking_depth"] == 25.5
    app.edit_selection("locking_depth", "junk")  # unparsable -> ignored
    assert app.doc.segments.segments[0]["locking_depth"] == 25.5


def test_edit_vertex_moves_it(app):
    _make_two_segments(app)
    vid = next(iter(app.doc.segments.vertices))
    app.select("vertex", [vid])
    app.edit_selection("lat", 12.5)
    assert app.doc.segments.vertices[vid][1] == 12.5
    assert app.state.selection_fields["lat"] == 12.5
    assert "segment" in app.state.dirty_kinds


def test_edit_command_coerced_and_dirty(app):
    app.dispatch(act.LoadCommand(data={"n_iter": 10, "run_name": "x"}), groups=())
    app.edit_command("n_iter", "12")
    assert app.doc.command["n_iter"] == 12  # int template stays int
    assert app.state.command_fields["n_iter"] == 12
    assert "command" in app.state.dirty_kinds
    app.edit_command("run_name", "y")
    assert app.doc.command["run_name"] == "y"


def test_command_fields_exclude_file_refs(app):
    app.dispatch(
        act.LoadCommand(
            data={
                "file_name": "cfg.json",
                "segment_file_name": "../segment/s.csv",
                "n_iter": 1,
            }
        ),
        groups=(),
    )
    fields = app.state.command_fields
    assert "segment_file_name" not in fields
    assert fields["file_name"] == "cfg.json"  # panel title uses it
    assert fields["n_iter"] == 1


def test_delete_selection(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.delete_selection()
    assert len(app.doc.segments.segments) == 1
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.doc.segments.segments[0]["name"] == "b"


def test_split_selection(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.split_selection()
    assert len(app.doc.segments.segments) == 3
    assert app.state.test_probe["undo_depth"] == 3  # 2 creates + 1 split


# -- mesh / generic handlers ---------------------------------------------------------


def test_generic_key_mapping_and_removal(app, data_dir):
    csv_path = data_dir / "segment" / "japan_segment.csv"
    app._load_kind("generic", csv_path)
    cols = app.state.generic_collections
    assert len(cols) == 1
    assert cols[0]["name"] == "japan_segment.csv"
    assert "lon1" in cols[0]["columns"]
    app.set_generic_keys("japan_segment.csv", "start_lon_key", "lon1")
    assert app.doc.generic["japan_segment.csv"].start_lon_key == "lon1"
    assert app.state.generic_collections[0]["keys"]["start_lon_key"] == "lon1"
    app.remove_generic("japan_segment.csv")
    assert app.state.generic_collections == []


def test_mesh_load_and_remove(app, data_dir):
    msh = data_dir / "mesh" / "japan.msh"
    if not msh.is_file():
        pytest.skip("japan.msh not present")
    app._load_kind("mesh", msh)
    assert app.state.mesh_names == ["japan.msh"]
    app.remove_mesh("japan.msh")
    assert app.state.mesh_names == []
    app.on_undo()
    assert app.state.mesh_names == ["japan.msh"]


# -- map events ------------------------------------------------------------------------


def test_map_click_selects_and_normalizes_tab(app):
    app.dispatch(act.CreateVelocity(props={"name": "v0"}), dirty=("station",))
    app.on_map_click(
        {
            "picked": True,
            "layerId": "velocities",
            "index": 0,
            "coordinate": [140.0, 35.0],
        }
    )
    assert app.state.selection == {"kind": "velocity", "ids": [0]}
    assert app.state.inspector_tab == "velocities"  # tab name, not kind
    assert app.state.test_probe["last_pick"]["layerId"] == "velocities"


def test_map_click_background_keeps_selection(app):
    _make_two_segments(app)
    app.select("segment", [0])
    app.on_map_click({"picked": False, "coordinate": [1.0, 2.0]})
    assert app.state.selection == {"kind": "segment", "ids": [0]}


def test_lasso_click_and_escape(app):
    app.on_toggle_lasso()
    assert app.state.selection_mode == "lasso"
    app.on_map_click({"picked": False, "coordinate": [10.0, 10.0]})
    app.on_map_click({"picked": False, "coordinate": [-350.0, 12.0]})
    assert app.state.lasso_points == [[10.0, 10.0], [10.0, 12.0]]
    app.on_map_key({"key": "Escape"})
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []


def test_arm_new_and_vertex_op_set_mode_and_hint(app):
    app.arm_new("segment")
    assert app.state.selection_mode == "mapClick"
    assert "segment" in app.state.mode_hint
    app.controller.cancel()
    assert app.state.selection_mode == "normal"

    # vertex ops require a single selected vertex (else no-op)
    app.arm_vertex_op("merge")
    assert app.state.selection_mode == "normal"  # nothing selected: no-op

    _make_two_segments(app)
    vid = next(iter(app.doc.segments.vertices))
    app.select("vertex", [vid])
    app.arm_vertex_op("merge")
    assert app.state.selection_mode == "override"
    app.controller.cancel()
    app.arm_vertex_op("extrude")
    assert app.state.selection_mode == "mapClick"


# -- project / files ---------------------------------------------------------------------


def test_open_config_populates(app, example_project):
    app.open_config(example_project)
    probe = app.state.test_probe
    assert probe["counts"]["segments"] > 0
    assert probe["counts"]["vertices"] > 0
    assert app.state.can_undo is False
    assert app.state.dirty_kinds == []
    assert app.state.command_fields  # unknown keys included
    assert "segment_file_name" not in app.state.command_fields
    assert isinstance(app.state.mesh_names, list)
    assert app.state.folder_label.endswith("_config.json")


def test_save_kind_roundtrip(app, example_project):
    app.open_config(example_project)
    app.select("segment", [0])
    app.edit_selection("dip", 33.0)
    assert app.state.dirty_kinds == ["segment"]
    app.save_kind("segment")
    assert app.state.dirty_kinds == []
    graph = read_segments(app.refs.paths["segment"].read_text())
    assert graph.segments[0]["dip"] == 33.0


def test_save_all_writes_dirty_kinds(app, example_project):
    app.open_config(example_project)
    app.select("block", [0])
    app.edit_selection("name", "renamed_block")
    assert app.state.dirty_kinds == ["block"]
    app.on_save_all()
    assert app.state.dirty_kinds == []
    assert "renamed_block" in app.refs.paths["block"].read_text()


def test_save_kind_as_rewrites_command_ref(app, example_project):
    app.open_config(example_project)
    target = example_project.parent / "renamed_segment.csv"
    app._save_as("segment", target)
    assert target.is_file()
    assert app.refs.paths["segment"] == target
    assert app.doc.command["segment_file_name"] == "renamed_segment.csv"
    assert "command" in app.state.dirty_kinds


def test_load_kind_replaces_slice(app, example_project):
    segment_csv = example_project.parent.parent / "segment"
    path = next(iter(segment_csv.glob("*_segment.csv")))
    app._load_kind("segment", Path(path))
    assert len(app.doc.segments.segments) > 0
    assert app.refs.paths["segment"] == Path(path)
    assert app.state.dirty_kinds == []  # freshly loaded == on-disk content
    assert app.state.can_undo is True  # loads are undoable


def test_display_toggle_rebuilds_overlay(app):
    _make_two_segments(app)
    app.select("segment", [0])
    assert app.state["deck_layers_overlay"]
    app.on_toggle_display("segment")  # hide segments -> highlight suppressed
    assert app.state.display["segment"]["hide"] is True
    assert app.state["deck_layers_overlay"] == []


def test_map_style_preset(app):
    app.update_display("map", "styleName", "none")
    assert app.state.deck_map_style is None
    app.update_display("map", "styleName", "carto")
    assert app.state.deck_map_style == core.mapbox.CARTO_POSITRON_STYLE_URL


def test_default_display_untouched_by_boot(app):
    # settings.load was stubbed to identity: display matches defaults exactly.
    assert app.state.display == default_display()
