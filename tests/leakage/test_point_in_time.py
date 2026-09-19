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


def test_splits_module_exposes_no_random_split():
    """There is deliberately no random_split function. If one appears, this
    test is the conversation about why."""
    import cvm.features.splits as splits

    assert not hasattr(splits, "random_split")


# --- Data-level invariants (E1: unmark xfail as the pipeline lands) -------


@pytest.mark.slow
def test_no_feature_column_reads_past_the_snapshot_date():
    """THE POINT-IN-TIME GUARANTEE, asserted against the real store.

    Asking what was known on a past date must never return a row observed
    after it. If it does, every backtest is scored against information the
    model would not have had, every metric is inflated, and nothing in the
    output looks wrong.
    """
    from cvm.config import settings
    from cvm.features.store import get_features

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    import pandas as pd

    full = pd.read_parquet(settings.feature_store_offline, columns=["snapshot_date"])
    snapshots = pd.to_datetime(full["snapshot_date"])
    cutoff = snapshots.quantile(0.5)

    visible = get_features(as_of=str(cutoff.date()))
    assert not visible.empty, "an as-of read at the median date returned nothing"

    latest = pd.to_datetime(visible["snapshot_date"]).max()
    assert latest <= cutoff, (
        f"as-of {cutoff.date()} returned a row from {latest.date()}: the store is "
        "serving the future, and every backtest built on it is invalid."
    )
    assert len(visible) < len(full), "the as-of filter returned everything; it is not filtering"


@pytest.mark.slow
def test_train_and_test_are_disjoint_in_time():
    """No row in train may be contemporaneous with or later than any row in
    test. A model scored on rows from its own training period is scored on the
    present, which is not the task."""
    import pandas as pd

    from cvm.config import settings
    from cvm.features.splits import temporal_split

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    features = pd.read_parquet(settings.feature_store_offline)
    train, validation, test = temporal_split(features)

    train_latest = pd.to_datetime(train["snapshot_date"]).max()
    val_earliest = pd.to_datetime(validation["snapshot_date"]).min()
    val_latest = pd.to_datetime(validation["snapshot_date"]).max()
    test_earliest = pd.to_datetime(test["snapshot_date"]).min()

    assert (
        train_latest < val_earliest
    ), f"train reaches {train_latest.date()} and validation starts {val_earliest.date()}"
    assert (
        val_latest < test_earliest
    ), f"validation reaches {val_latest.date()} and test starts {test_earliest.date()}"

    # And no subscriber may appear in more than one split, or the model is
    # scored on people it has already seen.
    ids = [set(part["subscriber_id_hashed"]) for part in (train, validation, test)]
    assert (
        not ids[0] & ids[1] and not ids[1] & ids[2] and not ids[0] & ids[2]
    ), "a subscriber appears in more than one split"


@pytest.mark.slow
def test_no_label_artifact_survives_into_the_feature_store():
    """The store may keep the TARGET -- it is the training matrix -- but never
    an artefact. hazard_score, churn_date and days_to_churn each let a model
    reconstruct the outcome directly."""
    import pandas as pd

    from cvm.config import settings
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    columns = set(pd.read_parquet(settings.feature_store_offline).columns)
    target = load_conf("features")["target"]["name"]

    leaked = (set(LABEL_ARTIFACT_FIELDS) - {target}) & columns
    assert not leaked, f"label artefacts reached the feature store: {sorted(leaked)}"
    assert target in columns, f"the target {target!r} is absent, so the store cannot be trained on"


@pytest.mark.slow
def test_uci_duplicate_rows_are_dropped():
    """~300 exact duplicates, ~9.5% of the dataset. Leaving them in is half the
    reason the published figures are inflated.

    A duplicate row that survives into a random split puts the same subscriber
    on both sides of it, so the model is scored partly on rows it trained on.
    That is why this is a leakage test and not a data-quality one.
    """
    from cvm.ingest.uci_iranian import duplicate_audit, load

    conf = load_conf("data")["sources"]["uci_iranian"]["quality"]
    audit = duplicate_audit()

    expected = conf["expected_duplicate_rows"]
    tolerance = conf["duplicate_row_tolerance"]
    assert abs(audit["duplicates_dropped"] - expected) <= tolerance, (
        f"dropped {audit['duplicates_dropped']:.0f} duplicates, config expects "
        f"{expected} +/-{tolerance}. If the source changed, update conf/data.yaml "
        "AND the figure quoted in the proposal."
    )

    # The landed frame must actually be free of them, not merely audited.
    df = load()
    feature_columns = [
        c for c in df.columns if c not in {"subscriber_id_hashed", "snapshot_date", "source"}
    ]
    assert not df.duplicated(subset=feature_columns).any(), "duplicates survived load()"
    assert len(df) == audit["rows_clean"]


