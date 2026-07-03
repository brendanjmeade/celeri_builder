"""Velocity reducers — faithful ports of celeri_ui ``src/State/Velocity/*``."""

from __future__ import annotations

from celeri_builder.model.actions import (
    CreateVelocity,
    DeleteVelocities,
    EditVelocities,
    LoadVelocities,
    MoveVelocity,
)
from celeri_builder.model.document import Document
from celeri_builder.model.schema import DEFAULT_VELOCITY


def create_velocity(doc: Document, action: CreateVelocity) -> Document:
    """CreateVelocity.ts: append ``defaultVelocity`` merged with the props."""
    return doc.with_(velocities=(*doc.velocities, {**DEFAULT_VELOCITY, **action.props}))


def edit_velocities(doc: Document, action: EditVelocities) -> Document:
    """EditVelocityData.ts: shallow-merge the patch into every indexed row."""
    if not action.indices:
        return doc
    velocities = list(doc.velocities)
    for i in action.indices:
        velocities[i] = {**velocities[i], **action.patch}
    return doc.with_(velocities=tuple(velocities))


def delete_velocities(doc: Document, action: DeleteVelocities) -> Document:
    """DeleteVelocity.ts: keep every row whose index is not listed."""
    drop = set(action.indices)
    kept = tuple(v for i, v in enumerate(doc.velocities) if i not in drop)
    if len(kept) == len(doc.velocities):
        return doc
    return doc.with_(velocities=kept)


def move_velocity(doc: Document, action: MoveVelocity) -> Document:
    """MoveVelocity.ts: merge the new position (``lon``/``lat``) into one row."""
    velocities = list(doc.velocities)
    velocities[action.index] = {
        **velocities[action.index],
        "lon": action.lon,
        "lat": action.lat,
    }
    return doc.with_(velocities=tuple(velocities))


def load_velocities(doc: Document, action: LoadVelocities) -> Document:
    """LoadNewVelocityData.tsx: replace the whole slice."""
    return doc.with_(velocities=tuple(action.rows))
