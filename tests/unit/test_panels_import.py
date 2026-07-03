"""Import-time and construction smoke tests for the inspector UI modules.

The panels are pure UI (no logic to unit-test), but importing them catches
syntax/metadata errors, and building them against a stub app catches bad
widget kwargs and malformed Vue expressions at construction time.
"""

from __future__ import annotations

import importlib

import pytest
from trame.app import get_server
from trame.ui.vuetify3 import VAppLayout

from celeri_builder.app.ui import inspector, mode_banner
from celeri_builder.app.ui.panels import PANELS
from celeri_builder.model import schema

MODULES = (
    "celeri_builder.app.ui.editable_item",
    "celeri_builder.app.ui.inspector",
    "celeri_builder.app.ui.mode_banner",
    "celeri_builder.app.ui.panel_base",
    "celeri_builder.app.ui.panels",
    "celeri_builder.app.ui.panels.block_panel",
    "celeri_builder.app.ui.panels.command_panel",
    "celeri_builder.app.ui.panels.generic_panel",
    "celeri_builder.app.ui.panels.map_settings_panel",
    "celeri_builder.app.ui.panels.mesh_panel",
    "celeri_builder.app.ui.panels.segment_panel",
    "celeri_builder.app.ui.panels.velocity_panel",
    "celeri_builder.app.ui.panels.vertex_panel",
)


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)


def test_panels_registry_covers_all_tabs():
    assert [name for name, _ in inspector.TABS] == list(PANELS)
    assert all(callable(build) for build in PANELS.values())


def test_schema_editor_metadata():
    assert schema.SEGMENT_HIDDEN_FIELDS == (
        "lon1",
        "lat1",
        "lon2",
        "lat2",
        "start",
        "end",
    )
    assert schema.COMMAND_HIDDEN_FIELDS == (
        "segment_file_name",
        "station_file_name",
        "block_file_name",
        "mesh_parameters_file_name",
        "file_name",
    )


class _StubApp:
    """Just enough of the CeleriBuilderApp method contract to build the UI."""

    def __init__(self, server):
        self.server = server

    @property
    def state(self):
        return self.server.state

    # contract methods (integrate agent implements the real ones)
    def update_display(self, panel, key, value):
        pass

    def open_kind(self, kind):
        pass

    def save_kind(self, kind):
        pass

    def save_kind_as(self, kind):
        pass

    def edit_selection(self, key, value):
        pass

    def delete_selection(self):
        pass

    def edit_command(self, key, value):
        pass

    def arm_new(self, kind):
        pass

    def split_selection(self):
        pass

    def arm_vertex_op(self, op):
        pass

    def remove_mesh(self, name):
        pass

    def set_generic_keys(self, name, key, value):
        pass

    def remove_generic(self, name):
        pass


def test_ui_builds_against_stub_app():
    server = get_server("test_panels_import_smoke", client_type="vue3")
    app = _StubApp(server)
    app.state.selection_mode = "normal"
    app.state.folder_label = ""

    with VAppLayout(server):
        mode_banner.build(app)
        inspector.build(app)

    assert app.state.inspector_tab == "command"
    assert app.state.inspector_open is False
    assert app.state.mode_hint == ""
    assert app.state.selection == {"kind": None, "ids": []}
    assert app.state.selection_fields == {}
    assert app.state.command_fields == {}
    assert app.state.mesh_names == []
    assert app.state.generic_collections == []
