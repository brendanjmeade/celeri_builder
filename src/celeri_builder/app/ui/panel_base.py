"""Shared building blocks for inspector panels.

Every display-settings control funnels through
``app.update_display(panel, key, value)`` — the single nested-dict funnel on
``CeleriBuilderApp`` — and the ``panel``/``key`` pairs used by the panels
match ``deck/display.py`` ``default_display()`` exactly.

``build_field_rows`` renders a dynamic property editor over any state dict
(``selection_fields`` / ``command_fields``): string edits fire immediately;
debouncing of numeric edits is handled SERVER-side by the receiving app
method (celeri_ui's 1 s client timeout, ported to the server).
"""

from __future__ import annotations

import json
from contextlib import contextmanager

from trame.widgets import html
from trame.widgets import vuetify3 as v3

v3.enable_lab()  # VNumberInput lives in Vuetify labs.

#: JS: VColorPicker ``hexa`` event ("#rrggbbaa") -> ``[r, g, b, a]`` list,
#: the color representation ``default_display()`` stores.
HEXA_EVENT_TO_RGBA = (
    "[parseInt($event.slice(1, 3), 16),"
    " parseInt($event.slice(3, 5), 16),"
    " parseInt($event.slice(5, 7), 16),"
    " $event.length > 7 ? parseInt($event.slice(7, 9), 16) : 255]"
)

#: Preset swatches in every color menu (celeri_ui's default palette hues).
PRESET_SWATCHES = [
    ["#FFFF00", "#00FFFF", "#FF0000"],
    ["#00FF00", "#0000FF", "#FF00FF"],
    ["#FFFFFF", "#AAAAAA", "#000000"],
]


def js_literal(value) -> str:
    """JSON-ish JS literal using single quotes (HTML attrs are
    double-quoted, so double quotes inside expressions would break them)."""
    return json.dumps(value).replace('"', "'")


def rgba_expr(panel: str, key: str) -> str:
    """JS path of a stored ``[r, g, b, a]`` display color."""
    return f"display.{panel}.{key}"


def rgba_to_hexa_expr(panel: str, key: str) -> str:
    """JS turning the stored ``[r, g, b, a]`` into ``#rrggbbaa``."""
    path = rgba_expr(panel, key)
    return (
        f"'#' + {path}.map(c => Math.max(0, Math.min(255, Math.round(c)))"
        ".toString(16).padStart(2, '0')).join('')"
    )


@contextmanager
def labeled_row(label: str, classes: str = ""):
    """A ``label | control`` row; yields the 40%-wide control container."""
    with html.Div(classes=f"d-flex justify-space-between align-center my-1 {classes}"):
        html.Span(label, classes="text-subtitle-2 font-weight-bold")
        with html.Div(style="width: 40%; flex-shrink: 0;") as slot:
            yield slot


def toggle_row(app, label: str, panel: str, key: str) -> None:
    """Visibility switch; checked = shown (inverts a ``hide*`` key)."""
    with labeled_row(label):
        v3.VSwitch(
            model_value=(f"!display.{panel}.{key}",),
            update_modelValue=(app.update_display, f"['{panel}', '{key}', !$event]"),
            density="compact",
            hide_details=True,
            color="primary",
            classes=f"ctl-{panel}-{key}",
        )


def color_row(app, label: str, panel: str, key: str) -> None:
    """Color swatch button opening a VColorPicker menu (rgba round-trip)."""
    path = rgba_expr(panel, key)
    swatch_style = (
        "`width: 100%; height: 26px; border: 1px solid #666;"
        f" background: rgba(${{{path}[0]}}, ${{{path}[1]}},"
        f" ${{{path}[2]}}, ${{{path}[3] / 255}});`"
    )
    with labeled_row(label):
        with v3.VBtn(
            variant="outlined",
            density="compact",
            classes=f"ctl-{panel}-{key} color-swatch",
            style=(swatch_style,),
        ):
            with v3.VMenu(
                activator="parent",
                close_on_content_click=False,
                location="top",
            ):
                with v3.VCard(classes="pa-1"):
                    v3.VColorPicker(
                        model_value=(rgba_to_hexa_expr(panel, key),),
                        update_modelValue=(
                            app.update_display,
                            f"['{panel}', '{key}', {HEXA_EVENT_TO_RGBA}]",
                        ),
                        mode="hexa",
                        show_swatches=True,
                        swatches=(js_literal(PRESET_SWATCHES),),
                        elevation=0,
                        width=300,
                        canvas_height=120,
                    )


