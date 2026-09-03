"""Velocity (station) CSV <-> row dicts (ports celeri_ui ``VelocityFile.ts``).

Same fill policy as segments against ``VELOCITY_FIELDS``; a trailing
empty-string column (trailing-comma file, e.g. japan_station.csv) is kept
in the row dicts so ``canonical_table`` re-emits it.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pandas as pd

from celeri_builder.model.schema import VELOCITY_FIELDS, read_default


def read_velocities(text: str) -> tuple[dict, ...]:
    """Read velocity data from CSV text and return tuple of dicts."""
    velocity_df = pd.read_csv(io.StringIO(text))

    # Fill missing values with read defaults only for existing columns
    for field in VELOCITY_FIELDS:
        if field in velocity_df.columns:
            velocity_df[field] = velocity_df[field].fillna(read_default)

    # Convert to tuple of dicts
    return tuple(velocity_df.to_dict("records"))


def write_velocities(rows: Sequence[dict]) -> str:
    """Convert velocity rows to CSV text with canonical column order."""
    velocity_df = pd.DataFrame(rows)

    # Ensure canonical columns are first in the DataFrame
    canonical_cols = [col for col in VELOCITY_FIELDS if col in velocity_df.columns]
    other_cols = [col for col in velocity_df.columns if col not in VELOCITY_FIELDS]
    velocity_df = velocity_df[canonical_cols + other_cols]

    # Convert to CSV text
    return velocity_df.to_csv(index=False)
