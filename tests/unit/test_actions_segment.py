"""Segment action reducers — one-for-one port of celeri_ui
``mocha/tests/SegmentState.spec.tsx`` ("Segment Actions mutate state as
expected"). The fault-dip-projection cases from that spec live in
``test_dip_projection.py``.
"""

from __future__ import annotations

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import reduce
from celeri_builder.model.vertex_graph import SegmentGraph


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


def create(start, end, **props):
    return act.CreateSegment(start=start, end=end, props=props)


def test_can_load_new_data_into_the_segment_state():
    graph = SegmentGraph(vertices={0: (0.0, 0.0)}, vertex_index={}, next_id=0)
    doc = apply(act.LoadSegments(graph=graph))
    assert len(doc.segments.segments) == 0
    assert doc.segments.vertex_index == {}
    assert doc.segments.vertices[0] == (0.0, 0.0)
    assert doc.segments.vertices[0][0] == 0


def test_can_bridge_vertices():
    graph = SegmentGraph()
    graph, a = graph.get_or_insert(0.0, 0.0)
    graph, b = graph.get_or_insert(1.0, 1.0)
    doc = apply(act.BridgeVertices(a=a, b=b), doc=Document(segments=graph))
    assert len(doc.segments.segments) == 1
    assert doc.segments.segments[0]["start"] == 0
    assert doc.segments.segments[0]["end"] == 1


def test_bridge_with_identical_or_missing_vertices_is_a_noop():
    before = apply(create((0.0, 0.0), (1.0, 1.0)))
    assert reduce(before, act.BridgeVertices(a=0, b=0)) is before
    assert reduce(before, act.BridgeVertices(a=0, b=99)) is before
    assert reduce(before, act.BridgeVertices(a=99, b=0)) is before


def test_can_create_segments():
    doc = apply(create((0.0, 0.0), (1.0, 1.0)))
    assert len(doc.segments.segments) == 1
    seg = doc.segments.segments[0]
    assert seg["dip"] == 90
    assert seg["locking_depth"] == 15
    assert doc.segments.vertices[seg["start"]][1] == 0
    assert doc.segments.vertices[seg["end"]][1] == 1
    # graph rows carry vertex ids, never raw lon/lat columns
    for key in ("lon1", "lat1", "lon2", "lat2"):
        assert key not in seg


def test_can_create_2_segments_that_share_a_vertex():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        create((1.0, 1.0), (2.0, 2.0)),
    )
    assert len(doc.segments.segments) == 2
    first, second = doc.segments.segments
    assert doc.segments.vertices[second["start"]][1] == 1
    assert doc.segments.vertices[second["end"]][1] == 2
    assert second["start"] == first["end"]


def test_can_delete_a_segment():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        act.DeleteSegments(indices=(0,)),
    )
    assert len(doc.segments.segments) == 0
    assert doc.segments.vertices == {}


def test_can_delete_a_segment_sharing_a_vertex_with_another_segment():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        create((1.0, 1.0), (2.0, 2.0)),
        act.DeleteSegments(indices=(1,)),
    )
    assert len(doc.segments.segments) == 1
    assert len(doc.segments.vertices) == 2


def test_can_delete_multiple_segments_and_their_associated_vertices():
    before = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        create((1.0, 1.0), (2.0, 2.0)),
        create((2.0, 2.0), (3.0, 3.0)),
    )
    doc = reduce(before, act.DeleteSegments(indices=(0, 1)))

    assert doc.segments.vertices is not before.segments.vertices
    assert doc.segments.vertex_index is not before.segments.vertex_index

    assert len(doc.segments.segments) == 1
    assert len(doc.segments.vertices) == 2

    assert doc.segments.segments[0]["start"] == 2
    assert doc.segments.segments[0]["end"] == 3
    assert doc.segments.vertices[2][1] == 2
    assert doc.segments.vertices[3][1] == 3


def test_can_edit_a_segments_data():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        create((0.0, 0.0), (1.0, 1.0)),
        act.EditSegments(indices=(0, 1), patch={"dip": 80}),
    )
    assert doc.segments.segments[0]["dip"] == 80
    assert doc.segments.segments[0]["locking_depth"] == 15
    assert doc.segments.segments[1]["dip"] == 80
    assert doc.segments.segments[1]["locking_depth"] == 15


def test_can_extrude_a_segment():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        act.ExtrudeSegment(vertex_id=0, target=(2.0, 2.0)),
    )
    assert doc.segments.segments[1]["start"] == 0
    assert doc.segments.segments[1]["end"] == 2
    assert doc.segments.vertices[2][0] == 2


def test_can_merge_vertices():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        create((1.0, 1.0), (2.0, 2.0)),
        act.MergeVertices(keep=0, remove=1),
    )
    assert 0 in doc.segments.vertices
    assert 1 not in doc.segments.vertices
    assert len(doc.segments.segments) == 1
    assert doc.segments.segments[0]["start"] == 0
    assert doc.segments.segments[0]["end"] == 2
    assert doc.segments.vertices[0][1] == 0


def test_merging_a_vertex_with_itself_doesnt_change_the_state():
    before = apply(create((0.0, 0.0), (1.0, 1.0)))
    doc = reduce(before, act.MergeVertices(keep=0, remove=0))
    assert doc is before
    assert 0 in doc.segments.vertices
    assert 1 in doc.segments.vertices
    assert len(doc.segments.segments) == 1
    assert doc.segments.segments[0]["start"] == 0
    assert doc.segments.segments[0]["end"] == 1
    assert doc.segments.vertices[0][1] == 0


def test_can_move_vertices():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        act.MoveVertex(vertex_id=0, lon=2.0, lat=2.0),
    )
    assert doc.segments.vertices[0][0] == 2


def test_can_split_segments():
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0)),
        act.EditSegments(indices=(0,), patch={"name": "test_name"}),
        act.SplitSegments(indices=(0,)),
    )
    assert doc.segments.segments[0]["start"] == 0
    assert doc.segments.segments[0]["end"] == 2
    assert doc.segments.segments[0]["name"] == "test_name_a"
    assert doc.segments.segments[1]["start"] == 2
    assert doc.segments.segments[1]["end"] == 1
    assert doc.segments.segments[1]["name"] == "test_name_b"
    assert doc.segments.vertices[2][0] == 0.5


def test_can_split_multiple_segments_in_one_action():
    # vertices 0,1,2 -- split both rows; midpoints get ids 3 and 4;
    # _a halves replace in place, _b halves append at the array end.
    doc = apply(
        create((0.0, 0.0), (1.0, 1.0), name="sa"),
        create((1.0, 1.0), (2.0, 2.0), name="sb"),
        act.SplitSegments(indices=(0, 1)),
    )
    rows = [(s["name"], s["start"], s["end"]) for s in doc.segments.segments]
    assert rows == [
        ("sa_a", 0, 3),
        ("sb_a", 1, 4),
        ("sa_b", 3, 1),
        ("sb_b", 4, 2),
    ]
    assert doc.segments.vertices[3] == (0.5, 0.5)
    assert doc.segments.vertices[4] == (1.5, 1.5)
