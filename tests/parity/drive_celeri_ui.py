"""Replay an abstract edit script against the LIVE celeri_ui web app.

This driver is GATED and DEFERRED: in this environment celeri_ui has no
``node_modules`` and there is no Mapbox token, so :func:`availability`
returns a skip reason and nothing here runs. It is written to run fully on
a token-equipped local checkout once the operator runs::

    cd celeri_ui && npm install
    echo "VITE_MAPBOX_TOKEN=pk...." > .env      # or export CELERI_UI_MAPBOX_TOKEN
    uv run pytest -m parity

What it does when enabled:

1. starts ``npm run dev`` (Vite) as a subprocess and waits for the banner;
2. opens Chromium at ``localhost:3000/?fake-dir`` and, BEFORE app scripts
   run, injects ``window.FakeDirectory`` (``page.add_init_script``) with the
   region files FLATTENED into a single directory and the config's
   ``*_file_name`` fields rewritten to bare filenames -- celeri_ui's
   ``GetProjectFile`` cannot resolve ``../segment/...`` against the in-memory
   FS, so flattening is the documented workaround;
3. drives each abstract op via celeri_ui ``data-testid`` selectors and, for
   geometry ops, synthetic Mapbox-canvas clicks computed with the SAME
   web-mercator pixel math the builder UI tests use;
4. saves via the toolbar and reads the results back out of
   ``window.FakeDirectory`` with ``page.evaluate``.

NOTE (celeri_ui parity fact): celeri_ui's ``saveFiles`` writes segment,
block and velocity CSVs but NOT the command JSON (its command save is
commented out in ``App.tsx``). The comparator therefore compares only the
CSV kinds for the celeri_ui side.
"""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from celeri_builder.io.project import load_project

try:  # playwright is a test dependency; guard so a missing install skips, not errors.
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised only where playwright is absent
    sync_playwright = None

# celeri_ui lives beside celeri_builder in the celeri_build workspace.
CELERI_UI_DIR = Path(
    os.environ.get(
        "CELERI_UI_DIR",
        Path(__file__).resolve().parents[3] / "celeri_ui",
    )
)

# The pinned parity view for celeri_ui's map. Must match the pixel math the
# builder UI tests use so identical lon/lat map to identical canvas pixels.
PARITY_VIEW = {"longitude": 140.0, "latitude": 37.5, "zoom": 5}

_MESH_PARAM_KEY = "mesh_parameters_file_name"
_CONFIG_FILE_KEYS = (
    "segment_file_name",
    "block_file_name",
    "station_file_name",
    _MESH_PARAM_KEY,
    "mogi_file_name",
    "sar_file_name",
)


# -- availability gate --------------------------------------------------------


def mapbox_token() -> str | None:
    """The Mapbox token from ``CELERI_UI_MAPBOX_TOKEN`` or ``celeri_ui/.env``."""
    token = os.environ.get("CELERI_UI_MAPBOX_TOKEN")
    if token:
        return token.strip()
    env_file = CELERI_UI_DIR / ".env"
    if env_file.is_file():
        for raw in env_file.read_text().splitlines():
            line = raw.strip()
            if line.startswith("VITE_MAPBOX_TOKEN"):
                _, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                if value:
                    return value
    return None


def availability() -> tuple[bool, str]:
    """``(True, "")`` when celeri_ui can run here, else ``(False, reason)``."""
    if not CELERI_UI_DIR.is_dir():
        return False, f"celeri_ui checkout not found at {CELERI_UI_DIR}"
    if not (CELERI_UI_DIR / "node_modules").is_dir():
        return (
            False,
            f"celeri_ui/node_modules missing (run `cd {CELERI_UI_DIR} && npm install`)",
        )
    if mapbox_token() is None:
        return (
            False,
            "no Mapbox token (set CELERI_UI_MAPBOX_TOKEN or celeri_ui/.env "
            "VITE_MAPBOX_TOKEN)",
        )
    if sync_playwright is None:
        return False, "playwright not installed"
    return True, ""


# -- FakeDirectory construction ----------------------------------------------


