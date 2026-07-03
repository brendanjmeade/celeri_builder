"""Command (config) reducers — ports of celeri_ui ``src/State/Command/State.ts``."""

from __future__ import annotations

from typing import Any

from celeri_builder.model.actions import EditCommand, LoadCommand, NewCommand
from celeri_builder.model.command_defaults import DEFAULT_COMMAND
from celeri_builder.model.document import Document


def _fresh_default_command() -> dict[str, Any]:
    """A private copy of DEFAULT_COMMAND (list values copied, not shared)."""
    return {
        k: list(v) if isinstance(v, list) else v for k, v in DEFAULT_COMMAND.items()
    }


def load_command(doc: Document, action: LoadCommand) -> Document:
    """loadCommandData: replace the command wholesale."""
    return doc.with_(command=dict(action.data))


def new_command(doc: Document, _action: NewCommand) -> Document:
    """createCommandFile: reset to the default command."""
    return doc.with_(command=_fresh_default_command())


def edit_command(doc: Document, action: EditCommand) -> Document:
    """editCommandData: shallow-merge the patch (unknown keys survive)."""
    if not action.patch:
        return doc
    return doc.with_(command={**doc.command, **action.patch})
