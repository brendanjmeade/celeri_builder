"""M3 UI gate: geometry editing with real mouse events.

S5 new-segment two clicks + shared-vertex reuse, S6 drag vertex (endpoint
follows) + auto-merge, S7 split + a vertex operation (extrude). Coordinates
are isolated from the japan CSV so real-mouse picks/creates are unambiguous.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from .conftest import wait_probe
from .helpers import deck_box, latlon_to_px, open_japan_config
from .test_m2_select_inspect import (
    click_segment_mid,
    isolated_segments,
    load_segments,
    midpoint,
    norm_lon,
    visible,
)

pytestmark = pytest.mark.ui

ARTIFACTS = Path(__file__).parent / "artifacts"


# -- coordinate isolation from the japan CSV ---------------------------------


def on_map(box, lon, lat) -> bool:
    """True when lon/lat maps to a map pixel clear of the docked panels.

    The inspector docks bottom-right (~40% x ~45%) and the edit-mode panel
    bottom-left; a click there hits the panel, not the map. We also keep a
    margin off the container edges.
    """
    x, y = latlon_to_px(box, lon, lat)
    vw = box["x"] + box["width"]
    vh = box["y"] + box["height"]
    if not (box["x"] + 40 <= x <= vw - 40):
        return False
    if not (box["y"] + 40 <= y <= vh - 40):
        return False
    # bottom-right inspector (conservative rectangle)
    if x >= vw * 0.58 and y >= vh * 0.52:
        return False
    # bottom-left edit-mode panel
    return not (x <= box["x"] + 360 and y >= vh - 190)


def all_endpoints(rows) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for r in rows:
        pts.append((norm_lon(float(r["lon1"])), float(r["lat1"])))
        pts.append((norm_lon(float(r["lon2"])), float(r["lat2"])))
    return pts


def unique_vertices(rows) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    out: list[tuple[float, float]] = []
    for p in all_endpoints(rows):
        key = (round(p[0], 6), round(p[1], 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def isolated_vertices(
    rows, box, n=2, min_gap=0.4, spread=1.0
) -> list[tuple[float, float]]:
    """Panel-clear vertices far (``min_gap``) from every other vertex and
    mutually at least ``spread`` apart, most-isolated first (clean picks)."""
    verts = unique_vertices(rows)
    cands = []
    for p in verts:
        if not (visible(p) and on_map(box, *p)):
            continue
        gap = min(
            (math.hypot(p[0] - q[0], p[1] - q[1]) for q in verts if q is not p),
            default=999.0,
        )
        if gap >= min_gap:
            cands.append((gap, p))
    cands.sort(reverse=True)
    picked: list[tuple[float, float]] = []
    for _, p in cands:
        if all(math.hypot(p[0] - c[0], p[1] - c[1]) >= spread for c in picked):
            picked.append(p)
        if len(picked) >= n:
            break
    return picked


def empty_points(
    rows, box, n=3, avoid=(), min_gap=0.35, sep=0.6
) -> list[tuple[float, float]]:
    """Panel-clear points far from every existing vertex, from ``avoid``, and
    from each other — safe spots to click a new feature into being."""
    verts = unique_vertices(rows)
    out: list[tuple[float, float]] = []
    lon = 136.2
    while lon <= 143.8 and len(out) < n:
        lat = 35.8
        while lat <= 39.2 and len(out) < n:
            c = (lon, lat)
            if on_map(box, *c):
                far_existing = all(
                    math.hypot(c[0] - q[0], c[1] - q[1]) >= min_gap for q in verts
                )
                far_others = all(
                    math.hypot(c[0] - a[0], c[1] - a[1]) >= sep for a in [*avoid, *out]
                )
                if far_existing and far_others:
                    out.append(c)
            lat += 0.2
        lon += 0.2
    return out


def drag(page, sx, sy, tx, ty, steps=12, settle=350):
    """Stepped real-mouse drag: hover to arm pan-disable, then down/move*/up."""
    page.mouse.move(sx, sy)
    page.wait_for_timeout(settle)
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(sx + (tx - sx) * i / steps, sy + (ty - sy) * i / steps)
        page.wait_for_timeout(30)
    page.mouse.up()


# -- S5: new segment, two map clicks, shared-vertex reuse --------------------


def test_new_segment_two_map_clicks(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    box = deck_box(app_page)

    # edit-mode -> draggable-layer watcher wiring (proven against the server)
    app_page.locator(".btn-mode-block").click()
    assert wait_probe(app_page, lambda pr: pr.get("drag_layers") == ["blocks"])
    app_page.locator(".btn-mode-segment").click()
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr.get("mode") == "segment" and pr.get("drag_layers") == ["vertices"]
        ),
    )
    assert probe, "Segment mode did not set drag layers to vertices"

    # open the segment inspector panel to reveal New Segment
    app_page.locator(".tab-segment").click()
    app_page.wait_for_selector(".btn-new-segment", state="visible")

    segs0 = probe["counts"]["segments"]
    verts0 = probe["counts"]["vertices"]
    p1, p2, p3 = empty_points(rows, box, n=3)

    # first segment: two clicks at two empty points -> +1 segment, +2 vertices
    app_page.locator(".btn-new-segment").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "mapClick")
    app_page.mouse.click(*latlon_to_px(box, *p1))
    assert wait_probe(
        app_page, lambda pr: "end" in (pr.get("mode_hint") or "").lower()
    ), "banner did not advance to the end-point hint"
    app_page.mouse.click(*latlon_to_px(box, *p2))
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr.get("selection_mode") == "normal"
            and pr["counts"]["segments"] == segs0 + 1
        ),
    )
    assert probe, "two map clicks did not create a segment"
    assert probe["counts"]["vertices"] == verts0 + 2, "expected two new vertices"

    # second segment: FIRST click reuses p2 (same pixel = same coordinate)
    px2 = latlon_to_px(box, *p2)
    app_page.locator(".btn-new-segment").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "mapClick")
    app_page.mouse.click(*px2)
    assert wait_probe(app_page, lambda pr: "end" in (pr.get("mode_hint") or "").lower())
    app_page.mouse.click(*latlon_to_px(box, *p3))
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr.get("selection_mode") == "normal"
            and pr["counts"]["segments"] == segs0 + 2
        ),
    )
    assert probe, "second segment was not created"
    # shared vertex reused: only ONE new vertex (p3), not two
    assert probe["counts"]["vertices"] == verts0 + 3, (
        f"shared-vertex reuse failed: vertices {probe['counts']['vertices']}"
        f" != {verts0 + 3}"
    )

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s5_new_segment.png"))


# -- S6: drag a vertex (endpoint follows) + auto-merge on drop ----------------


def test_drag_vertex_follows_and_automerges(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    box = deck_box(app_page)

    verts: list[tuple[float, float]] = []
    for min_gap, spread in ((0.4, 1.5), (0.35, 1.2), (0.3, 1.0), (0.3, 0.7)):
        verts = isolated_vertices(rows, box, n=2, min_gap=min_gap, spread=spread)
        if len(verts) == 2:
            break
    assert len(verts) == 2, "need two panel-clear isolated vertices"
    v_src, w_src = verts
    target = empty_points(rows, box, n=1, avoid=[v_src, w_src], min_gap=0.35, sep=0.4)[
        0
    ]

    vx, vy = latlon_to_px(box, *v_src)
    wx, wy = latlon_to_px(box, *w_src)
    tx, ty = latlon_to_px(box, *target)

    # select the first vertex so we can watch its coordinate move
    app_page.mouse.click(vx, vy)
    probe = wait_probe(
        app_page, lambda pr: (pr.get("selection") or {}).get("kind") == "vertex"
    )
    assert probe, "clicking an isolated vertex did not select it"
    v_id = probe["selection"]["ids"][0]
    verts_before = probe["counts"]["vertices"]

    # drag it to the empty target: the attached segment endpoint follows
    drag(app_page, vx, vy, tx, ty)
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr.get("undo_depth", 0) == 1
            and abs((pr.get("selection_fields") or {}).get("lon", -999) - target[0])
            < 0.3
        ),
    )
    assert probe, "vertex did not follow the drag to the target"
    assert probe["selection"]["ids"] == [v_id], "the moved vertex kept its id"
    assert probe["counts"]["vertices"] == verts_before, "a plain move keeps the count"

    # select the second vertex, drag it onto the SAME pixel -> auto-merge
    app_page.mouse.click(wx, wy)
    probe = wait_probe(
        app_page,
        lambda pr: (
            (pr.get("selection") or {}).get("kind") == "vertex"
            and pr["selection"]["ids"] != [v_id]
        ),
    )
    assert probe, "clicking the second isolated vertex did not select it"

    drag(app_page, wx, wy, tx, ty)
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr["counts"]["vertices"] == verts_before - 1
            and pr.get("undo_depth", 0) == 2
        ),
    )
    assert probe, "dropping a vertex onto another did not auto-merge (-1 vertex)"

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s6_drag_automerge.png"))


# -- S7: split a segment, then extrude from a vertex --------------------------


def test_split_and_extrude(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    box = deck_box(app_page)

    # select an isolated segment (panel-clear midpoint) and split it
    seg_idx = next(
        i for i in isolated_segments(rows, n=8) if on_map(box, *midpoint(rows[i]))
    )
    click_segment_mid(app_page, box, rows, seg_idx)
    probe = wait_probe(
        app_page, lambda pr: (pr.get("selection") or {}).get("kind") == "segment"
    )
    assert probe, "did not select the segment to split"
    segs0 = probe["counts"]["segments"]

    app_page.locator(".btn-split").click()
    probe = wait_probe(app_page, lambda pr: pr["counts"]["segments"] == segs0 + 1)
    assert probe, "split did not add a segment"
    names = probe.get("segment_names") or []
    assert any(str(n).endswith("_a") for n in names), "no _a half after split"
    assert any(str(n).endswith("_b") for n in names), "no _b half after split"

    # extrude a new segment from an isolated vertex to an empty target
    vtx = isolated_vertices(rows, box, n=1, min_gap=0.4)[0]
    target = empty_points(rows, box, n=1, avoid=[vtx], min_gap=0.4, sep=0.4)[0]
    vx, vy = latlon_to_px(box, *vtx)
    app_page.mouse.click(vx, vy)
    probe = wait_probe(
        app_page, lambda pr: (pr.get("selection") or {}).get("kind") == "vertex"
    )
    assert probe, "did not select the vertex to extrude from"
    segs1 = probe["counts"]["segments"]

    app_page.wait_for_selector(".btn-extrude", state="visible")
    app_page.locator(".btn-extrude").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "mapClick")

    app_page.mouse.click(*latlon_to_px(box, *target))
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr.get("selection_mode") == "normal"
            and pr["counts"]["segments"] == segs1 + 1
        ),
    )
    assert probe, "extrude did not add a segment from the selected vertex"

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s7_split_extrude.png"))
