"""deck/ layer-descriptor tests on a small synthetic Document (no io/)."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

pytest.importorskip(
    "celeri_builder.geo.dip", reason="geo/dip.py not landed yet (parallel agent)"
)

from celeri_builder.deck.display import default_display, hex_to_rgba
from celeri_builder.deck.layers.segments import shortest_line_coordinates
from celeri_builder.deck.primitives import (
    SHIFT_SUFFIX,
    line_descriptors,
    scatter_descriptors,
)
from celeri_builder.deck.scene import register_all
from celeri_builder.model.document import Document, GenericCollection, Mesh
from celeri_builder.model.vertex_graph import build_graph

ALL_GROUPS = {
    "graticule",
    "meshes",
    "dip_projection",
    "generic",
    "segments",
    "velocities",
    "vertices",
    "blocks",
    "overlay",  # M2 selection/lasso overlay (empty with no selection)
}


def _segment_rows(dips=(45.0, 90.0, 90.0)) -> list[dict]:
    """3 segments, the last crossing the Pacific antimeridian (lon > 180)."""
    coords = [
        (140.0, 35.0, 141.0, 36.0),
        (141.0, 36.0, 142.0, 37.0),
        (175.0, 40.0, 190.0, 42.0),
    ]
    return [
        {
            "name": f"seg_{i}",
            "lon1": lon1,
            "lat1": lat1,
            "lon2": lon2,
            "lat2": lat2,
            "dip": dip,
            "locking_depth": 15.0,
        }
        for i, ((lon1, lat1, lon2, lat2), dip) in enumerate(
            zip(coords, dips, strict=True)
        )
    ]


def make_document(dips=(45.0, 90.0, 90.0)) -> Document:
    mesh = Mesh(
        name="tiny",
        vertices=np.array(
            [[140.0, 35.0, 0.0], [141.0, 35.0, -10.0], [140.5, 36.0, -20.0]]
        ),
        triangles=np.array([[0, 1, 2]]),
    )
    generic = GenericCollection(
        rows=({"a_lon": 10.0, "a_lat": 5.0, "b_lon": 11.0, "b_lat": 6.0},),
        columns=("a_lon", "a_lat", "b_lon", "b_lat"),
        start_lon_key="a_lon",
        start_lat_key="a_lat",
        end_lon_key="b_lon",
        end_lat_key="b_lat",
    )
    return Document(
        segments=build_graph(_segment_rows(dips)),
        blocks=(
            {"name": "block_a", "interior_lon": 141.5, "interior_lat": 35.5},
            {"name": "block_b", "interior_lon": 143.0, "interior_lat": 38.0},
        ),
        velocities=(
            {
                "name": "STA1",
                "lon": 140.2,
                "lat": 35.2,
                "east_vel": 10.0,
                "north_vel": 5.0,
            },
            {
                "name": "STA2",
                "lon": 141.2,
                "lat": 36.2,
                "east_vel": 0.0,
                "north_vel": 0.0,
            },
        ),
        meshes={"tiny": mesh},
        generic={"test": generic},
        command={},
    )


@pytest.fixture
def doc() -> Document:
    return make_document()


@pytest.fixture
def scene():
    return register_all()


def test_build_all_returns_every_group(scene, doc):
    result = scene.build_all(doc, default_display())
    assert set(result) == ALL_GROUPS
    # bottom -> top draw order
    assert list(result) == [
        "graticule",
        "meshes",
        "dip_projection",
        "generic",
        "segments",
        "velocities",
        "vertices",
        "blocks",
        "overlay",
    ]


def test_build_all_json_serializable(scene, doc):
    display = default_display()
    display["grid"]["show"] = True  # exercise the graticule too
    result = scene.build_all(doc, display)
    text = json.dumps(result)
    assert "segments" in text


def test_build_subset_and_unknown_group(scene, doc):
    result = scene.build(["vertices", "blocks"], doc, default_display())
    assert list(result) == ["vertices", "blocks"]
    with pytest.raises(KeyError):
        scene.build(["nope"], doc, default_display())


@pytest.mark.parametrize(
    ("panel", "flag", "group"),
    [
        ("segment", "hide", "segments"),
        ("vertex", "hide", "vertices"),
        ("block", "hide", "blocks"),
        ("velocity", "hide", "velocities"),
        ("mesh", "hide", "meshes"),
        ("generic", "hide", "generic"),
        ("segment", "hideProjection", "dip_projection"),
    ],
)
def test_hide_flags_empty_their_groups(scene, doc, panel, flag, group):
    display = default_display()
    assert scene.build_all(doc, display)[group], "group should start non-empty"
    display[panel][flag] = True
    assert scene.build_all(doc, display)[group] == []


def test_graticule_off_by_default_and_toggleable(scene, doc):
    display = default_display()
    assert scene.build_all(doc, display)["graticule"] == []
    display["grid"]["show"] = True
    (descriptor, *rest) = scene.build_all(doc, display)["graticule"]
    assert descriptor["type"] == "PathLayer"
    assert descriptor["id"] == "graticule"
    # 0..360 meridians (37) + -80..80 parallels (17) at 10 degree spacing
    assert len(descriptor["data"]) == 37 + 17
    # parallels span past lon 180 -> shifted twin present
    assert [d["id"] for d in rest] == ["graticule" + SHIFT_SUFFIX]


def test_pacific_segment_emits_shift_twin(scene, doc):
    result = scene.build_all(doc, default_display())
    ids = [d["id"] for d in result["segments"]]
    assert ids == [
        "segments",
        "segments" + SHIFT_SUFFIX,
        "segments_hit",
        "segments_hit" + SHIFT_SUFFIX,
    ]
    base = result["segments"][0]
    twin = result["segments"][1]
    assert len(base["data"]) == 3
    # antimeridian-shortest: 175 -> 190 stays continuous past 180
    assert base["data"][2]["slon"] == 175.0
    assert base["data"][2]["tlon"] == 190.0
    # twin longitudes are shifted by exactly -360
    assert twin["data"][2]["slon"] == 175.0 - 360.0
    assert twin["data"][2]["tlon"] == 190.0 - 360.0
    # hit layer is fat, nearly invisible, pickable
    hit = result["segments"][2]
    assert hit["pickable"] is True
    assert hit["widthMinPixels"] == 12
    assert hit["getColor"][3] == 1
    # vertices include the >180 vertex, so they twin as well
    assert [d["id"] for d in result["vertices"]] == [
        "vertices",
        "vertices" + SHIFT_SUFFIX,
    ]


def test_no_twin_when_all_lons_at_most_180():
    rows = [{"slon": 10.0, "slat": 0.0, "tlon": 20.0, "tlat": 1.0}]
    assert [d["id"] for d in line_descriptors("x", rows)] == ["x"]
    points = [{"lon": 150.0, "lat": 0.0}]
    assert [d["id"] for d in scatter_descriptors("y", points)] == ["y"]


def test_shortest_line_wraps_the_short_way():
    (alon, _), (blon, _) = shortest_line_coordinates((350.0, 0.0), (10.0, 1.0))
    assert (alon, blon) == (350.0, 370.0)
    (alon, _), (blon, _) = shortest_line_coordinates((-170.0, 0.0), (175.0, 1.0))
    assert (alon, blon) == (190.0, 175.0)


def test_dip_projection_present_for_dipping_segment(scene, doc):
    result = scene.build_all(doc, default_display())
    (descriptor,) = result["dip_projection"]
    assert descriptor["type"] == "PolygonLayer"
    # only the 45 degree segment projects (the two dip-90 ones skip)
    assert len(descriptor["data"]) == 1
    polygon = descriptor["data"][0]["polygon"]
    assert len(polygon) == 4
    assert all(len(point) == 2 for point in polygon)
    # fill = projectionColor at half opacity
    assert descriptor["getFillColor"] == [255, 255, 0, 127]


def test_dip_projection_empty_when_all_dips_vertical(scene):
    vertical = make_document(dips=(90.0, 90.0, 90.0))
    result = scene.build_all(vertical, default_display())
    assert result["dip_projection"] == []


def test_velocity_arrows_math(scene, doc):
    display = default_display()
    result = scene.build_all(doc, display)
    arrows = next(d for d in result["velocities"] if d["id"] == "velocity_arrows")
    anchors = next(d for d in result["velocities"] if d["id"] == "velocities")
    # zero-magnitude STA2 gets no arrow rows but keeps its anchor
    assert len(arrows["data"]) == 3
    assert len(anchors["data"]) == 2
    shaft, head_1, head_2 = arrows["data"]
    magnitude = math.hypot(10.0, 5.0)
    scale = magnitude * display["velocity"]["scale"]
    assert shaft["slon"] == 140.2
    assert shaft["tlon"] == pytest.approx(140.2 + (10.0 / magnitude) * scale)
    assert shaft["tlat"] == pytest.approx(35.2 + (5.0 / magnitude) * scale)
    # both head strokes start at the tip and are arrowHead*scale long
    head_len = display["velocity"]["scale"] * display["velocity"]["arrowHead"]
    for head in (head_1, head_2):
        assert head["slon"] == shaft["tlon"]
        assert head["slat"] == shaft["tlat"]
        length = math.hypot(head["tlon"] - head["slon"], head["tlat"] - head["slat"])
        assert length == pytest.approx(head_len)
    # the two strokes are mirrored about the shaft direction
    assert head_1["tlon"] != head_2["tlon"]


def test_mesh_rows_come_from_edges(scene, doc):
    (descriptor,) = scene.build_all(doc, default_display())["meshes"]
    assert descriptor["type"] == "LineLayer"
    assert len(descriptor["data"]) == 3  # one triangle -> 3 unique edges
    assert all(row["name"] == "tiny" for row in descriptor["data"])


def test_generic_layer_and_missing_keys_skip(scene, doc):
    (descriptor,) = scene.build_all(doc, default_display())["generic"]
    assert descriptor["id"] == "generic_test"
    assert descriptor["data"][0] == {
        "index": 0,
        "slon": 10.0,
        "slat": 5.0,
        "tlon": 11.0,
        "tlat": 6.0,
    }
    unmapped = doc.with_(
        generic={
            "test": GenericCollection(
                rows=doc.generic["test"].rows,
                columns=doc.generic["test"].columns,
            )
        }
    )
    assert scene.build_all(unmapped, default_display())["generic"] == []


def test_blocks_have_name_tooltips(scene, doc):
    (descriptor,) = scene.build_all(doc, default_display())["blocks"]
    assert descriptor["pickable"] is True
    assert [row["tooltip"] for row in descriptor["data"]] == ["block_a", "block_b"]


def test_hex_to_rgba():
    assert hex_to_rgba("#ffff00") == [255, 255, 0, 255]
    assert hex_to_rgba("00ffff", alpha=128) == [0, 255, 255, 128]
    assert hex_to_rgba("oops") == [0, 0, 0, 255]
