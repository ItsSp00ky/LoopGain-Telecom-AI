import json
from dataclasses import replace

import joblib
import numpy as np
import pandas as pd
import pytest
from conftest import build_population_raw

from prepaid_churn import cli
from prepaid_churn.bundle import BundleError, save_bundle
from prepaid_churn.cli import OUTPUT_CONTRACT_PATH, main
from prepaid_churn.schema import InvalidExportError
from prepaid_churn.scoring import (
    LOW_RISK_REASON,
    OUTPUT_COLUMN_NAMES,
    SILENT_BAND,
    SILENT_REASON,
    contributions,
    feature_label,
    format_value,
    output_contract_markdown,
    score,
    validate_output,
)
from prepaid_churn.training import feature_columns

SCORED_AT = "2026-09-19T12:00:00+00:00"


@pytest.fixture
def export() -> pd.DataFrame:
    return build_population_raw()


def test_scores_follow_the_output_contract(export, bundle):
    scores = score(export, bundle, SCORED_AT)
    assert list(scores.columns) == OUTPUT_COLUMN_NAMES
    assert scores["subscriber_id"].tolist() == export["id"].astype(str).tolist()
    validate_output(scores)
    assert (scores["model_version"] == bundle.version).all()


def test_silent_customers_are_not_scored(export, bundle):
    # Hand-made customers 1 and 3 have no calls and no data in month 8 (decision 12).
    scores = score(export, bundle, SCORED_AT)
    is_silent = (export["id"] % 4).isin([1, 3])
    silent = scores[is_silent]
    assert (silent["risk_band"] == SILENT_BAND).all()
    assert silent["churn_probability"].isna().all()
    assert (silent["reason_1"] == SILENT_REASON).all()
    active = scores[~is_silent]
    assert active["churn_probability"].between(0, 1).all()
    assert active["risk_band"].isin(["high", "medium", "low"]).all()


def test_one_customer_alone_scores_like_inside_the_batch(export, bundle):
    whole = score(export, bundle, SCORED_AT)
    for row in range(4):  # one of each hand-made customer
        alone = score(export.iloc[[row]], bundle, SCORED_AT)
        pd.testing.assert_frame_equal(alone, whole.iloc[[row]].reset_index(drop=True))


def with_thresholds(bundle, high: float, medium: float):
    """The same bundle and probabilities with other band thresholds, to choose the bands."""
    champion = replace(bundle.champion, high_threshold=high, medium_threshold=medium)
    return replace(bundle, champion=champion)


def test_reasons_name_a_factor_and_its_value(export, bundle):
    scores = score(export, with_thresholds(bundle, high=0.0, medium=0.0), SCORED_AT)
    active = scores[scores["risk_band"] != SILENT_BAND]
    assert (active["risk_band"] == "high").all()
    reasons = active[["reason_1", "reason_2", "reason_3"]].stack()
    assert len(reasons) > 0, "no active customer got a reason"
    assert reasons.str.contains(": ").all()
    assert not reasons.str.contains("_").any()  # plain words, not column names
    assert not reasons.eq(LOW_RISK_REASON).any()


def test_low_risk_customers_get_one_plain_line_instead_of_reasons(export, bundle):
    """SHAP always finds a few small upward pushes, which would read as warning signs."""
    scores = score(export, with_thresholds(bundle, high=2.0, medium=1.5), SCORED_AT)
    low = scores[scores["risk_band"] == "low"]
    assert len(low) == (scores["risk_band"] != SILENT_BAND).sum() > 0
    assert (low["reason_1"] == LOW_RISK_REASON).all()
    assert low[["reason_2", "reason_3"]].isna().all().all()
    unchanged = score(export, bundle, SCORED_AT)
    pd.testing.assert_series_equal(scores["churn_probability"], unchanged["churn_probability"])


def test_an_invalid_export_is_rejected_before_scoring(export, bundle):
    with pytest.raises(InvalidExportError, match="aon"):
        score(export.drop(columns="aon"), bundle, SCORED_AT)