@pytest.mark.slow
def test_uci_leaky_field_is_dropped_by_default():
    """`Customer Value` is a pre-computed score that partially encodes the
    outcome. It is the other half of why the published figures are inflated.

    ``drop_leaky=False`` must still work: reproducing the inflated number is
    how we show it is wrong, so the naive path is a deliberate feature.
    """
    from cvm.ingest.uci_iranian import load

    leaky = load_conf("data")["sources"]["uci_iranian"]["leaky_columns"]
    assert leaky, "no leaky columns configured -- the audit claim has no basis"

    honest = load()
    naive = load(drop_leaky=False)
    for column in leaky:
        assert column not in honest.columns, f"{column} reached the honest feature matrix"
        assert column in naive.columns, f"{column} missing from the naive reproduction"


def test_a_single_feature_cannot_reconstruct_the_label():
    """Sanity check against an undetected leak: no single feature should reach
    a near-perfect AUC on its own.

    THE BROADEST NET IN THE SUITE. Every other leakage test names a specific
    field and checks it is absent, so each one only catches a leak someone
    already thought of. This one names nothing: it ranks the whole matrix by
    univariate AUC and fails if any column is suspiciously close to a perfect
    predictor. A leak nobody anticipated shows up here as a single column doing
    a job no single column should be able to do.

    0.95 rather than 0.99, because the useful failure is the near-miss. A
    column at 0.97 is not literally the label, and it is still a column that
    makes the model look far better than it will be in production.

    WHAT THIS TEST DOES NOT CATCH, measured rather than assumed. It catches
    DETERMINISTIC reconstruction: `days_to_churn` scores 1.0000 and trips it
    instantly. It does NOT catch `hazard_score`, which reaches only 0.8799 --
    because the label is a Bernoulli DRAW from that hazard, so the probability
    cannot perfectly separate outcomes it only governs in expectation. Lowering
    the threshold to catch it would leave almost no margin over the strongest
    legitimate driver (`days_since_last_topup`, 0.7471) and would start failing
    on honest data.

    So this is the second line and not the first. `test_label_artifacts_are_
    excluded_from_features` catches every artefact we know the name of; this
    one catches an unanticipated column that is near-deterministic. Neither
    covers the other, which is why both exist.
    """
    import pandas as pd
    from sklearn.metrics import roc_auc_score

    from cvm.config import settings
    from cvm.models.m1_churn.gradient_boosting import prepare_matrix

    path = settings.feature_store_offline
    if not path.exists():
        pytest.skip(f"{path} does not exist; run `python -m cvm.features.run`")

    frame = pd.read_parquet(path)
    X, y = prepare_matrix(frame)
    assert y is not None and 0 < y.mean() < 0.5

    scores = {}
    for column in X.columns:
        values = X[column]
        usable = values.notna()
        # A column that is constant, or missing wherever the label varies, has
        # no univariate AUC -- skipping it is correct, and counting it as 0.5
        # would hide a column that is only present for churners.
        if usable.sum() < 100 or values[usable].nunique() < 2:
            continue
        if y[usable].nunique() < 2:
            continue
        auc = roc_auc_score(y[usable], values[usable])
        scores[column] = max(auc, 1 - auc)  # a perfectly INVERTED feature leaks too

    assert scores, "no column was scorable, so this test proved nothing"

    worst = max(scores, key=scores.get)
    assert scores[worst] < 0.95, (
        f"{worst} alone reaches AUC {scores[worst]:.4f}. A single feature that "
        "nearly reconstructs the label is a leak, whether or not it is on the "
        f"artefact list. Top five: "
        f"{sorted(((v, k) for k, v in scores.items()), reverse=True)[:5]}"
    )
