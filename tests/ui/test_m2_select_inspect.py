"""M2 UI gate: S3 click-select + inspector; S4 multi-select bulk edit."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from .conftest import wait_probe
from .helpers import TEST_VIEW, deck_box, latlon_to_px, open_japan_config

pytestmark = pytest.mark.ui

ARTIFACTS = Path(__file__).parent / "artifacts"


def load_segments(root: Path) -> list[dict]:
    with (root / "segment" / "japan_segment.csv").open() as f:
        return list(csv.DictReader(f))


def norm_lon(lon: float) -> float:
    return lon + 360 if lon < 0 else lon


def midpoint(row: dict) -> tuple[float, float]:
    return (
        (norm_lon(float(row["lon1"])) + norm_lon(float(row["lon2"]))) / 2,
        (float(row["lat1"]) + float(row["lat2"])) / 2,
    )


def visible(mid: tuple[float, float]) -> bool:
    return (
        abs(mid[0] - TEST_VIEW["longitude"]) < 4.5
        and abs(mid[1] - TEST_VIEW["latitude"]) < 2.2
    )


def isolated_segments(rows: list[dict], n: int = 2, min_gap_deg: float = 0.35):
    """Indices of visible segments whose midpoints are far from every other
    segment's midpoint AND endpoints (so a 12px hit-line click is unambiguous)."""
    mids = [midpoint(r) for r in rows]
    ends = []
    for r in rows:
        ends.append((norm_lon(float(r["lon1"])), float(r["lat1"])))
        ends.append((norm_lon(float(r["lon2"])), float(r["lat2"])))
    picked = []
    for i, mid in enumerate(mids):
        if not visible(mid):
            continue
        mid_gaps = (
            math.hypot(mid[0] - m[0], mid[1] - m[1])
            for j, m in enumerate(mids)
            if j != i
        )
        end_gaps = (math.hypot(mid[0] - e[0], mid[1] - e[1]) for e in ends)
        gap = min(*mid_gaps, *end_gaps)
        if gap >= min_gap_deg:
            picked.append((gap, i))
    picked.sort(reverse=True)
    return [i for _, i in picked[:n]]


def click_segment_mid(page, box, rows, index):
    x, y = latlon_to_px(box, *midpoint(rows[index]))
    page.mouse.click(x, y)


def test_click_segment_shows_inspector(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    targets = isolated_segments(rows)
    assert targets, "no isolated visible segment found for the test"
    idx = targets[0]

    box = deck_box(app_page)
    click_segment_mid(app_page, box, rows, idx)
    probe = wait_probe(
        app_page, lambda pr: (pr.get("selection") or {}).get("kind") == "segment"
    )
    assert probe, "clicking a segment midpoint did not select a segment"
    assert probe["selection"]["ids"] == [idx]

    # inspector switched to the segment tab and shows the row's dip
    fields = probe.get("selection_fields") or {}
    assert float(fields.get("dip")) == float(rows[idx]["dip"])
    tab = app_page.locator(".tab-segment")
    assert "v-tab--selected" in (tab.get_attribute("class") or "")

    # clicking the active tab collapses the inspector body (celeri_ui parity)
    tab.click()
    probe = wait_probe(app_page, lambda pr: pr.get("inspector_open") is False)
    assert probe, "clicking active tab did not collapse the inspector"
    tab.click()  # restore

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s3_segment_selected.png"))


def test_multiselect_bulk_edit_dip(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    targets = isolated_segments(rows, n=8)
    # need two isolated segments with differing dips
    pair = None
    for i in targets:
        for j in targets:
            if j != i and float(rows[i]["dip"]) != float(rows[j]["dip"]):
                pair = (i, j)
                break
        if pair:
            break
    assert pair, "no isolated segment pair with differing dips in view"
    a, b = pair

    box = deck_box(app_page)
    click_segment_mid(app_page, box, rows, a)
    wait_probe(app_page, lambda pr: (pr.get("selection") or {}).get("ids") == [a])
    app_page.keyboard.down("Shift")
    click_segment_mid(app_page, box, rows, b)
    app_page.keyboard.up("Shift")
    probe = wait_probe(
        app_page,
        lambda pr: (
            sorted((pr.get("selection") or {}).get("ids") or []) == sorted([a, b])
        ),
    )
    assert probe, "shift-click did not extend the selection"
    assert probe["selection_fields"].get("dip") == "-", "mixed dips must show '-'"

    undo_before = probe.get("undo_depth", 0)

    # edit dip via the inspector input labeled dip
    dip_input = app_page.locator(".field-editor-dip input").first
    dip_input.fill("60")
    dip_input.press("Enter")

    probe = wait_probe(
        app_page,
        lambda pr: (pr.get("selection_fields") or {}).get("dip") == 60,
        timeout=10,
    )
    assert probe, "bulk dip edit did not apply to the selection"
    assert probe.get("undo_depth") == undo_before + 1, "bulk edit must be ONE undo step"

    # undo reverts both dips (selection_fields back to mixed)
    app_page.locator(".btn-undo").click()
    probe = wait_probe(
        app_page, lambda pr: (pr.get("selection_fields") or {}).get("dip") == "-"
    )
    assert probe, "undo did not revert the bulk edit"

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s4_bulk_edit.png"))
