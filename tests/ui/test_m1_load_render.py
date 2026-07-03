"""M1 UI gate: S1 open-folder renders all layers; S2 display toggles."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import read_probe, wait_probe
from .helpers import open_japan_config

pytestmark = pytest.mark.ui

ARTIFACTS = Path(__file__).parent / "artifacts"


def csv_row_count(path: Path) -> int:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    return len(lines) - 1  # header


def test_open_folder_renders_layers(app_server, app_page):
    probe = open_japan_config(app_page, wait_probe)

    root = app_server["root"]
    expected = {
        "segments": csv_row_count(root / "segment" / "japan_segment.csv"),
        "blocks": csv_row_count(root / "block" / "japan_block.csv"),
        "velocities": csv_row_count(root / "station" / "japan_station.csv"),
        # japan_mesh.json carries 4 entries (nankai, japan, sagami,
        # japan_mock_cmi) — see test_project_load.py.
        "meshes": 4,
    }
    counts = probe["counts"]
    for key, value in expected.items():
        assert counts[key] == value, f"{key}: probe {counts[key]} != csv {value}"
    # vertex sharing: fewer vertices than 2x segments
    assert 0 < counts["vertices"] < 2 * counts["segments"]

    rows = probe["layer_rows"]
    assert rows["segments"] >= counts["segments"]  # visible + hit layers
    assert rows["vertices"] >= counts["vertices"]
    assert rows["blocks"] >= counts["blocks"]
    assert rows["velocities"] >= counts["velocities"]
    assert rows["meshes"] > 0

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s1_japan_loaded.png"))


@pytest.mark.usefixtures("app_server")
def test_display_toggles(app_page):
    probe = open_japan_config(app_page, wait_probe)
    assert probe["layer_rows"]["segments"] > 0

    # hide segments
    app_page.locator(".btn-show-segment").click()
    probe = wait_probe(app_page, lambda pr: pr["layer_rows"]["segments"] == 0)
    assert probe, "segment layer did not empty on hide"

    # show again
    app_page.locator(".btn-show-segment").click()
    probe = wait_probe(app_page, lambda pr: pr["layer_rows"]["segments"] > 0)
    assert probe, "segment layer did not return on show"

    # grid graticule off by default, appears on toggle
    assert read_probe(app_page)["layer_rows"]["graticule"] == 0
    app_page.locator(".btn-show-grid").click()
    probe = wait_probe(app_page, lambda pr: pr["layer_rows"]["graticule"] > 0)
    assert probe, "graticule did not appear"
    app_page.locator(".btn-show-grid").click()

    ARTIFACTS.mkdir(exist_ok=True)
    app_page.screenshot(path=str(ARTIFACTS / "s2_toggles.png"))
