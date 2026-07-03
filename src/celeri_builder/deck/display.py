"""Per-panel display settings, mirroring celeri_ui's initial defaults.

Values come from the ``default*DisplaySettings`` consts in celeri_ui
(SegmentsPanel.tsx, VertexPanel.tsx, BlockPanel.tsx, VelocitiesPanel.tsx,
MeshPanel.tsx, GenericSegmentPanel.tsx, App.tsx grid toggle,
MapSettingsPanel.tsx style name). Hex colors are converted to the
``[r, g, b, a]`` lists the deck descriptors consume. celeri_ui names
``activeColor``/``activeWidth`` are exposed here as ``selectedColor`` /
``selectedWidth`` (the plan's naming; used from M2 for selection recolor).
"""

from __future__ import annotations

RGBA = list[int]


def hex_to_rgba(value: str, alpha: int = 255) -> RGBA:
    """``"#rrggbb"`` -> ``[r, g, b, alpha]`` (black on malformed input)."""
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        return [0, 0, 0, alpha]
    try:
        return [int(text[i : i + 2], 16) for i in (0, 2, 4)] + [alpha]
    except ValueError:
        return [0, 0, 0, alpha]


def default_display() -> dict[str, dict]:
    """Fresh nested display-settings dict (one sub-dict per panel)."""
    return {
        # SegmentsPanel.tsx defaultSegmentDisplaySettings
        "segment": {
            "hide": False,
            "color": hex_to_rgba("#ffff00"),
            "selectedColor": hex_to_rgba("#00ffff"),
            "width": 1,
            "selectedWidth": 2,
            "hideProjection": False,
            "projectionColor": hex_to_rgba("#ffff00"),
            "plottableKey": "",
        },
        # VertexPanel.tsx defaultVertexDisplaySettings
        "vertex": {
            "hide": False,
            "color": hex_to_rgba("#ffff00"),
            "selectedColor": hex_to_rgba("#00ffff"),
            "radius": 3,
        },
        # BlockPanel.tsx defaultBlockDisplaySettings
        "block": {
            "hide": False,
            "color": hex_to_rgba("#0000ff"),
            "selectedColor": hex_to_rgba("#ff0000"),
            "radius": 6,
            "plottableKey": "",
        },
        # VelocitiesPanel.tsx defaultVelocityDisplaySettings
        "velocity": {
            "hide": False,
            "color": hex_to_rgba("#ffffff"),
            "selectedColor": hex_to_rgba("#aaaaaa"),
            "scale": 0.02,
            "width": 1,
            "arrowHead": 1,
            "plottableKey": "",
        },
        # MeshPanel.tsx defaultMeshDisplaySettings
        "mesh": {
            "hide": False,
            "color": hex_to_rgba("#ffffff"),
            "width": 0.1,
        },
        # GenericSegmentPanel.tsx defaultGenericSegmentDisplaySettings
        "generic": {
            "hide": False,
            "color": hex_to_rgba("#ffffff"),
            "width": 0.1,
        },
        # App.tsx: displayGrid starts false; 10 deg is the plan's spacing.
        "grid": {
            "show": False,
            "spacing": 10,
        },
        # MapSettingsPanel.tsx defaultMapSettings.currentStyleName
        "map": {
            "styleName": "default",
        },
    }
