"""Bottom-left floating panel: lasso toggle, hover coordinates, edit-mode
buttons, and per-layer display toggles (celeri_ui EditModePanel)."""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

EDIT_MODES = (
    ("block", "Block"),
    ("vertex", "Vertex"),
    ("velocities", "Velocity"),
    ("segment", "Segment"),
)

# label, display panel, hide key ('show' for grid which is inverted)
DISPLAY_TOGGLES = (
    ("Block", "block"),
    ("Vertex", "vertex"),
    ("Velocity", "velocity"),
    ("Segment", "segment"),
    ("Grid", "grid"),
    ("Mesh", "mesh"),
    ("CSVs", "generic"),
)


def build(app):
    with v3.VCard(
        classes="edit-mode-panel pa-2",
        style=(
            "position: absolute; bottom: 12px; left: 12px; z-index: 5;"
            "min-width: 300px; opacity: 0.94;"
        ),
    ):
        with html.Div(classes="d-flex align-center mb-1"):
            v3.VBtn(
                "Lasso Selection",
                size="x-small",
                classes="btn-lasso",
                variant=("selection_mode === 'lasso' ? 'flat' : 'outlined'",),
                color="primary",
                click=app.on_toggle_lasso,
            )
            html.Span(
                "{{ hover_lonlat ? hover_lonlat[0].toFixed(3) + ', ' "
                "+ hover_lonlat[1].toFixed(3) : '' }}",
                classes="text-caption ml-3 hover-coords",
            )
        with html.Div(classes="d-flex align-center mb-1"):
            html.Span("Editing:", classes="text-caption mr-2")
            with v3.VBtnToggle(
                v_model=("edit_mode",),
                density="compact",
                mandatory=False,
                classes="edit-mode-toggle",
            ):
                for value, label in EDIT_MODES:
                    v3.VBtn(
                        label,
                        size="x-small",
                        value=value,
                        classes=f"btn-mode-{value}",
                    )
        with html.Div(classes="d-flex align-center flex-wrap"):
            html.Span("Displaying:", classes="text-caption mr-2")
            for label, panel in DISPLAY_TOGGLES:
                key = "show" if panel == "grid" else "hide"
                on_value = "true" if key == "show" else "false"
                v3.VBtn(
                    label,
                    size="x-small",
                    classes=f"mr-1 btn-show-{panel}",
                    variant=(
                        f"display.{panel}.{key} === {on_value} ? 'flat' : 'outlined'",
                    ),
                    color="secondary",
                    click=(app.on_toggle_display, f"['{panel}']"),
                )
