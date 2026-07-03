"""Basemap style resolution (port of fennil ``app/deck/mapbox.py``).

fennil handed its style to pydeck, which knows how to talk to Mapbox.
celeri-deck renders the basemap with MapLibre instead, and MapLibre cannot
resolve ``mapbox://`` URLs — so when a token is present the local
monochrome-bathymetry style is loaded and every ``mapbox://`` source /
sprite / glyph URL is rewritten into its token-bearing
``https://api.mapbox.com`` equivalent.

Resolution ladder (:func:`resolve_style`):

- ``CELERI_BUILDER_NO_BASEMAP=1``  -> ``None`` (no basemap; editor still works)
- token in ``CELERI_BUILDER_MAPBOX_TOKEN`` (dotenv-loaded, quotes stripped)
  -> the rewritten monochrome style as a dict
- otherwise -> the public carto positron style URL string
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

TOKEN_ENV_KEY = "CELERI_BUILDER_MAPBOX_TOKEN"
NO_BASEMAP_ENV_KEY = "CELERI_BUILDER_NO_BASEMAP"
MONOCHROME_STYLE_PATH = Path(__file__).with_name(
    "mapbox_monochrome_bathymetry_style.json"
)

#: Public, tokenless fallback style (pydeck's "light" carto style).
CARTO_POSITRON_STYLE_URL = (
    "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
)

MAPBOX_API = "https://api.mapbox.com"
MAPBOX_SCHEME = "mapbox://"

load_dotenv()
TOKEN = os.getenv(TOKEN_ENV_KEY, "").strip().strip('"').strip("'")
HAS_MAPBOX_TOKEN = bool(TOKEN)


def _load_monochrome_mapbox_style() -> dict[str, Any]:
    # Local monochrome style with a custom bathymetry layer (from fennil).
    return json.loads(MONOCHROME_STYLE_PATH.read_text(encoding="utf-8"))


def _rewrite_source_url(url: str, token: str) -> str:
    """``mapbox://{tileset,...}`` -> v4 TileJSON URL MapLibre can fetch."""
    if not url.startswith(MAPBOX_SCHEME):
        return url
    tilesets = url[len(MAPBOX_SCHEME) :]
    return f"{MAPBOX_API}/v4/{tilesets}.json?secure&access_token={token}"


def _rewrite_sprite_url(url: str, token: str) -> str:
    """``mapbox://sprites/{user}/{style}`` -> styles/v1 sprite URL."""
    prefix = MAPBOX_SCHEME + "sprites/"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix) :]
    return f"{MAPBOX_API}/styles/v1/{path}/sprite?access_token={token}"


def _rewrite_glyphs_url(url: str, token: str) -> str:
    """``mapbox://fonts/{user}/{fontstack}/{range}.pbf`` -> fonts/v1 URL.

    The ``{fontstack}``/``{range}`` placeholders are literal template slots
    MapLibre fills in, so they must survive the rewrite untouched.
    """
    prefix = MAPBOX_SCHEME + "fonts/"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix) :]
    return f"{MAPBOX_API}/fonts/v1/{path}?access_token={token}"


def rewrite_mapbox_style(style: dict[str, Any], token: str) -> dict[str, Any]:
    """Return a copy of ``style`` with mapbox:// URLs made MapLibre-readable."""
    out = dict(style)
    sources = {}
    for name, raw_source in style.get("sources", {}).items():
        source = dict(raw_source)
        url = source.get("url", "")
        if isinstance(url, str) and url:
            source["url"] = _rewrite_source_url(url, token)
        sources[name] = source
    out["sources"] = sources
    sprite = style.get("sprite")
    if isinstance(sprite, str) and sprite:
        out["sprite"] = _rewrite_sprite_url(sprite, token)
    glyphs = style.get("glyphs")
    if isinstance(glyphs, str) and glyphs:
        out["glyphs"] = _rewrite_glyphs_url(glyphs, token)
    return out


def resolve_style(token: str | None = None) -> dict[str, Any] | str | None:
    """Resolve the basemap style for the celeri-deck widget.

    Returns a style dict (token-bearing monochrome), a style URL string
    (carto fallback), or ``None`` (``CELERI_BUILDER_NO_BASEMAP=1``).
    """
    if os.environ.get(NO_BASEMAP_ENV_KEY, "").strip() == "1":
        return None
    if token is None:
        token = TOKEN
    if token:
        return rewrite_mapbox_style(_load_monochrome_mapbox_style(), token)
    return CARTO_POSITRON_STYLE_URL
