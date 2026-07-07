"""Side-by-side parity: replay P0-P6 and compare the saved files.

Two test families, both parametrized over the abstract scripts:

- ``test_builder_contract`` ALWAYS runs. It replays each script against the
  celeri_builder engine and asserts the saved files satisfy the file-format
  contract and the script's expected edit -- a runnable builder-side
  regression that needs neither a browser nor celeri_ui.
- ``test_parity_vs_celeri_ui`` replays the SAME script against the live
  celeri_ui web app and compares the two outputs through the
  :data:`NORMALIZATIONS` table, which encodes every documented intentional
  difference so any UNDOCUMENTED divergence fails loudly. It SKIPS cleanly
  when celeri_ui is unavailable (the case in this environment).
"""

from __future__ import annotations

import json

import pytest

from celeri_builder.io.segment_io import read_segments, write_segments
from celeri_builder.io.tabular import read_table
from celeri_builder.model.schema import SEGMENT_FIELDS

from . import drive_builder
from .edit_scripts import SCRIPTS, EditScript, all_scripts

pytestmark = pytest.mark.parity

SCRIPT_IDS = [s.id for s in all_scripts()]


# ---------------------------------------------------------------------------
# Documented intentional differences (celeri_builder vs celeri_ui).
#
# The comparator is permissive ONLY where a row here says so; every other
# divergence is a failure. celeri_builder is allowed to be a SUPERSET
# (extra canonical columns), never to drop or corrupt data celeri_ui keeps.
# ---------------------------------------------------------------------------

NORMALIZATIONS: dict[str, dict] = {
    "segment": {
        # Canonical columns celeri_ui's narrower field list omits; celeri_builder
        # synthesizes them (read default 0). Present in builder, absent in ui:
        # tolerated.
        "builder_only_columns": {
            "ss_reg_flag",
            "ds_reg_flag",
            "ts_reg_flag",
            "slip_rate_bound_sigma",
        },
        "float_atol": 1e-6,
        # Compared as strings: celeri_ui coerces numeric-looking names to
        # numbers ("2" -> 2), celeri_builder keeps them lossless. Equal after
        # numeric normalization.
        "name_columns": {"name"},
    },
    "block": {
        "builder_only_columns": set(),
        "float_atol": 1e-6,
        "name_columns": {"name"},
    },
    "station": {
        "builder_only_columns": set(),
        "float_atol": 1e-6,
        "name_columns": {"name"},
    },
}

# Additional documented, non-column differences (asserted structurally by the
# builder-contract test rather than the comparator):
#   * trailing newline           -- builder writes one, celeri_ui does not
#   * config/command JSON        -- builder rewrites it (indent=4, all keys
#                                   preserved); celeri_ui does NOT save it, so
#                                   the command kind is never compared
#   * proper ../ path resolution -- builder resolves against the config dir;
#                                   celeri_ui needs files flattened + bare names


# -- shared value comparison --------------------------------------------------


