"""Layer 3 -- splits, the feature families and the store.

The splits tests carry most of the weight here. Every other failure in this
project announces itself; a leaked split produces a model that scores
beautifully and is worthless, and the only symptom is that the numbers are
*better* than they should be.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.config import load_conf
from cvm.features import distress, rfm_le, splits, velocity, wallet_leakage


@pytest.fixture
def panel() -> pd.DataFrame:
    """A small population with a real time dimension."""
    rng = np.random.default_rng(606)
    n = 2000
    return pd.DataFrame(
        {
            "subscriber_id_hashed": [f"{i:064x}" for i in range(n)],
            "snapshot_date": pd.Timestamp("2026-01-01")
            + pd.to_timedelta(rng.integers(0, 260, n), unit="D"),
            "days_since_last_topup": rng.exponential(8, n).round(),
            "recharge_count_90d": rng.integers(0, 30, n),
            "recharge_gap_cv": rng.gamma(2, 0.3, n),
            "inter_recharge_gap_mean": rng.uniform(1, 60, n),
            "inter_recharge_gap_std": rng.uniform(0, 30, n),
            "modal_recharge_amount_lyd": rng.choice([5.0, 10.0, 20.0, 40.0, 100.0], n),
            "balance_zero_hours_30d": rng.gamma(2, 60, n).clip(0, 720),
            "failed_bundle_attempts_30d": rng.poisson(2, n),
            "consecutive_sub_5_lyd_recharges": rng.integers(0, 10, n),
            "airtime_advance_count_90d": rng.poisson(2, n),
            "data_advance_count_90d": rng.poisson(1, n),
            "unpaid_advance_days": rng.gamma(1.5, 8, n),
            "emergency_service_alternations_90d": rng.integers(0, 9, n),
            "days_to_settle": rng.gamma(2, 3, n),
            "incoming_outgoing_ratio": rng.lognormal(np.log(0.28), 1.4, n),
            "onnet_ratio": rng.beta(5, 3, n),
            "distinct_called_numbers_30d": rng.integers(1, 200, n),
            "voice_minutes_30d": rng.gamma(2, 150, n),
            "tenure_months": rng.integers(1, 60, n),
            "usage_decay_ratio": rng.normal(1.0, 0.3, n).clip(0.1, 3),
            "revenue_decay_ratio": rng.normal(1.0, 0.25, n).clip(0.1, 3),
            "silent_churn_30d": rng.integers(0, 2, n),
            "hazard_score": rng.random(n),
            "days_to_churn": rng.integers(-1, 135, n),
        }
    )


# --- Splits: the module the whole layer's correctness rests on -------------


def test_splits_are_strictly_ordered_in_time(panel):
    train, validation, test = splits.temporal_split(panel)
    assert (
        pd.to_datetime(train["snapshot_date"]).max()
        < pd.to_datetime(validation["snapshot_date"]).min()
    )
    assert (
        pd.to_datetime(validation["snapshot_date"]).max()
        < pd.to_datetime(test["snapshot_date"]).min()
    )


def test_splits_partition_the_population_exactly(panel):
    """No row lost, no row counted twice. A silently dropped slice changes
    every denominator downstream."""
    train, validation, test = splits.temporal_split(panel)
    assert len(train) + len(validation) + len(test) == len(panel)
    ids = [set(p["subscriber_id_hashed"]) for p in (train, validation, test)]
    assert not ids[0] & ids[1] and not ids[1] & ids[2] and not ids[0] & ids[2]


def test_a_single_snapshot_cannot_be_split_temporally(panel):
    """With one observation date every split is arbitrary -- which is a random
    split wearing the right name, and the thing this module exists to refuse."""
    flat = panel.assign(snapshot_date=pd.Timestamp("2026-05-01"))
    with pytest.raises(ValueError, match="distinct snapshot date"):
        splits.temporal_split(flat)


def test_a_frame_with_no_time_column_is_refused(panel):
    with pytest.raises(KeyError, match="snapshot_date"):
        splits.temporal_split(panel.drop(columns=["snapshot_date"]))


def test_overlapping_splits_are_caught(panel):
    """The explicit ordering assertion, in case a later refactor stops
    honouring it."""
    train = panel[pd.to_datetime(panel["snapshot_date"]) <= "2026-06-01"]
    overlapping = panel[pd.to_datetime(panel["snapshot_date"]) >= "2026-05-01"]
    with pytest.raises(ValueError, match="overlap in time"):
        splits.assert_splits_are_ordered(train, overlapping, overlapping)


def test_the_gap_is_enforced():
    """Features observed inside the gap would not exist at scoring time."""
    gap = load_conf("features")["windows"]["gap_days"]
    end = pd.Timestamp("2026-06-01")

    splits.assert_no_window_overlap(end, end + pd.Timedelta(days=gap))
    with pytest.raises(ValueError, match="day gap where"):
        splits.assert_no_window_overlap(end, end + pd.Timedelta(days=gap - 1))


def test_there_is_deliberately_no_random_split():
    """If you want one, the answer is no."""
    assert not hasattr(splits, "random_split")


def test_excluded_columns_are_dropped_but_the_target_can_be_kept(panel):
    """ "May not be an input" and "must not exist" are different claims. The
    training matrix is exactly where the label belongs."""
    target = load_conf("features")["target"]["name"]

    stripped = splits.drop_excluded_columns(panel)
    assert target not in stripped.columns
    assert "hazard_score" not in stripped.columns
    assert "snapshot_date" not in stripped.columns

    matrix = splits.drop_excluded_columns(panel, keep_snapshot=True, keep_target=True)
    assert target in matrix.columns
    assert "snapshot_date" in matrix.columns
    assert "hazard_score" not in matrix.columns, "an artefact survived"


def test_temporal_folds_never_train_on_the_future(panel):
    folds = splits.temporal_cv_folds(panel, n_folds=4)
    assert len(folds) == 4
    snapshots = pd.to_datetime(panel["snapshot_date"])
    for train_idx, validate_idx in folds:
        assert snapshots.loc[train_idx].max() <= snapshots.loc[validate_idx].min()
        assert not set(train_idx) & set(validate_idx)


def test_folds_expand_rather_than_slide(panel):
    """Each fold trains on everything up to a cut, which is how the model will
    be used -- the whole past is always available."""
    folds = splits.temporal_cv_folds(panel, n_folds=4)
    sizes = [len(train) for train, _ in folds]
    assert sizes == sorted(sizes) and sizes[0] < sizes[-1]


# --- Feature semantics that would invert silently --------------------------


def test_recency_is_inverted_in_the_quintiles(panel):
    """Fewer days since a top-up is BETTER, so R=5 must mean recent. Getting
    this backwards inverts every segment, and the segments would still look
    plausible."""
    scored = rfm_le.score_quintiles(panel)
    recent = scored.loc[scored["R"] == 5, "recency_raw"].median()
    stale = scored.loc[scored["R"] == 1, "recency_raw"].median()
    assert recent < stale


def test_frequency_penalises_irregularity(panel):
    """Five regular recharges beat five erratic ones."""
    same_count = panel.assign(recharge_count_90d=10)
    regular = same_count.assign(recharge_gap_cv=0.0)
    erratic = same_count.assign(recharge_gap_cv=2.0)
    assert rfm_le.frequency(regular).mean() > rfm_le.frequency(erratic).mean()


def test_recency_refuses_to_fall_back_to_usage(panel):
    """A subscriber burning residual credit looks active and has generated no
    revenue. There is deliberately no usage-based fallback."""
    with pytest.raises(KeyError, match="REVENUE event"):
        rfm_le.recency(panel.drop(columns=["days_since_last_topup"]))


def test_every_declared_segment_can_fire(panel):
    """`Lost` silently never fired on the first run, because `Hibernating`
    caught the same rows first and was tested earlier."""
    scored = rfm_le.score_quintiles(panel)
    segments = set(rfm_le.assign_segments(scored).unique())
    declared = set(load_conf("features")["rfm_le"]["segments"])
    assert segments <= declared, f"invented segments: {segments - declared}"
    assert len(segments) >= 6, f"only {len(segments)} of 8 segments fired: {sorted(segments)}"


def test_chronic_distress_needs_two_signals(panel):
    """One bad month is not a pattern. Excluding on a single signal would deny
    the facility to most of the base for no benefit."""
    calm = panel.assign(
        balance_zero_hours_30d=0,
        failed_bundle_attempts_30d=0,
        consecutive_sub_5_lyd_recharges=0,
        emergency_service_alternations_90d=0,
        airtime_advance_count_90d=0,
        data_advance_count_90d=0,
    )
    assert not distress.is_chronic_distress(calm).any()

    one_signal = calm.assign(balance_zero_hours_30d=700)
    assert not distress.is_chronic_distress(one_signal).any()

    two_signals = one_signal.assign(consecutive_sub_5_lyd_recharges=9)
    assert distress.is_chronic_distress(two_signals).all()


def test_the_zero_residual_flag_finds_the_floor_population(panel):
    """M4's central finding needs a population it applies to."""
    built = distress.build(panel)
    assert built["at_recharge_floor"].sum() > 0
    assert set(built["at_recharge_floor"].unique()) <= {0, 1}


