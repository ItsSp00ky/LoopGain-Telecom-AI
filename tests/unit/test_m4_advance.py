"""Layer 4 -- M4 advance: the PD heads, reject inference, and the limit function.

THIS IS THE ONLY MODULE THAT LENDS MONEY, so the failure mode is not a bad
metric — it is a real subscriber handed a debt that consumes their next
recharge. The behavioural guards live in tests/guardrails/; these cover the
machinery underneath them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.config import load_conf
from cvm.decision import advance_limit
from cvm.models.m4_advance import reject_inference, repayment_pd


@pytest.fixture
def population() -> pd.DataFrame:
    """Borrowers and never-borrowers, with the -1 sentinel the generator uses."""
    rng = np.random.default_rng(606)
    n = 3000
    took = rng.random(n) < 0.38
    return pd.DataFrame(
        {
            "subscriber_id_hashed": [f"{i:064x}" for i in range(n)],
            "airtime_advance_count_90d": np.where(took, rng.integers(1, 6, n), 0).astype(float),
            "data_advance_count_90d": np.where(took & (rng.random(n) < 0.5), 1.0, 0.0),
            "days_to_settle": np.where(took, rng.gamma(2, 3, n), -1.0),
            "modal_recharge_amount_lyd": rng.choice([5.0, 10.0, 20.0, 40.0], n),
            "balance_zero_hours_30d": rng.gamma(2, 50, n),
            "driver": rng.normal(size=n),
        }
    )


# --- The label --------------------------------------------------------------


def test_only_borrowers_have_an_observed_outcome(population):
    """62% never took an advance, so they have no settlement outcome. Coercing
    the -1 sentinel to "repaid" or "defaulted" would invent 62,000 rows."""
    observed = repayment_pd.build_label(population, "airtime")

    assert len(observed) < len(population)
    assert (observed["airtime_advance_count_90d"] > 0).all()
    assert (observed["days_to_settle"] >= 0).all()


def test_the_label_is_censored_at_the_configured_horizon(population):
    horizon = load_conf("advance")["limit_function"]["censor_at_days"]
    observed = repayment_pd.build_label(population, "airtime")

    expected = (observed["days_to_settle"] <= horizon).astype(int)
    assert (observed["repaid_by_next_recharge"] == expected).all()
    assert horizon == 14


def test_an_unknown_product_is_refused(population):
    with pytest.raises(ValueError, match="unknown product"):
        repayment_pd.build_label(population, "sms")


# --- The two regressions that mattered most --------------------------------


def test_sample_weight_reaches_fit_not_the_constructor():
    """REGRESSION, and it silently disabled the whole reject-inference
    correction. LightGBM accepts arbitrary constructor keywords and discards
    the ones it does not know, so `sample_weight` passed there is dropped
    without a warning. Measured: mean p = 0.504 through the constructor and
    0.950 through fit(), on identical data and weights."""
    from cvm.models.m1_churn.gradient_boosting import train

    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(2000, 3)), columns=list("abc"))
    y = pd.Series((rng.random(2000) < 0.5).astype(int))
    weight = np.where(y == 1, 0.97, 0.03)

    weighted = train(X, y, kind="lightgbm", n_estimators=40, sample_weight=weight)
    unweighted = train(X, y, kind="lightgbm", n_estimators=40)

    assert weighted.predict_proba(X)[:, 1].mean() > unweighted.predict_proba(X)[:, 1].mean() + 0.2


def test_a_fit_only_parameter_in_params_raises():
    """The guard that stops the same bug returning by a different name."""
    from cvm.models.m1_churn.gradient_boosting import train

    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    y = pd.Series([0, 1, 0, 1])
    with pytest.raises(TypeError, match="fit\\(\\) parameters"):
        train(X, y, kind="lightgbm", eval_metric="auc")


def test_calibration_never_uses_inferred_labels():
    """REGRESSION. Fuzzy augmentation gives each never-borrowed subscriber two
    rows, one labelled repaid and one defaulted, so the augmented set is near
    50/50 whatever the weights are. Fitting is fine -- the weights carry the
    information. Calibrating on it teaches the isotonic map to send every score
    to 0.5, and it does that silently: mean PD moved 0.97 -> 0.61 and the shift
    was reported as a bias correction."""
    rng = np.random.default_rng(1)
    n = 2000
    X = pd.DataFrame(rng.normal(size=(n, 3)), columns=list("abc"))
    y = pd.Series((rng.random(n) < 0.95).astype(int))  # a high-repayment base

    honest = repayment_pd.train(X, y, product="airtime", calibration=(X, y))
    mean_pd = honest.predict_proba(X)[:, 1].mean()

    assert mean_pd == pytest.approx(
        y.mean(), abs=0.05
    ), f"calibrated mean {mean_pd:.3f} against an observed {y.mean():.3f}"


# --- Reject inference -------------------------------------------------------


def test_fuzzy_augmentation_duplicates_each_reject_with_complementary_weights():
    """It is not new information -- the outcome was never observed. It stops
    the model being confident about a region it has no data in, which is a real
    benefit and a modest one."""
    accepted = pd.DataFrame({"x": [1.0, 2.0], "repaid_by_next_recharge": [1, 0]})
    rejected = pd.DataFrame({"x": [3.0, 4.0]})

    class Stub:
        def predict_proba(self, X):
            return np.column_stack([np.full(len(X), 0.3), np.full(len(X), 0.7)])

    augmented = reject_inference.fuzzy_augmentation(accepted, rejected, Stub())

    assert len(augmented) == len(accepted) + 2 * len(rejected)
    weights = augmented[reject_inference.WEIGHT]
    assert weights.iloc[: len(accepted)].eq(1.0).all()
    # Each reject contributes 0.7 to repaid and 0.3 to defaulted -- summing to 1.
    per_reject = weights.iloc[len(accepted) :].to_numpy().reshape(2, -1).sum(axis=0)
    assert per_reject == pytest.approx(1.0)


def test_reject_inference_cannot_be_quietly_disabled(monkeypatch):
    """Config marks it mandatory and tests/guardrails/ asserts that. A
    correction with an off switch is not a correction."""
    import cvm.models.m4_advance.reject_inference as module

    monkeypatch.setattr(module, "_conf", lambda: {"enabled": False, "method": "fuzzy_augmentation"})
    with pytest.raises(ValueError, match="documented as mandatory"):
        module.fuzzy_augmentation(
            pd.DataFrame({"x": [1.0], "repaid_by_next_recharge": [1]}),
            pd.DataFrame({"x": [2.0]}),
            None,
        )


def test_bias_is_quantified_with_a_sign_not_just_a_magnitude():
    """The DIRECTION is the surprising part here. A bank's gate selects the
    safer tail; Almadar's gate is `balance <= 0.5 LYD`, which selects on being
    broke -- so the textbook direction cannot be assumed."""
    rng = np.random.default_rng(2)
    accepted = pd.DataFrame({"balance": rng.normal(0, 1, 500), "tenure": rng.normal(5, 1, 500)})
    rejected = pd.DataFrame({"balance": rng.normal(2, 1, 900), "tenure": rng.normal(5, 1, 900)})

    bias = reject_inference.quantify_bias(accepted, rejected)

    assert bias["standardised_mean_differences"]["balance"] < -1.0, "sign must be preserved"
    assert bias["max_abs_smd_feature"] == "balance"
    assert bias["n_accepted"] == 500 and bias["n_rejected"] == 900


def test_bias_needs_comparable_columns():
    with pytest.raises(ValueError, match="no shared numeric columns"):
        reject_inference.quantify_bias(pd.DataFrame({"a": [1.0]}), pd.DataFrame({"b": [2.0]}))


# --- Lockout risk -----------------------------------------------------------


def test_lockout_risk_is_not_one_minus_pd():
    """If it were, the function would not exist. PD asks whether they settle;
    lockout asks whether THIS debt, at THIS size, against THEIR recharge
    behaviour, is still outstanding at day 14."""
    X = pd.DataFrame({"modal_recharge_amount_lyd": [40.0, 40.0], "a": [0.0, 0.0]})

    class Stub:
        columns = None

        def predict_proba(self, X):
            return np.column_stack([np.full(len(X), 0.2), np.full(len(X), 0.8)])

    small = repayment_pd.predict_lockout_risk(Stub(), X, pd.Series([1.0, 1.0]))
    large = repayment_pd.predict_lockout_risk(Stub(), X, pd.Series([5.0, 5.0]))

    assert (large > small).all(), "a bigger debt against the same subscriber must be riskier"
    assert not np.allclose(small, 1 - 0.8), "it is not simply 1 - PD"


# --- The four terms ---------------------------------------------------------


def test_pd_bands_are_monotonic_through_the_function():
    """Config asserts the bands are ordered; this asserts the function honours
    them. Higher repayment probability must never yield a lower limit."""
    limits = [advance_limit.limit_from_pd(p, "airtime") for p in np.linspace(0, 1, 50)]
    assert limits == sorted(limits)


def test_airtime_only_ever_offers_real_denominations():
    """We cannot invent a 2 LYD advance."""
    real = set(load_conf("catalogue")["emergency_credit"]["rasid_fi_waqtuh"]["denominations_lyd"])
    offered = {advance_limit.limit_from_pd(p, "airtime") for p in np.linspace(0, 1, 200)}
    assert offered - {0.0} <= {float(d) for d in real}


def test_the_data_product_is_grant_or_decline():
    """Flat 5 LYD, so the only decision available is yes or no."""
    offered = {advance_limit.limit_from_pd(p, "data") for p in np.linspace(0, 1, 200)}
    assert offered == {0.0, 5.0}


def test_an_out_of_range_probability_is_refused():
    for bad in (-0.1, 1.2):
        with pytest.raises(ValueError, match="must be a probability"):
            advance_limit.limit_from_pd(bad)


def test_affordability_leaves_change_off_the_modal_recharge():
    """The fraction is strictly below 1.0 and that is the point. At 1.0 a debt
    equal to the modal recharge is allowed -- the zero-residual case."""
    fraction = load_conf("advance")["safety_guards"]["affordability_ceiling"][
        "max_debt_as_fraction_of_modal_recharge"
    ]
    assert fraction < 1.0
    assert advance_limit.affordability_ceiling(5.0) == pytest.approx(5.0 * fraction)
    assert advance_limit.affordability_ceiling(5.0) < 5.0


def test_unknown_recharge_behaviour_grants_nothing():
    """Absence of evidence is not evidence of capacity to repay."""
    assert advance_limit.affordability_ceiling(float("nan")) == 0.0
    assert advance_limit.affordability_ceiling(None) == 0.0


def test_an_unknown_tier_gets_the_most_conservative_ceiling():
    """A typo in a tier name must not widen someone's credit."""
    ceilings = load_conf("advance")["limit_function"]["tier_ceiling_lyd"]
    assert advance_limit.limit_from_tier("platnium") == float(min(ceilings.values()))
    assert advance_limit.limit_from_tier("GOLD") == float(ceilings["gold"])


def test_clv_bounds_the_exposure():
    fraction = load_conf("advance")["limit_function"]["max_fraction_of_clv"]
    assert advance_limit.limit_from_clv(480.0) == pytest.approx(480.0 * fraction)
    assert advance_limit.limit_from_clv(float("nan")) == 0.0


def test_step_down_lands_on_real_rungs_only():
    """5 -> 3 -> 1 -> 0, never 4 or 2."""
    assert advance_limit._step_down(5.0) == 3.0
    assert advance_limit._step_down(3.0) == 1.0
    assert advance_limit._step_down(1.0) == 0.0
