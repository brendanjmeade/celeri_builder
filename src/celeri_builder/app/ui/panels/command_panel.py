"""Command (config) inspector panel (celeri_ui ``Components/CommandPanel.tsx``).

Open / Save / Save As for the command JSON, plus an editor row for every
command key in ``state.command_fields`` (a dict the integrate agent keeps
in sync with ``doc.command``, unknown keys included) except the
file-reference keys in ``COMMAND_HIDDEN_FIELDS``. Edits call
``app.edit_command(key, value)``; numeric debouncing is handled
server-side by that method.
"""

from __future__ import annotations

from trame.widgets import html

from celeri_builder.app.ui import panel_base
from celeri_builder.model.schema import COMMAND_HIDDEN_FIELDS


def build(app) -> None:
    app.state.setdefault("command_fields", {})
    panel_base.file_buttons(app, "command", "Open Command File", "Save Command File")
    with html.Div(
        classes="command-fields pa-2 mt-2",
        style="border: 1px solid rgba(127, 127, 127, 0.5); border-radius: 4px;",
    ):
        # celeri_ui titles the editor with the command's file_name.
        html.Span(
            "{{ String(command_fields.file_name ?? 'Command') }}",
            classes="text-h6 command-title",
        )
        panel_base.build_field_rows(
            "command_fields",
            app.edit_command,
            hidden=COMMAND_HIDDEN_FIELDS,
        )
