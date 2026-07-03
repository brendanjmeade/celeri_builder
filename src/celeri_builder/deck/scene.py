"""Layer-group registry: turns a Document + display settings into descriptors.

Each layer group (one module under ``deck/layers/``) registers a builder
``builder(doc, display, selection) -> list[descriptor dict]``. The app pushes
each group's list into its own ``deck_layers_<group>`` trame state variable,
so groups re-sync to the client independently.

``selection`` is ``{"kind": str | None, "ids": set()}``; builders will use it
for selected-color swaps from M2 on (M1 always passes it empty).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from celeri_builder.deck.layers import (
    blocks,
    dip_projection,
    generic,
    graticule,
    labels,
    meshes,
    segments,
    selection,
    velocities,
    vertices,
)
from celeri_builder.model.document import Document

Selection = dict
Builder = Callable[[Document, dict, Selection], list[dict]]


def empty_selection() -> Selection:
    return {"kind": None, "ids": set()}


class SceneBuilder:
    """Registry of ordered layer-group builders."""

    def __init__(self) -> None:
        self._builders: dict[str, tuple[int, Builder]] = {}

    def register(self, name: str, order: int, builder: Builder) -> None:
        """Register (or replace) a group; ``order`` sorts bottom -> top."""
        self._builders[name] = (order, builder)

    def group_names(self) -> list[str]:
        """All registered group names, bottom -> top."""
        return sorted(self._builders, key=lambda name: self._builders[name][0])

    def build(
        self,
        names: Iterable[str],
        doc: Document,
        display: dict,
        selection: Selection | None = None,
    ) -> dict[str, list[dict]]:
        """Build a subset of groups; result keys are in draw (order) order."""
        if selection is None:
            selection = empty_selection()
        wanted = set(names)
        unknown = wanted - self._builders.keys()
        if unknown:
            msg = f"unknown layer group(s): {sorted(unknown)}"
            raise KeyError(msg)
        # TODO(M2+): per-slice identity caching goes here — skip rebuilding a
        # group when the Document slices and display sub-dicts it reads are
        # identical (by object identity) to the previous build's inputs.
        return {
            name: self._builders[name][1](doc, display, selection)
            for name in self.group_names()
            if name in wanted
        }

    def build_all(
        self,
        doc: Document,
        display: dict,
        selection: Selection | None = None,
    ) -> dict[str, list[dict]]:
        """Build every registered group, bottom -> top."""
        return self.build(self.group_names(), doc, display, selection)


def register_all() -> SceneBuilder:
    """SceneBuilder with every ``deck/layers/`` module registered."""
    scene = SceneBuilder()
    for module in (
        graticule,
        meshes,
        dip_projection,
        generic,
        segments,
        velocities,
        vertices,
        blocks,
        labels,
        selection,
    ):
        scene.register(module.GROUP, module.ORDER, module.build)
    return scene
