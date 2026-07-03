"""Unit tests for model/vertex_graph.py — the celeri_ui shared-vertex model:
floor-cell micro-degree dedup, 0-360 lon normalization, first-occurrence
snapping, and the immutable move/merge/GC operations."""

from __future__ import annotations

import dataclasses

import pytest

from celeri_builder.model.vertex_graph import (
    SegmentGraph,
    build_graph,
    normalize_lon,
    vertex_key,
)


def make_row(lon1, lat1, lon2, lat2, **extra):
    row = {"name": "seg", "dip": 90.0, "locking_depth": 15.0}
    row.update(extra)
    row.update({"lon1": lon1, "lat1": lat1, "lon2": lon2, "lat2": lat2})
    return row


class TestDedup:
    def test_same_floor_cell_dedups_to_one_vertex(self):
        g = SegmentGraph()
        g, a = g.get_or_insert(1.0000001, 2.0000001)
        g, b = g.get_or_insert(1.0000004, 2.0000009)
        assert a == b
        assert len(g.vertices) == 1
        assert g.next_id == 1

    def test_coords_straddling_cell_boundary_stay_distinct(self):
        g = SegmentGraph()
        g, a = g.get_or_insert(1.0000009, 2.0)
        g, b = g.get_or_insert(1.0000011, 2.0)
        assert a != b
        assert len(g.vertices) == 2

    def test_antimeridian_wrap_dedups(self):
        g = SegmentGraph()
        g, a = g.get_or_insert(-179.9999999, 0.0)
        g, b = g.get_or_insert(180.0000001, 0.0)
        assert a == b


class TestNegativeFloorRegression:
    def test_key_uses_floor_not_trunc_for_negatives(self):
        # floor(-0.5) == -1; trunc would give 0 and collide with cell 0.
        assert vertex_key(0.0, -0.0000005) == (0, -1)
        assert vertex_key(0.0, 0.0000004) == (0, 0)

    def test_near_zero_negative_lat_gets_own_cell(self):
        g = SegmentGraph()
        g, a = g.get_or_insert(10.0, -0.0000005)
        g, b = g.get_or_insert(10.0, 0.0000004)
        assert a != b
        assert len(g.vertices) == 2


class TestNormalizeLon:
    def test_negative_lon_gains_360(self):
        assert normalize_lon(-179.9) == pytest.approx(180.1)
        assert normalize_lon(-120.0) == 240.0

    def test_non_negative_lon_unchanged(self):
        assert normalize_lon(0.0) == 0.0
        assert normalize_lon(15.5) == 15.5
        assert normalize_lon(359.9) == 359.9

    def test_build_graph_stores_normalized_lons(self):
        g = build_graph([make_row(-120.0, 10.0, -119.5, 11.0)])
        assert g.vertices[0] == (240.0, 10.0)
        assert g.vertices[1] == (240.5, 11.0)
        assert vertex_key(240.0, 10.0) in g.vertex_index


class TestFirstOccurrenceSnap:
    def test_second_insert_in_cell_returns_first_id_and_coords(self):
        g0 = SegmentGraph()
        g1, a = g0.get_or_insert(5.0000001, 5.0)
        g2, b = g1.get_or_insert(5.0000004, 5.0)
        assert b == a
        assert g2.vertices[a] == (5.0000001, 5.0)
        # reusing an existing cell does not build a new graph
        assert g2 is g1


class TestBuildGraph:
    def test_chain_shares_middle_vertices(self):
        rows = [
            make_row(0.0, 0.0, 1.0, 1.0),
            make_row(1.0, 1.0, 2.0, 2.0),
            make_row(2.0, 2.0, 3.0, 3.0),
        ]
        g = build_graph(rows)
        assert len(g.vertices) == 4
        assert sorted(g.vertices) == [0, 1, 2, 3]
        assert g.next_id == 4
        assert [(s["start"], s["end"]) for s in g.segments] == [(0, 1), (1, 2), (2, 3)]
        assert g.vertices[0] == (0.0, 0.0)
        assert g.vertices[3] == (3.0, 3.0)

    def test_expand_rows_reproduces_input(self):
        rows = [
            make_row(0.0, 0.0, 1.0, 1.0, name="a"),
            make_row(1.0, 1.0, 2.0, 2.0, name="b"),
        ]
        g = build_graph(rows)
        out = g.expand_rows()
        assert out == rows
        for row in out:
            assert "start" not in row
            assert "end" not in row


