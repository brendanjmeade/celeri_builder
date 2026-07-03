"""Python side of the celeri-deck interactive map widget."""

from trame_client.widgets.core import AbstractElement

from celeri_builder.widgets import module


class DeckEditor(AbstractElement):
    """Interactive deck.gl map that forwards pick/drag/key events to Python.

    Layers are plain JSON descriptor lists held in per-group trame state
    variables named ``deck_layers_<group>``; pass the group names in order
    (bottom to top). Each group re-syncs to the client independently, so
    editing vertices never re-sends mesh payloads.

    Events (all payloads are plain dicts, coordinates are [lon, lat]):
    ``ready``, ``click``, ``hover``, ``dragstart``, ``drag``, ``dragend``,
    ``viewstate``, ``mapkey``.
    """

    def __init__(self, groups=None, **kwargs):
        super().__init__("celeri-deck", **kwargs)
        if self.server:
            self.server.enable_module(module)
        if groups:
            expr = "[].concat(" + ", ".join(
                f"(deck_layers_{g} || [])" for g in groups
            ) + ")"
            self._attributes["layers"] = f':layers="{expr}"'
        else:
            self._attr_names += [("layers", ":layers")]
        self._attr_names += [
            ("map_style", ":mapStyle"),
            ("view_state", ":viewState"),
            ("view_state_revision", ":viewStateRevision"),
            ("drag_layers", ":dragLayers"),
            ("cursor_mode", "cursorMode"),
            ("hover_rate_ms", ":hoverRateMs"),
            ("drag_rate_ms", ":dragRateMs"),
            ("viewstate_rate_ms", ":viewstateRateMs"),
        ]
        self._event_names += [
            "ready",
            "click",
            "hover",
            "dragstart",
            "drag",
            "dragend",
            "viewstate",
            "mapkey",
        ]
