"""Canvas math and interaction helpers for UI tests."""

from __future__ import annotations

import math

# The app pins this view in testing mode (core.TEST_VIEW).
TEST_VIEW = {"longitude": 140.0, "latitude": 37.5, "zoom": 5}


def world_px(lon: float, lat: float, zoom: float) -> tuple[float, float]:
    world = 512 * 2**zoom
    x = (lon / 360 + 0.5) * world
    merc_y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    y = (0.5 - merc_y / (2 * math.pi)) * world
    return x, y


def latlon_to_px(box: dict, lon: float, lat: float, view=None) -> tuple[float, float]:
    """Map lon/lat to page pixels inside the deck container's bounding box."""
    view = view or TEST_VIEW
    lon = lon - 360 if lon > 180 and view["longitude"] <= 180 else lon
    wx, wy = world_px(lon, lat, view["zoom"])
    cx, cy = world_px(view["longitude"], view["latitude"], view["zoom"])
    return (
        box["x"] + box["width"] / 2 + (wx - cx),
        box["y"] + box["height"] / 2 + (wy - cy),
    )


def deck_box(page) -> dict:
    loc = page.locator(".celeri-deck")
    loc.wait_for(state="visible")
    return loc.bounding_box()


def open_japan_config(page, wait_probe):
    """Drive the file explorer to open config/japan_config.json."""
    page.locator(".btn-open-config").click()
    page.wait_for_selector(".file-explorer", state="visible")
    page.locator(".fx-entry", has_text="config").first.click()
    page.locator(".fx-entry", has_text="japan_config.json").first.click()
    page.locator(".fx-confirm").click()
    probe = wait_probe(page, lambda pr: (pr.get("counts") or {}).get("segments", 0) > 0)
    assert probe, "config never loaded (probe has no segment counts)"
    return probe
