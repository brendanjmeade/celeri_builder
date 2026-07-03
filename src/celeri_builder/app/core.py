"""CeleriBuilderApp: trame application shell (M1: load + display + save)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import ClassVar

from trame.app import TrameApp
from trame.ui.vuetify3 import VAppLayout
from trame.widgets import html

from celeri_builder.app import settings
from celeri_builder.app.ui import edit_mode_panel, top_bar
from celeri_builder.app.ui.file_explorer import FileExplorer
from celeri_builder.deck import mapbox
from celeri_builder.deck.display import default_display
from celeri_builder.deck.scene import empty_selection, register_all
from celeri_builder.io import project as project_io
from celeri_builder.model.document import Document
from celeri_builder.widgets import DeckEditor

# Bottom-to-top z-order of scene layer groups (celeri_ui layering).
GROUPS = (
    "graticule",
    "meshes",
    "generic",
    "dip_projection",
    "segments",
    "blocks",
    "velocities",
    "vertices",
)

DEFAULT_VIEW = {"longitude": 180.0, "latitude": 30.0, "zoom": 2}
TEST_VIEW = {"longitude": 140.0, "latitude": 37.5, "zoom": 5}


class CeleriBuilderApp(TrameApp):
    def __init__(self, server=None, root_dir: Path | None = None):
        super().__init__(server, client_type="vue3")
        self.scene = register_all()

        self.testing = os.environ.get("CELERI_BUILDER_TESTING") == "1"
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.doc = Document()
        self.refs: project_io.FileRefs | None = None
        self._save_task: asyncio.Task | None = None

        state = self.state
        state.trame__title = "celeri_builder"
        state.display = settings.load(default_display())
        for group in GROUPS:
            state[f"deck_layers_{group}"] = []
        state.deck_map_style = mapbox.resolve_style()
        state.deck_view_state = dict(TEST_VIEW if self.testing else DEFAULT_VIEW)
        state.deck_view_state_rev = 0
        state.deck_drag_layers = []
        state.deck_cursor_mode = "normal"
        state.folder_label = ""
        state.dirty_kinds = []
        state.can_undo = False
        state.can_redo = False
        state.edit_mode = "vertex"
        state.selection_mode = "normal"
        state.hover_lonlat = None
        state.test_probe = {}

        if self.server.hot_reload:
            self.server.controller.on_server_reload.add(self._build_ui)
        self._build_ui()

    # -- helpers --------------------------------------------------------------

    def _refresh(self, groups=None):
        """Rebuild layer-group descriptors from the document into state."""
        names = tuple(groups) if groups else GROUPS
        built = self.scene.build(names, self.doc, self.state.display, empty_selection())
        with self.state as state:
            for name in names:
                state[f"deck_layers_{name}"] = built.get(name, [])
        self._update_probe()

    def _update_probe(self):
        if not self.testing:
            return
        graph = self.doc.segments
        with self.state as state:
            state.test_probe = {
                "counts": {
                    "segments": len(graph.segments),
                    "vertices": len(graph.vertices),
                    "blocks": len(self.doc.blocks),
                    "velocities": len(self.doc.velocities),
                    "meshes": len(self.doc.meshes),
                },
                "mode": state.edit_mode,
                "selection_mode": state.selection_mode,
                "dirty": sorted(state.dirty_kinds),
                "layer_rows": {
                    g: sum(len(d.get("data", [])) for d in state[f"deck_layers_{g}"])
                    for g in GROUPS
                },
            }

    def _fly_to_data(self):
        vertices = list(self.doc.segments.vertices.values())
        lons = [v[0] for v in vertices] + [
            b.get("interior_lon", 0) for b in self.doc.blocks
        ]
        lats = [v[1] for v in vertices] + [
            b.get("interior_lat", 0) for b in self.doc.blocks
        ]
        if not lons:
            return
        with self.state as state:
            state.deck_view_state = {
                "longitude": (min(lons) + max(lons)) / 2,
                "latitude": (min(lats) + max(lats)) / 2,
                "zoom": 5,
            }
            state.deck_view_state_rev += 1

    # -- file actions ---------------------------------------------------------

    def on_open_config(self):
        self.file_explorer.open(
            self.open_config, extension=".json", title="Open config file"
        )

    def open_config(self, path: Path):
        doc, refs = project_io.load_project(Path(path))
        self.doc = doc
        self.refs = refs
        with self.state as state:
            state.folder_label = Path(path).parent.name + "/" + Path(path).name
            state.dirty_kinds = []
        self._refresh()
        if not self.testing:
            self._fly_to_data()

    def on_save_all(self):
        if self.refs is None:
            return
        kinds = set(self.state.dirty_kinds) or None
        if kinds is None:
            return
        project_io.save_project(self.doc, self.refs, kinds)
        with self.state as state:
            state.dirty_kinds = []
        self._update_probe()

    def mark_dirty(self, *kinds: str):
        with self.state as state:
            state.dirty_kinds = sorted(set(state.dirty_kinds) | set(kinds))

    # -- undo/redo (M2 wires the Store; placeholders keep TopBar honest) -----

    def on_undo(self):
        pass

    def on_redo(self):
        pass

    # -- display / mode handlers -----------------------------------------------

    PANEL_GROUPS: ClassVar[dict[str, tuple[str, ...]]] = {
        "segment": ("segments", "dip_projection"),
        "vertex": ("vertices",),
        "block": ("blocks",),
        "velocity": ("velocities",),
        "mesh": ("meshes",),
        "generic": ("generic",),
        "grid": ("graticule",),
    }

    def on_toggle_display(self, panel: str):
        display = json.loads(json.dumps(self.state.display))
        key = "show" if panel == "grid" else "hide"
        display[panel][key] = not display[panel][key]
        self.set_display(display, groups=self.PANEL_GROUPS.get(panel))

    def update_display(self, panel: str, key: str, value):
        """Single funnel for every nested display edit (reassigns the dict)."""
        display = json.loads(json.dumps(self.state.display))
        display[panel][key] = value
        self.set_display(display, groups=self.PANEL_GROUPS.get(panel))

    def set_display(self, display: dict, groups=None):
        with self.state as state:
            state.display = display
        self._refresh(groups)
        self._schedule_settings_save()

    def _schedule_settings_save(self):
        async def _save_later():
            await asyncio.sleep(1.0)
            settings.save(self.state.display)

        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        try:
            loop = asyncio.get_event_loop()
            self._save_task = loop.create_task(_save_later())
        except RuntimeError:
            settings.save(self.state.display)

    def on_toggle_lasso(self):
        with self.state as state:
            state.selection_mode = (
                "normal" if state.selection_mode == "lasso" else "lasso"
            )
        self._update_probe()

    # -- widget events (M1: hover + camera only; M2 adds picking) --------------

    def on_map_hover(self, event):
        with self.state as state:
            state.hover_lonlat = event.get("coordinate")

    def on_map_click(self, event):
        if self.testing:
            with self.state as state:
                probe = dict(state.test_probe or {})
                probe["last_pick"] = {
                    "picked": event.get("picked"),
                    "layerId": event.get("layerId"),
                    "index": event.get("index"),
                    "coordinate": event.get("coordinate"),
                }
                state.test_probe = probe

    def on_map_viewstate(self, event):
        with self.state as state:
            state.deck_view_state = {
                "longitude": event.get("longitude"),
                "latitude": event.get("latitude"),
                "zoom": event.get("zoom"),
            }

    def on_map_key(self, event):
        if event.get("key") == "Escape":
            with self.state as state:
                state.selection_mode = "normal"
            self._update_probe()

    # -- ui ------------------------------------------------------------------------

    def _build_ui(self):
        with VAppLayout(self.server, fill_height=True) as layout:
            self.ui = layout
            top_bar.build(self)
            with html.Div(
                style="position: fixed; inset: 48px 0 0 0;",
            ):
                DeckEditor(
                    groups=GROUPS,
                    map_style=("deck_map_style",),
                    view_state=("deck_view_state",),
                    view_state_revision=("deck_view_state_rev",),
                    drag_layers=("deck_drag_layers",),
                    cursor_mode=("deck_cursor_mode",),
                    click=(self.on_map_click, "[$event]"),
                    hover=(self.on_map_hover, "[$event]"),
                    viewstate=(self.on_map_viewstate, "[$event]"),
                    mapkey=(self.on_map_key, "[$event]"),
                )
            edit_mode_panel.build(self)
            self.file_explorer = FileExplorer(self, self.root_dir)
            self.file_explorer.build()
            if self.testing:
                html.Div(
                    "{{ JSON.stringify(test_probe) }}",
                    classes="test-probe",
                    style="display: none;",
                )
