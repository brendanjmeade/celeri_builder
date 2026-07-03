"""Generic-segments (CSV overlay) inspector panel
(celeri_ui ``Components/GenericSegmentPanel.tsx``).

Display settings (``display.generic.*``), Open Segments (arbitrary CSV via
``app.open_kind('generic')``) and one card per loaded collection with
column-mapping selects. Collections come from ``state.generic_collections``
(maintained by the integrate agent from ``doc.generic``) as a list of
``{"name": str, "columns": [str, ...], "keys": {<key>: str, ...}}`` where
``keys`` holds ``GenericCollection``'s ``start_lon_key`` / ``start_lat_key``
/ ``end_lon_key`` / ``end_lat_key`` / ``plot_key``. Changing a select calls
``app.set_generic_keys(name, key, value)``; the remove button calls
``app.remove_generic(name)``.
"""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui import panel_base

# (GenericCollection key, label) — celeri_ui field definitions.
KEY_SELECTS = (
    ("start_lon_key", "Start Longitude"),
    ("start_lat_key", "Start Latitude"),
    ("end_lon_key", "End Longitude"),
    ("end_lat_key", "End Latitude"),
    ("plot_key", "Plot Key"),
)


def build(app) -> None:
    app.state.setdefault("generic_collections", [])
    panel_base.toggle_row(app, "Display", "generic", "hide")
    with html.Div(classes="d-flex justify-space-between align-center my-1"):
        v3.VBtn(
            "Open Segments",
            size="small",
            variant="tonal",
            classes="btn-open-generic",
            click=(app.open_kind, "['generic']"),
        )
    panel_base.color_row(app, "Color", "generic", "color")
    panel_base.slider_row(app, "Width", "generic", "width", 0.1, 2, 0.1)

    with html.Div(
        v_for="col in generic_collections",
        key=("col.name",),
        classes="generic-collection pa-2 mt-2",
        style="border: 1px solid rgba(127, 127, 127, 0.5); border-radius: 4px;",
    ):
        with html.Div(classes="d-flex justify-space-between align-center mb-1"):
            html.Span("{{ col.name }}", classes="text-h6")
            v3.VBtn(
                "Remove",
                size="small",
                color="error",
                variant="tonal",
                classes="btn-remove-generic",
                click=(app.remove_generic, "[col.name]"),
            )
        for key, label in KEY_SELECTS:
            with html.Div(classes="d-flex justify-space-between align-center my-1"):
                html.Span(label, classes="text-subtitle-2 font-weight-bold")
                with html.Div(style="width: 40%; flex-shrink: 0;"):
                    v3.VSelect(
                        model_value=(f"col.keys.{key}",),
                        items=("col.columns",),
                        update_modelValue=(
                            app.set_generic_keys,
                            f"[col.name, '{key}', $event]",
                        ),
                        density="compact",
                        hide_details=True,
                        variant="outlined",
                        classes=f"select-{key}",
                    )
