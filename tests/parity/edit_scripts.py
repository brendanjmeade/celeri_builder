"""Abstract edit scripts (P0-P6) as pure DATA.

Each script is a sequence of *abstract* edit operations expressed as
``(op_name, params)`` tuples. The same script is replayed against BOTH the
celeri_builder engine (``drive_builder``) and the live celeri_ui web app
(``drive_celeri_ui``); the saved files are then compared. Because the ops
are data (segment *names* and *coordinates*, never row indices or vertex
ids), each driver resolves them against its own state.

Op vocabulary (params shown):

- ``("edit_segments", {"names": [...], "patch": {"dip": 60}})`` -- bulk edit
- ``("create_segment", {"start": [lon, lat], "end": [lon, lat]})``
- ``("move_vertex", {"at": [lon, lat], "to": [lon, lat]})`` -- ``at`` selects
  an existing vertex by coordinate; ``to`` is the destination. If ``to``
  lands on an occupied vertex cell the graph auto-merges.
- ``("delete_segments", {"names": [...]})``
- ``("split_segment", {"name": ...})`` -- split at the arithmetic midpoint
- ``("undo_all", {})`` -- undo every history entry

``checks`` on each script are data-driven builder-side contract
expectations interpreted by ``test_parity_saved_files`` (so the builder
half is a runnable regression even when celeri_ui is unavailable):

- ``segments_delta`` / ``vertices_delta`` -- change vs. the pristine load
- ``segment_dip`` -- ``{name: expected_dip}`` in the saved segment file
- ``names_present`` / ``names_absent`` -- segment names after the edits
- ``new_segment_names`` -- names expected to appear from creation ops
- ``equals_script`` -- id of another script whose saved files must be
  byte-for-byte identical (used by P6: edits + full undo == P0)
"""

from __future__ import annotations

from dataclasses import dataclass

Op = tuple[str, dict]

# -- fixed reference geometry (japan_segment.csv) ----------------------------
#
# All names below are UNIQUE in japan_segment.csv (each resolves to exactly
# one row); coordinates are stored 0-360 exactly as they appear in the CSV.

SEG_A = "aleun"  # japan row: unique, dip 90
SEG_B = "alu_1"  # japan row: unique, dip 90
SEG_SPLIT = "alu_2a"  # japan row: unique, dip 90

# Two empty micro-degree cells (no existing vertex) -> a genuinely new segment.
CREATE_START = (142.0, 39.0)
CREATE_END = (142.5, 39.5)

# A vertex that exists (aleun's start) moved to an EMPTY cell -> pure move.
MOVE_AT = (197.495, 53.352)
MOVE_TO = (198.5, 54.5)

# A vertex (alu_2b's end) moved onto ANOTHER existing vertex (alu_1's start)
# -> the auto-merge branch (occupant repointed and deleted; -1 vertex).
MERGE_AT = (179.415, 50.516)
MERGE_ONTO = (164.025, 55.235)

REGION = "japan"


@dataclass(frozen=True)
class EditScript:
    """One replayable script plus its builder-side contract expectations."""

    id: str
    title: str
    region: str
    ops: tuple[Op, ...]
    checks: dict


_P0 = EditScript(
    id="P0",
    title="open -> save (canonicalization only, no edits)",
    region=REGION,
    ops=(),
    checks={"segments_delta": 0, "vertices_delta": 0},
)

_P1 = EditScript(
    id="P1",
    title="bulk-edit dip=60 on two named segments",
    region=REGION,
    ops=(("edit_segments", {"names": [SEG_A, SEG_B], "patch": {"dip": 60}}),),
    checks={
        "segments_delta": 0,
        "vertices_delta": 0,
        "segment_dip": {SEG_A: 60, SEG_B: 60},
    },
)

_P2 = EditScript(
    id="P2",
    title="create a segment from two coordinates",
    region=REGION,
    ops=(("create_segment", {"start": list(CREATE_START), "end": list(CREATE_END)}),),
    checks={
        "segments_delta": 1,
        "vertices_delta": 2,
        "new_segment_names": ["new_segment"],
    },
)

_P3 = EditScript(
    id="P3",
    title="move a vertex to a new (empty) coordinate",
    region=REGION,
    ops=(("move_vertex", {"at": list(MOVE_AT), "to": list(MOVE_TO)}),),
    checks={"segments_delta": 0, "vertices_delta": 0},
)

_P3_MERGE = EditScript(
    id="P3_automerge",
    title="move a vertex onto another vertex (auto-merge variant)",
    region=REGION,
    ops=(("move_vertex", {"at": list(MERGE_AT), "to": list(MERGE_ONTO)}),),
    checks={"segments_delta": 0, "vertices_delta": -1},
)

_P4 = EditScript(
    id="P4",
    title="delete two named segments",
    region=REGION,
    ops=(("delete_segments", {"names": [SEG_A, SEG_B]}),),
    checks={"segments_delta": -2, "names_absent": [SEG_A, SEG_B]},
)

_P5 = EditScript(
    id="P5",
    title="split a named segment at its midpoint",
    region=REGION,
    ops=(("split_segment", {"name": SEG_SPLIT}),),
    checks={
        "segments_delta": 1,
        "names_present": [f"{SEG_SPLIT}_a", f"{SEG_SPLIT}_b"],
        "names_absent": [SEG_SPLIT],
    },
)

_P6 = EditScript(
    id="P6",
    title="P1 edits then full undo (must equal P0 output)",
    region=REGION,
    ops=(
        ("edit_segments", {"names": [SEG_A, SEG_B], "patch": {"dip": 60}}),
        ("undo_all", {}),
    ),
    checks={"segments_delta": 0, "vertices_delta": 0, "equals_script": "P0"},
)


#: The canonical P0-P6 set (plus the P3 auto-merge variant), in run order.
SCRIPTS: dict[str, EditScript] = {
    s.id: s for s in (_P0, _P1, _P2, _P3, _P3_MERGE, _P4, _P5, _P6)
}


def all_scripts() -> list[EditScript]:
    """Every script in deterministic run order."""
    return list(SCRIPTS.values())
