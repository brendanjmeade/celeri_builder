"""Display-settings persistence (celeri_ui used per-panel localStorage).

One JSON file in the platform user-config dir; loaded at startup and merged
over the schema defaults, saved (debounced by the caller) whenever display
settings change. Never persists camera, selection, or edit mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import platformdirs

SETTINGS_FILE = "display_settings.json"


def settings_path() -> Path:
    return Path(platformdirs.user_config_dir("celeri_builder")) / SETTINGS_FILE


def load(defaults: dict[str, Any]) -> dict[str, Any]:
    """Return defaults deep-merged with whatever was previously saved."""
    path = settings_path()
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return json.loads(json.dumps(defaults))  # deep copy
    return _merge(defaults, saved)


def save(display: dict[str, Any]) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(display, indent=2) + "\n")
    except OSError:  # persistence is best-effort
        pass


def _merge(base: dict, override: dict) -> dict:
    out: dict[str, Any] = {}
    for key, value in base.items():
        if key in override:
            if isinstance(value, dict) and isinstance(override[key], dict):
                out[key] = _merge(value, override[key])
            else:
                out[key] = override[key]
        else:
            out[key] = (
                json.loads(json.dumps(value)) if isinstance(value, dict) else value
            )
    return out
