"""Snapshot undo/redo store over the immutable :class:`Document`.

The Document is immutable and reducers structurally share untouched
slices, so history entries are cheap references to whole past Documents.
A dispatch whose reducer returns the SAME object (identity, not equality)
is a no-op: no history entry, no notification.
"""

from __future__ import annotations

from collections.abc import Callable

from celeri_builder.model.actions import Action, Batch
from celeri_builder.model.document import Document
from celeri_builder.model.reducers import reduce as _reduce

# fn(old_doc, new_doc, action). ``action`` is None for undo/redo/reset.
Subscriber = Callable[[Document, Document, "Action | None"], None]


class Store:
    """Holds the current Document plus bounded undo/redo stacks."""

    def __init__(self, doc: Document, limit: int = 200) -> None:
        self._doc = doc
        self._limit = limit
        self._past: list[Document] = []
        self._future: list[Document] = []
        self._subscribers: list[Subscriber] = []

    # -- queries -----------------------------------------------------------

    @property
    def doc(self) -> Document:
        return self._doc

    @property
    def can_undo(self) -> bool:
        return bool(self._past)

    @property
    def can_redo(self) -> bool:
        return bool(self._future)

    # -- subscriptions -----------------------------------------------------

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        """Register ``fn(old, new, action)``; returns an unsubscribe."""
        self._subscribers.append(fn)

        def unsubscribe() -> None:
            if fn in self._subscribers:
                self._subscribers.remove(fn)

        return unsubscribe

    def _notify(self, old: Document, new: Document, action: Action | None) -> None:
        for fn in list(self._subscribers):
            fn(old, new, action)

    # -- dispatch / history --------------------------------------------------

    def dispatch(self, action: Action) -> Document:
        """Reduce; identical result object means no history entry."""
        new = _reduce(self._doc, action)
        if new is self._doc:
            return self._doc
        old = self._doc
        self._past.append(old)
        if len(self._past) > self._limit:
            del self._past[0]
        self._future.clear()
        self._doc = new
        self._notify(old, new, action)
        return new

    def batch(self, *actions: Action) -> Document:
        """Apply several actions as ONE undoable history entry."""
        return self.dispatch(Batch(actions=tuple(actions)))

    def undo(self) -> Document | None:
        """Step back one entry; ``None`` when there is nothing to undo."""
        if not self._past:
            return None
        old = self._doc
        self._future.append(old)
        self._doc = self._past.pop()
        self._notify(old, self._doc, None)
        return self._doc

    def redo(self) -> Document | None:
        """Step forward one entry; ``None`` when there is nothing to redo."""
        if not self._future:
            return None
        old = self._doc
        self._past.append(old)
        self._doc = self._future.pop()
        self._notify(old, self._doc, None)
        return self._doc

    def reset(self, doc: Document) -> None:
        """Replace the document and clear ALL history (e.g. project load)."""
        old = self._doc
        self._doc = doc
        self._past.clear()
        self._future.clear()
        self._notify(old, doc, None)
