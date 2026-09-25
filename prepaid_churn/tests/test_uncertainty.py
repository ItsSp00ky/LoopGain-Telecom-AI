"""Intervals on the frozen test metrics: they must change nothing and prove what they claim.

Everything here runs on small made-up predictions or on the hand-made population of
`conftest.py`, never on the real dataset.
"""

from dataclasses import replace

import numpy as np
import pytest
from sklearn.metrics import average_precision_score

from prepaid_churn.cli import build_parser
from prepaid_churn.evaluation import (
    BASELINE,
    CAPTURE_SHARE,
    frozen_test_probabilities,
    resample_metrics,
    top_share_metrics,
    uncertainty_report,
)

CHAMPION = "lightgbm"


@pytest.fixture
def made_up():
    """1,000 customers, about 8% churn, one informative model and one that guesses."""
    rng = np.random.default_rng(7)
    y = (rng.random(1000) < 0.08).astype(int)
    informative = np.clip(0.05 + 0.5 * y + rng.normal(0, 0.15, 1000), 0.001, 0.999)
    guessing = rng.uniform(0.0, 0.2, 1000)
    return y, {CHAMPION: informative, BASELINE: guessing}


def test_the_same_seed_gives_the_same_intervals(made_up):
    y, probabilities = made_up
    first = resample_metrics(y, probabilities, repeats=50, seed=1)
    again = resample_metrics(y, probabilities, repeats=50, seed=1)
    other = resample_metrics(y, probabilities, repeats=50, seed=2)
    assert first.equals(again)
    assert not first.equals(other)


def test_the_estimates_are_computed_exactly_as_the_release_gate_does(made_up):
    """If these drifted, the report's estimates would stop matching evaluation_all.md."""
    y, probabilities = made_up
    everyone = resample_metrics(y, probabilities, repeats=1, seed=0)
    assert len(everyone) == 1
    report = uncertainty_report(y, probabilities, CHAMPION, "2026-09-19", repeats=20)
    published = average_precision_score(y, probabilities[CHAMPION])
    capture = top_share_metrics(probabilities[CHAMPION], y, (CAPTURE_SHARE,))["recall"].iloc[0]
    assert f"{published:.4f} [" in report
    assert f"{capture:.4f} [" in report


def test_a_model_against_itself_differs_by_exactly_zero(made_up):
    """The difference is paired: both columns are scored on the same resampled customers."""
    y, probabilities = made_up
    twins = {CHAMPION: probabilities[CHAMPION], BASELINE: probabilities[CHAMPION]}
    samples = resample_metrics(y, twins, repeats=40, seed=3)
    assert (samples[f"{CHAMPION}.pr_auc"] == samples[f"{BASELINE}.pr_auc"]).all()


def test_a_clearly_better_model_wins_almost_every_resample(made_up):
    y, probabilities = made_up
    samples = resample_metrics(y, probabilities, repeats=200, seed=4)
    wins = (samples[f"{CHAMPION}.pr_auc"] > samples[f"{BASELINE}.pr_auc"]).mean()
    assert wins > 0.99


def test_a_resample_with_one_class_is_drawn_again():
    """Three customers, one churner: about 30% of raw draws have no churner at all."""
    y = np.array([1, 0, 0])
    probabilities = {CHAMPION: np.array([0.9, 0.2, 0.1])}
    samples = resample_metrics(y, probabilities, repeats=30, seed=5)
    assert len(samples) == 30
    assert samples["churn_rate"].between(0, 1, inclusive="neither").all()


def test_the_report_says_it_changes_nothing_and_checks_every_gate(made_up):
    y, probabilities = made_up
    report = uncertainty_report(y, probabilities, CHAMPION, "2026-09-19", repeats=100)
    assert "This analysis changes nothing." in report
    assert "may be used to justify a change" in report
    for check in ("capture", "better_than_chance", "calibration", "better_than_baseline"):
        assert f"| {check} |" in report
    assert "They do not cover training randomness" in report


def test_the_frozen_predictions_are_reproduced_exactly(trained):
    """Repeating the validation-only freeze must give the saved champion's predictions."""
    datasets, champion = trained["datasets"], trained["champion"]
    probabilities = frozen_test_probabilities(
        trained["models"], champion, datasets["validation"], datasets["test"]
    )
    assert set(probabilities) == {"logistic_regression", "lightgbm"}
    assert np.array_equal(probabilities[champion.name], champion.predict(datasets["test"]))


def test_predictions_that_do_not_match_the_saved_champion_are_refused(trained):
    """An interval around different predictions would describe a model nobody evaluated."""
    datasets = trained["datasets"]
    impostor = replace(trained["champion"], name="not_the_champion")
    with pytest.raises(ValueError, match="did not reproduce the saved champion"):
        frozen_test_probabilities(
            trained["models"], impostor, datasets["validation"], datasets["test"]
        )


def test_uncertainty_is_a_churn_command():
    args = build_parser().parse_args(["uncertainty", "--repeats", "500"])
    assert (args.command, args.repeats) == ("uncertainty", 500)
    assert args.report.name == "uncertainty.md"
