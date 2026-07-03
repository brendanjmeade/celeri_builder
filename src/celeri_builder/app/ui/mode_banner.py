"""Top-center selection-mode banner (celeri_ui ``SelectionModeDetails.tsx``).

Visible whenever ``state.selection_mode != 'normal'``. The main line shows
``state.mode_hint`` (set by the interaction controller when arming a mode);
when no hint is set the per-mode default applies — lasso shows
"Press Enter to Select". A second line always reads
"Press Escape to cancel".
"""

from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

_HINT = "mode_hint || (selection_mode === 'lasso' ? 'Press Enter to Select' : '')"


def build(app) -> None:
    app.state.setdefault("mode_hint", "")
    with v3.VCard(
        v_show=("selection_mode !== 'normal'",),
        classes="mode-banner pa-3 text-center",
        style=(
            "position: absolute; top: 60px; left: 50%;"
            " transform: translateX(-50%); z-index: 10;"
            " pointer-events: none; opacity: 0.94;"
        ),
    ):
        html.Div(
            "{{ selection_mode }}",
            classes="text-subtitle-1 font-weight-medium mode-name",
        )
        html.Div(
            f"{{{{ {_HINT} }}}}",
            v_show=(_HINT,),
            classes="text-body-2 mode-hint",
        )
        html.Div(
            "Press Escape to cancel",
            classes="text-caption text-medium-emphasis",
        )
