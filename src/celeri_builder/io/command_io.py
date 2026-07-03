"""Config ("command") JSON I/O.

Intentional fix over celeri_ui: ``read_command`` performs NO key
filtering. celeri_ui's ``ParseCommandFile`` restricted the parsed JSON
to ``defaultCommand``'s fieldNames, silently dropping real celeri keys
(``solve_type``, ``elastic_operator_cache_dir``, ``lon_range``,
``lat_range``, ``iterative_coupling_*``, ...). Here every key survives,
in document order (``json.loads`` preserves insertion order).
"""

from __future__ import annotations

import json
from typing import Any


def read_command(text: str) -> dict[str, Any]:
    """Parse a command/config JSON file into a plain order-preserving dict."""
    data = json.loads(text)
    if not isinstance(data, dict):
        msg = "command file must contain a JSON object"
        raise ValueError(msg)
    return data


def write_command(command: dict[str, Any]) -> str:
    """Serialize a command dict: 4-space-indented JSON plus trailing newline."""
    return json.dumps(command, indent=4) + "\n"