def slider_row(
    app,
    label: str,
    panel: str,
    key: str,
    min_value: float,
    max_value: float,
    step: float,
) -> None:
    """Numeric slider (celeri_ui range inputs); commits on release (``end``)
    so dragging does not flood the server with layer rebuilds."""
    with labeled_row(label):
        v3.VSlider(
            model_value=(f"display.{panel}.{key}",),
            min=min_value,
            max=max_value,
            step=step,
            density="compact",
            hide_details=True,
            thumb_label=True,
            end=(app.update_display, f"['{panel}', '{key}', $event]"),
            classes=f"ctl-{panel}-{key}",
        )


def select_row(app, label: str, panel: str, key: str, items: list) -> None:
    """Dropdown over static ``items`` (e.g. plottableKey field lists)."""
    with labeled_row(label):
        v3.VSelect(
            model_value=(f"display.{panel}.{key}",),
            # literal list: lists/tuples mean (expr, default) to trame,
            # so static items ship as a JS array-literal expression
            items=(js_literal(list(items)),),
            update_modelValue=(app.update_display, f"['{panel}', '{key}', $event]"),
            density="compact",
            hide_details=True,
            variant="outlined",
            classes=f"ctl-{panel}-{key}",
        )


def file_buttons(
    app,
    kind: str,
    open_label: str,
    save_label: str,
    save_as: bool = True,
) -> None:
    """Open / Save / Save As buttons for one file kind."""
    with html.Div(classes="d-flex justify-space-between align-center my-1 flex-wrap"):
        v3.VBtn(
            open_label,
            size="small",
            variant="tonal",
            classes=f"btn-open-{kind}",
            click=(app.open_kind, f"['{kind}']"),
        )
        v3.VBtn(
            save_label,
            size="small",
            variant="tonal",
            classes=f"btn-save-{kind}",
            click=(app.save_kind, f"['{kind}']"),
        )
        if save_as:
            v3.VBtn(
                "Save As",
                size="small",
                variant="tonal",
                classes=f"btn-save-as-{kind}",
                click=(app.save_kind_as, f"['{kind}']"),
            )


def action_row(label: str, button_label: str, classes: str, click) -> None:
    """A ``label | button`` row (Add New <Entity> rows)."""
    with html.Div(classes="d-flex justify-space-between align-center my-1"):
        html.Span(label, classes="text-subtitle-2 font-weight-bold")
        v3.VBtn(
            button_label,
            size="small",
            variant="tonal",
            classes=classes,
            click=click,
        )


def build_field_rows(source: str, edit, hidden: tuple[str, ...] = ()) -> None:
    """One editor row per ``(field, value)`` in the state dict ``source``.

    ``edit`` is the server method receiving ``(field, value)`` on every
    change. Numeric values (and only those — a multi-selection's mixed
    marker ``"-"`` is a string) get a VNumberInput, everything else a
    VTextField, matching celeri_ui EditableItem's typeof switch. Numeric
    debouncing is the server method's job (see module docstring).
    """
    hidden_js = js_literal(list(hidden))
    with html.Template(v_for=f"(value, field) in {source}", key=("field",)):
        with html.Div(
            v_if=f"!{hidden_js}.includes(field)",
            classes="d-flex justify-space-between align-center my-1 field-row",
        ):
            html.Span(
                "{{ field }}",
                classes="text-subtitle-2 font-weight-bold text-truncate mr-2",
            )
            with html.Div(style="width: 40%; flex-shrink: 0;"):
                v3.VNumberInput(
                    v_if="typeof value === 'number'",
                    model_value=("value",),
                    update_modelValue=(edit, "[field, $event]"),
                    density="compact",
                    hide_details=True,
                    variant="outlined",
                    control_variant="stacked",
                    classes=("`field-editor field-editor-${field}`",),
                )
                v3.VTextField(
                    v_else=True,
                    model_value=("value",),
                    update_modelValue=(edit, "[field, $event]"),
                    density="compact",
                    hide_details=True,
                    variant="outlined",
                    classes=("`field-editor field-editor-${field}`",),
                )
