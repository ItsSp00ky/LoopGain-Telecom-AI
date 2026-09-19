"""Layer 4 -- M3 uplift: the two-model difference, Qini, and the quadrants.

The failure that matters here is not a crash. It is a model that ranks by CHURN
RISK while being called an uplift model -- which happens whenever one arm is
empty, or the control model is fitted on nothing, or the scores are read off the
rows they were trained on. Every one of those produces a plausible ranking and
funds the wrong people.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.config import load_conf
from cvm.models.m3_uplift import evaluate, two_model


@pytest.fixture
def arms() -> tuple[pd.DataFrame, pd.Series, pd.Series, np.ndarray]:
    """A randomised experiment with a KNOWN heterogeneous effect.

    Treatment helps where `driver > 0` and actively hurts where `driver < -1`,
    so the fixture contains genuine sleeping dogs rather than only noise.
    """
    rng = np.random.default_rng(606)
    n = 8000
    driver = rng.normal(size=n)
    treated = pd.Series((rng.random(n) < 0.5).astype(int))

    effect = np.where(driver > 0, 0.15, 0.0) + np.where(driver < -1, -0.12, 0.0)
    probability = np.clip(0.30 + effect * treated.to_numpy(), 0.01, 0.99)
    outcome = pd.Series((rng.random(n) < probability).astype(int))

    X = pd.DataFrame({"driver": driver, "noise": rng.normal(size=n)})
    return X, outcome, treated, effect


# --- Qini: the metric every claim in this module rests on ------------------


@pytest.mark.parametrize("share", [0.5, 0.85, 0.15])
def test_qini_matches_scikit_uplift_at_any_arm_split(share):
    """THE ONE THAT MATTERS. Criteo's arms are 85/15, and every Qini formula
    has a term rescaling the control arm to the treated arm's size. Getting it
    wrong produces a curve that looks fine and is wrong by the ratio.

    The first implementation normalised by the total incremental response
    instead of by the perfect curve: right sign, right ordering, magnitude
    about 3x too large. It would have been quoted beside the word "Qini" and
    been incomparable to every published number.

    Tolerance is 1e-4 rather than exact, and the gap is real rather than
    sloppy: sklift builds its curve at distinct score thresholds while this one
    steps through every row, so the two trapezoidal integrals differ in the
    fifth decimal (measured 5e-6 to 3e-5). That is far below anything reported
    and far above nothing -- a tolerance of 1e-9 would fail for a reason that
    is not a bug, and 1e-2 would wave through the 3x normalisation error this
    test exists to catch."""
    from sklift.metrics import qini_auc_score

    rng = np.random.default_rng(42)
    n = 20000
    t = (rng.random(n) < share).astype(int)
    score = rng.normal(size=n)
    y = (rng.random(n) < 0.05 + 0.04 * t * (score > 0)).astype(int)

    assert evaluate.qini_coefficient(score, y, t) == pytest.approx(
        qini_auc_score(y, score, t), abs=1e-4
    )


def test_qini_is_near_zero_for_a_random_ranking(arms):
    _X, y, t, _ = arms
    rng = np.random.default_rng(0)
    assert evaluate.qini_coefficient(rng.normal(size=len(y)), y, t) == pytest.approx(0.0, abs=0.05)


def test_qini_rises_when_the_ranking_is_the_true_effect(arms):
    """A model that knew the individual effect must beat a random one. If it
    does not, the metric is not measuring ranking quality."""
    _X, y, t, effect = arms
    rng = np.random.default_rng(0)

    informed = evaluate.qini_coefficient(effect, y, t)
    random = evaluate.qini_coefficient(rng.normal(size=len(y)), y, t)
    assert informed > random + 0.05


def test_qini_refuses_a_single_arm(arms):
    """Without both arms there is no counterfactual and no treatment effect to
    measure -- the number would be a response curve wearing a Qini label."""
    _X, y, _t, _ = arms
    with pytest.raises(ValueError, match="one arm is empty"):
        evaluate.qini_coefficient(np.arange(len(y)), y, np.ones(len(y)))


def test_qini_refuses_mismatched_lengths(arms):
    _X, y, t, _ = arms
    with pytest.raises(ValueError, match="lengths differ"):
        evaluate.qini_coefficient(np.arange(10), y, t)


# --- uplift@k ---------------------------------------------------------------


def test_uplift_at_k_concentrates_above_the_population_rate(arms):
    """The number the Campaign Builder needs: treating the top 30% should beat
    treating everyone, or targeting buys nothing."""
    _X, y, t, effect = arms
    overall = y[t == 1].mean() - y[t == 0].mean()
    assert evaluate.uplift_at_k(effect, y, t, k=0.3) > overall


def test_uplift_at_k_over_the_whole_population_is_the_naive_lift(arms):
    """k=1 has no ranking left to do, so it must reduce to the overall
    difference in rates. A formula that does not is rescaling something twice."""
    _X, y, t, effect = arms
    overall = float(y[t == 1].mean() - y[t == 0].mean())
    assert evaluate.uplift_at_k(effect, y, t, k=1.0) == pytest.approx(overall, abs=1e-12)


def test_uplift_at_k_rejects_an_out_of_range_k(arms):
    _X, y, t, effect = arms
    for bad in (0.0, 1.5, -0.2):
        with pytest.raises(ValueError, match="fraction in"):
            evaluate.uplift_at_k(effect, y, t, k=bad)


# --- The two-model difference ----------------------------------------------


def test_both_arms_must_be_populated(arms):
    """A control model fitted on nothing does not raise -- LightGBM fits a
    constant -- and every 'uplift' becomes the treated probability minus that
    constant. A churn model wearing an uplift model's name."""
    X, y, _t, _ = arms
    with pytest.raises(ValueError, match="Both arms must be populated"):
        two_model.train_two_model(X, y, pd.Series(np.ones(len(y), dtype=int)))