def _num(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _values_equal(a, b, *, atol: float, as_name: bool) -> bool:
    if as_name:
        # Numeric-name coercion tolerance: "2" == 2 == 2.0.
        na, nb = _num(a), _num(b)
        if na is not None and nb is not None:
            return abs(na - nb) <= atol
        return str(a) == str(b)
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= atol
    return str(a) == str(b)


def compare_tabular(kind: str, builder_text: str, ui_text: str) -> list[str]:
    """Diffs between a builder and celeri_ui output of ``kind`` (empty == match).

    Both files are parsed with :mod:`celeri_builder.io`. Comparison is over
    the column intersection minus documented builder-only columns; a column
    present in celeri_ui but missing from celeri_builder is a failure (builder
    must keep the superset).
    """
    norm = NORMALIZATIONS[kind]
    builder = read_table(builder_text)
    ui = read_table(ui_text)
    diffs: list[str] = []

    if len(builder.rows) != len(ui.rows):
        diffs.append(f"{kind}: row count builder={len(builder.rows)} ui={len(ui.rows)}")
        return diffs

    b_cols = {c for c in builder.columns if c != ""}
    u_cols = {c for c in ui.columns if c != ""}
    ui_only = u_cols - b_cols
    if ui_only:
        diffs.append(
            f"{kind}: columns present in celeri_ui but dropped by builder: "
            f"{sorted(ui_only)}"
        )

    builder_extra = (b_cols - u_cols) - norm["builder_only_columns"]
    # Extra builder columns beyond the documented set are still a superset and
    # not a failure on their own, but surface undocumented additions.
    if builder_extra:
        diffs.append(
            f"{kind}: undocumented builder-only columns (not in NORMALIZATIONS): "
            f"{sorted(builder_extra)}"
        )

    shared = sorted(b_cols & u_cols)
    for i, (br, ur) in enumerate(zip(builder.rows, ui.rows, strict=False)):
        for col in shared:
            if not _values_equal(
                br.get(col, ""),
                ur.get(col, ""),
                atol=norm["float_atol"],
                as_name=col in norm["name_columns"],
            ):
                diffs.append(
                    f"{kind}[row {i}].{col}: builder={br.get(col)!r} ui={ur.get(col)!r}"
                )
    return diffs


# -- builder-side contract ----------------------------------------------------


def _named_dips(segment_text: str) -> dict[str, float]:
    table = read_table(segment_text)
    return {str(r.get("name")): r.get("dip") for r in table.rows}


def _segment_names(segment_text: str) -> list[str]:
    return [str(r.get("name")) for r in read_table(segment_text).rows]


def _assert_canonical_segment(segment_text: str) -> None:
    table = read_table(segment_text)
    # Canonical celeri columns first, in order.
    assert table.columns[: len(SEGMENT_FIELDS)] == list(SEGMENT_FIELDS), (
        "segment columns are not canonical-order-first"
    )
    assert segment_text.endswith("\n"), "segment file missing trailing newline"
    # lon/lat columns are written with exactly 6 decimals.
    for line in segment_text.splitlines()[1:]:
        cells = line.split(",")
        for name in ("lon1", "lat1", "lon2", "lat2"):
            idx = table.columns.index(name)
            cell = cells[idx]
            frac = cell.split(".")
            assert len(frac) == 2, f"{name} not decimal: {cell!r}"
            assert len(frac[1]) == 6, f"{name} not 6-decimal: {cell!r}"


def _assert_idempotent(run: drive_builder.BuilderRun) -> None:
    # Re-loading and re-saving the segment file must be byte-identical (the
    # canonical form is a fixed point).
    text = run.text("segment")
    assert write_segments(read_segments(text)) == text, "segment save not idempotent"


def _assert_config_preserved(run: drive_builder.BuilderRun) -> None:
    text = run.text("command")
    assert text.endswith("\n"), "config missing trailing newline"
    data = json.loads(text)
    # Keys celeri_ui would drop must survive.
    for key in ("solve_type", "elastic_operator_cache_dir", "lon_range", "lat_range"):
        assert key in data, f"config dropped celeri key {key!r}"
    # indent=4 formatting.
    assert text.splitlines()[1].startswith("    "), "config not indent=4"


@pytest.mark.parametrize("script", all_scripts(), ids=SCRIPT_IDS)
def test_builder_contract(script: EditScript, builder_workspace) -> None:
    """Replay a script against the engine; assert the saved files hold the
    contract and the expected edit landed. Runs with no celeri_ui/browser."""
    run = drive_builder.replay(builder_workspace(script.region), script.ops)
    checks = script.checks

    base_segments = len(run.baseline.segments.segments)
    base_vertices = len(run.baseline.segments.vertices)
    final_segments = len(run.document.segments.segments)
    final_vertices = len(run.document.segments.vertices)

    # -- always-on canonicalization / preservation invariants --
    _assert_canonical_segment(run.text("segment"))
    _assert_idempotent(run)
    _assert_config_preserved(run)

    # -- structural deltas --
    if "segments_delta" in checks:
        assert final_segments - base_segments == checks["segments_delta"]
        # The saved file agrees with the in-memory document.
        assert len(_segment_names(run.text("segment"))) == final_segments
    if "vertices_delta" in checks:
        assert final_vertices - base_vertices == checks["vertices_delta"]

    # -- the specific edit landed, verified from the SAVED file --
    saved_segment_text = run.text("segment")
    if "segment_dip" in checks:
        dips = _named_dips(saved_segment_text)
        for name, expected in checks["segment_dip"].items():
            assert _num(dips[name]) == pytest.approx(expected), (
                f"{name} dip {dips.get(name)!r} != {expected}"
            )
    names = _segment_names(saved_segment_text)
    for name in checks.get("names_present", []):
        assert name in names, f"expected segment {name!r} missing after edit"
    for name in checks.get("new_segment_names", []):
        assert name in names, f"created segment {name!r} missing"
    for name in checks.get("names_absent", []):
        assert name not in names, f"segment {name!r} should be gone after edit"

    # -- edits + full undo == pristine open->save (byte-for-byte) --
    if "equals_script" in checks:
        other = SCRIPTS[checks["equals_script"]]
        other_run = drive_builder.replay(builder_workspace(other.region), other.ops)
        for kind in ("segment", "block", "station", "command"):
            assert run.text(kind) == other_run.text(kind), (
                f"{script.id} {kind} output differs from {other.id} after undo"
            )


# -- side-by-side vs live celeri_ui (gated / deferred) -----------------------


@pytest.mark.parametrize("script", all_scripts(), ids=SCRIPT_IDS)
def test_parity_vs_celeri_ui(
    script: EditScript, builder_workspace, celeri_ui_driver
) -> None:
    """Replay the SAME script against celeri_ui and diff the saved files.

    Skips cleanly when celeri_ui is unavailable (no node_modules / no token).
    When both run, only NORMALIZATIONS-sanctioned differences are tolerated;
    any other divergence fails.
    """
    builder_run = drive_builder.replay(builder_workspace(script.region), script.ops)
    ui_config = builder_workspace(script.region)
    ui_result = celeri_ui_driver.run_script(ui_config, script.ops)

    all_diffs: list[str] = []
    # celeri_ui writes segment/block/station CSVs (never the command JSON).
    for kind in ("segment", "block", "station"):
        if kind not in ui_result.files:
            continue
        all_diffs += compare_tabular(kind, builder_run.text(kind), ui_result.text(kind))

    assert not all_diffs, "undocumented builder vs celeri_ui divergence:\n" + "\n".join(
        all_diffs
    )
