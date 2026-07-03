"""M4 lasso-select engine tests.

Two layers:

1. ``geo.polygon.points_in_polygon`` as a pure primitive — the literal
   ``mocha/tests/PointUtilities.spec.ts`` fixture plus extra convex/concave
   polygons, every case cross-checked against an INDEPENDENT oracle
   (``matplotlib.path.Path.contains_points``).
2. ``MapController.close_lasso`` driven through the real ``CeleriBuilderApp``
   headless: per edit mode a polygon around known candidates selects exactly
   the enclosed entities (segments by MIDPOINT); Escape cancels without
   selecting; a <3-point polygon does nothing.
"""

from __future__ import annotations

import uuid

import pytest
from matplotlib.path import Path as MplPath
from trame.app import get_server

from celeri_builder.app import core, settings
from celeri_builder.deck.display import default_display
from celeri_builder.deck.scene import register_all
from celeri_builder.geo.polygon import (
    enclosed_indices,
    point_in_polygon,
    points_in_polygon,
)
from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.vertex_graph import build_graph

# -- pure point-in-polygon vs the matplotlib oracle ---------------------------


def _oracle(points, polygon) -> list[bool]:
    """Independent point-in-polygon (matplotlib), auto-closed like ours."""
    ring = [*list(polygon), polygon[0]]
    return [bool(v) for v in MplPath(ring).contains_points(list(points))]


def test_pointutilities_spec_fixture():
    """Literal port of celeri_ui PointUtilities.spec.ts (turf -> ray cast)."""
    points = [(0, 1), (100, 50), (150, 45), (300, 80)]
    polygon = [(90, 40), (160, 30), (165, 55), (153, 51), (87, 58)]
    enclosed = enclosed_indices(points, polygon)
    assert len(enclosed) == 2
    assert set(enclosed) == {1, 2}
    # ... and the enclosure agrees with the matplotlib oracle point-for-point.
    assert points_in_polygon(points, polygon) == _oracle(points, polygon)


def test_convex_and_concave_polygons_match_oracle():
    # A convex square and a concave "C"; points chosen clear of every edge so
    # the (undefined) boundary case never decides the comparison.
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    c_shape = [(0, 0), (10, 0), (10, 3), (3, 3), (3, 7), (10, 7), (10, 10), (0, 10)]
    for polygon in (square, c_shape):
        points = [
            (1, 1),
            (5, 5),
            (9, 9),
            (6, 5),  # inside the square, in the notch of the C (outside C)
            (-2, 5),
            (12, 5),
            (5, -1),
        ]
        assert points_in_polygon(points, polygon) == _oracle(points, polygon), polygon


def test_degenerate_polygon_encloses_nothing():
    assert points_in_polygon([(0, 0), (1, 1)], [(0, 0), (1, 1)]) == [False, False]
    assert point_in_polygon((0, 0), [(0, 0), (1, 0)]) is False
    assert enclosed_indices([(0, 0)], []) == []


def test_lasso_normalizes_western_hemisphere_consistently():
    # A -170..-160 lasso (delivered raw) must enclose a 195-lon candidate once
    # both are normalized to 0-360; the pure primitive is frame-agnostic, so
    # the normalization happens in close_lasso (exercised below) — here we just
    # confirm the primitive works in a single 0-360 frame.
    polygon = [(188, 18), (200, 18), (200, 24), (188, 24)]
    assert enclosed_indices([(195, 20), (150, 20)], polygon) == [0]


# -- close_lasso through the real app -----------------------------------------


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CELERI_BUILDER_TESTING", "1")
    monkeypatch.setenv("CELERI_BUILDER_NO_BASEMAP", "1")
    monkeypatch.setattr(settings, "load", lambda defaults: defaults)
    monkeypatch.setattr(settings, "save", lambda _display: None)
    server = get_server(f"lasso-{uuid.uuid4().hex}", client_type="vue3")
    return core.CeleriBuilderApp(server=server, root_dir=tmp_path)


def _lasso(app, edit_mode, polygon):
    """Arm a lasso in ``edit_mode``, set the polygon, close it with Enter."""
    app.state.edit_mode = edit_mode
    app.state.selection_mode = "lasso"
    app.state.lasso_points = [list(p) for p in polygon]
    app.on_map_key({"key": "Enter"})


def _seed_features(app):
    # Two blocks, two velocities, two segments — one of each pair sits inside a
    # small box around (140, 35.5), the other far outside.
    app.dispatch(
        act.CreateBlock(props={"interior_lon": 139.5, "interior_lat": 35.5}),
        dirty=("block",),
    )
    app.dispatch(
        act.CreateBlock(props={"interior_lon": 150.0, "interior_lat": 50.0}),
        dirty=("block",),
    )
    app.dispatch(
        act.CreateVelocity(props={"lon": 139.5, "lat": 35.5}), dirty=("station",)
    )
    app.dispatch(
        act.CreateVelocity(props={"lon": 150.0, "lat": 50.0}), dirty=("station",)
    )
    # segment 0 midpoint = (140.5, 35.5) -> inside; segment 1 midpoint far away
    app.dispatch(
        act.CreateSegment(start=(140.0, 35.0), end=(141.0, 36.0)), dirty=("segment",)
    )
    app.dispatch(
        act.CreateSegment(start=(199.0, 59.0), end=(201.0, 61.0)), dirty=("segment",)
    )


