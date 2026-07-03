"""Inspector panel build functions, keyed by inspector tab name."""

from __future__ import annotations

from celeri_builder.app.ui.panels.block_panel import build as build_block
from celeri_builder.app.ui.panels.command_panel import build as build_command
from celeri_builder.app.ui.panels.generic_panel import build as build_generic
from celeri_builder.app.ui.panels.map_settings_panel import (
    build as build_map_settings,
)
from celeri_builder.app.ui.panels.mesh_panel import build as build_mesh
from celeri_builder.app.ui.panels.segment_panel import build as build_segment
from celeri_builder.app.ui.panels.velocity_panel import build as build_velocity
from celeri_builder.app.ui.panels.vertex_panel import build as build_vertex

#: tab name -> build(app), matching celeri_ui Inspector's ``windows``.
PANELS = {
    "command": build_command,
    "segment": build_segment,
    "vertex": build_vertex,
    "block": build_block,
    "velocities": build_velocity,
    "mesh": build_mesh,
    "csv": build_generic,
    "map": build_map_settings,
}

__all__ = [
    "PANELS",
    "build_block",
    "build_command",
    "build_generic",
    "build_map_settings",
    "build_mesh",
    "build_segment",
    "build_velocity",
    "build_vertex",
]
