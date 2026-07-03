"""Dip-projection tests ported from celeri_ui mocha/tests/SegmentState.spec.tsx
('can calculate fault dip projections'), plus a cross-check against fennil's
independent bottom-edge formula (geo/projections.calculate_fault_bottom_edge).
"""

from __future__ import annotations

import math

import pytest

from celeri_builder.geo.dip import TURF_EARTH_RADIUS_KM, fault_dip_projection
from celeri_builder.geo.projections import calculate_fault_bottom_edge

# turf.js result for a 1 km westward offset at the equator (mocha constant).
TURF_1KM_WEST_LON = -0.008993203637245385


class TestSkipRules:
    def test_locking_depth_zero_returns_none(self):
        assert fault_dip_projection(0.0, 0.0, 1.0, 1.0, 50.0, 0.0) is None

    def test_locking_depth_negative_returns_none(self):
        assert fault_dip_projection(0.0, 0.0, 1.0, 1.0, 50.0, -5.0) is None

    def test_dip_90_returns_none(self):
        assert fault_dip_projection(0.0, 0.0, 1.0, 1.0, 90.0, 10.0) is None

    def test_dip_90_int_returns_none(self):
        assert fault_dip_projection(0.0, 0.0, 1.0, 1.0, 90, 15) is None


class TestMochaDip45Depth1:
    """Exact mocha case: N-S segment (0,0)-(0,1), dip 45, locking depth 1 km.

    mocha rect order is [start, proj_start, proj_end, end]; our frozen
    interface returns [p1, p2, proj2, proj1], so proj1 == rect[1] and
    proj2 == rect[2] for this segment (p1 is the TS 'start').
    """

    @pytest.fixture
    def poly(self):
        return fault_dip_projection(0.0, 0.0, 0.0, 1.0, 45.0, 1.0)

    def test_returns_four_corners(self, poly):
        assert poly is not None
        assert len(poly) == 4

    def test_surface_trace_first(self, poly):
        assert poly[0] == (0.0, 0.0)
        assert poly[1] == (0.0, 1.0)

    def test_bottom_edge_matches_mocha_expectation(self, poly):
        proj2, proj1 = poly[2], poly[3]
        assert proj1[0] == pytest.approx(TURF_1KM_WEST_LON, abs=1e-3)
        assert proj1[1] == pytest.approx(0.0, abs=1e-3)
        assert proj2[0] == pytest.approx(TURF_1KM_WEST_LON, abs=1e-3)
        assert proj2[1] == pytest.approx(1.0, abs=1e-3)

    def test_equator_corner_reproduces_turf_exactly(self, poly):
        # At the equator the turf math is analytically clean: the port must
        # reproduce the mocha constant far tighter than the 1e-3 contract.
        proj1 = poly[3]
        assert proj1[0] == pytest.approx(TURF_1KM_WEST_LON, abs=1e-9)
        assert proj1[1] == pytest.approx(0.0, abs=1e-12)


class TestOffsetMath:
    def test_dip_greater_than_90_projects_to_opposite_side(self):
        poly = fault_dip_projection(0.0, 0.0, 0.0, 1.0, 135.0, 1.0)
        assert poly is not None
        proj1 = poly[3]
        # tan(135-90) * 1 km = 1 km, but east instead of west.
        assert proj1[0] == pytest.approx(-TURF_1KM_WEST_LON, abs=1e-9)

    def test_distance_is_locking_depth_over_tan_dip(self):
        # dip 30, depth 10 -> horizontal = 10/tan(30) = 17.32 km, NOT
        # tan(30)*10 = 5.77 km (TS uses the dip complement in dipBase).
        poly = fault_dip_projection(0.0, 0.0, 0.0, 1.0, 30.0, 10.0)
        assert poly is not None
        expected_deg = -math.degrees(
            (10.0 / math.tan(math.radians(30.0))) / TURF_EARTH_RADIUS_KM
        )
        assert poly[3][0] == pytest.approx(expected_deg, abs=1e-6)

    def test_short_segment_clamps_at_vertex_plus_normal(self):
        # Projection distance (tan(85)*15 ~ 171 km) far exceeds the
        # degree-space normal length (~0.11 km): turf `along` clamps at the
        # line's last coordinate, i.e. vertex + normal.
        poly = fault_dip_projection(0.0, 0.0, 0.001, 0.0, 5.0, 15.0)
        assert poly is not None
        assert poly[3] == (0.0, -0.001)
        assert poly[2] == (0.001, -0.001)


class TestFennilCrossCheck:
    def test_rough_agreement_with_calculate_fault_bottom_edge(self):
        # W->E segment at lat 20 with dip < 90: both formulations put the
        # bottom edge SOUTH of the trace at ~depth/tan(dip) km.
        lon1, lat1, lon2, lat2 = 10.0, 20.0, 12.0, 20.0
        dip, depth = 30.0, 10.0

        poly = fault_dip_projection(lon1, lat1, lon2, lat2, dip, depth)
        assert poly is not None
        proj2, proj1 = poly[2], poly[3]

        f_lon1, f_lat1, f_lon2, f_lat2 = calculate_fault_bottom_edge(
            lon1, lat1, lon2, lat2, depth, dip
        )

        # Same side: both south of the surface trace.
        assert proj1[1] < lat1
        assert f_lat1 < lat1
        assert proj2[1] < lat2
        assert f_lat2 < lat2

        # Same magnitude (small formulation differences only).
        assert proj1[1] == pytest.approx(f_lat1, abs=0.01)
        assert proj1[0] == pytest.approx(f_lon1, abs=0.01)
        assert proj2[1] == pytest.approx(f_lat2, abs=0.01)
        assert proj2[0] == pytest.approx(f_lon2, abs=0.01)

        # And the offset is really ~17.3 km (depth/tan(dip)), not 5.8 km.
        offset_deg = lat1 - proj1[1]
        expected_deg = math.degrees(
            (depth / math.tan(math.radians(dip))) / TURF_EARTH_RADIUS_KM
        )
        assert offset_deg == pytest.approx(expected_deg, rel=1e-3)