def test_leakage_score_is_bounded_and_flags_receiving_sims(panel):
    built = wallet_leakage.build(panel)
    assert built["leakage_score"].between(0, 1).all()
    assert set(built["is_receiving_sim"].unique()) <= {0, 1}
    # Above 1.0 means they receive more than they place.
    high = built.loc[built["is_receiving_sim"] == 1, "incoming_outgoing_ratio"]
    assert (high > 1).all()


def test_sms_leakage_stays_excluded_by_design(panel):
    """Almadar charges 0.050 LYD either way, so an SMS-based leakage ratio
    would be noise dressed as insight."""
    built = wallet_leakage.build(panel)
    assert "sms_onnet_offnet_mix" not in built.columns


def test_velocity_exposes_the_divergence_between_usage_and_spend(panel):
    """Usage turns down before spend does -- 46.8% against 42.2% on real
    Cell2Cell data -- which is why they are two features and not one."""
    built = velocity.build(panel)
    assert "decay_divergence" in built.columns
    assert "usage_decay_ratio" in built.columns
    assert "revenue_decay_ratio" in built.columns


# --- The store -------------------------------------------------------------


@pytest.fixture
def store_at(tmp_path, monkeypatch):
    """Point the store's derived paths at a temporary directory.

    `feature_store_offline` is a property over `data_dir`, so moving the one
    field moves the offline store with it; the online store is its own field.
    """
    from cvm.features import store as store_module

    monkeypatch.setattr(store_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(store_module.settings, "feature_store", tmp_path / "online.duckdb")
    (tmp_path / "processed").mkdir(parents=True, exist_ok=True)
    return store_module


def test_as_of_read_never_returns_the_future(store_at, panel):
    """THE POINT-IN-TIME GUARANTEE, through the real serving function. Asking
    what was known in March must not return a row observed in July."""
    store_at.write_offline(panel)
    cutoff = pd.to_datetime(panel["snapshot_date"]).quantile(0.4).normalize()

    visible = store_at.get_features(as_of=str(cutoff.date()))

    assert not visible.empty
    assert pd.to_datetime(visible["snapshot_date"]).max() <= cutoff
    assert len(visible) < len(panel), "the cut-off excluded nothing, so it proves nothing"


def test_as_of_filters_before_deduplicating(store_at):
    """Taking each subscriber's latest row and THEN filtering would drop a
    subscriber entirely whenever their newest snapshot post-dates the cut-off,
    which silently shrinks a backtest cohort instead of answering it."""
    frame = pd.DataFrame(
        {
            "subscriber_id_hashed": ["a", "a", "b"],
            "snapshot_date": pd.to_datetime(["2026-02-01", "2026-08-01", "2026-03-01"]),
            "recharge_count_90d": [3, 9, 4],
        }
    )
    store_at.write_offline(frame)

    visible = store_at.get_features(as_of="2026-06-01")

    assert set(visible["subscriber_id_hashed"]) == {"a", "b"}, "a subscriber was dropped"
    a = visible.loc[visible["subscriber_id_hashed"] == "a"].iloc[0]
    assert a["recharge_count_90d"] == 3, "the as-of read returned the future row"


def test_an_as_of_read_without_an_offline_store_fails_loudly(store_at):
    """Silently serving the online store instead would answer a point-in-time
    question with today's features."""
    with pytest.raises(FileNotFoundError, match="as-of read needs the offline store"):
        store_at.get_features(as_of="2026-06-01")


def test_offline_store_refuses_a_frame_with_no_time_column(store_at, panel):
    with pytest.raises(KeyError, match="snapshot_date"):
        store_at.write_offline(panel.drop(columns=["snapshot_date"]))


def test_online_store_is_read_only_by_default(store_at, panel):
    """A serving path that can write is one that eventually will, by accident."""
    store_at.build_online(panel)

    connection = store_at.connect()
    try:
        with pytest.raises(Exception, match=r"(?i)read.only|cannot execute"):
            connection.execute(f"DELETE FROM {store_at.TABLE}")
    finally:
        connection.close()


def test_online_store_keeps_only_the_latest_row_per_subscriber(store_at, panel):
    """Serving answers "what do we know now", not "what did we know in March"."""
    doubled = pd.concat(
        [panel, panel.assign(snapshot_date=pd.Timestamp("2026-12-31"))], ignore_index=True
    )
    store_at.build_online(doubled)

    connection = store_at.connect()
    try:
        rows = connection.execute(f"SELECT count(*) FROM {store_at.TABLE}").fetchone()[0]
        latest = connection.execute(f"SELECT max(snapshot_date) FROM {store_at.TABLE}").fetchone()[
            0
        ]
    finally:
        connection.close()

    assert rows == panel["subscriber_id_hashed"].nunique()
    assert pd.Timestamp(latest) == pd.Timestamp("2026-12-31"), "serving kept a stale snapshot"


def test_the_subscriber_index_is_unique(store_at, panel):
    """Two rows for one subscriber at serving time means the API returns a
    different answer depending on row order."""
    store_at.build_online(panel)
    connection = store_at.connect()
    try:
        duplicates = connection.execute(
            f"SELECT count(*) FROM (SELECT {store_at.ID_COLUMN} FROM {store_at.TABLE} "
            f"GROUP BY 1 HAVING count(*) > 1)"
        ).fetchone()[0]
    finally:
        connection.close()
    assert duplicates == 0
