"""M4 UI gate: S8 lasso select (+ Esc cancel), S9 deep undo/redo, S10 save.

Real-mouse polygon clicks + an independent matplotlib point-in-polygon oracle
(S8); a scripted create/edit/delete sequence walked all the way down the undo
stack and back up (S9); and the Save Active Files button writing exactly the
dirty file while leaving the others byte-identical (S10).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest
from matplotlib.path import Path as MplPath

from celeri_builder.io.segment_io import read_segments

from .conftest import DATA_DIR, wait_probe
from .helpers import deck_box, latlon_to_px, open_japan_config
from .test_m2_select_inspect import (
    click_segment_mid,
    isolated_segments,
    load_segments,
    midpoint,
)
from .test_m3_edit_geometry import empty_points, on_map

pytestmark = pytest.mark.ui

ARTIFACTS = Path(__file__).parent / "artifacts"


# -- helpers ------------------------------------------------------------------


def load_blocks(root: Path) -> list[dict]:
    with (root / "block" / "japan_block.csv").open() as f:
        return list(csv.DictReader(f))


def block_points(rows: list[dict]) -> list[tuple[float, float]]:
    return [(float(r["interior_lon"]), float(r["interior_lat"])) for r in rows]


def oracle_enclosed(points, polygon) -> set[int]:
    """Independent point-in-polygon (matplotlib), auto-closed."""
    ring = [*list(polygon), polygon[0]]
    mask = MplPath(ring).contains_points(list(points))
    return {i for i, inside in enumerate(mask) if inside}


def min_edge_distance(point, polygon) -> float:
    """Distance from ``point`` to the nearest polygon edge (robustness guard)."""
    px, py = point
    best = float("inf")
    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def counts(probe: dict) -> dict:
    return dict(probe["counts"])


def lasso_click_polygon(page, box, corners):
    """Click each corner as a lasso vertex, waiting for the polygon to grow."""
    for i, (lon, lat) in enumerate(corners, start=1):
        page.mouse.click(*latlon_to_px(box, lon, lat))
        probe = wait_probe(page, lambda pr, i=i: len(pr.get("lasso_points") or []) == i)
        assert probe, f"lasso corner {i} at {lon},{lat} never registered"
    return probe["lasso_points"]


def press_map_key(page, key):
    # Blur any focused control (e.g. the lasso button) so the key reaches the
    # widget's window listener and does not re-trigger a button click.
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press(key)


# -- S8: lasso select + Escape cancel -----------------------------------------


def test_lasso_select(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    blocks = load_blocks(app_server["root"])
    pts = block_points(blocks)
    box = deck_box(app_page)

    # A rectangle enclosing a small, cleanly separable block cluster.
    corners = [(138.3, 38.0), (143.0, 38.0), (143.0, 40.5), (138.3, 40.5)]
    assert all(on_map(box, *c) for c in corners), "a lasso corner hits a panel"

    # Block edit mode -> lasso selects blocks by their interior point.
    app_page.locator(".btn-mode-block").click()
    assert wait_probe(app_page, lambda pr: pr.get("drag_layers") == ["blocks"])

    # Escape cancels a started lasso without changing the selection.
    app_page.locator(".btn-lasso").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "lasso")
    lasso_click_polygon(app_page, box, corners[:2])
    press_map_key(app_page, "Escape")
    probe = wait_probe(app_page, lambda pr: pr.get("selection_mode") == "normal")
    assert probe, "Escape did not return the lasso to normal mode"
    assert (probe.get("selection") or {}).get("kind") is None, (
        "Escape must not select anything"
    )
    assert probe.get("lasso_points") == [], "Escape did not clear the lasso overlay"

    # Now the real lasso: four corners, then read the polygon the app actually
    # recorded (removes projection round-trip slack), run the INDEPENDENT
    # matplotlib oracle over it, and compare to the app's own selection.
    app_page.locator(".btn-lasso").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "lasso")
    polygon = lasso_click_polygon(app_page, box, corners)
    expected = oracle_enclosed(pts, polygon)
    assert expected, "the recorded polygon should enclose at least one block"
    assert expected != set(range(len(pts))), "polygon should exclude some blocks too"
    # Robustness: no block may sit within 0.15 deg of an edge of the polygon we
    # are actually testing against (keeps the oracle/app comparison decisive).
    assert all(min_edge_distance(p, polygon) > 0.15 for p in pts), (
        "a block is too close to a polygon edge for a stable pick"
    )

    press_map_key(app_page, "Enter")
    probe = wait_probe(
        app_page,
        lambda pr: (
            (pr.get("selection") or {}).get("kind") == "block"
            and pr.get("selection_mode") == "normal"
        ),
    )
    assert probe, "lasso Enter did not select blocks"
    assert set(probe["selection"]["ids"]) == expected, (
        f"lasso selected {probe['selection']['ids']}, oracle expected {sorted(expected)}"
    )
    assert probe.get("inspector_tab") == "block"
    assert probe.get("lasso_points") == [], "Enter did not clear the lasso overlay"

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s8_lasso.png"))


# -- S9: create / edit / delete, then walk the undo stack down and back up ----


def _select_isolated_segment(page, box, rows) -> int:
    idx = next(
        i for i in isolated_segments(rows, n=8) if on_map(box, *midpoint(rows[i]))
    )
    click_segment_mid(page, box, rows, idx)
    probe = wait_probe(page, lambda pr: (pr.get("selection") or {}).get("ids") == [idx])
    assert probe, "failed to select an isolated segment"
    return idx


def _edit_dip(page, new_dip) -> None:
    dip_input = page.locator(".field-editor-dip input").first
    dip_input.fill(str(new_dip))
    dip_input.press("Enter")


def test_undo_redo_full_stack(app_server, app_page):
    open_japan_config(app_page, wait_probe)
    rows = load_segments(app_server["root"])
    box = deck_box(app_page)

    s0 = wait_probe(app_page, lambda pr: pr.get("counts"))
    c0 = counts(s0)
    assert app_page.locator(".btn-undo").is_disabled(), "undo enabled with empty stack"
    assert app_page.locator(".btn-redo").is_disabled(), "redo enabled with empty stack"

    # -- step 1: bulk dip edit on a selected segment (ONE undo entry) --------
    seg_idx = _select_isolated_segment(app_page, box, rows)
    orig_dip = float(rows[seg_idx]["dip"])
    new_dip = 12.5 if orig_dip != 12.5 else 40.0
    _edit_dip(app_page, new_dip)
    probe = wait_probe(
        app_page,
        lambda pr: (
            (pr.get("selection_fields") or {}).get("dip") == new_dip
            and pr.get("undo_depth") == 1
        ),
        timeout=12,
    )
    assert probe, "dip edit did not commit as one undo entry"
    c1 = counts(probe)

    # -- step 2: create a block via one click in block mode -----------------
    app_page.locator(".btn-mode-block").click()
    assert wait_probe(app_page, lambda pr: pr.get("drag_layers") == ["blocks"])
    app_page.locator(".tab-block").click()
    app_page.wait_for_selector(".btn-new-block", state="visible")
    pt = empty_points(rows, box, n=1)[0]
    app_page.locator(".btn-new-block").click()
    assert wait_probe(app_page, lambda pr: pr.get("selection_mode") == "mapClick")
    app_page.mouse.click(*latlon_to_px(box, *pt))
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr["counts"]["blocks"] == c0["blocks"] + 1
            and pr.get("undo_depth") == 2
            and pr.get("selection_mode") == "normal"
        ),
    )
    assert probe, "block create did not add a block as a second undo entry"
    c2 = counts(probe)

    # -- step 3: delete the still-selected segment --------------------------
    app_page.locator(".tab-segment").click()
    app_page.wait_for_selector(".btn-delete", state="visible")
    app_page.locator(".btn-delete").click()
    probe = wait_probe(
        app_page,
        lambda pr: (
            pr["counts"]["segments"] == c0["segments"] - 1 and pr.get("undo_depth") == 3
        ),
    )
    assert probe, "delete did not remove the segment as a third undo entry"
    c3 = counts(probe)
    assert not app_page.locator(".btn-undo").is_disabled()
    assert app_page.locator(".btn-redo").is_disabled(), "redo enabled before any undo"

    # -- undo x3: counts return to each prior snapshot ----------------------
    for depth, expected in ((2, c2), (1, c1), (0, c0)):
        app_page.locator(".btn-undo").click()
        probe = wait_probe(app_page, lambda pr, d=depth: pr.get("undo_depth") == d)
        assert probe, f"undo did not reach depth {depth}"
        assert counts(probe) == expected, f"counts wrong after undo to depth {depth}"
    assert app_page.locator(".btn-undo").is_disabled(), "undo enabled at empty stack"
    assert not app_page.locator(".btn-redo").is_disabled()

    # the dip edit was reverted by the final undo
    click_segment_mid(app_page, box, rows, seg_idx)
    probe = wait_probe(
        app_page,
        lambda pr: (pr.get("selection") or {}).get("ids") == [seg_idx],
    )
    assert probe, "could not re-select the segment after full undo"
    assert float(probe["selection_fields"]["dip"]) == orig_dip, "dip not reverted"

    # -- redo x3: final state returns ---------------------------------------
    for depth, expected in ((1, c1), (2, c2), (3, c3)):
        app_page.locator(".btn-redo").click()
        probe = wait_probe(app_page, lambda pr, d=depth: pr.get("undo_depth") == d)
        assert probe, f"redo did not reach depth {depth}"
        assert counts(probe) == expected, f"counts wrong after redo to depth {depth}"
    assert app_page.locator(".btn-redo").is_disabled(), "redo enabled after full redo"
    assert not app_page.locator(".btn-undo").is_disabled()

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s9_undo_redo.png"))


# -- S10: Save Active Files writes only the dirty file ------------------------


def test_save_writes_expected_files(app_server, app_page):
    root = app_server["root"]
    open_japan_config(app_page, wait_probe)
    rows = load_segments(root)
    box = deck_box(app_page)

    seg_path = root / "segment" / "japan_segment.csv"
    pristine_segment = seg_path.read_text()
    pristine_block = (DATA_DIR / "block" / "japan_block.csv").read_bytes()

    # edit one segment's dip
    seg_idx = _select_isolated_segment(app_page, box, rows)
    orig_dip = float(rows[seg_idx]["dip"])
    new_dip = 23.5 if orig_dip != 23.5 else 40.0
    _edit_dip(app_page, new_dip)
    probe = wait_probe(
        app_page,
        lambda pr: (
            (pr.get("selection_fields") or {}).get("dip") == new_dip
            and "segment" in (pr.get("dirty") or [])
        ),
        timeout=12,
    )
    assert probe, "dip edit did not mark the segment file dirty"

    # save; the dirty badge clears
    app_page.locator(".btn-save-all").click()
    probe = wait_probe(app_page, lambda pr: pr.get("dirty") == [])
    assert probe, "Save Active Files did not clear the dirty state"

    # the segment file changed on disk and reflects the edit on reload
    saved_segment = seg_path.read_text()
    assert saved_segment != pristine_segment, "segment file was not rewritten"
    reloaded = read_segments(saved_segment)
    assert float(reloaded.expand_rows()[seg_idx]["dip"]) == new_dip, (
        "saved segment file does not reflect the dip edit"
    )

    # the (never-dirtied) block file is byte-identical to the pristine copy
    saved_block = (root / "block" / "japan_block.csv").read_bytes()
    assert saved_block == pristine_block, "an unedited file was rewritten by save"

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s10_save.png"))
