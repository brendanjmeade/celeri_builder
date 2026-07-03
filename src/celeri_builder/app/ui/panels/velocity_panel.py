"""Velocity inspector panel (celeri_ui ``Components/VelocitiesPanel.tsx``).

Display settings (``display.velocity.*``), Open / Save / Save As for the
station (velocity) file, New Velocity arming, and the velocity selection
editor.
"""

from __future__ import annotations

from celeri_builder.app.ui import panel_base
from celeri_builder.app.ui.editable_item import build_editable_item
from celeri_builder.model.schema import VELOCITY_FIELDS

PLOT_KEY_OPTIONS = ["", *VELOCITY_FIELDS]


def build(app) -> None:
    panel_base.toggle_row(app, "Display", "velocity", "hide")
    panel_base.file_buttons(app, "station", "Open Velocities", "Save Velocities")
    panel_base.color_row(app, "Color", "velocity", "color")
    panel_base.color_row(app, "Selected Color", "velocity", "selectedColor")
    panel_base.slider_row(app, "Scale", "velocity", "scale", 0.001, 0.1, 0.001)
    panel_base.slider_row(app, "Width", "velocity", "width", 0.1, 2, 0.1)
    panel_base.slider_row(app, "Arrow Head Size", "velocity", "arrowHead", 0.5, 5, 0.1)
    panel_base.select_row(
        app, "Plotted Value", "velocity", "plottableKey", PLOT_KEY_OPTIONS
    )
    panel_base.action_row(
        "Add New Velocity",
        "New Velocity",
        "btn-new-velocity",
        (app.arm_new, "['velocity']"),
    )
    build_editable_item(app, "velocity")
