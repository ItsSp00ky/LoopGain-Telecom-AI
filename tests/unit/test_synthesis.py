"""Layer 2 -- the generator, the overlays, the hazard and the gate.

Most of these are regression tests for bugs that got through review and were
caught by running the thing. Each one names the failure it prevents, because a
test whose purpose is not obvious gets deleted the first time it is
inconvenient.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.config import load_conf
from cvm.synthesis import overlays
from cvm.synthesis.hazard import (
    LABEL_ARTIFACT_FIELDS,
    LABEL_DRIVER_FIELDS,
    assert_label_is_learnable,
    generate_labels,
    hazard,
)
from cvm.synthesis.quality_gate import GateResult, correlation_delta, ks_complement, split_for_gate
from cvm.synthesis.quantile_map import (
    assert_on_ladder,
    enforce_orderings,
    map_to_lyd_ladder,
    match_empirical_marginals,
    preserve_point_masses,
    recharge_ladder,
)


@pytest.fixture
def population() -> pd.DataFrame:
    """A small overlaid population. Enough rows for the hazard to be stable."""
    base = pd.DataFrame(
        {
            "subscriber_id_hashed": [f"{i:064x}" for i in range(4000)],
            "snapshot_date": pd.Timestamp("2026-09-18"),
        }
    )
    return overlays.apply_all(base)


# --- The hazard ------------------------------------------------------------


def test_hazard_mean_equals_the_target_rate(population):
    """THE REGRESSION TEST FOR THE PRECEDENCE BUG.

    `1.0 / (1.0 + np.exp(...)).mean()` is 1/mean(1+exp), not mean(1/(1+exp)):
    the `.mean()` binds to the parenthesised term. It converged happily to a
    9.9% churn rate against a 3.5% target, and every calibration claim
    downstream would then have been measured against a prior nobody chose.
    """
    target = load_conf("data")["synthesis"]["hazard_function"]["base_monthly_churn"]
    assert hazard(population).mean() == pytest.approx(target, abs=1e-4)


@pytest.mark.parametrize("target", [0.005, 0.035, 0.20])
def test_hazard_tracks_any_target(population, target: float):
    """The intercept is solved per run, so changing a driver weight must not
    silently move the realised base rate."""
    assert hazard(population, base_monthly_churn=target).mean() == pytest.approx(target, abs=1e-4)


def test_hazard_refuses_a_driver_it_cannot_see(population):
    with pytest.raises(KeyError, match="days_since_last_topup"):
        hazard(population.drop(columns=["days_since_last_topup"]))


def test_drivers_and_artefacts_are_disjoint():
    """Confusing them breaks the project in opposite directions: excluding a
    driver guts the model, including an artefact makes it omniscient."""
    assert not set(LABEL_DRIVER_FIELDS) & set(LABEL_ARTIFACT_FIELDS)


def test_labels_land_strictly_inside_the_outcome_window(population):
    """The 15-day gap is the point. A churn date inside it would let a model
    exploit behaviour it would not have at scoring time."""
    windows = load_conf("features")["windows"]
    start = windows["observation_days"] + windows["gap_days"]
    end = start + windows["outcome_days"]

    labelled = generate_labels(population)
    churned = labelled[labelled["silent_churn_30d"] == 1]

    assert churned["days_to_churn"].between(start, end - 1).all()
    assert (labelled.loc[labelled["silent_churn_30d"] == 0, "days_to_churn"] == -1).all()
    assert labelled.loc[labelled["silent_churn_30d"] == 0, "churn_date"].isna().all()


def test_a_flat_hazard_is_rejected_as_unlearnable(population):
    """The opposite failure to leakage, and far harder to notice: if the hazard
    has no spread the draw is a coin flip, every model scores at chance, and it
    looks like a modelling problem for days."""
    flat = generate_labels(population)
    rng = np.random.default_rng(0)
    flat["silent_churn_30d"] = rng.integers(0, 2, len(flat))

    with pytest.raises(ValueError, match="too narrow"):
        assert_label_is_learnable(flat)


# --- Overlays --------------------------------------------------------------


def test_every_hazard_driver_is_produced_by_the_overlays(population):
    """The overlays must run before labels, and between them they must supply
    every field the hazard reads."""
    assert not set(LABEL_DRIVER_FIELDS) - set(population.columns)


def test_weekend_overlay_refuses_a_usage_multiplier(population, monkeypatch):
    """Friday-Saturday is a public fact; a usage multiplier on top of it would
    be the guessed part, and conf/market.yaml records that decision."""
    conf = load_conf("data")
    original = conf["synthesis"]["business_overlays"]["weekend_rhythm"]["apply_usage_multiplier"]
    conf["synthesis"]["business_overlays"]["weekend_rhythm"]["apply_usage_multiplier"] = True
    try:
        with pytest.raises(ValueError, match="apply_usage_multiplier"):
            overlays.apply_weekend_rhythm(population)
    finally:
        conf["synthesis"]["business_overlays"]["weekend_rhythm"][
            "apply_usage_multiplier"
        ] = original


def test_morning_overlay_requires_the_weekend_overlay_first():
    """The bump is applied to subscribers whose mornings are free, and the
    weekend share is how they are identified."""
    with pytest.raises(KeyError, match="apply_weekend_rhythm"):
        overlays.apply_morning_offpeak_usage(pd.DataFrame({"x": [1, 2, 3]}))


def test_emergency_credit_requires_the_prepaid_overlay_first():
    """Advances are conditioned on being broke, which prepaid mechanics
    establish."""
    with pytest.raises(KeyError, match="balance_zero_hours_30d"):
        overlays.apply_emergency_credit_behaviour(pd.DataFrame({"x": [1, 2, 3]}))


def test_dual_sim_tail_is_fatter_than_the_single_sim_baseline(population):
    """The measured Cell2Cell baseline is a SINGLE-SIM postpaid market: 3.0%
    above 1.0. At 85% dual-SIM penetration the generated tail must be far
    fatter, and that deviation is the entire point of the overlay."""
    baseline = load_conf("features")["families"]["leakage"]["baseline_share_above_one"]
    assert (population["incoming_outgoing_ratio"] > 1).mean() > baseline * 2


def test_the_zero_residual_population_exists(population):
    """M4's central finding needs subscribers it applies to: a modal recharge
    equal to the smallest card, against a data advance of the same size."""
    assert population["exceeds_modal_recharge"].notna().any()
    smallest = min(recharge_ladder())
    at_the_floor = population["modal_recharge_amount_lyd"] <= smallest
    assert at_the_floor.sum() > 0


def test_overlays_never_invent_a_denomination(population):
    assert_on_ladder(population["modal_recharge_amount_lyd"])


# --- Quantile mapping and the structural corrections -----------------------


def test_ladder_is_read_from_config_not_hardcoded():
    """An earlier version carried (5, 10, 15, 20, 25, 50, 100) -- three
    denominations Almadar does not sell."""
    assert recharge_ladder() == tuple(load_conf("market")["recharge"]["denominations_lyd"])


def test_mapping_preserves_rank_and_lands_on_the_ladder():
    values = pd.Series(np.random.default_rng(1).lognormal(3, 1, 2000))
    mapped = map_to_lyd_ladder(values)
    assert_on_ladder(mapped)
    assert values.corr(mapped, method="spearman") > 0.85


def test_empirical_marginals_match_the_reference_exactly():
    """SDV's fitted marginals truncated every tail -- incoming_outgoing_ratio
    to 8.3 where the real maximum is 24.0. Taking the marginal from the data
    makes range, quantiles and point masses match."""
    rng = np.random.default_rng(2)
    real = pd.DataFrame({"a": rng.lognormal(0, 1.5, 3000), "b": rng.normal(100, 30, 3000)})
    synthetic = pd.DataFrame({"a": rng.beta(2, 5, 3000), "b": rng.normal(50, 5, 3000)})

    matched = match_empirical_marginals(real, synthetic)
    for column in ("a", "b"):
        assert matched[column].min() == pytest.approx(real[column].min())
        assert matched[column].max() == pytest.approx(real[column].max())
        assert matched[column].median() == pytest.approx(real[column].median(), rel=0.02)


def test_point_masses_are_restored_in_both_directions():
    """Symmetry is necessary, not tidy. A Beta marginal produced 0% zeros where
    the real data has 7.5%; a GAMMA marginal produced 40% where the real data
    has 3.5%. Too many zeros is the case nobody expects and the worse one --
    adding zeros cannot fix it."""
    real = pd.DataFrame({"few": np.r_[np.zeros(100), np.ones(900)]})  # 10% zeros

    too_few = pd.DataFrame({"few": np.linspace(0.001, 1, 1000)})
    too_many = pd.DataFrame({"few": np.r_[np.zeros(600), np.linspace(0.1, 1, 400)]})

    assert (preserve_point_masses(real, too_few)["few"] == 0).mean() == pytest.approx(
        0.10, abs=0.01
    )
    assert (preserve_point_masses(real, too_many)["few"] == 0).mean() == pytest.approx(
        0.10, abs=0.01
    )


def test_orderings_are_restored():
    """`active_lines <= household_lines` holds for 100.00% of real rows: you
    cannot have more active lines than lines. A copula models the correlation
    and nothing else."""
    broken = pd.DataFrame({"active_lines": [5, 1, 9], "household_lines": [2, 4, 3]})
    fixed = enforce_orderings(broken, {"active_lines": "household_lines"})
    assert (fixed["active_lines"] <= fixed["household_lines"]).all()


# --- The gate --------------------------------------------------------------


def test_split_for_gate_is_disjoint_and_seeded():
    """A gate score that moves with the split is not a gate score."""
    frame = pd.DataFrame({"x": range(1000)})
    left, right = split_for_gate(frame, 0.25)

    assert len(left) + len(right) == len(frame)
    assert not set(left["x"]) & set(right["x"])
    assert split_for_gate(frame, 0.25)[0].equals(left)


def test_the_detector_cannot_separate_real_from_real():
    """THE CALIBRATION CHECK, and the one that makes every other number
    meaningful. Two disjoint halves of one distribution must score at chance.
    If this drifts from 0.5 the detector is broken and no gate reading can be
    trusted."""
    from cvm.synthesis.quality_gate import detection_auc

    rng = np.random.default_rng(606)
    frame = pd.DataFrame(
        {"a": rng.normal(0, 1, 6000), "b": rng.lognormal(0, 1, 6000), "c": rng.poisson(3, 6000)}
    )
    left, right = split_for_gate(frame, 0.5)

    assert detection_auc(left, right, detector="logistic") == pytest.approx(0.5, abs=0.06)
    assert detection_auc(left, right, detector="boosted") == pytest.approx(0.5, abs=0.06)


def test_identical_frames_score_perfectly_on_the_statistical_metrics():
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({"a": rng.normal(size=2000), "b": rng.normal(size=2000)})
    assert ks_complement(frame, frame) == pytest.approx(1.0)
    assert correlation_delta(frame, frame) == pytest.approx(0.0, abs=1e-9)


def test_gate_summary_reports_the_boosted_detector_without_gating_on_it():
    """It rises without bound with sample size for any imperfect generator, so
    it has no defensible absolute threshold -- but it must stay visible."""
    passing = GateResult(0.99, 0.02, 0.52, 0.95, 0.94, passed=True)
    summary = passing.summary()

    assert "reported" in summary
    assert "GATE PASSED" in summary
    assert "WATCH" in summary, "a boosted AUC of 0.95 must be flagged for attention"
    assert "detection AUC (boosted)" not in [name for name, *_ in passing.checks()]


def test_enforce_raises_on_a_failing_gate():
    from cvm.synthesis.quality_gate import enforce

    with pytest.raises(ValueError, match="Quality gate failed"):
        enforce(GateResult(0.5, 0.5, 0.99, 0.99, 0.2, passed=False))
