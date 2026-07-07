"""M0 spike: prove the celeri-deck widget round-trips events with Python.

Run:  python spike/deck_widget_spike.py --server --port 5391
Then open http://localhost:5391/ (or drive it with spike/verify_spike.py).

Success criteria (from the plan):
- click picks (layerId, index); empty click gives lon/lat
- hover events reach Python at <= 10 Hz
- drag: pan disarmed over point, client ghost, dragend commits server-side
- camera survives a layer push (big-data button)
- japan-scale push (2000 lines + 1500 points) stays interactive
"""

import argparse
import json
import time

from trame.app import TrameApp
from trame.ui.vuetify3 import VAppLayout
from trame.widgets import html
from trame.widgets import vuetify3 as v3

from celeri_builder.widgets import DeckEditor

CARTO_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

POINTS = [
    {"lon": 0.0, "lat": 0.0, "name": "origin", "tooltip": "origin"},
    {"lon": 20.0, "lat": 10.0, "name": "p_ne", "tooltip": "p_ne"},
    {"lon": -20.0, "lat": -10.0, "name": "p_sw", "tooltip": "p_sw"},
]

LINES = [
    {"slon": 0.0, "slat": 0.0, "tlon": 20.0, "tlat": 10.0, "name": "l0"},
    {"slon": 0.0, "slat": 0.0, "tlon": -20.0, "tlat": -10.0, "name": "l1"},
]


def point_layer(points):
    return {
        "type": "ScatterplotLayer",
        "id": "points",
        "data": points,
        "getPosition": ["@lon", "@lat"],
        "getFillColor": [200, 30, 30, 255],
        "radiusMinPixels": 8,
        "pickable": True,
    }


def line_layer(lines):
    return {
        "type": "LineLayer",
        "id": "lines",
        "data": lines,
        "getSourcePosition": ["@slon", "@slat"],
        "getTargetPosition": ["@tlon", "@tlat"],
        "getColor": [30, 30, 200, 255],
        "getWidth": 3,
        "pickable": True,
        "widthUnits": "pixels",
    }


class SpikeApp(TrameApp):
    def __init__(self, server=None, map_style=CARTO_STYLE):
        super().__init__(server, client_type="vue3")
        self._points = [dict(p) for p in POINTS]
        self._lines = [dict(line) for line in LINES]
        self._map_style = map_style
        self._push_started = 0.0
        self._counters = {"hover": 0, "drag": 0, "click": 0}

        self.state.deck_layers_points = [point_layer(self._points)]
        self.state.deck_layers_lines = [line_layer(self._lines)]
        self.state.deck_view_state = {"longitude": 0, "latitude": 0, "zoom": 2}
        self.state.deck_view_state_rev = 0
        self.state.spike_probe = {"ready": False}

        self._build_ui()

    # -- probe ---------------------------------------------------------------
    def _update_probe(self, **patch):
        with self.state:
            probe = {**(self.state.spike_probe or {}), **patch}
            self.state.spike_probe = probe
        print("EVT", json.dumps(patch), flush=True)

    # -- event handlers --------------------------------------------------------
    def on_ready(self, _event=None):
        self._update_probe(ready=True)

    def on_click(self, event):
        self._counters["click"] += 1
        self._update_probe(last_click=event, n_click=self._counters["click"])

    def on_hover(self, event):
        self._counters["hover"] += 1
        self._update_probe(
            last_hover={"coordinate": event.get("coordinate")},
            n_hover=self._counters["hover"],
            hover_t=time.time(),
        )

    def on_dragstart(self, event):
        self._update_probe(last_dragstart=event)

    def on_drag(self, _event):
        self._counters["drag"] += 1
        self._update_probe(n_drag=self._counters["drag"])

    def on_dragend(self, event):
        # Commit the move server-side: update the row and push fresh layers.
        idx = event.get("index", -1)
        coord = event.get("coordinate")
        if event.get("layerId") == "points" and idx >= 0 and coord:
            self._points[idx] = {
                **self._points[idx],
                "lon": coord[0],
                "lat": coord[1],
            }
            with self.state:
                self.state.deck_layers_points = [point_layer(self._points)]
        self._update_probe(last_dragend=event, points=self._points)

    def on_viewstate(self, event):
        self._update_probe(view_state=event)

    def on_mapkey(self, event):
        self._update_probe(last_key=event)

    # -- actions ----------------------------------------------------------------
    def load_big(self):
        n_lines, n_points = 2000, 1500
        lines = [
            {
                "slon": (i * 0.17) % 60 - 30.0,
                "slat": (i * 0.11) % 40 - 20.0,
                "tlon": (i * 0.17) % 60 - 29.0,
                "tlat": (i * 0.11) % 40 - 19.0,
                "name": f"big_l{i}",
            }
            for i in range(n_lines)
        ]
        points = [
            {
                "lon": (i * 0.23) % 60 - 30.0,
                "lat": (i * 0.13) % 40 - 20.0,
                "name": f"big_p{i}",
                "tooltip": f"big_p{i}",
            }
            for i in range(n_points)
        ]
        self._push_started = time.time()
        with self.state:
            self.state.deck_layers_lines = [line_layer(self._lines + lines)]
            self.state.deck_layers_points = [point_layer(self._points + points)]
        self._update_probe(big_loaded=True, big_push_t=self._push_started)

    def fly_to(self):
        with self.state:
            self.state.deck_view_state = {
                "longitude": 140,
                "latitude": 37.5,
                "zoom": 5,
            }
            self.state.deck_view_state_rev += 1
        self._update_probe(flew=True)

    # -- ui ----------------------------------------------------------------------
    def _build_ui(self):
        with VAppLayout(self.server, fill_height=True) as layout:
            self.ui = layout
            with html.Div(
                style=(
                    "width: 800px; height: 600px; position: relative;"
                    "border: 1px solid #888;"
                ),
            ):
                DeckEditor(
                    groups=["lines", "points"],
                    map_style=("deck_map_style", self._map_style),
                    view_state=("deck_view_state",),
                    view_state_revision=("deck_view_state_rev",),
                    drag_layers=("deck_drag_layers", ["points"]),
                    ready=(self.on_ready, "[$event]"),
                    click=(self.on_click, "[$event]"),
                    hover=(self.on_hover, "[$event]"),
                    dragstart=(self.on_dragstart, "[$event]"),
                    drag=(self.on_drag, "[$event]"),
                    dragend=(self.on_dragend, "[$event]"),
                    viewstate=(self.on_viewstate, "[$event]"),
                    mapkey=(self.on_mapkey, "[$event]"),
                )
            with html.Div(style="padding: 8px;"):
                v3.VBtn("Load big", click=self.load_big, classes="btn-big")
                v3.VBtn("Fly to Japan", click=self.fly_to, classes="btn-fly")
            html.Pre(
                "{{ spike_probe }}",
                classes="spike-probe",
                style="font-size: 10px; max-width: 800px; white-space: pre-wrap;",
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blank", action="store_true", help="no basemap")
    args, _ = parser.parse_known_args()
    app = SpikeApp(map_style=None if args.blank else CARTO_STYLE)
    app.server.start()


if __name__ == "__main__":
    main()
