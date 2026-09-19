import numpy as np
import pytest
from sklearn.metrics import log_loss

from prepaid_churn.evaluation import (
    Calibrator,
    best_f1_threshold,
    choose_calibrator,
    evaluation_report,
    freeze,
    release_gate,
    reliability_table,
    risk_band,
    success_thresholds,
    top_share_metrics,
)
from prepaid_churn.training import train_models
from prepaid_churn.windows import build_datasets


@pytest.fixture
def overconfident():
    """True churn probabilities and a model that overstates them (square root)."""
    rng = np.random.default_rng(0)
    truth = rng.uniform(0, 0.3, 5000)
    y = (rng.uniform(size=truth.size) < truth).astype(int)
    return np.sqrt(truth), y


@pytest.mark.parametrize("method", ["sigmoid", "isotonic"])
def test_calibration_fixes_overconfident_probabilities(overconfident, method):
    raw, y = overconfident
    calibrated = Calibrator(method).fit(raw, y).transform(raw)
    assert log_loss(y, calibrated) < log_loss(y, raw)
    assert calibrated.min() > 0 and calibrated.max() < 1


def test_no_calibration_is_the_identity():
    probability = np.array([0.1, 0.5, 0.9])
    np.testing.assert_allclose(
        Calibrator("none").fit(probability, [0, 1, 1]).transform(probability), probability
    )


def test_unknown_calibration_method():
    with pytest.raises(ValueError):
        Calibrator("magic")


def test_choose_calibrator_picks_the_lowest_cross_validated_loss(overconfident):
    raw, y = overconfident
    calibrator, scores = choose_calibrator(raw, y)
    assert calibrator.method == min(scores, key=scores.get)
    assert calibrator.method != "none"


def test_best_f1_threshold_separates_clean_classes():
    probability = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    y = np.array([0, 0, 0, 1, 1, 1])
    assert best_f1_threshold(probability, y) == 0.7


def test_top_share_metrics():
    probability = np.linspace(1, 0, 20)  # riskiest first
    y = np.array([1, 1, 0, 1] + [0] * 16)
    table = top_share_metrics(probability, y, shares=(0.10, 0.20))
    assert table.loc["top 10%", "customers"] == 2
    assert table.loc["top 10%", "precision"] == 1.0
    assert table.loc["top 20%", "recall"] == 1.0


def test_reliability_table(overconfident):
    raw, y = overconfident
    table = reliability_table(raw, y)
    assert len(table) == 10
    assert table["customers"].sum() == len(y)
    assert table["predicted"].is_monotonic_increasing


def test_risk_band():
    assert risk_band([0.9, 0.2, 0.01], high=0.5, medium=0.05).tolist() == ["high", "medium", "low"]


def test_freeze_and_report(population):
    datasets = build_datasets(population)
    models = train_models(datasets["train"])
    champion, choices = freeze(models, datasets["validation"], chosen_at="2026-09-19")
    assert champion.name in models
    assert set(choices) == set(models)
    probability = champion.predict(datasets["test"])
    assert probability.shape == (len(datasets["test"]),)
    gate = release_gate(champion, choices, models, datasets["test"])
    assert gate["champion"] == champion.name
    assert set(gate["test_metrics"]) == set(models)
    report = evaluation_report(champion, choices, models, datasets["test"], gate)
    assert "Frozen choices" in report
    assert "2026-09-19" in report
    assert "Success thresholds (decision 13)" in report


def _ranked(churners_on_top: int) -> tuple[np.ndarray, np.ndarray]:
    """100 customers, 10 churners; `churners_on_top` of them are among the 10 riskiest."""
    y = np.zeros(100, dtype=int)
    y[:churners_on_top] = 1
    y[50 : 50 + 10 - churners_on_top] = 1
    probability = np.linspace(0.2, 0.001, 100)  # mean 0.1005, the churn rate is 0.10
    return y, probability


def test_success_thresholds_pass_for_a_good_model():
    y, probability = _ranked(churners_on_top=8)
    checks = success_thresholds(y, probability, baseline_probability=probability[::-1])
    assert all(check["passed"] for check in checks.values())
    assert checks["capture"]["value"] == 0.8


def test_each_success_threshold_can_fail():
    y, probability = _ranked(churners_on_top=4)
    checks = success_thresholds(y, probability * 2, baseline_probability=probability)
    assert not checks["capture"]["passed"]  # 4 of 10 churners in the riskiest 10%
    assert not checks["calibration"]["passed"]  # mean prediction 0.20 against 0.10
    assert not checks["better_than_baseline"]["passed"]  # same ranking as the baseline
    y, _ = _ranked(churners_on_top=0)
    assert not success_thresholds(y, probability)["better_than_chance"]["passed"]


def test_a_baseline_champion_has_nothing_to_beat():
    y, probability = _ranked(churners_on_top=8)
    assert success_thresholds(y, probability)["better_than_baseline"]["passed"]