def test_a_broken_output_row_is_caught(export, bundle):
    scores = score(export, bundle, SCORED_AT)
    scores.loc[0, "churn_probability"] = np.nan  # active customer without a probability
    with pytest.raises(BundleError, match="only already_silent subscribers have no probability"):
        validate_output(scores)


def test_every_model_feature_has_a_plain_label(trained):
    for feature in feature_columns(trained["datasets"]["train"]):
        label = feature_label(feature)
        assert "_" not in label, feature


def test_format_value():
    assert format_value("cur_onnet_share", 0.25) == "25%"
    assert format_value("diff_incoming_share", -0.1) == "-10%"
    assert format_value("trend_total_og_mou", 0.5) == "50%"
    assert format_value("cur_night_pck_user", 1.0) == "yes"
    assert format_value("days_since_last_rech_window", 23.0) == "23"
    assert format_value("cur_roam_og_mou", 1234.56) == "1,234.6"


@pytest.mark.parametrize("name", ["lightgbm", "logistic_regression"])
def test_contributions_add_up_to_the_model_log_odds(trained, name):
    model = trained["models"][name]
    validation = trained["datasets"]["validation"]
    x = validation[feature_columns(validation)]
    contribution = contributions(model, x)
    assert contribution.shape == x.shape
    if name == "lightgbm":
        base = model.predict(x, pred_contrib=True)[:, -1]
        log_odds = model.predict(x, raw_score=True)
    else:
        base = model[-1].intercept_[0]
        log_odds = model.decision_function(x)
    np.testing.assert_allclose(contribution.sum(axis=1) + base, log_odds, atol=1e-6)


def test_output_contract_document_is_current():
    assert OUTPUT_CONTRACT_PATH.read_text(encoding="utf-8") == output_contract_markdown()


def test_bundle_and_score_commands(trained, bundle, export, tmp_path, monkeypatch, capsys):
    data_dir = tmp_path / "processed" / "all"
    data_dir.mkdir(parents=True)
    trained["datasets"]["validation"].to_parquet(data_dir / "validation.parquet", index=False)
    model_dir = tmp_path / "models" / "all"
    model_dir.mkdir(parents=True)
    joblib.dump(bundle.champion, model_dir / "champion.joblib")
    (model_dir / cli.GATE_FILE).write_text(json.dumps(bundle.manifest["release_gate"]), "utf-8")
    monkeypatch.setattr(cli, "MODELS_DIR", tmp_path / "models")

    bundle_dir = tmp_path / "bundle"
    main(["bundle", "--data-dir", str(data_dir), "--output-dir", str(bundle_dir)])
    source, output = tmp_path / "export.csv", tmp_path / "scores" / "scores.csv"
    export.to_csv(source, index=False)
    main(["score", "--input", str(source), "--output", str(output), "--bundle", str(bundle_dir)])

    scores = pd.read_csv(output, dtype={"subscriber_id": str})
    assert len(scores) == len(export)
    assert f"{len(export)} subscribers scored" in capsys.readouterr().out


def test_score_without_bundle_fails_cleanly(export, tmp_path, capsys):
    source = tmp_path / "export.csv"
    export.to_csv(source, index=False)
    with pytest.raises(SystemExit) as exc:
        main(["score", "--input", str(source), "--bundle", str(tmp_path / "none")])
    assert exc.value.code == 1
    assert "churn bundle" in capsys.readouterr().err


def test_a_saved_bundle_scores_the_same(export, bundle, tmp_path):
    from prepaid_churn.bundle import load_bundle

    loaded = load_bundle(save_bundle(bundle, tmp_path))
    pd.testing.assert_frame_equal(
        score(export, loaded, SCORED_AT), score(export, bundle, SCORED_AT)
    )


def test_feature_labels_read_as_sentences():
    assert feature_label("cur_roam_og_mou") == "Outgoing roaming minutes this month"
    assert feature_label("prev_days_since_last_rech") == (
        "Days since the last recharge, at the end of last month"
    )
    assert feature_label("days_since_last_rech_window") == "Days since the last recharge"
