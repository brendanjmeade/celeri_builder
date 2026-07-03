"""Block action reducers — one-for-one port of celeri_ui
``mocha/tests/BlockState.spec.ts`` ("Block actions mutate state as
expected")."""

from __future__ import annotations

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import reduce
from celeri_builder.model.schema import DEFAULT_BLOCK


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


def test_can_load_new_data_into_the_block_state():
    doc = apply(act.LoadBlocks(rows=({**DEFAULT_BLOCK, "name": "test"},)))
    assert len(doc.blocks) == 1
    assert doc.blocks[0]["name"] == "test"


def test_can_create_a_new_block():
    doc = apply(act.CreateBlock(props={"name": "test"}))
    assert len(doc.blocks) == 1
    assert doc.blocks[0]["name"] == "test"
    # remaining columns come from defaultBlock
    assert doc.blocks[0]["interior_lon"] == 0
    assert doc.blocks[0]["rotation_flag"] == 0


def test_can_edit_block_data():
    doc = apply(
        act.CreateBlock(props={"name": "test"}),
        act.CreateBlock(props={"name": "test"}),
        act.EditBlocks(indices=(0, 1), patch={"name": "test2"}),
    )
    assert len(doc.blocks) == 2
    assert doc.blocks[0]["name"] == "test2"
    assert doc.blocks[1]["name"] == "test2"


def test_can_delete_a_block():
    doc = apply(
        act.CreateBlock(props={"name": "test"}),
        act.DeleteBlocks(indices=(0,)),
    )
    assert len(doc.blocks) == 0


def test_can_move_a_block():
    doc = apply(
        act.CreateBlock(props={"name": "test"}),
        act.MoveBlock(index=0, lon=1.0, lat=1.0),
    )
    assert len(doc.blocks) == 1
    assert doc.blocks[0]["interior_lat"] == 1
    assert doc.blocks[0]["interior_lon"] == 1
