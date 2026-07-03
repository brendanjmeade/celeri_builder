"""Config ("command") JSON round-trip + DEFAULT_COMMAND fidelity."""

from __future__ import annotations

import json

from celeri_builder.io.command_io import read_command, write_command
from celeri_builder.model.command_defaults import DEFAULT_COMMAND

# Real celeri keys that celeri_ui's ParseCommandFile silently dropped;
# our read_command must preserve them (intentional fix).
UI_DROPPED_KEYS = (
    "solve_type",
    "elastic_operator_cache_dir",
    "lon_range",
    "lat_range",
)


def test_roundtrip_semantic(raw_text, region):
    original = raw_text("config", region)
    written = write_command(read_command(original))
    assert json.loads(written) == json.loads(original)


def test_all_keys_survive(raw_text, region):
    original = json.loads(raw_text("config", region))
    result = json.loads(write_command(read_command(raw_text("config", region))))
    for key in UI_DROPPED_KEYS:
        assert key in original  # sanity: the example data really has them
        assert key in result
    coupling_keys = [k for k in original if k.startswith("iterative_coupling")]
    if region == "japan":
        assert len(coupling_keys) >= 2  # sanity: japan config has them
    for key in coupling_keys:
        assert key in result
        assert result[key] == original[key]


def test_key_order_preserved(raw_text, region):
    original = raw_text("config", region)
    written = write_command(read_command(original))
    assert list(json.loads(written)) == list(json.loads(original))


def test_trailing_newline(raw_text, region):
    written = write_command(read_command(raw_text("config", region)))
    assert written.endswith("\n")


def test_second_generation_idempotent(raw_text, region):
    once = write_command(read_command(raw_text("config", region)))
    twice = write_command(read_command(once))
    assert twice == once


def test_synthetic_unknown_keys_survive():
    synthetic = {
        "file_name": "synthetic",
        "mcmc_samples": 5000,
        "zz_unknown": {
            "nested": {"values": [1, 2.5, "three"], "flag": True},
            "why_not": None,
        },
        "segment_file_name": "../segment/x.csv",
    }
    text = json.dumps(synthetic, indent=2) + "\n"
    result = json.loads(write_command(read_command(text)))
    assert result == synthetic
    assert list(result) == list(synthetic)
    assert result["mcmc_samples"] == 5000
    assert result["zz_unknown"]["nested"]["values"] == [1, 2.5, "three"]


class TestDefaultCommand:
    """DEFAULT_COMMAND must match celeri_ui Command.ts defaultCommand."""

    def test_key_count(self):
        assert len(DEFAULT_COMMAND) == 59

    def test_first_and_last_keys(self):
        keys = list(DEFAULT_COMMAND)
        assert keys[0] == "file_name"
        assert keys[-1] == "slip_file_names"

    def test_misspelled_key_preserved(self):
        # celeri_ui really spells the value key without the second 'r'.
        assert "locking_depth_overide_value" in DEFAULT_COMMAND
        assert "locking_depth_override_value" not in DEFAULT_COMMAND
        # ... while the flag key is spelled correctly.
        assert "locking_depth_override_flag" in DEFAULT_COMMAND
        assert DEFAULT_COMMAND["locking_depth_overide_value"] == 0

    def test_spot_values(self):
        assert DEFAULT_COMMAND["file_name"] == "Default Command"
        assert DEFAULT_COMMAND["material_lambda"] == 3e10
        assert DEFAULT_COMMAND["tri_smooth"] == 10_000
        assert DEFAULT_COMMAND["tri_edge"] == [0, 0, 0]
        assert DEFAULT_COMMAND["tri_slip_sign"] == [0, 0]
        assert DEFAULT_COMMAND["inversion_type"] == "standard"
        assert DEFAULT_COMMAND["solution_method"] == "backslash"
        assert DEFAULT_COMMAND["slip_file_names"] == ""
