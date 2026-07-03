"""Command (config) action reducers — celeri_ui ``src/State/Command/State.ts``
behavior: load replaces, new resets to defaultCommand, edit shallow-merges
and preserves unknown keys."""

from __future__ import annotations

from celeri_builder.model import actions as act
from celeri_builder.model.command_defaults import DEFAULT_COMMAND
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import reduce


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


def test_load_command_replaces_the_command_state():
    doc = apply(act.LoadCommand(data={"file_name": "x", "custom_key": 1}))
    assert doc.command == {"file_name": "x", "custom_key": 1}


def test_load_command_copies_the_payload():
    payload = {"file_name": "x"}
    doc = apply(act.LoadCommand(data=payload))
    assert doc.command == payload
    assert doc.command is not payload


def test_new_command_resets_to_the_default_command():
    doc = apply(
        act.LoadCommand(data={"file_name": "x", "custom_key": 1}),
        act.NewCommand(),
    )
    assert doc.command == DEFAULT_COMMAND
    assert "custom_key" not in doc.command
    # (sic) celeri parity: the misspelled key is present
    assert doc.command["locking_depth_overide_value"] == 0


def test_new_command_does_not_share_mutable_values_with_the_template():
    doc = apply(act.NewCommand())
    assert doc.command is not DEFAULT_COMMAND
    assert doc.command["tri_edge"] is not DEFAULT_COMMAND["tri_edge"]
    assert doc.command["tri_slip_sign"] is not DEFAULT_COMMAND["tri_slip_sign"]


def test_edit_command_merges_the_patch():
    doc = apply(act.NewCommand(), act.EditCommand(patch={"n_iterations": 5}))
    assert doc.command["n_iterations"] == 5
    assert doc.command["file_name"] == "Default Command"


def test_edit_command_preserves_unknown_keys():
    doc = apply(
        act.LoadCommand(data={**DEFAULT_COMMAND, "mystery_key": "keep me"}),
        act.EditCommand(patch={"n_iterations": 5}),
    )
    assert doc.command["n_iterations"] == 5
    assert doc.command["mystery_key"] == "keep me"
    assert doc.command["solution_method"] == "backslash"


def test_edit_command_can_introduce_new_keys():
    doc = apply(act.NewCommand(), act.EditCommand(patch={"brand_new": 7}))
    assert doc.command["brand_new"] == 7
