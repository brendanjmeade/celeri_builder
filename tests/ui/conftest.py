"""UI test fixtures: launch the app under test, provide probe helpers."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CELERI_DATA_DIR", REPO.parent / "data"))

pytestmark = pytest.mark.ui


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def japan_project(tmp_path) -> Path:
    """Copy the japan input tree into a per-test tmp dir; returns its root.

    Function-scoped so each test gets a clean app + files (save tests mutate
    the tree, and the trame server keeps process state across page reloads)."""
    if not DATA_DIR.exists():
        pytest.skip(f"example data dir not found: {DATA_DIR}")
    root = tmp_path / "japan_project"
    for sub in ("config", "segment", "block", "station", "mogi"):
        (root / sub).mkdir(parents=True)
        for f in (DATA_DIR / sub).glob("japan_*"):
            shutil.copy(f, root / sub / f.name)
    (root / "mesh").mkdir()
    for f in (DATA_DIR / "mesh").iterdir():
        if f.is_file():
            shutil.copy(f, root / "mesh" / f.name)
    return root


@pytest.fixture
def app_server(japan_project):
    """Start celeri-builder headless on a free port in testing mode.

    Function-scoped: a fresh server per test isolates process state."""
    port = _free_port()
    env = {
        **os.environ,
        "CELERI_BUILDER_TESTING": "1",
        "CELERI_BUILDER_NO_BASEMAP": "1",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from celeri_builder.app import main; main()",
            "--server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--root-dir",
            str(japan_project),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if "App running" in line:
            break
        if proc.poll() is not None:
            rest = proc.stdout.read()
            pytest.fail(f"app failed to start:\n{line}{rest}")
    time.sleep(0.5)
    yield {"port": port, "root": japan_project}
    proc.terminate()


@pytest.fixture
def app_page(app_server, page):
    """Playwright page pointed at the running app."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"http://127.0.0.1:{app_server['port']}/", wait_until="networkidle")
    page.wait_for_selector(".celeri-deck", state="visible", timeout=15000)
    return page


def read_probe(page) -> dict:
    txt = page.locator(".test-probe").inner_text()
    return json.loads(txt) if txt else {}


def wait_probe(page, pred, timeout=15.0, poll=0.1):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = read_probe(page)
            if pred(last):
                return last
        except Exception:
            pass
        time.sleep(poll)
    return last if last and pred(last) else None
