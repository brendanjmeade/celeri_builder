"""Trame module registration for the celeri-deck widget.

Serves the vendored deck.gl / MapLibre bundles and the celeri_deck Vue 3
component so the app never loads client code from a CDN.
"""

from pathlib import Path

serve_path = str(Path(__file__).with_name("serve").resolve())

serve = {"__celeri_builder": serve_path}

scripts = [
    "__celeri_builder/maplibre-gl.js",
    "__celeri_builder/deck.min.js",
    "__celeri_builder/celeri_deck.js",
]

styles = ["__celeri_builder/maplibre-gl.css"]

vue_use = ["CeleriDeck"]
