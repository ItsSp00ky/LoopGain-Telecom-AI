import json

import numpy as np
import pandas as pd
import pytest

from prepaid_churn.bundle import save_bundle
from prepaid_churn.clean import clean
from prepaid_churn.cli import main
from prepaid_churn.features import add_features
from prepaid_churn.operator_market import load_market, load_offers, operator_view
from prepaid_churn.schema import validate
from prepaid_churn.scoring import OUTPUT_COLUMN_NAMES, score
from prepaid_churn.segmentation import compare_clusters, tiers_report, write_cluster_plots
from prepaid_churn.value import (
    SCORE_COLUMNS,
    TIERS,
    VALUE_COLUMNS,
    ValueModelError,
    apply_tiers,
    expected_months,
    fit_tiers,
    load_tiers,
    save_tiers,
    tier_export,
    value_measures,
    value_scenarios,
)
from prepaid_churn.windows import WINDOW_A, WINDOW_B, build_datasets, window_features

SCORED_AT = "2026-09-20T12:00:00+00:00"


@pytest.fixture
def train(population):
    return build_datasets(population)["train"]


@pytest.fixture
def tier_model(train):
    return fit_tiers(train, load_market())


def test_measures_use_recharge_events_and_service_breadth(raw):
    frame = add_features(window_features(clean(validate(raw)), WINDOW_A))
    frame.loc[0, ["days_since_last_rech_window", "days_since_last_rech_data_window"]] = [20, 4]
    frame.loc[0, ["prev_total_rech_num", "cur_total_rech_num"]] = [4, 2]
    frame.loc[0, ["prev_total_rech_data", "cur_total_rech_data"]] = [1, 1]
    frame.loc[0, ["prev_total_rech_amt", "cur_total_rech_amt"]] = [100, 200]
    frame.loc[0, ["prev_av_rech_amt_data", "cur_av_rech_amt_data"]] = [30, 10]
    frame.loc[0, ["prev_monthly_3g", "cur_roam_og_mou"]] = [1, 4]
    measures = value_measures(frame, 0.1)
    assert measures.loc[0, "recency"] == 4
    assert measures.loc[0, "frequency"] == 4
    assert measures.loc[0, "monetary"] == 17
    assert measures.loc[0, "engagement"] == 4
    assert measures.loc[0, "tenure"] == raw.loc[0, "aon"]


def test_money_matches_t18(raw, tier_model):
    cleaned = clean(validate(raw))
    view = operator_view(cleaned, WINDOW_B, load_market(), load_offers())
    tiers = tier_export(raw, tier_model)
    np.testing.assert_allclose(tiers["monthly_spend_lyd"], view["monthly_spend_lyd"])


def test_recent_recharge_scores_higher_and_ties_stay_together(train):
    frame = pd.concat([train.iloc[[0]]] * 10, ignore_index=True)
    for column in ("days_since_last_rech_window", "days_since_last_rech_data_window"):
        frame[column] = [0, 0, 3, 3, 10, 10, 20, 20, 50, 50]
    result = apply_tiers(frame, fit_tiers(frame, load_market()))
    assert result["recency_score"].is_monotonic_decreasing
    assert result.loc[0, "recency_score"] > result.loc[9, "recency_score"]
    for index in range(0, 10, 2):
        assert result.loc[index, "value_tier"] == result.loc[index + 1, "value_tier"]


def test_constant_and_single_customer_training_is_neutral(train):
    constant = pd.concat([train.iloc[[0]]] * 6, ignore_index=True)
    for frame in (constant, constant.iloc[[0]]):
        model = fit_tiers(frame, load_market())
        result = apply_tiers(frame, model)
        assert result[SCORE_COLUMNS].eq(3).all().all()
        assert result["value_tier"].eq("medium").all()


def test_tiers_are_independent_of_batch_size_order_and_labels(raw, train, tier_model):
    whole = tier_export(raw, tier_model)
    assert whole["value_tier"].isin(TIERS).all()
    for index in range(len(raw)):
        alone = tier_export(raw.iloc[[index]], tier_model)
        pd.testing.assert_frame_equal(alone, whole.iloc[[index]].reset_index(drop=True))
    shuffled = tier_export(raw.iloc[::-1], tier_model).iloc[::-1].reset_index(drop=True)
    pd.testing.assert_frame_equal(shuffled, whole)
    changed = train.copy()
    changed["churn"] = 1 - changed["churn"]
    changed["cur_month_9"] = 1e12
    assert fit_tiers(changed, load_market()).version == tier_model.version


