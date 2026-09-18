"""Temporal splitting and point-in-time correctness.  Owner: E1

Three invariants, all asserted in tests/leakage/ and required in CI:

1. Features are computed over a window ending strictly before the label window
   opens. Framing: 90d observation -> 15d gap -> 30d outcome.
2. Splits are TEMPORAL, never random. A random split leaks the future.
3. Any field used to generate the synthetic label is excluded from the feature
   matrix -- including the UCI `Customer Value` column.

There is deliberately no `random_split` function in this module. If you want
one, the answer is no.

WHY THIS FILE IS THE RISKIEST IN THE PROJECT. Every other failure announces
itself: a crash, a failing assertion, a number that looks wrong. This one does
not. A leaked split produces a model that scores beautifully, ships, and is
worthless -- and the only symptom is that the metrics are *better* than they
should be, which nobody investigates. So the invariants here are enforced by
raising rather than by warning, and the tests that cover them are a required
CI gate rather than an ordinary suite.
"""

from __future__ import annotations

import logging
from datetime import date
from itertools import pairwise

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def _windows() -> dict:
    return load_conf("features")["windows"]


def _leakage_conf() -> dict:
    return load_conf("features")["leakage_controls"]


def temporal_split(
    df: pd.DataFrame,
    snapshot_column: str = "snapshot_date",
    train_end: date | None = None,
    val_end: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split train / validation / test by time.

    Defaults to 60/20/20 by snapshot-date QUANTILE rather than by calendar
    third, so the three parts are comparable in size even when observation is
    not uniform over the window. Explicit dates override that, because a real
    campaign has a real cut-off and the split should be allowed to match it.

    Every row in train is strictly older than every row in validation, and
    likewise validation to test. That is the whole point, and it is asserted
    before returning rather than trusted.
    """
    if snapshot_column not in df.columns:
        raise KeyError(
            f"{snapshot_column!r} is absent, so there is no time to split on. A split "
            "without a time dimension is a random split, and this module does not do "
            "random splits."
        )

    snapshots = pd.to_datetime(df[snapshot_column])
    if snapshots.nunique() < 3:
        raise ValueError(
            f"only {snapshots.nunique()} distinct snapshot date(s). A temporal split "
            "needs a time dimension; with one snapshot every split is arbitrary. See "
            "conf/data.yaml#synthesis.observation_window."
        )

    if train_end is None:
        train_end = snapshots.quantile(0.60)
    if val_end is None:
        val_end = snapshots.quantile(0.80)
    train_end, val_end = pd.Timestamp(train_end), pd.Timestamp(val_end)
    if not train_end < val_end:
        raise ValueError(f"train_end {train_end.date()} must precede val_end {val_end.date()}")

    train = df[snapshots <= train_end]
    validation = df[(snapshots > train_end) & (snapshots <= val_end)]
    test = df[snapshots > val_end]

    for name, part in (("train", train), ("validation", validation), ("test", test)):
        if part.empty:
            raise ValueError(f"the {name} split is empty; the cut-offs do not fit the data")

    assert_splits_are_ordered(train, validation, test, snapshot_column)
    log.info(
        "temporal split: train %d (to %s), validation %d (to %s), test %d -- %.0f/%.0f/%.0f%%",
        len(train),
        train_end.date(),
        len(validation),
        val_end.date(),
        len(test),
        100 * len(train) / len(df),
        100 * len(validation) / len(df),
        100 * len(test) / len(df),
    )
    return train, validation, test


def assert_splits_are_ordered(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    snapshot_column: str = "snapshot_date",
) -> None:
    """Fail if any split reaches forward in time into a later one.

    Checked explicitly rather than inferred from how the split was made,
    because the expensive version of this bug is a later refactor that quietly
    stops honouring the ordering.
    """
    parts = [("train", train), ("validation", validation), ("test", test)]
    for (earlier_name, earlier), (later_name, later) in pairwise(parts):
        if earlier.empty or later.empty:
            continue
        latest = pd.to_datetime(earlier[snapshot_column]).max()
        earliest = pd.to_datetime(later[snapshot_column]).min()
        if latest >= earliest:
            raise ValueError(
                f"{earlier_name} reaches to {latest.date()} but {later_name} starts at "
                f"{earliest.date()}: the splits overlap in time, so the model would be "
                "scored partly on rows contemporaneous with its training data."
            )


def assert_no_window_overlap(
    feature_window_end: date, label_window_start: date, gap_days: int | None = None
) -> None:
    """Fail if the feature window reaches into the label window.

    The gap is not padding. Features observed inside it would not exist at
    scoring time -- in production you predict from what you knew *then*, and
    the 15 days between observation and outcome are precisely what you did not
    know. A model trained through the gap is being fed the future.
    """
    gap = _windows()["gap_days"] if gap_days is None else gap_days
    feature_end = pd.Timestamp(feature_window_end)
    label_start = pd.Timestamp(label_window_start)
    actual = (label_start - feature_end).days

    if actual < gap:
        raise ValueError(
            f"features end {feature_end.date()} and labels open {label_start.date()}: "
            f"a {actual}-day gap where {gap} is required. The missing "
            f"{gap - actual} day(s) would be visible to the model at training time "
            "and absent at scoring time."
        )


def drop_excluded_columns(
    df: pd.DataFrame, keep_snapshot: bool = False, keep_target: bool = False
) -> pd.DataFrame:
    """Remove every column in conf/features.yaml#leakage_controls.excluded_columns.

    TWO OF THE EXCLUDED COLUMNS ARE NOT SIMPLY RUBBISH, and both need a way
    back in at the right moment:

    * `snapshot_date` is excluded because it would leak the split, and it is
      also what `temporal_split` splits ON. The pipeline splits first with it
      and drops it second; `keep_snapshot` makes that ordering explicit rather
      than a matter of luck.
    * `silent_churn_30d` is excluded because a model must never see the label
      among its FEATURES -- but the training matrix is exactly the place the
      label belongs. `keep_target` is how the offline store keeps it. A store
      written without it is a store nothing can be trained on, which is a
      quiet and expensive way to be wrong.

    The distinction is between "may not be an input" and "must not exist".

    Also verifies the excluded list is still a superset of the label artefacts.
    A field added to `LABEL_ARTIFACT_FIELDS` and forgotten here is the exact
    drift the leakage suite exists to catch, and catching it at the point of
    use is better than catching it in CI.
    """
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    excluded = set(_leakage_conf()["excluded_columns"])
    drifted = set(LABEL_ARTIFACT_FIELDS) - excluded
    if drifted:
        raise ValueError(
            f"{sorted(drifted)} generate the label but are not in "
            "conf/features.yaml#leakage_controls.excluded_columns. A model given any "
            "of them reconstructs the outcome directly."
        )

    if keep_snapshot:
        excluded.discard("snapshot_date")
    if keep_target:
        excluded.discard(load_conf("features")["target"]["name"])

    present = [c for c in df.columns if c in excluded]
    log.info("dropped %d excluded column(s): %s", len(present), present)
    return df.drop(columns=present)


def temporal_cv_folds(
    df: pd.DataFrame, n_folds: int = 5, snapshot_column: str = "snapshot_date"
) -> list[tuple[pd.Index, pd.Index]]:
    """Expanding-window folds. Any SMOTE/ADASYN resampling happens INSIDE a
    fold, never before the split.

    Expanding rather than sliding: each fold trains on everything up to a cut
    and validates on the next block, which is how the model will actually be
    used -- you always have the whole past available.

    Returns index pairs rather than frames so a caller cannot accidentally
    resample the union. Resampling before the split puts synthetic neighbours
    of validation rows into training, which inflates every score and is
    invisible in the output.
    """
    if snapshot_column not in df.columns:
        raise KeyError(f"{snapshot_column!r} is absent; folds would not be temporal")
    if n_folds < 2:
        raise ValueError(f"n_folds must be at least 2, got {n_folds}")

    snapshots = pd.to_datetime(df[snapshot_column])
    order = snapshots.sort_values().index
    cuts = np.array_split(np.asarray(order), n_folds + 1)

    folds: list[tuple[pd.Index, pd.Index]] = []
    for i in range(n_folds):
        train_idx = pd.Index(np.concatenate(cuts[: i + 1]))
        validate_idx = pd.Index(cuts[i + 1])
        # Belt and braces: every training row must be older than every
        # validation row in the same fold.
        if snapshots.loc[train_idx].max() > snapshots.loc[validate_idx].min():
            raise ValueError(f"fold {i} overlaps in time; the ordering is broken")
        folds.append((train_idx, validate_idx))

    log.info(
        "temporal CV: %d expanding folds, train sizes %s",
        n_folds,
        [len(t) for t, _ in folds],
    )
    return folds
