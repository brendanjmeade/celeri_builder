"""Mesh inspector panel (celeri_ui ``Components/MeshPanel.tsx``).

Display settings (``display.mesh.*``), Open Mesh (single ``.msh``) and
Open Meshes (mesh-parameters JSON), plus the list of loaded meshes
(``state.mesh_names``, maintained by the integrate agent from
``doc.meshes``) with a per-mesh remove button.
"""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui import panel_base


def build(app) -> None:
    app.state.setdefault("mesh_names", [])
    panel_base.toggle_row(app, "Display", "mesh", "hide")
    with html.Div(classes="d-flex justify-space-between align-center my-1"):
        v3.VBtn(
            "Open Mesh",
            size="small",
            variant="tonal",
            classes="btn-open-mesh",
            click=(app.open_kind, "['mesh']"),
        )
        v3.VBtn(
            "Open Meshes",
            size="small",
            variant="tonal",
            classes="btn-open-mesh_params",
            click=(app.open_kind, "['mesh_params']"),
        )
    panel_base.color_row(app, "Color", "mesh", "color")
    panel_base.slider_row(app, "Width", "mesh", "width", 0.1, 2, 0.1)
    with v3.VList(
        v_show=("mesh_names.length",),
        density="compact",
        classes="mesh-list",
    ):
        with v3.VListItem(
            v_for="name in mesh_names",
            key=("name",),
            classes="mesh-item",
        ):
            v3.VListItemTitle("{{ name }}")
            with html.Template(v_slot_append=True):
                v3.VBtn(
                    icon="mdi-close",
                    size="x-small",
                    variant="text",
                    classes="btn-remove-mesh",
                    click=(app.remove_mesh, "[name]"),
                )
