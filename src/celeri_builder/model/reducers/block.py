"""Block reducers — faithful ports of celeri_ui ``src/State/Block/*``."""

from __future__ import annotations

from celeri_builder.model.actions import (
    CreateBlock,
    DeleteBlocks,
    EditBlocks,
    LoadBlocks,
    MoveBlock,
)
from celeri_builder.model.document import Document
from celeri_builder.model.schema import DEFAULT_BLOCK


def create_block(doc: Document, action: CreateBlock) -> Document:
    """CreateBlock.ts: append ``defaultBlock`` merged with the props."""
    return doc.with_(blocks=(*doc.blocks, {**DEFAULT_BLOCK, **action.props}))


def edit_blocks(doc: Document, action: EditBlocks) -> Document:
    """EditBlockData.ts: shallow-merge the patch into every indexed row."""
    if not action.indices:
        return doc
    blocks = list(doc.blocks)
    for i in action.indices:
        blocks[i] = {**blocks[i], **action.patch}
    return doc.with_(blocks=tuple(blocks))


def delete_blocks(doc: Document, action: DeleteBlocks) -> Document:
    """DeleteBlock.ts: keep every row whose index is not listed."""
    drop = set(action.indices)
    kept = tuple(b for i, b in enumerate(doc.blocks) if i not in drop)
    if len(kept) == len(doc.blocks):
        return doc
    return doc.with_(blocks=kept)


def move_block(doc: Document, action: MoveBlock) -> Document:
    """MoveBlock.ts: set ``interior_lon``/``interior_lat`` on one row."""
    blocks = list(doc.blocks)
    blocks[action.index] = {
        **blocks[action.index],
        "interior_lon": action.lon,
        "interior_lat": action.lat,
    }
    return doc.with_(blocks=tuple(blocks))


def load_blocks(doc: Document, action: LoadBlocks) -> Document:
    """LoadNewBlockData.tsx: replace the whole slice."""
    return doc.with_(blocks=tuple(action.rows))
