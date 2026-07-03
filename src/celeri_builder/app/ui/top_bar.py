"""Top application bar: open folder, save, undo/redo (celeri_ui TopBar)."""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3


def build(app):
    with v3.VAppBar(density="compact", flat=True):
        v3.VAppBarTitle("celeri_builder")
        v3.VSpacer()
        html.Span(
            "Working in {{ folder_label }}",
            v_show="folder_label",
            classes="text-caption mr-4 folder-label",
        )
        v3.VBtn(
            "Open Config",
            prepend_icon="mdi-folder-open",
            variant="text",
            classes="btn-open-config",
            click=app.on_open_config,
        )
        with v3.VBtn(
            "Save Active Files",
            prepend_icon="mdi-content-save",
            variant="text",
            classes="btn-save-all",
            disabled=("!dirty_kinds.length",),
            click=app.on_save_all,
        ):
            v3.VBadge(
                content=("dirty_kinds.length",),
                v_show="dirty_kinds.length",
                inline=True,
            )
        v3.VBtn(
            icon="mdi-undo",
            variant="text",
            classes="btn-undo",
            disabled=("!can_undo",),
            click=app.on_undo,
        )
        v3.VBtn(
            icon="mdi-redo",
            variant="text",
            classes="btn-redo",
            disabled=("!can_redo",),
            click=app.on_redo,
        )