def flatten_project(config_path: Path) -> tuple[dict, dict]:
    """Flatten a region project into celeri_ui's ``window.FakeDirectory`` shape.

    Returns ``(fake_directory, filenames)`` where ``fake_directory`` is
    ``{"root": {<bare filename>: <text>, ...}}`` (InMemoryFileSystem expects
    a top-level ``root`` folder) and ``filenames`` maps each ``kind`` to the
    bare filename it now lives under. The config JSON is rewritten so every
    ``*_file_name`` value is a bare filename resolvable against the flat root.
    """
    config_path = Path(config_path)
    project_root = config_path.parents[1]
    command = json.loads(config_path.read_text())

    root: dict[str, str] = {}
    filenames: dict[str, str] = {}

    def add(kind: str, source: Path) -> str:
        name = source.name
        root[name] = source.read_text()
        filenames[kind] = name
        return name

    kind_by_key = {
        "segment_file_name": "segment",
        "block_file_name": "block",
        "station_file_name": "station",
    }
    for key, kind in kind_by_key.items():
        value = command.get(key)
        if not value:
            continue
        source = (project_root / value.replace("../", "", 1)).resolve()
        if not source.is_file():
            source = (config_path.parent / value).resolve()
        command[key] = add(kind, source)

    # Mesh params JSON + every .msh it references, all flattened. celeri_ui
    # already reduces mesh_filename to its last path component, but flatten
    # the referenced files so they resolve in the flat root.
    mesh_value = command.get(_MESH_PARAM_KEY)
    if mesh_value:
        mesh_json = (project_root / mesh_value.replace("../", "", 1)).resolve()
        if mesh_json.is_file():
            mesh_params = json.loads(mesh_json.read_text())
            for entry in mesh_params if isinstance(mesh_params, list) else []:
                ref = entry.get("mesh_filename")
                if not ref:
                    continue
                bare = Path(ref).name
                msh = (mesh_json.parent / bare).resolve()
                if msh.is_file():
                    root[bare] = msh.read_text()
                entry["mesh_filename"] = bare
            bare_json = mesh_json.name
            root[bare_json] = json.dumps(mesh_params)
            command[_MESH_PARAM_KEY] = bare_json
            filenames["mesh_params"] = bare_json

    # Drop references celeri_ui does not load, keeping the config resolvable.
    for key in ("mogi_file_name", "sar_file_name"):
        if command.get(key):
            command[key] = Path(str(command[key])).name

    config_name = config_path.name
    root[config_name] = json.dumps(command, indent=2)
    filenames["command"] = config_name
    return {"root": root}, filenames


# -- pixel math (identical to tests/ui web-mercator) --------------------------


def _world_px(lon: float, lat: float, zoom: float) -> tuple[float, float]:
    world = 512 * 2**zoom
    x = (lon / 360 + 0.5) * world
    merc_y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    y = (0.5 - merc_y / (2 * math.pi)) * world
    return x, y


def latlon_to_px(box: dict, lon: float, lat: float, view: dict | None = None):
    """lon/lat -> page pixels inside the map container (same math as tests/ui)."""
    view = view or PARITY_VIEW
    if lon > 180 and view["longitude"] <= 180:
        lon -= 360
    wx, wy = _world_px(lon, lat, view["zoom"])
    cx, cy = _world_px(view["longitude"], view["latitude"], view["zoom"])
    return (
        box["x"] + box["width"] / 2 + (wx - cx),
        box["y"] + box["height"] / 2 + (wy - cy),
    )


# -- dev-server + browser session --------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class CeleriUiResult:
    """Saved file text read back out of ``window.FakeDirectory``."""

    files: dict[str, str]  # kind -> file text

    def text(self, kind: str) -> str:
        return self.files[kind]


