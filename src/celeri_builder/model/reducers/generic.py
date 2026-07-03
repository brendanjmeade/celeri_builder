"""Generic-segment reducers — ports of celeri_ui ``src/State/GenericSegments/*``."""

from __future__ import annotations

import dataclasses

from celeri_builder.model.actions import LoadGeneric, RemoveGeneric, SetGenericKeys
from celeri_builder.model.document import Document


def load_generic(doc: Document, action: LoadGeneric) -> Document:
    """LoadNewGenericCollectionData.ts: insert/replace the named collection."""
    return doc.with_(generic={**doc.generic, action.name: action.collection})


def set_generic_keys(doc: Document, action: SetGenericKeys) -> Document:
    """SetGenericSegmentPositionKeys.ts: update the position/plot column
    mapping on one collection; missing collection is a no-op."""
    old = doc.generic.get(action.name)
    if old is None:
        return doc
    updated = dataclasses.replace(old, **action.keys)
    return doc.with_(generic={**doc.generic, action.name: updated})


def remove_generic(doc: Document, action: RemoveGeneric) -> Document:
    """RemoveGenericSegmentCollection.ts: drop the named collection."""
    if action.name not in doc.generic:
        return doc
    return doc.with_(generic={k: v for k, v in doc.generic.items() if k != action.name})
