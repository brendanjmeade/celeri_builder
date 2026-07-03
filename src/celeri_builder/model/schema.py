"""Canonical celeri field orders and defaults.

Column orders match celeri's canonical file formats (which celeri_ui's
``fieldNames`` also follow). Two kinds of defaults exist and they differ,
matching celeri_ui exactly:

- READ defaults: value used when a column is missing from a file
  (``0`` for numbers, ``""`` for name) — see ProcessParsedSegmentFile.
- NEW-entity defaults: values for interactively created entities
  (``default_segment`` etc., ported from celeri_ui State/*/ *.ts).
"""

from __future__ import annotations

SEGMENT_FIELDS: tuple[str, ...] = (
    "name",
    "lon1",
    "lat1",
    "lon2",
    "lat2",
    "dip",
    "create_ribbon_mesh",
    "locking_depth",
    "locking_depth_flag",
    "ss_rate",
    "ss_rate_sig",
    "ss_rate_flag",
    "ds_rate",
    "ds_rate_sig",
    "ds_rate_flag",
    "ts_rate",
    "ts_rate_sig",
    "ts_rate_flag",
    "mesh_file_index",
    "mesh_flag",
    "ss_rate_bound_flag",
    "ss_rate_bound_min",
    "ss_rate_bound_max",
    "ds_rate_bound_flag",
    "ds_rate_bound_min",
    "ds_rate_bound_max",
    "ts_rate_bound_flag",
    "ts_rate_bound_min",
    "ts_rate_bound_max",
    "ss_reg_flag",
    "ds_reg_flag",
    "ts_reg_flag",
    "slip_rate_bound_sigma",
)

# Interactive-creation defaults (celeri_ui src/State/Segment/Segment.ts
# defaultSegment). lon/lat fields are supplied by the creation gesture.
DEFAULT_SEGMENT: dict[str, float | str] = {
    "name": "new_segment",
    "lon1": 0.0,
    "lat1": 0.0,
    "lon2": 10.0,
    "lat2": 10.0,
    "dip": 90.0,
    "create_ribbon_mesh": 0,
    "locking_depth": 15.0,
    "locking_depth_flag": 0,
    "ss_rate": 0.0,
    "ss_rate_sig": 0.0,
    "ss_rate_flag": 0,
    "ds_rate": 0.0,
    "ds_rate_sig": 0.0,
    "ds_rate_flag": 0,
    "ts_rate": 0.0,
    "ts_rate_sig": 0.0,
    "ts_rate_flag": 0,
    "mesh_file_index": -1,
    "mesh_flag": 0,
    "ss_rate_bound_flag": 0,
    "ss_rate_bound_min": -1.0,
    "ss_rate_bound_max": 1.0,
    "ds_rate_bound_flag": 0,
    "ds_rate_bound_min": -1.0,
    "ds_rate_bound_max": 1.0,
    "ts_rate_bound_flag": 0,
    "ts_rate_bound_min": -1.0,
    "ts_rate_bound_max": 1.0,
    "ss_reg_flag": 0,
    "ds_reg_flag": 0,
    "ts_reg_flag": 0,
    "slip_rate_bound_sigma": 1.0,
}

BLOCK_FIELDS: tuple[str, ...] = (
    "other1",
    "other2",
    "other3",
    "other4",
    "other5",
    "other6",
    "name",
    "interior_lon",
    "interior_lat",
    "euler_lon",
    "euler_lon_sig",
    "euler_lat",
    "euler_lat_sig",
    "rotation_rate",
    "rotation_rate_sig",
    "rotation_flag",
    "apriori_flag",
    "strain_rate",
    "strain_rate_sig",
    "strain_rate_flag",
)

DEFAULT_BLOCK: dict[str, float | str] = {
    "other1": 0,
    "other2": 0,
    "other3": 0,
    "other4": 0,
    "other5": 0,
    "other6": 0,
    "name": "",
    "interior_lon": 0.0,
    "interior_lat": 0.0,
    "euler_lon": 0.0,
    "euler_lon_sig": 0.0,
    "euler_lat": 0.0,
    "euler_lat_sig": 0.0,
    "rotation_rate": 0.0,
    "rotation_rate_sig": 0.0,
    "rotation_flag": 0,
    "apriori_flag": 0,
    "strain_rate": 0.0,
    "strain_rate_sig": 0.0,
    "strain_rate_flag": 0,
}

VELOCITY_FIELDS: tuple[str, ...] = (
    "lon",
    "lat",
    "corr",
    "other1",
    "name",
    "east_vel",
    "north_vel",
    "east_sig",
    "north_sig",
    "flag",
    "up_vel",
    "up_sig",
    "east_adjust",
    "north_adjust",
    "up_adjust",
)

DEFAULT_VELOCITY: dict[str, float | str] = {
    "lon": 0.0,
    "lat": 0.0,
    "corr": 0.0,
    "other1": 0,
    "name": "",
    "east_vel": 0.0,
    "north_vel": 0.0,
    "east_sig": 0.0,
    "north_sig": 0.0,
    "flag": 0,
    "up_vel": 0.0,
    "up_sig": 0.0,
    "east_adjust": 0.0,
    "north_adjust": 0.0,
    "up_adjust": 0.0,
}


def read_default(field: str):
    """Default used when a known column is missing from a file on read."""
    return "" if field == "name" else 0


# -- editor field metadata -----------------------------------------------------
#
# Fields hidden from property editors (celeri_ui ``ignoreFields`` parity).

# SegmentsPanel.tsx: endpoint coordinates are edited on the map, and
# start/end are the vertex graph's internal ids.
SEGMENT_HIDDEN_FIELDS: tuple[str, ...] = (
    "lon1",
    "lat1",
    "lon2",
    "lat2",
    "start",
    "end",
)

# CommandPanel.tsx: file-reference keys are managed by open/save handling.
COMMAND_HIDDEN_FIELDS: tuple[str, ...] = (
    "segment_file_name",
    "station_file_name",
    "block_file_name",
    "mesh_parameters_file_name",
    "file_name",
)
