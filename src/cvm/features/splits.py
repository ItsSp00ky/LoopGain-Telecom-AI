"""Temporal splitting and point-in-time correctness.  Owner: E1

Three invariants, all asserted in tests/leakage/ and required in CI:

1. Features are computed over a window ending strictly before the label window
   opens. Framing: 90d observation -> 15d gap -> 30d outcome.
2. Splits are TEMPORAL, never random. A random split leaks the future.
3. Any field used to generate the synthetic label is excluded from the feature
   matrix -- including the UCI `Customer Value` column.

There is deliberately no `random_split` function in this module. If you want
one, the answer is no.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def temporal_split(
    df: pd.DataFrame,
    snapshot_column: str = "snapshot_date",
    train_end: date | None = None,
    val_end: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split train / validation / test by time."""
    raise NotImplementedError("TODO(E1)")


def assert_no_window_overlap(
    feature_window_end: date, label_window_start: date, gap_days: int = 15
) -> None:
    """Fail if the feature window reaches into the label window."""
    raise NotImplementedError("TODO(E1)")


def drop_excluded_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove every column in conf/features.yaml#leakage_controls.excluded_columns."""
    raise NotImplementedError("TODO(E1)")


def temporal_cv_folds(df: pd.DataFrame, n_folds: int = 5) -> list[tuple[pd.Index, pd.Index]]:
    """Expanding-window folds. Any SMOTE/ADASYN resampling happens INSIDE a
    fold, never before the split."""
    raise NotImplementedError("TODO(E1)")