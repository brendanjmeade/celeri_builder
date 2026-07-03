"""EditableItem: bulk property editor for the current selection
(celeri_ui ``Components/EditableItem.tsx``).

Renders one row per entry of ``state.selection_fields`` — a dict
``field -> value`` precomputed SERVER-side from the selection, where a
multi-selection collapses fields with differing values to the mixed
marker ``"-"``. Every change calls ``app.edit_selection(field, value)``:
string edits apply immediately, while numeric-field debouncing
(celeri_ui's 1 s client-side timeout) is handled SERVER-side inside
``app.edit_selection``.

Title: a single selection shows its ``name``; a multi-selection shows
``Edit Selected <Kind>s``. A Delete button (``app.delete_selection``)
appears for deletable kinds.
"""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui import panel_base
from celeri_builder.model.schema import SEGMENT_HIDDEN_FIELDS

# Per-kind editor configuration (labels per celeri_ui panels).
KINDS: dict[str, dict] = {
    "segment": {
        "single": "Segment",
        "plural": "Edit Selected Segments",
        "hidden": SEGMENT_HIDDEN_FIELDS,
        "deletable": True,
    },
    "block": {
        "single": "Block",
        "plural": "Edit Selected Blocks",
        "hidden": (),
        "deletable": True,
    },
    "velocity": {
        "single": "Velocity",
        "plural": "Edit Selected Velocities",
        "hidden": (),
        "deletable": True,
    },
    # Vertices have no name; celeri_ui titles each editor 'Selected Vertex'
    # and offers no delete (vertex GC is automatic).
    "vertex": {
        "single": "Selected Vertex",
        "plural": "Edit Selected Vertices",
        "hidden": (),
        "deletable": False,
    },
}


def build_editable_item(app, kind: str, controls=None, deletable=None) -> None:
    """Selection editor for ``kind``; hidden while nothing of it is selected.

    ``controls``: optional zero-arg callable emitting extra header buttons
    (e.g. Split Segment / vertex ops). ``deletable`` overrides the per-kind
    default.
    """
    cfg = KINDS[kind]
    if deletable is None:
        deletable = cfg["deletable"]
    title = (
        "selection.ids.length === 1"
        f" ? String(selection_fields.name ?? '{cfg['single']}')"
        f" : '{cfg['plural']}'"
    )
    with html.Div(
        v_if=f"selection.kind === '{kind}' && selection.ids.length > 0",
        classes=f"editable-item editable-item-{kind} pa-2 mt-2",
        style="border: 1px solid rgba(127, 127, 127, 0.5); border-radius: 4px;",
    ):
        with html.Div(classes="d-flex justify-space-between align-center mb-1"):
            html.Span(
                f"{{{{ {title} }}}}",
                classes="text-h6 editable-item-title",
            )
            with html.Div(classes="d-flex justify-end ga-1 flex-wrap"):
                if controls is not None:
                    controls()
                if deletable:
                    v3.VBtn(
                        "Delete",
                        size="small",
                        color="error",
                        variant="tonal",
                        classes="btn-delete",
                        click=app.delete_selection,
                    )
        panel_base.build_field_rows(
            "selection_fields",
            app.edit_selection,
            hidden=tuple(cfg["hidden"]),
        )
