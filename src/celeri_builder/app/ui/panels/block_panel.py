"""Block inspector panel (celeri_ui ``Components/BlockPanel.tsx``).

Display settings (``display.block.*``), Open / Save / Save As for the
block file, New Block arming, and the block selection editor.
"""

from __future__ import annotations

from celeri_builder.app.ui import panel_base
from celeri_builder.app.ui.editable_item import build_editable_item
from celeri_builder.model.schema import BLOCK_FIELDS

PLOT_KEY_OPTIONS = ["", *BLOCK_FIELDS]


def build(app) -> None:
    panel_base.toggle_row(app, "Display", "block", "hide")
    panel_base.file_buttons(app, "block", "Open Blocks", "Save Blocks")
    panel_base.color_row(app, "Color", "block", "color")
    panel_base.color_row(app, "Selected Color", "block", "selectedColor")
    panel_base.slider_row(app, "Radius", "block", "radius", 2, 10, 0.5)
    panel_base.select_row(
        app, "Plotted Value", "block", "plottableKey", PLOT_KEY_OPTIONS
    )
    panel_base.action_row(
        "Add New Block",
        "New Block",
        "btn-new-block",
        (app.arm_new, "['block']"),
    )
    build_editable_item(app, "block")
