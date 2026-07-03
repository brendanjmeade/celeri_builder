"""Shared fixtures: example celeri data, per-region tmp project copies."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# The sibling workspace data dir (celeri_build/data) unless overridden.
DATA_DIR = Path(
    os.environ.get("CELERI_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
)

REGIONS = ("japan", "wna")


@pytest.fixture(scope="session")
def data_dir() -> Path:
    if not DATA_DIR.exists():
        pytest.skip(f"example data dir not found: {DATA_DIR}")
    return DATA_DIR


@pytest.fixture(params=REGIONS)
def region(request) -> str:
    return request.param


@pytest.fixture
def example_project(tmp_path: Path, data_dir: Path, region: str) -> Path:
    """Copy one region's full input tree into tmp, preserving relative
    layout (config/, segment/, block/, station/, mesh/, mogi/). Returns the
    config file path. Save tests operate on the copy only."""
    for sub in ("config", "segment", "block", "station", "mogi"):
        src = data_dir / sub
        dst = tmp_path / sub
        dst.mkdir()
        for f in src.glob(f"{region}_*"):
            shutil.copy(f, dst / f.name)
    # mesh dir: mesh params json + every .msh it references (plus extras)
    (tmp_path / "mesh").mkdir()
    for f in (data_dir / "mesh").iterdir():
        if f.is_file():
            shutil.copy(f, tmp_path / "mesh" / f.name)
    return tmp_path / "config" / f"{region}_config.json"


@pytest.fixture
def raw_text(data_dir: Path):
    """Loader for raw example file text, e.g. raw_text('segment', 'japan')."""

    def _load(kind: str, region_name: str, ext: str | None = None) -> str:
        suffix = {"config": "json", "mesh": "json"}.get(kind, "csv")
        if ext:
            suffix = ext
        name = f"{region_name}_{kind}.{suffix}"
        return (data_dir / kind / name).read_text()

    return _load
