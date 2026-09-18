"""Point-in-time correctness. Required in CI; never skipped.

Three invariants from section 2.5:

1. Features are computed over a window ending strictly before the label window
   opens.
2. Splits are temporal, never random.
3. Any field used to generate the synthetic label is excluded from the feature
   matrix -- including the UCI `Customer Value` column.

"Inflated metrics from duplicates or leaky features" is a High/High entry in the
risk register. This file is the mitigation.
"""

from __future__ import annotations

import pytest

from cvm.config import load_conf

pytestmark = pytest.mark.leakage


@pytest.fixture
def features_conf() -> dict:
    return load_conf("features")


# --- Config-level invariants (these run now) ------------------------------


def test_temporal_split_is_configured_and_random_is_forbidden(features_conf):
    lc = features_conf["leakage_controls"]
    assert lc["split_strategy"] == "temporal"
    assert lc["forbid_random_split"] is True
    assert lc["enforce_point_in_time"] is True


def test_customer_value_is_excluded(features_conf):
    """The UCI field that partially encodes the outcome. Dropping it is why our
    metrics are lower than the published ~0.99 AUC, and that gap is a headline
    result rather than an embarrassment."""
    assert "Customer Value" in features_conf["leakage_controls"]["excluded_columns"]


def test_label_artifacts_are_excluded_from_features(features_conf):
    """Every label ARTIFACT must be excluded.

    This catches the subtlest failure mode in the project: a synthetic label
    trivially recoverable from a column we forgot to drop, producing a model
    that looks excellent and knows nothing.
    """
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    lc = features_conf["leakage_controls"]
    assert lc["exclude_label_artifacts"] is True
    missing = set(LABEL_ARTIFACT_FIELDS) - set(lc["excluded_columns"])
    assert not missing, (
        f"These fields encode the label but are not in excluded_columns: {sorted(missing)}. "
        "Add them in conf/features.yaml -- do not remove them from hazard.py."
    )


def test_label_drivers_are_deliberately_available(features_conf):
    """The mirror image, and just as important.

    The hazard is a function of observable behaviour so the signal is
    recoverable. If someone "tightens" leakage control by excluding the drivers
    too, the model has nothing left to learn and every metric collapses for a
    reason nobody will be able to find. This test documents that the overlap is
    intentional.
    """
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS, LABEL_DRIVER_FIELDS

    excluded = set(features_conf["leakage_controls"]["excluded_columns"])
    wrongly_excluded = set(LABEL_DRIVER_FIELDS) & excluded
    assert not wrongly_excluded, (
        f"These are label DRIVERS, not artifacts, and must stay available as "
        f"features: {sorted(wrongly_excluded)}. Excluding them leaves the model "
        "nothing to learn. See cvm/synthesis/hazard.py."
    )
    # The two categories must not overlap, or the distinction is meaningless.
    assert not set(LABEL_DRIVER_FIELDS) & set(LABEL_ARTIFACT_FIELDS)


def test_observation_window_and_label_window_do_not_touch(features_conf):
    """90d observation -> 15d gap -> 30d outcome. The gap must be positive."""
    w = features_conf["windows"]
    assert w["gap_days"] > 0
    assert w["observation_days"] == 90
    assert w["outcome_days"] == 30


def test_resampling_happens_inside_cv_folds_only(features_conf):
    """SMOTE before the split leaks synthetic neighbours of test rows into
    training. Inside the fold it is a legitimate comparison arm."""
    assert features_conf["imbalance"]["resample_inside_cv_folds_only"] is True


def test_sequences_are_not_pre_aggregated(features_conf):
    """Aggregating before the LSTM would make the M1 benchmark meaningless:
    both arms would be eating the same engineered features."""
    assert features_conf["sequences"]["no_hand_aggregation"] is True


def test_splits_module_exposes_no_random_split():
    """There is deliberately no random_split function. If one appears, this
    test is the conversation about why."""
    import cvm.features.splits as splits

    assert not hasattr(splits, "random_split")


# --- Data-level invariants (E1: unmark xfail as the pipeline lands) -------


@pytest.mark.xfail(reason="feature store not built yet", strict=False)
def test_no_feature_column_reads_past_the_snapshot_date():
    raise NotImplementedError("TODO(E1)")


@pytest.mark.xfail(reason="feature store not built yet", strict=False)
def test_train_and_test_are_disjoint_in_time():
    raise NotImplementedError("TODO(E1)")


@pytest.mark.xfail(reason="ingestion not implemented yet", strict=False)
def test_uci_duplicate_rows_are_dropped():
    """~300 exact duplicates, ~9.5% of the dataset. Leaving them in is half the
    reason the published figures are inflated."""
    raise NotImplementedError("TODO(E1)")


@pytest.mark.xfail(reason="M1 not trained yet", strict=False)
def test_a_single_feature_cannot_reconstruct_the_label():
    """Sanity check against an undetected leak: no single feature should reach
    a near-perfect AUC on its own."""
    raise NotImplementedError("TODO(E2)")
