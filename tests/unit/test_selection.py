"""Selection dispatch + overlay tests.

Ports celeri_ui mocha/tests/SelectionMode.spec.ts one-for-one against the
pure ``select_dispatch`` helper and the MapController's non-trame parts
(the app is faked with a dict-backed state duck type), then covers the
'overlay' layer group (selection highlights + in-progress lasso polygon).
"""

from __future__ import annotations

import pytest

from celeri_builder.app.interaction import LAYER_KINDS, MapController, select_dispatch
from celeri_builder.deck.display import default_display
from celeri_builder.deck.layers import selection as selection_layer
from celeri_builder.deck.primitives import SHIFT_SUFFIX
from celeri_builder.deck.scene import register_all
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import SegmentGraph, build_graph, vertex_key

EMPTY = {"kind": None, "ids": []}


# -- fakes ---------------------------------------------------------------


class FakeState:
    """Dict-backed duck type for trame state (attribute access + flush)."""

    def __init__(self, **values):
        object.__setattr__(self, "data", dict(values))

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "data")[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        object.__getattribute__(self, "data")[name] = value

    def flush(self):
        pass


class FakeApp:
    """Minimal CeleriBuilderApp stand-in for MapController."""

    def __init__(self, doc: Document | None = None):
        self.doc = doc if doc is not None else Document()
        self.state = FakeState(
            selection_mode="normal",
            lasso_points=[],
            inspector_tab="",
            inspector_open=False,
            edit_mode="vertex",
            selection=dict(EMPTY),
        )
        self.select_calls = []

    def select(self, kind, ids, additive=False):
        self.select_calls.append((kind, list(ids), additive))
        self.state.selection = select_dispatch(
            self.state.selection_mode,
            kind,
            ids,
            self.state.selection,
            additive=additive,
        )


def make_doc() -> Document:
    rows = [
        {"name": "s0", "lon1": 140.0, "lat1": 35.0, "lon2": 141.0, "lat2": 36.0},
        {"name": "s1", "lon1": 141.0, "lat1": 36.0, "lon2": 142.0, "lat2": 37.0},
    ]
    return Document(
        segments=build_graph(rows),
        blocks=(
            {"name": "b0", "interior_lon": 150.0, "interior_lat": 40.0},
            {"name": "b1", "interior_lon": -170.0, "interior_lat": 41.0},
        ),
        velocities=(
            {
                "name": "v0",
                "lon": 145.0,
                "lat": 30.0,
                "east_vel": 1.0,
                "north_vel": 1.0,
            },
        ),
    )


def sparse_vertex_doc() -> Document:
    """Graph whose vertex ids are NOT contiguous (post-deletion shape)."""
    vertices = {0: (140.0, 35.0), 2: (141.0, 36.0), 7: (142.0, 37.0)}
    graph = SegmentGraph(
        vertices=vertices,
        vertex_index={
            vertex_key(lon, lat): vid for vid, (lon, lat) in vertices.items()
        },
        next_id=8,
        segments=({"name": "s", "start": 0, "end": 2},),
    )
    return Document(segments=graph)


def click(layer_id=None, index=None, coordinate=(140.0, 35.0), shift=False):
    return {
        "coordinate": list(coordinate),
        "picked": layer_id is not None,
        "layerId": layer_id,
        "index": index,
        "shiftKey": shift,
    }


# -- select_dispatch: SelectionMode.spec.ts one-for-one -------------------


def test_can_set_a_normal_selection():
    result = select_dispatch("normal", "vertex", [4, 5], EMPTY)
    assert result == {"kind": "vertex", "ids": [4, 5]}


def test_can_set_a_lasso_selection():
    # lasso-mode select behaves like normal (and records the lasso hits —
    # one selection dict covers both in this engine).
    result = select_dispatch("lasso", "vertex", [4, 5], EMPTY)
    assert result == {"kind": "vertex", "ids": [4, 5]}


def test_override_does_not_change_the_selection():
    current = {"kind": "segment", "ids": [3]}
    assert select_dispatch("override", "vertex", [4, 5], current) == current


def test_map_click_ignores_select_calls():
    current = {"kind": "segment", "ids": [3]}
    assert select_dispatch("mapClick", "vertex", [4, 5], current) == current


def test_normal_selection_replaces_other_kind():
    current = {"kind": "block", "ids": [1, 2]}
    result = select_dispatch("normal", "segment", [0], current)
    assert result == {"kind": "segment", "ids": [0]}


def test_additive_unions_same_kind_and_replaces_across_kinds():
    current = {"kind": "vertex", "ids": [4]}
    result = select_dispatch("normal", "vertex", [5, 4], current, additive=True)
    assert result == {"kind": "vertex", "ids": [4, 5]}
    result = select_dispatch("normal", "block", [1], current, additive=True)
    assert result == {"kind": "block", "ids": [1]}


# -- MapController: normal mode -------------------------------------------


def test_normal_click_selects_sets_tab_and_keeps_lasso():
    app = FakeApp(make_doc())
    MapController(app).handle_click(click("vertices", 0))
    assert app.select_calls == [("vertex", [0], False)]
    assert app.state.selection == {"kind": "vertex", "ids": [0]}
    assert app.state.inspector_tab == "vertex"
    assert app.state.inspector_open is True
    assert app.state.lasso_points == []


def test_normal_background_click_is_a_noop():
    app = FakeApp(make_doc())
    MapController(app).handle_click(click())
    assert app.select_calls == []
    assert app.state.inspector_tab == ""
    assert app.state.inspector_open is False


def test_normal_click_on_unpickable_layer_is_a_noop():
    app = FakeApp(make_doc())
    MapController(app).handle_click(click("meshes", 0))
    assert app.select_calls == []


@pytest.mark.parametrize(
    ("layer_id", "kind", "index"),
    [
        ("segments_hit", "segment", 1),
        ("blocks", "block", 1),
        ("velocities", "velocity", 0),
    ],
)
def test_layer_id_maps_to_kind(layer_id, kind, index):
    assert LAYER_KINDS[layer_id] == kind
    app = FakeApp(make_doc())
    MapController(app).handle_click(click(layer_id, index))
    assert app.select_calls == [(kind, [index], False)]
    assert app.state.inspector_tab == kind


def test_shift_suffix_twin_reports_base_layer():
    app = FakeApp(make_doc())
    MapController(app).handle_click(click("segments_hit" + SHIFT_SUFFIX, 0))
    assert app.select_calls == [("segment", [0], False)]


def test_shift_click_is_additive():
    app = FakeApp(make_doc())
    controller = MapController(app)
    controller.handle_click(click("segments_hit", 0))
    controller.handle_click(click("segments_hit", 1, shift=True))
    assert app.select_calls[-1] == ("segment", [1], True)
    assert app.state.selection == {"kind": "segment", "ids": [0, 1]}


def test_vertex_pick_maps_row_index_to_sparse_vertex_id():
    app = FakeApp(sparse_vertex_doc())
    MapController(app).handle_click(click("vertices", 1))
    assert app.select_calls == [("vertex", [2], False)]
    app.select_calls.clear()
    MapController(app).handle_click(click("vertices", 99))
    assert app.select_calls == []


# -- MapController: lasso mode ---------------------------------------------


def test_lasso_clicks_accumulate_points_regardless_of_picked():
    app = FakeApp(make_doc())
    app.state.selection_mode = "lasso"
    controller = MapController(app)
    controller.handle_click(click(coordinate=(140.0, 35.0)))
    controller.handle_click(click("vertices", 0, coordinate=(-170.0, 10.0)))
    assert app.state.lasso_points == [[140.0, 35.0], [190.0, 10.0]]
    assert app.select_calls == []


def test_escape_cancels_to_normal_and_clears_lasso():
    app = FakeApp(make_doc())
    app.state.selection_mode = "lasso"
    app.state.lasso_points = [[140.0, 35.0], [141.0, 35.0]]
    MapController(app).handle_key({"key": "Escape"})
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []


class RecordingController(MapController):
    def __init__(self, app):
        super().__init__(app)
        self.closed = []

    def close_lasso(self, polygon):
        self.closed.append(polygon)


def test_enter_closes_lasso_only_with_more_than_two_points():
    app = FakeApp(make_doc())
    app.state.selection_mode = "lasso"
    app.state.lasso_points = [[140.0, 35.0], [141.0, 35.0]]
    controller = RecordingController(app)
    controller.handle_key({"key": "Enter"})
    assert controller.closed == []  # <=2 points: no close, still back to normal
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []

    app.state.selection_mode = "lasso"
    points = [[140.0, 35.0], [141.0, 35.0], [141.0, 36.0]]
    app.state.lasso_points = list(points)
    controller.handle_key({"key": "Enter"})
    assert controller.closed == [points]
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []


def test_enter_outside_lasso_mode_is_a_noop():
    app = FakeApp(make_doc())
    controller = RecordingController(app)
    controller.handle_key({"key": "Enter"})
    assert controller.closed == []
    assert app.state.selection_mode == "normal"


# -- MapController: armed override / mapClick -------------------------------


def test_override_routes_only_matching_kind_to_callback():
    app = FakeApp(make_doc())
    controller = MapController(app)
    received = []
    controller.arm("override", {"label": "test", "kind": "vertex"}, received.append)
    assert app.state.selection_mode == "override"
    controller.handle_click(click("blocks", 0))  # wrong kind: ignored
    controller.handle_click(click())  # background: ignored
    assert received == []
    controller.handle_click(click("vertices", 0))
    assert received == [[0]]
    # no selection/tab side effects (SelectionMode.spec.ts: tab stays '')
    assert app.select_calls == []
    assert app.state.inspector_tab == ""
    assert app.state.selection == EMPTY


def test_map_click_ignores_entity_picks_and_delivers_coordinates():
    app = FakeApp(make_doc())
    controller = MapController(app)
    received = []
    controller.arm("mapClick", {"label": "test"}, received.append)
    controller.handle_click(click("vertices", 0, coordinate=(140.5, 35.5)))
    controller.handle_click(click(coordinate=(-170.0, 10.0)))
    assert received == [[140.5, 35.5], [190.0, 10.0]]
    assert app.select_calls == []
    assert app.state.selection == EMPTY


def test_escape_disarms_the_armed_callback():
    app = FakeApp(make_doc())
    controller = MapController(app)
    received = []
    controller.arm("override", {"kind": "vertex"}, received.append)
    controller.handle_key({"key": "Escape"})
    assert controller.armed is None
    assert app.state.selection_mode == "normal"
    controller.handle_click(click("vertices", 0))
    assert received == []
    assert app.select_calls == [("vertex", [0], False)]  # back to normal select


def test_arm_rejects_unknown_mode():
    controller = MapController(FakeApp())
    with pytest.raises(ValueError, match="cannot arm"):
        controller.arm("lasso", {}, lambda _: None)


# -- overlay layer group ------------------------------------------------------


def test_scene_registers_overlay_on_top():
    names = register_all().group_names()
    assert names[-1] == "overlay"


def test_empty_selection_builds_empty_group():
    doc = make_doc()
    result = selection_layer.build(doc, default_display(), {"kind": None, "ids": set()})
    assert result == []


def test_selected_segment_produces_highlight_row():
    doc = make_doc()
    display = default_display()
    result = selection_layer.build(doc, display, {"kind": "segment", "ids": {1}})
    (descriptor,) = result
    assert descriptor["type"] == "LineLayer"
    assert descriptor["id"] == "selection_segments"
    assert descriptor["getColor"] == display["segment"]["selectedColor"]
    assert descriptor["getWidth"] == display["segment"]["selectedWidth"]
    (row,) = descriptor["data"]
    assert row == {
        "index": 1,
        "slon": 141.0,
        "slat": 36.0,
        "tlon": 142.0,
        "tlat": 37.0,
    }


def test_selected_segment_highlight_uses_shortest_line_and_twin():
    doc = Document(
        segments=build_graph(
            [{"name": "s", "lon1": 175.0, "lat1": 40.0, "lon2": -170.0, "lat2": 42.0}]
        )
    )
    result = selection_layer.build(
        doc, default_display(), {"kind": "segment", "ids": {0}}
    )
    assert [d["id"] for d in result] == [
        "selection_segments",
        "selection_segments" + SHIFT_SUFFIX,
    ]
    row = result[0]["data"][0]
    assert (row["slon"], row["tlon"]) == (175.0, 190.0)


def test_vertex_highlight_points_and_radius():
    doc = sparse_vertex_doc()
    display = default_display()
    result = selection_layer.build(doc, display, {"kind": "vertex", "ids": {2, 99}})
    (descriptor,) = result
    assert descriptor["type"] == "ScatterplotLayer"
    assert descriptor["id"] == "selection_vertices"
    assert descriptor["getFillColor"] == display["vertex"]["selectedColor"]
    assert descriptor["getRadius"] == display["vertex"]["radius"] + 2
    assert descriptor["data"] == [{"id": 2, "lon": 141.0, "lat": 36.0}]


def test_block_highlight_normalizes_longitude():
    doc = make_doc()
    display = default_display()
    result = selection_layer.build(doc, display, {"kind": "block", "ids": {1}})
    assert [d["id"] for d in result] == [
        "selection_blocks",
        "selection_blocks" + SHIFT_SUFFIX,  # lon 190 crosses the antimeridian
    ]
    assert result[0]["data"] == [{"index": 1, "lon": 190.0, "lat": 41.0}]
    assert result[0]["getFillColor"] == display["block"]["selectedColor"]


def test_velocity_highlight_at_station():
    doc = make_doc()
    display = default_display()
    result = selection_layer.build(doc, display, {"kind": "velocity", "ids": {0}})
    (descriptor,) = result
    assert descriptor["id"] == "selection_velocities"
    assert descriptor["data"] == [{"index": 0, "lon": 145.0, "lat": 30.0}]
    assert descriptor["getFillColor"] == display["velocity"]["selectedColor"]


def test_hidden_panel_suppresses_highlight():
    doc = make_doc()
    display = default_display()
    display["segment"]["hide"] = True
    assert selection_layer.build(doc, display, {"kind": "segment", "ids": {0}}) == []


def test_stale_ids_are_skipped():
    doc = make_doc()
    result = selection_layer.build(
        doc, default_display(), {"kind": "segment", "ids": {9}}
    )
    assert result == []


def test_lasso_points_produce_polygon_descriptor():
    doc = make_doc()
    points = [[140.0, 35.0], [141.0, 35.0], [141.0, 36.0]]
    result = selection_layer.build(
        doc, default_display(), {"kind": None, "ids": set(), "lasso": points}
    )
    assert [d["id"] for d in result] == ["lasso_fill", "lasso_outline"]
    fill, outline = result
    assert fill["type"] == "PolygonLayer"
    assert fill["getFillColor"] == [255, 255, 0, 60]
    assert fill["data"] == [{"polygon": points}]
    assert outline["type"] == "PathLayer"
    assert outline["data"] == [{"path": points}]


def test_lasso_with_two_points_draws_outline_only():
    doc = make_doc()
    points = [[140.0, 35.0], [141.0, 35.0]]
    result = selection_layer.build(
        doc, default_display(), {"kind": None, "ids": set(), "lasso": points}
    )
    assert [d["id"] for d in result] == ["lasso_outline"]
    single = selection_layer.build(
        doc, default_display(), {"kind": None, "ids": set(), "lasso": points[:1]}
    )
    assert single == []


def test_scene_build_all_carries_overlay_with_lasso():
    doc = make_doc()
    scene = register_all()
    result = scene.build_all(
        doc,
        default_display(),
        {"kind": "segment", "ids": {0}, "lasso": [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]]},
    )
    ids = [d["id"] for d in result["overlay"]]
    assert ids == ["selection_segments", "lasso_fill", "lasso_outline"]
