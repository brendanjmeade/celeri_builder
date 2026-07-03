"""Bottom-right docked inspector (celeri_ui ``Inspector.tsx`` +
``InspectorPanelBase.tsx``).

A VCard docked bottom-right (45% tall / 40% wide when open) that appears
once a folder is open (``state.folder_label``). The tab strip drives
``state.inspector_tab``; clicking the ACTIVE tab toggles
``state.inspector_open`` instead (celeri_ui collapses by setting
``activeTab`` to ``''`` — here tab and openness are separate keys so the
last tab is remembered). When collapsed only the tab strip remains,
hugging the bottom edge like celeri_ui's ``flex-col-reverse`` layout.
"""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from celeri_builder.app.ui.panels import PANELS

# (tab value, label) — celeri_ui Inspector's ``windows`` mapping, in order.
TABS = (
    ("command", "Command"),
    ("segment", "Segment"),
    ("vertex", "Vertices"),
    ("block", "Block"),
    ("velocities", "Velocities"),
    ("mesh", "Mesh"),
    ("csv", "Generic Segments"),
    ("map", "Map"),
)

_CARD_STYLE = (
    "`position: absolute; bottom: 0; right: 0; width: 40%; z-index: 5;"
    " display: flex; flex-direction: column;"
    " ${inspector_open ? 'height: 45%;' : ''}`"
)


def _tab_click(name: str) -> str:
    """Select the tab, or toggle the body when it is already active."""
    return (
        f"if (inspector_tab === '{name}')"
        " { inspector_open = !inspector_open }"
        f" else {{ inspector_tab = '{name}'; inspector_open = true }}"
    )


def build(app) -> None:
    state = app.state
    state.setdefault("inspector_tab", "command")
    state.setdefault("inspector_open", False)
    state.setdefault("selection", {"kind": None, "ids": []})
    state.setdefault("selection_fields", {})

    with v3.VCard(
        v_show=("folder_label",),
        classes="inspector",
        style=(_CARD_STYLE,),
    ):
        with v3.VTabs(
            model_value=("inspector_tab",),
            density="compact",
            show_arrows=True,
            # flex-shrink-0 keeps the tab strip at its natural height: without
            # it, a tall panel body shrinks BOTH flex children and crushes the
            # tabs to a few pixels, so they can't be scrolled to or clicked.
            classes="inspector-tabs flex-grow-0 flex-shrink-0",
        ):
            for name, label in TABS:
                v3.VTab(
                    label,
                    value=name,
                    size="small",
                    classes=f"tab-{name}",
                    click=_tab_click(name),
                )
        with v3.VCardText(
            v_if=("inspector_open",),
            classes="inspector-body",
            style="flex: 1 1 auto; overflow-y: auto; overflow-x: hidden;",
        ):
            for name, _label in TABS:
                with html.Div(
                    v_if=f"inspector_tab === '{name}'",
                    classes=f"panel-{name}",
                ):
                    PANELS[name](app)