def test_scoring_ignores_label_and_month_outside_window(raw, tier_model):
    changed = raw.copy()
    changed["churn_probability"] = "not an input"
    changed["total_rech_amt_6"] *= 100
    changed["total_rech_amt_9"] = 1e12
    pd.testing.assert_frame_equal(tier_export(raw, tier_model), tier_export(changed, tier_model))


def test_window_a_ignores_future_month(raw):
    cleaned = clean(validate(raw))
    original = value_measures(add_features(window_features(cleaned, WINDOW_A)), 0.1)
    cleaned["total_rech_amt_8"] = 1e12
    cleaned["churn_probability"] = 1
    actual = value_measures(add_features(window_features(cleaned, WINDOW_A)), 0.1)
    pd.testing.assert_frame_equal(actual, original)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -1])
def test_unexpected_missing_or_invalid_value_input_fails(train, bad):
    train["cur_total_rech_amt"] = train["cur_total_rech_amt"].astype(float)
    train.loc[0, "cur_total_rech_amt"] = bad
    with pytest.raises(ValueModelError, match="finite, nonnegative"):
        fit_tiers(train, load_market())


def test_empty_or_missing_training_input_fails(train):
    with pytest.raises(ValueModelError, match="without training"):
        fit_tiers(train.iloc[:0], load_market())
    with pytest.raises(ValueModelError, match="missing"):
        fit_tiers(train.drop(columns="tenure_days"), load_market())


def test_tier_artifact_roundtrip_and_frozen_money_rate(train, tier_model, tmp_path):
    path = tmp_path / "tiers.json"
    save_tiers(tier_model, path)
    loaded = load_tiers(path)
    assert loaded == tier_model
    market = load_market()
    market["arpu"]["monthly_lyd"] *= 2
    assert fit_tiers(train, market).version != loaded.version
    pd.testing.assert_frame_equal(apply_tiers(train, loaded), apply_tiers(train, tier_model))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("rate", 0),
        ("rate", float("inf")),
        ("training_rows", False),
        ("schema_version", 2),
        ("schema_version", True),
        ("training_window", "B"),
        ("cutoffs", {}),
        ("version", "tampered"),
    ],
)
def test_corrupt_tier_artifact_is_rejected(tier_model, tmp_path, field, bad):
    path = tmp_path / "tiers.json"
    save_tiers(tier_model, path)
    payload = json.loads(path.read_text("utf-8"))
    payload[field] = bad
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueModelError, match="Invalid tier artifact"):
        load_tiers(path)


def test_scenario_endpoints_monotonicity_and_sensitivity():
    probability = pd.Series([0.0, 0.1, 0.5, 1.0, np.nan])
    result = value_scenarios(pd.Series([40.0] * 5), probability)
    assert result.loc[0, "expected_months_12m"] == 12
    assert result.loc[3, "expected_months_12m"] == 0
    assert result.iloc[4].isna().all()
    assert result.loc[1, "expected_months_12m"] == pytest.approx(sum(0.9**m for m in range(1, 13)))
    assert result.loc[:3, "value_12m_base_lyd"].is_monotonic_decreasing
    assert (result.loc[:3, "value_12m_low_lyd"] <= result.loc[:3, "value_12m_base_lyd"]).all()
    assert (result.loc[:3, "value_12m_base_lyd"] <= result.loc[:3, "value_12m_high_lyd"]).all()
    assert result.loc[:3, "value_12m_high_lyd"].le(480).all()


@pytest.mark.parametrize("bad", [-0.01, 1.01, np.inf])
def test_invalid_risk_is_rejected_before_sensitivity_clipping(bad):
    with pytest.raises(ValueModelError, match="probabilities"):
        value_scenarios(pd.Series([40.0]), pd.Series([bad]))


def test_misaligned_value_and_risk_is_rejected():
    with pytest.raises(ValueModelError, match="indices"):
        value_scenarios(pd.Series([40.0], index=[1]), pd.Series([0.2], index=[2]))


