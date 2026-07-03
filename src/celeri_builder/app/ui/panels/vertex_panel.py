"""Vertex inspector panel (celeri_ui ``Components/VertexPanel.tsx``).

Display settings (``display.vertex.*``), Open / Save of the segment file
(vertices live in it), per-selected-vertex lon/lat editors (the integrate
agent supplies ``selection_fields`` as ``{lon, lat}`` when
``selection.kind == 'vertex'``), and the Merge / Bridge / Extrude vertex
operations, which arm an override selection mode via
``app.arm_vertex_op(op)``.
"""

from __future__ import annotations

from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui import panel_base
from celeri_builder.app.ui.editable_item import build_editable_item

VERTEX_OPS = (
    ("merge", "Merge", "btn-merge"),
    ("bridge", "Bridge", "btn-bridge"),
    ("extrude", "Extrude", "btn-extrude"),
)


def build(app) -> None:
    panel_base.toggle_row(app, "Display", "vertex", "hide")
    panel_base.file_buttons(
        app,
        "segment",
        "Open Segments",
        "Save Segments & Vertices",
        save_as=False,
    )
    panel_base.color_row(app, "Color", "vertex", "color")
    panel_base.slider_row(app, "Radius", "vertex", "radius", 0.1, 5, 0.1)
    panel_base.color_row(app, "Active Color", "vertex", "selectedColor")

    def _ops() -> None:
        for op, label, classes in VERTEX_OPS:
            v3.VBtn(
                label,
                size="small",
                variant="tonal",
                classes=classes,
                click=(app.arm_vertex_op, f"['{op}']"),
            )

    build_editable_item(app, "vertex", controls=_ops)