class TestMoveVertex:
    def test_plain_move_updates_coords_and_index(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        moved = g.move_vertex(0, 10.5, -20.25)
        assert moved.vertices[0] == (10.5, -20.25)
        assert moved.vertex_index[vertex_key(10.5, -20.25)] == 0
        assert vertex_key(0.0, 0.0) not in moved.vertex_index
        # segments still reference the moved vertex id
        assert moved.segments[0]["start"] == 0

    def test_move_normalizes_lon(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        moved = g.move_vertex(0, -120.0, 5.0)
        assert moved.vertices[0] == (240.0, 5.0)

    def test_move_onto_occupied_cell_auto_merges(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0), make_row(1.0, 1.0, 2.0, 2.0)])
        # vertex ids: 0=(0,0), 1=(1,1), 2=(2,2); land vertex 0 in 2's cell
        merged = g.move_vertex(0, 2.0000002, 2.0000007)
        assert 2 not in merged.vertices
        assert merged.vertices[0] == (2.0000002, 2.0000007)
        # segments that pointed at the occupant now point at the moved vertex
        assert [(s["start"], s["end"]) for s in merged.segments] == [(0, 1), (1, 0)]
        assert merged.vertex_index[vertex_key(2.0000002, 2.0000007)] == 0

    def test_move_missing_vertex_is_noop(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        assert g.move_vertex(99, 5.0, 5.0) is g


class TestMergeVertices:
    def test_merge_repoints_drops_zero_length_and_removes_vertex(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0), make_row(1.0, 1.0, 2.0, 2.0)])
        merged = g.merge_vertices(0, 1)
        assert 1 not in merged.vertices
        # segment 0 became zero-length (0->0) and was dropped
        assert len(merged.segments) == 1
        assert (merged.segments[0]["start"], merged.segments[0]["end"]) == (0, 2)
        # keep's coordinates are retained
        assert merged.vertices[0] == (0.0, 0.0)
        assert vertex_key(1.0, 1.0) not in merged.vertex_index

    def test_untouched_vertices_keep_their_ids(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0), make_row(1.0, 1.0, 2.0, 2.0)])
        merged = g.merge_vertices(0, 1)
        assert merged.vertices[2] == (2.0, 2.0)
        assert merged.vertex_index[vertex_key(2.0, 2.0)] == 2

    def test_merge_with_itself_is_noop(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        assert g.merge_vertices(0, 0) is g

    def test_merge_missing_vertex_is_noop(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        assert g.merge_vertices(0, 99) is g


class TestTryRemoveVertex:
    def test_removes_orphan(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        g, orphan = g.get_or_insert(50.0, 50.0)
        removed = g.try_remove_vertex(orphan)
        assert orphan not in removed.vertices
        assert vertex_key(50.0, 50.0) not in removed.vertex_index

    def test_keeps_referenced_vertex(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        assert g.try_remove_vertex(0) is g
        assert g.try_remove_vertex(1) is g

    def test_missing_vertex_is_noop(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0)])
        assert g.try_remove_vertex(99) is g


class TestImmutability:
    def test_operations_return_new_graphs_and_leave_original_intact(self):
        g = build_graph([make_row(0.0, 0.0, 1.0, 1.0), make_row(1.0, 1.0, 2.0, 2.0)])
        vertices_before = dict(g.vertices)
        index_before = dict(g.vertex_index)
        segments_before = tuple(dict(s) for s in g.segments)

        moved = g.move_vertex(1, 5.0, 5.0)
        merged = g.merge_vertices(0, 1)
        inserted, _ = g.get_or_insert(9.0, 9.0)

        assert moved is not g
        assert merged is not g
        assert inserted is not g
        assert g.vertices == vertices_before
        assert g.vertex_index == index_before
        assert tuple(dict(s) for s in g.segments) == segments_before

    def test_graph_dataclass_is_frozen(self):
        g = SegmentGraph()
        with pytest.raises(dataclasses.FrozenInstanceError):
            g.next_id = 5  # type: ignore[misc]