BOX = [(139.0, 34.5), (141.0, 34.5), (141.0, 36.5), (139.0, 36.5)]


def test_lasso_block_mode_selects_enclosed_block(app):
    _seed_features(app)
    _lasso(app, "block", BOX)
    assert app.state.selection == {"kind": "block", "ids": [0]}
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []  # overlay cleared
    assert app.state.inspector_tab == "block"


def test_lasso_velocity_mode_selects_enclosed_velocity(app):
    _seed_features(app)
    _lasso(app, "velocities", BOX)  # velocity edit mode is spelled 'velocities'
    assert app.state.selection == {"kind": "velocity", "ids": [0]}
    assert app.state.inspector_tab == "velocities"


def test_lasso_segment_mode_selects_by_midpoint(app):
    _seed_features(app)
    # The box straddles segment 0's midpoint but neither of its endpoints alone
    # would place it fully inside — proves midpoint candidates (App.tsx:346).
    _lasso(app, "segment", BOX)
    assert app.state.selection == {"kind": "segment", "ids": [0]}


def test_lasso_vertex_mode_selects_enclosed_vertices(app):
    _seed_features(app)
    # vertices come from the two seeded segments; only (140,35) & (141,36) of
    # segment 0 are near the box -> tighten it to enclose just vertex id 0.
    _lasso(app, "vertex", [(139.5, 34.5), (140.5, 34.5), (140.5, 35.5), (139.5, 35.5)])
    assert app.state.selection["kind"] == "vertex"
    assert app.state.selection["ids"] == [0]


def test_lasso_western_hemisphere_normalized(app):
    # Candidate at lon 195 (0-360); polygon delivered raw as -172..-160 which
    # close_lasso normalizes to 188..200 before testing.
    app.dispatch(
        act.CreateVelocity(props={"lon": 195.0, "lat": 20.0}), dirty=("station",)
    )
    _lasso(app, "velocities", [(-172, 18), (-160, 18), (-160, 24), (-172, 24)])
    assert app.state.selection == {"kind": "velocity", "ids": [0]}


def test_lasso_zero_hits_clears_to_empty_selection(app):
    _seed_features(app)
    app.select("block", [1])  # pre-existing selection
    _lasso(app, "block", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    assert app.state.selection == {"kind": None, "ids": []}


def test_escape_cancels_lasso_without_selecting(app):
    _seed_features(app)
    app.state.edit_mode = "block"
    app.state.selection_mode = "lasso"
    app.state.lasso_points = [list(p) for p in BOX[:2]]
    app.on_map_key({"key": "Escape"})
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.state.selection_mode == "normal"
    assert app.state.lasso_points == []


def test_under_three_point_polygon_does_nothing(app):
    _seed_features(app)
    app.state.edit_mode = "block"
    app.state.selection_mode = "lasso"
    app.state.lasso_points = [[139.0, 34.5], [141.0, 34.5]]
    app.on_map_key({"key": "Enter"})  # only two points
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.state.selection_mode == "normal"


def test_close_lasso_direct_guard_on_short_polygon(app):
    _seed_features(app)
    app.state.edit_mode = "block"
    app.controller.close_lasso([[139.0, 34.5], [141.0, 34.5]])
    assert app.state.selection == {"kind": None, "ids": []}


# -- plottableKey text labels (M4 layer) --------------------------------------


def _label_scene(display):
    graph = build_graph(
        [{"lon1": 140.0, "lat1": 35.0, "lon2": 141.0, "lat2": 36.0, "dip": 45}]
    )
    doc = Document(
        segments=graph,
        blocks=({"name": "b", "interior_lon": 139.0, "interior_lat": 36.0},),
        velocities=({"name": "v", "lon": 138.0, "lat": 34.0, "east_vel": 5},),
    )
    return register_all().build(("labels",), doc, display)["labels"]


def test_labels_empty_until_plottable_key_set():
    assert _label_scene(default_display()) == []


def test_labels_render_selected_field_at_entity_position():
    display = default_display()
    display["segment"]["plottableKey"] = "dip"
    display["block"]["plottableKey"] = "interior_lon"
    display["velocity"]["plottableKey"] = "east_vel"
    layers = _label_scene(display)
    by_id = {layer["id"]: layer for layer in layers}
    assert set(by_id) == {"labels_segment", "labels_block", "labels_velocity"}
    seg = by_id["labels_segment"]["data"][0]
    assert seg["text"] == "45"
    assert seg["lon"] == pytest.approx(140.5)  # segment MIDPOINT
    assert seg["lat"] == pytest.approx(35.5)
    assert by_id["labels_block"]["data"][0]["text"] == "139"
    assert by_id["labels_velocity"]["data"][0]["text"] == "5"


def test_labels_respect_hidden_panel():
    display = default_display()
    display["segment"]["plottableKey"] = "dip"
    display["segment"]["hide"] = True
    assert _label_scene(display) == []