class CeleriUiSession:
    """A running celeri_ui dev server + Chromium page (context manager)."""

    def __init__(self) -> None:
        ok, reason = availability()
        if not ok:
            msg = f"celeri_ui unavailable: {reason}"
            raise RuntimeError(msg)
        self.port = _free_port()
        self._proc: subprocess.Popen | None = None
        self._pw = None
        self._browser = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> CeleriUiSession:
        self._start_dev_server()
        self._start_browser()
        return self

    def __exit__(self, *exc) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _start_dev_server(self) -> None:
        env = {**os.environ, "VITE_MAPBOX_TOKEN": mapbox_token() or ""}
        self._proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(self.port), "--strictPort"],
            cwd=CELERI_UI_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 90
        while time.time() < deadline:
            assert self._proc.stdout is not None
            line = self._proc.stdout.readline()
            if not line and self._proc.poll() is not None:
                rest = self._proc.stdout.read()
                msg = f"celeri_ui dev server exited early:\n{rest}"
                raise RuntimeError(msg)
            if "Local:" in line or "ready in" in line or "localhost" in line:
                break
        time.sleep(1.0)

    def _start_browser(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()

    # -- one script --------------------------------------------------------

    def run_script(self, config_path: Path, ops) -> CeleriUiResult:
        """Open the (flattened) project, replay ``ops``, save, read back."""
        self._region_config = Path(config_path)
        fake_dir, filenames = flatten_project(config_path)
        context = self._browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.add_init_script(f"window.FakeDirectory = {json.dumps(fake_dir)};")
        page.goto(f"http://127.0.0.1:{self.port}/?fake-dir", wait_until="networkidle")
        try:
            self._open_project(page, filenames["command"])
            for op, params in ops:
                self._apply(page, op, params)
            self._save(page)
            files = self._read_back(page, filenames)
        finally:
            context.close()
        return CeleriUiResult(files=files)

    # -- open + save + read-back ------------------------------------------

    def _open_project(self, page, config_name: str) -> None:
        # Toolbar: open the (fake) folder, then the command file via the
        # command panel + file explorer.
        page.get_by_test_id("open-folder-button").click()
        page.get_by_role("button", name="Open Command File").click()
        page.get_by_test_id(f"file-{config_name}").click()
        page.get_by_test_id("select-button").click()
        # Segments render once the command file resolves its references.
        page.wait_for_selector('[data-testid="map"]', state="visible")
        page.wait_for_timeout(500)

    def _save(self, page) -> None:
        page.get_by_test_id("save-file-button").click()
        page.wait_for_timeout(200)

    def _read_back(self, page, filenames: dict[str, str]) -> dict[str, str]:
        contents = page.evaluate("() => window.FakeDirectory.root")
        files: dict[str, str] = {}
        # celeri_ui writes segment/block/station CSVs; the command JSON is
        # NOT written back (its save is disabled in App.tsx).
        for kind in ("segment", "block", "station"):
            name = filenames.get(kind)
            if name and name in contents:
                files[kind] = contents[name]
        return files

    # -- op dispatch -------------------------------------------------------
    #
    # Each abstract op maps to a celeri_ui gesture. Map-pixel-dependent
    # gestures (clicks/drags) use latlon_to_px against the map canvas box;
    # the pinned PARITY_VIEW must match the builder's so identical lon/lat
    # produce identical pixels. These flows are exercised for the first time
    # on a token-equipped local run (calibration point).

    def _map_box(self, page) -> dict:
        loc = page.get_by_test_id("map")
        loc.wait_for(state="visible")
        return loc.bounding_box()

    def _click_lonlat(self, page, lon: float, lat: float) -> None:
        box = self._map_box(page)
        x, y = latlon_to_px(box, lon, lat)
        page.mouse.click(x, y)

    def _apply(self, page, op: str, params: dict) -> None:
        handler = {
            "edit_segments": self._edit_segments,
            "create_segment": self._create_segment,
            "move_vertex": self._move_vertex,
            "delete_segments": self._delete_segments,
            "split_segment": self._split_segment,
            "undo_all": self._undo_all,
        }.get(op)
        if handler is None:
            msg = f"unknown parity op {op!r}"
            raise ValueError(msg)
        handler(page, params)

    def _select_segment_by_name(self, page, name: str) -> None:
        # Enter Segment edit mode and pick the segment on the map. celeri_ui
        # selects segments by clicking their hit-line at the midpoint.
        page.get_by_test_id("edit-mode-segment").click()
        # Midpoint pixel resolution requires reading the segment geometry; on
        # the local run this reads the loaded CSV to compute the midpoint.
        lon, lat = _segment_midpoint(self._region_config, name)
        self._click_lonlat(page, lon, lat)

    def _edit_segments(self, page, params: dict) -> None:
        for name in params["names"]:
            self._select_segment_by_name(page, name)
            for field, value in params["patch"].items():
                editor = page.get_by_test_id(f"input-editor-{field}")
                editor.fill(str(value))
                editor.press("Enter")

    def _create_segment(self, page, params: dict) -> None:
        page.get_by_test_id("edit-mode-segment").click()
        self._click_lonlat(page, *params["start"])
        self._click_lonlat(page, *params["end"])

    def _move_vertex(self, page, params: dict) -> None:
        page.get_by_test_id("edit-mode-segment").click()
        box = self._map_box(page)
        x0, y0 = latlon_to_px(box, *params["at"])
        x1, y1 = latlon_to_px(box, *params["to"])
        page.mouse.move(x0, y0)
        page.mouse.down()
        page.mouse.move(x1, y1, steps=8)
        page.mouse.up()

    def _delete_segments(self, page, params: dict) -> None:
        for name in params["names"]:
            self._select_segment_by_name(page, name)
            page.get_by_test_id("editable-item-title").click()
            page.keyboard.press("Delete")

    def _split_segment(self, page, params: dict) -> None:
        self._select_segment_by_name(page, params["name"])
        page.get_by_test_id("split-segment-button").click()

    def _undo_all(self, page, _params: dict) -> None:
        undo = page.get_by_test_id("undo-button").first
        for _ in range(500):
            if undo.is_disabled():
                break
            undo.click()

    # The config path of the script currently running (set by run_script) so
    # segment-midpoint resolution can read the source geometry.
    _region_config: Path | None = None


def _segment_midpoint(config_path: Path | None, name: str) -> tuple[float, float]:
    """Midpoint lon/lat of a named segment, read from the source CSV.

    Used only on the live local run to aim map clicks at a segment's
    hit-line. Raises if the geometry cannot be resolved.
    """
    if config_path is None:
        msg = "segment geometry unavailable (no region config bound)"
        raise RuntimeError(msg)
    document, _ = load_project(config_path)
    for seg in document.segments.segments:
        if str(seg.get("name")) == str(name):
            (lon1, lat1), (lon2, lat2) = document.segments.segment_endpoints(seg)
            return (lon1 + lon2) / 2, (lat1 + lat2) / 2
    msg = f"segment {name!r} not found for midpoint resolution"
    raise KeyError(msg)


@contextmanager
def celeri_ui_session():
    """Yield a running :class:`CeleriUiSession`, or raise if unavailable."""
    session = CeleriUiSession()
    with session:
        yield session