def test_scored_tiers_preserve_t8_and_only_estimate_active_customers(raw, tier_model, bundle):
    result = tier_export(raw, tier_model, bundle, SCORED_AT)
    assert list(result.columns) == OUTPUT_COLUMN_NAMES + [column.name for column in VALUE_COLUMNS]
    pd.testing.assert_frame_equal(result[OUTPUT_COLUMN_NAMES], score(raw, bundle, SCORED_AT))
    assert result.loc[[1, 3], "value_status"].eq("already_silent").all()
    assert result.loc[[1, 3], "value_12m_base_lyd"].isna().all()
    assert result.loc[[0, 2], "value_status"].eq("scenario").all()
    assert result.loc[[0, 2], "value_12m_base_lyd"].notna().all()
    assert result["subscriber_id"].is_unique
    for index in range(len(raw)):
        alone = tier_export(raw.iloc[[index]], tier_model, bundle, SCORED_AT)
        pd.testing.assert_frame_equal(alone, result.iloc[[index]].reset_index(drop=True))


def test_tiers_only_leaves_scenarios_missing_and_preserves_text_ids(raw, tier_model):
    raw["id"] = ["0001", "0002", "NA", "0004"]
    result = tier_export(raw, tier_model)
    assert result["subscriber_id"].tolist() == raw["id"].tolist()
    assert result["value_12m_base_lyd"].isna().all()
    assert result.loc[[0, 2], "value_status"].eq("risk_unavailable").all()


def test_degenerate_clustering_does_not_claim_structure(train, tmp_path):
    train = train.iloc[[0]]
    model = fit_tiers(train, load_market())
    comparison = compare_clusters(apply_tiers(train, model))
    assert comparison.chosen_k is None
    write_cluster_plots(comparison, tmp_path)
    assert not list(tmp_path.glob("*.png"))
    assert "Too few distinct" in tiers_report(train, model, comparison)


def test_clusters_choose_best_valid_silhouette_and_write_plots(train, tier_model, tmp_path):
    tiers = apply_tiers(train, tier_model)
    comparison = compare_clusters(tiers)
    best = comparison.scores.sort_values(["silhouette", "k"], ascending=[False, True]).iloc[0]
    assert comparison.chosen_k == best["k"]
    assert len(comparison.labels) == len(train)
    write_cluster_plots(comparison, tmp_path)
    for name in ("tiers_pca.png", "tiers_dendrogram.png"):
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG")
    report = tiers_report(train, tier_model, comparison)
    assert "reporting convention" in report
    assert "not validated CLV" in report
    assert "not additional churn predictions" in report


def test_fit_and_tiers_commands_read_only_train_and_score_live_export(train, raw, bundle, tmp_path):
    # No validation or test parquet exists, and no evaluation or fitting is needed to serve.
    train_path, model_path = tmp_path / "train.parquet", tmp_path / "tiers.json"
    train.to_parquet(train_path)
    main(
        [
            "fit-tiers",
            "--train",
            str(train_path),
            "--output",
            str(model_path),
            "--report",
            str(tmp_path / "tiers.md"),
        ]
    )
    raw["id"] = ["0001", "0002", "0003", "0004"]
    input_path, output_path = tmp_path / "export.csv", tmp_path / "out.csv"
    raw.to_csv(input_path, index=False)
    args = [
        "tiers",
        "--input",
        str(input_path),
        "--model",
        str(model_path),
        "--output",
        str(output_path),
    ]
    main([*args, "--tiers-only"])
    assert (
        pd.read_csv(output_path)["value_status"].isin(["risk_unavailable", "already_silent"]).all()
    )
    save_bundle(bundle, tmp_path / "bundle")
    main([*args, "--bundle", str(tmp_path / "bundle")])
    output = pd.read_csv(output_path, dtype={"subscriber_id": str})
    assert output["subscriber_id"].tolist() == raw["id"].tolist()
    assert output["value_status"].isin(["scenario", "already_silent"]).all()


def test_months_function_handles_near_zero_without_division():
    assert expected_months(np.array([1e-16]))[0] == pytest.approx(12)


def test_scenario_overflow_fails_instead_of_exporting_infinity():
    with pytest.raises(ValueModelError, match="overflowed"):
        value_scenarios(pd.Series([1e308]), pd.Series([0.0]))
