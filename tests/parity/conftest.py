"""Fixtures for the side-by-side parity harness.

Two independent halves share these fixtures:

- the BUILDER half (``drive_builder``) runs anywhere -- it only needs a
  writable copy of a region project;
- the CELERI_UI half (``drive_celeri_ui``) is gated behind a running
  celeri_ui checkout + Mapbox token and cleanly skips otherwise.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from . import drive_celeri_ui

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CELERI_DATA_DIR", REPO.parent / "data"))

pytestmark = pytest.mark.parity


# -- example data + writable workspaces --------------------------------------


@pytest.fixture(scope="session")
def parity_data_dir() -> Path:
    """The pristine celeri_build/data tree (override with ``CELERI_DATA_DIR``)."""
    if not DATA_DIR.exists():
        pytest.skip(f"example data dir not found: {DATA_DIR}")
    return DATA_DIR


def _copy_region(data_dir: Path, region: str, dest: Path) -> Path:
    """Copy one region's full input tree into ``dest``; return its config path.

    Preserves the ``config/ segment/ block/ station/ mesh/ mogi/`` layout so
    the config's ``../segment/...`` references resolve exactly as they do in
    the source tree.
    """
    for sub in ("config", "segment", "block", "station", "mogi"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
        for f in (data_dir / sub).glob(f"{region}_*"):
            shutil.copy(f, dest / sub / f.name)
    (dest / "mesh").mkdir(exist_ok=True)
    for f in (data_dir / "mesh").iterdir():
        if f.is_file():
            shutil.copy(f, dest / "mesh" / f.name)
    return dest / "config" / f"{region}_config.json"


@pytest.fixture
def builder_workspace(parity_data_dir, tmp_path_factory):
    """Factory: ``make(region="japan") -> config_path`` for a fresh copy.

    Each call mints an isolated tmp copy so a save-in-place replay never
    disturbs the source data or another script's output.
    """

    def make(region: str = "japan") -> Path:
        dest = tmp_path_factory.mktemp(f"builder_{region}_")
        return _copy_region(parity_data_dir, region, dest)

    return make


# -- celeri_ui availability + session ----------------------------------------


@pytest.fixture(scope="session")
def celeri_ui_status() -> tuple[bool, str]:
    """``(available, reason)`` for the live celeri_ui half."""
    return drive_celeri_ui.availability()


@pytest.fixture(scope="session")
def celeri_ui_driver(celeri_ui_status):
    """A running celeri_ui dev server + browser, or a clean skip.

    Session-scoped: one dev server is reused across every parity script; each
    ``run_script`` call opens its own fresh browser context. Skips (with the
    concrete reason -- missing node_modules or token) when celeri_ui cannot
    run here, which is the case in this environment.
    """
    available, reason = celeri_ui_status
    if not available:
        pytest.skip(f"celeri_ui parity deferred: {reason}")
    session = drive_celeri_ui.CeleriUiSession()
    with session:
        yield session