def test_an_arm_with_one_outcome_value_is_refused(arms):
    X, y, t, _ = arms
    constant = y.copy()
    constant[t == 0] = 0
    with pytest.raises(ValueError, match="single outcome value"):
        two_model.train_two_model(X, constant, t)


def test_the_model_recovers_the_sign_of_the_known_effect(arms):
    """Fitted on one half, scored on the other. The correlation with the true
    injected effect is the only ground truth available -- you never observe
    both outcomes for the same person."""
    X, y, t, effect = arms
    cut = len(X) // 2

    treated_model, control_model = two_model.train_two_model(
        X.iloc[:cut], y.iloc[:cut], t.iloc[:cut]
    )
    uplift = two_model.predict_uplift(treated_model, control_model, X.iloc[cut:])

    assert np.corrcoef(uplift, effect[cut:])[0, 1] > 0.3


def test_negative_uplift_is_preserved_not_clipped(arms):
    """The sleeping-dog signal IS the negative tail. Clipping it to zero would
    remove the only thing that distinguishes this module from a response
    model."""
    X, y, t, _ = arms
    cut = len(X) // 2
    treated_model, control_model = two_model.train_two_model(
        X.iloc[:cut], y.iloc[:cut], t.iloc[:cut]
    )
    uplift = two_model.predict_uplift(treated_model, control_model, X.iloc[cut:])
    assert (uplift < 0).any(), "no negative uplift survived, so no sleeping dog can be found"


# --- Quadrants --------------------------------------------------------------


def test_the_four_quadrants_are_the_declared_four():
    uplift = pd.Series([0.2, 0.0, 0.0, -0.2])
    baseline = pd.Series([0.5, 0.9, 0.1, 0.5])

    quadrant = two_model.classify_quadrant(uplift, baseline)
    assert set(quadrant) <= set(two_model.QUADRANTS)


def test_sleeping_dogs_beat_persuadable_on_a_tie():
    """A subscriber can look persuadable on a noisy positive tail and still be
    a sleeping dog. The harmful call is the one to get wrong."""
    threshold = load_conf("models/m3_uplift")["sleeping_dog_threshold"]
    uplift = pd.Series([threshold - 0.01])
    baseline = pd.Series([0.5])

    assert two_model.classify_quadrant(uplift, baseline).iloc[0] == "sleeping_dog"


def test_the_sleeping_dog_threshold_is_negative():
    """A positive threshold would classify helped subscribers as harmed and
    exclude exactly the people the campaign is for."""
    assert load_conf("models/m3_uplift")["sleeping_dog_threshold"] < 0
    assert load_conf("models/m3_uplift")["exclude_sleeping_dogs"] is True


def test_quadrant_counts_name_all_four_even_when_empty():
    """A missing key reads as "we did not check" rather than "there are none",
    and a caller asserting `counts['sleeping_dog'] > 0` would KeyError."""
    counts = evaluate.quadrant_counts(pd.Series([0.2, 0.3]), pd.Series([0.5, 0.6]))
    assert set(counts) == set(two_model.QUADRANTS)
    assert counts["sleeping_dog"] == 0


# --- Expected value: the bridge to the decision engine ---------------------


def test_break_even_is_cost_over_clv():
    """5 / 480 = 1.0417 pp. The tightest number in the project."""
    assert evaluate.break_even_uplift(480.0, 5.0) == pytest.approx(0.0104167, abs=1e-6)


def test_expected_value_turns_positive_exactly_at_break_even():
    """The whole business case. Below it, treating loses money however high the
    churn score is."""
    assert evaluate.expected_value_of_treatment(0.0100, 480, 5) < 0
    assert evaluate.expected_value_of_treatment(0.0110, 480, 5) > 0
    assert evaluate.expected_value_of_treatment(5 / 480, 480, 5) == pytest.approx(0.0, abs=1e-9)


def test_expected_value_is_vectorised():
    value = evaluate.expected_value_of_treatment(
        np.array([0.02, 0.005]), np.array([480.0, 480.0]), 5.0
    )
    assert value.shape == (2,)
    assert value[0] > 0 > value[1]


def test_a_scalar_returns_a_scalar():
    """The roadmap's checkpoint calls it with three plain numbers."""
    assert isinstance(evaluate.expected_value_of_treatment(0.02, 480, 5), float)


# --- The control holdout ----------------------------------------------------


def test_the_holdout_is_the_configured_fraction():
    cohort = pd.DataFrame({"x": range(10000)})
    fraction = load_conf("models/m3_uplift")["control_holdout_fraction"]
    held = two_model.assign_control_holdout(cohort)
    assert held.mean() == pytest.approx(fraction, abs=0.02)


def test_the_holdout_is_reproducible():
    """A control group that moves between runs cannot measure anything."""
    cohort = pd.DataFrame({"x": range(5000)})
    assert two_model.assign_control_holdout(cohort).equals(two_model.assign_control_holdout(cohort))


def test_a_zero_holdout_is_refused():
    """Mandatory by config. Without a counterfactual the ROI is an assertion,
    and the proposal makes a specific ROI claim."""
    with pytest.raises(ValueError, match="holdout_is_mandatory"):
        two_model.assign_control_holdout(pd.DataFrame({"x": range(100)}), fraction=0.0)
