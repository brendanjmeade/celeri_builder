"""Generic-collection action reducers — one-for-one port of celeri_ui
``mocha/tests/GenericSegments.spec.ts`` ("Generic Segments")."""

from __future__ import annotations

from celeri_builder.model import actions as act
from celeri_builder.model.document import Document, GenericCollection
from celeri_builder.model.reducers import reduce


def apply(*actions: act.Action, doc: Document | None = None) -> Document:
    if doc is None:
        doc = Document()
    for action in actions:
        doc = reduce(doc, action)
    return doc


ROW = {
    "lon": 0,
    "lat": 0,
    "elon": 1,
    "elat": 1,
    "some_string": "test",
    "some_value": 15,
}


def make_collection() -> GenericCollection:
    return GenericCollection(rows=(dict(ROW),), columns=tuple(ROW))


def load() -> act.LoadGeneric:
    return act.LoadGeneric(name="segments", collection=make_collection())


def test_can_load_a_collection_of_segments_with_generic_data():
    doc = apply(load())
    assert "segments" in doc.generic
    rows = doc.generic["segments"].rows
    assert rows[0]["lon"] == 0
    assert rows[0]["elon"] == 1
    assert rows[0]["some_string"] == "test"
    assert rows[0]["some_value"] == 15


def test_can_set_a_generic_segments_longitude_latitude_and_plot_keys():
    doc = apply(
        load(),
        act.SetGenericKeys(
            name="segments",
            keys={
                "start_lon_key": "lon",
                "start_lat_key": "lat",
                "end_lon_key": "elon",
                "end_lat_key": "elat",
                "plot_key": "some_string",
            },
        ),
    )
    collection = doc.generic["segments"]
    assert collection.start_lon_key == "lon"
    assert collection.start_lat_key == "lat"
    assert collection.end_lon_key == "elon"
    assert collection.end_lat_key == "elat"
    assert collection.plot_key == "some_string"
    # the rows themselves are untouched
    assert collection.rows[0]["some_value"] == 15


def test_setting_keys_on_a_missing_collection_is_a_noop():
    before = apply(load())
    after = reduce(
        before, act.SetGenericKeys(name="missing", keys={"plot_key": "some_string"})
    )
    assert after is before


def test_can_remove_a_collection_of_segments_with_generic_data():
    doc = apply(load(), act.RemoveGeneric(name="segments"))
    assert "segments" not in doc.generic


def test_removing_a_missing_collection_is_a_noop():
    before = apply(load())
    assert reduce(before, act.RemoveGeneric(name="missing")) is before
