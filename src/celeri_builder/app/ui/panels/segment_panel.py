"""Segment inspector panel (celeri_ui ``Components/SegmentsPanel.tsx``).

Display settings (``display.segment.*`` keys from ``default_display()``),
Open / Save / Save As for the segment file, New Segment arming, and the
selection editor with a Split Segment control.
"""

from __future__ import annotations

from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui import panel_base
from celeri_builder.app.ui.editable_item import build_editable_item
from celeri_builder.model.schema import SEGMENT_FIELDS

PLOT_KEY_OPTIONS = ["", *SEGMENT_FIELDS]


def build(app) -> None:
    panel_base.toggle_row(app, "Display", "segment", "hide")
    panel_base.toggle_row(app, "Projection", "segment", "hideProjection")
    panel_base.file_buttons(app, "segment", "Open Segments", "Save Segments & Vertices")
    panel_base.color_row(app, "Color", "segment", "color")
    panel_base.slider_row(app, "Width", "segment", "width", 0.1, 2, 0.1)
    panel_base.color_row(app, "Active Color", "segment", "selectedColor")
    panel_base.slider_row(app, "Active Width", "segment", "selectedWidth", 0.1, 2, 0.1)
    panel_base.color_row(app, "Projection Color", "segment", "projectionColor")
    panel_base.select_row(
        app, "Plotted Value", "segment", "plottableKey", PLOT_KEY_OPTIONS
    )
    panel_base.action_row(
        "Add New Segment",
        "New Segment",
        "btn-new-segment",
        (app.arm_new, "['segment']"),
    )

    def _controls() -> None:
        v3.VBtn(
            "Split Segment",
            size="small",
            variant="tonal",
            classes="btn-split",
            click=app.split_selection,
        )

    build_editable_item(app, "segment", controls=_controls)
