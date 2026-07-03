"""Velocity action reducers — one-for-one port of celeri_ui
``mocha/tests/VelocityState.spec.ts`` ("Velocity actions mutate state as
expected")."""

from __future__ import annotations

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import reduce
from celeri_builder.model.schema import DEFAULT_VELOCITY


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


def test_can_load_new_data_into_the_velocity_state():
    doc = apply(act.LoadVelocities(rows=({**DEFAULT_VELOCITY, "name": "test"},)))
    assert len(doc.velocities) == 1
    assert doc.velocities[0]["name"] == "test"


def test_can_create_a_new_velocity():
    doc = apply(act.CreateVelocity(props={"name": "test"}))
    assert len(doc.velocities) == 1
    assert doc.velocities[0]["name"] == "test"
    # remaining columns come from defaultVelocity
    assert doc.velocities[0]["east_vel"] == 0
    assert doc.velocities[0]["flag"] == 0


def test_can_edit_velocity_data():
    doc = apply(
        act.CreateVelocity(props={"name": "test"}),
        act.CreateVelocity(props={"name": "test"}),
        act.EditVelocities(indices=(0, 1), patch={"name": "test2"}),
    )
    assert len(doc.velocities) == 2
    assert doc.velocities[0]["name"] == "test2"
    assert doc.velocities[1]["name"] == "test2"


def test_can_delete_a_velocity():
    doc = apply(
        act.CreateVelocity(props={"name": "test"}),
        act.CreateVelocity(props={"name": "test"}),
        act.DeleteVelocities(indices=(0,)),
    )
    assert len(doc.velocities) == 1


def test_can_move_a_velocity():
    doc = apply(
        act.CreateVelocity(props={"name": "test"}),
        act.MoveVelocity(index=0, lon=1.0, lat=1.0),
    )
    assert len(doc.velocities) == 1
    assert doc.velocities[0]["lat"] == 1
    assert doc.velocities[0]["lon"] == 1
