"""Map settings inspector panel (celeri_ui ``Components/MapSettingsPanel.tsx``).

celeri_ui offered arbitrary Mapbox user styles; celeri_builder's basemap
ladder (``deck/mapbox.py``) supports the token-bearing monochrome style,
the public carto fallback, and no basemap — so the panel is a preset
select over those, stored in ``display.map.styleName`` (``'default'``
means "whatever ``resolve_style()`` picked").
"""

from __future__ import annotations

from celeri_builder.app.ui import panel_base

STYLE_PRESETS = ["default", "monochrome", "carto", "none"]


def build(app) -> None:
    panel_base.select_row(app, "Select Style", "map", "styleName", STYLE_PRESETS)
