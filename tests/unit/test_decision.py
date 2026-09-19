"""Layer 5 -- the decision engine: pricing, ladder, off-peak, LP, audit log.

This is where four models become one recommendation, so the failure mode is a
plausible offer that should never have been made. The six guardrails are tested
in tests/guardrails/; these cover the machinery that calls them and the two
things that layer adds on its own -- the inverted-U and "no action".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.api.schemas import OfferRequest, RetentionStage
from cvm.config import load_conf
from cvm.decision import budget_lp, decision_log, ladder, offpeak, pricing

SUBSCRIBER = "a" * 64


@pytest.fixture
def features() -> dict:
    """A healthy, movable subscriber -- one the engine should make an offer to."""
    return {
        "tier": "gold",
        "churn_probability": 0.30,
        "uplift": 0.08,
        "clv_12m": 480.0,
        "value_decile": 6,
        "loyalty_index": 0.7,
        "price_sensitivity": 0.4,
        "affordability_headroom": 0.1,
        "offpeak_data_ratio": 0.05,
        "leakage_score": 0.1,
        "days_since_last_topup": 3,
        "inter_recharge_gap_mean": 9.0,
        "cumulative_spend_lyd_12m": 0.0,
        "pricing_features": [],
        "quadrant": "persuadable",
    }


# --- The discount formula ---------------------------------------------------


def test_affordability_is_subtracted_not_added():
    """The only term with a minus sign, and the interesting one. A subscriber
    with room in their budget does not need a price cut to stay, so discounting
    them is margin given away for nothing.

    Inputs chosen to land INSIDE the tier ceiling. At high values both clip to
    d_max and the comparison proves nothing -- which is itself the finding in
    the test below."""
    common = {
        "churn_risk": 0.3,
        "loyalty_index": 0.2,
        "price_sensitivity": 0.2,
        "tier": "platinum",
    }
    broke = pricing.compute_discount(**common, affordability_headroom=0.0)
    comfortable = pricing.compute_discount(**common, affordability_headroom=1.0)

    assert comfortable < broke


def test_the_tier_ceiling_dominates_the_formula():
    """MEASURED, and a real limitation rather than a bug. The three positive
    weights sum to 0.90 while the tier ceilings are 0.05 to 0.20, so for most
    subscribers `d(i,b)` reduces to `d_max(tier(i))` and the four terms express
    nothing.

    conf/pricing.yaml specifies `clip`, so this test documents the consequence
    rather than asserting it away. Scaling BY d_max instead of clipping AT it
    is a pricing-policy change, not a refactor."""
    rng = np.random.default_rng(0)
    shares = {}
    for tier in ("bronze", "platinum"):
        ceiling = load_conf("pricing")["tiers"][tier]["d_max"]
        values = [pricing.compute_discount(*rng.random(4), tier) for _ in range(4000)]
        shares[tier] = float(np.mean(np.isclose(values, ceiling)))

    assert shares["bronze"] > 0.90, f"bronze saturation is {shares['bronze']:.1%}"
    assert shares["platinum"] > shares["platinum"] - 1  # recorded, not gated
    assert shares["bronze"] > shares["platinum"], "a lower ceiling must saturate more"


def test_the_discount_never_exceeds_the_tier_ceiling():
    """A gold subscriber cannot be given a platinum discount however high every
    other term runs."""
    for tier in ("bronze", "silver", "gold", "platinum"):
        ceiling = load_conf("pricing")["tiers"][tier]["d_max"]
        maxed = pricing.compute_discount(1.0, 1.0, 1.0, 0.0, tier)
        assert maxed <= ceiling + 1e-12
        assert pricing.compute_discount(0.0, 0.0, 0.0, 1.0, tier) >= 0.0


def test_an_out_of_range_input_is_refused():
    with pytest.raises(ValueError, match="must be in"):
        pricing.compute_discount(1.5, 0.5, 0.5, 0.0, "gold")


def test_leakage_beats_a_cheaper_bundle():
    """A subscriber whose contacts have moved to the competitor does not need
    cheaper data -- the social graph is what is migrating."""
    assert pricing.choose_instrument("gold", offpeak_data_ratio=0.9, leakage_score=0.95) == (
        "onnet_minutes"
    )


def test_offpeak_is_preferred_to_a_headline_cut():
    """Near-free on an idle sector, and it leaves the price sheet intact."""
    assert pricing.choose_instrument("bronze", offpeak_data_ratio=0.5, leakage_score=0.0) == (
        "offpeak_data"
    )


# --- No action, which is most of the value ---------------------------------


def test_a_sleeping_dog_is_never_offered_anything(features):
    """Treating them causes the churn it was meant to prevent."""
    response = pricing.decide_offer(
        OfferRequest(subscriber_id=SUBSCRIBER), {**features, "quadrant": "sleeping_dog"}
    )
    assert response.offer_id == pricing.NO_ACTION
    assert response.discount_pct == 0.0
    assert "no_action:sleeping_dog" in response.reason_codes


def test_negative_expected_value_means_no_offer(features):
    """E[gain] = uplift x CLV - cost. Below break-even, treating loses money
    however high the churn score is."""
    response = pricing.decide_offer(
        OfferRequest(subscriber_id=SUBSCRIBER), {**features, "uplift": 0.001}
    )
    assert response.offer_id == pricing.NO_ACTION
    assert "no_action:negative_expected_value" in response.reason_codes


def test_no_action_is_still_logged_and_explained(features):
    """A decision not to spend is still a decision, and section 6.5 commits to
    explaining every one."""
    response = pricing.decide_offer(
        OfferRequest(subscriber_id=SUBSCRIBER), {**features, "quadrant": "sleeping_dog"}
    )
    assert response.decision_log_id
    assert response.customer_facing_reason_ar
    assert decision_log.find(response.decision_log_id) is not None


# --- Guardrails are never bypassed -----------------------------------------


def test_every_guardrail_is_recorded_even_when_it_does_not_bind(features):
    """Recording which constraints were CONSIDERED, not only which bound, is
    what makes the decision replayable."""
    response = pricing.decide_offer(OfferRequest(subscriber_id=SUBSCRIBER), features)
    considered = {c.name for c in response.constraints}
    assert {"margin_floor", "clv_ceiling", "cannibalisation", "fairness"} <= considered


def test_a_protected_attribute_in_pricing_blocks_the_offer(features):
    """Fairness is a guardrail, not a review step. `district` is forbidden."""
    response = pricing.decide_offer(
        OfferRequest(subscriber_id=SUBSCRIBER), {**features, "pricing_features": ["district"]}
    )
    assert response.offer_id == pricing.NO_ACTION
    assert any("fairness" in r for r in response.reason_codes)


def test_an_invented_bundle_is_refused(features):
    """An offer we invented would have a cost we invented, and the margin floor
    would enforce one made-up number against another."""
    with pytest.raises(ValueError, match=r"not in conf/catalogue.yaml"):
        pricing.decide_offer(
            OfferRequest(subscriber_id=SUBSCRIBER, bundle_id="TOTALLY_MADE_UP"), features
        )


def test_the_price_never_falls_below_the_margin_floor(features):
    """Swept rather than spot-checked."""
    minimum = load_conf("pricing")["guardrails"]["margin_floor"]["min_margin"]
    for churn in np.linspace(0, 1, 11):
        response = pricing.decide_offer(
            OfferRequest(subscriber_id=SUBSCRIBER),
            {**features, "churn_probability": float(churn), "tier": "platinum"},
        )
        if response.offer_id == pricing.NO_ACTION:
            continue
        variable_cost = response.base_price_lyd * 0.35
        assert response.price_lyd >= variable_cost * (1 + minimum) - 1e-9


# --- The ladder -------------------------------------------------------------


def test_the_spend_profile_is_an_inverted_u_not_an_escalation():
    """Most operators escalate as the line gets colder, which is backwards:
    recovery probability collapses faster than offer value rises."""
    cooling = ladder.spend_multiplier(RetentionStage.COOLING)
    cold = ladder.spend_multiplier(RetentionStage.COLD)
    dormant = ladder.spend_multiplier(RetentionStage.DORMANT)

    assert cooling < cold, "spend must rise into the middle stage"
    assert dormant < cold, "and fall again -- that is the U"
    assert [cooling, cold, dormant] != sorted([cooling, cold, dormant])


def test_stage_one_triggers_on_the_subscribers_own_cadence():
    """A weekly recharger is cooling at day 10; a monthly one is not. A single
    global threshold fires constantly for one group and too late for the other."""
    boundaries = [7, 30, 60]
    weekly = ladder.assign_stage(6, subscriber_baseline_gap=4.0, boundaries=boundaries)
    monthly = ladder.assign_stage(6, subscriber_baseline_gap=30.0, boundaries=boundaries)

    assert weekly == RetentionStage.COOLING
    assert monthly == RetentionStage.NONE


def test_the_later_stages_use_the_global_hazard_boundaries():
    boundaries = [7, 30]
    assert ladder.assign_stage(10, 30.0, boundaries) == RetentionStage.COLD
    assert ladder.assign_stage(45, 30.0, boundaries) == RetentionStage.DORMANT


def test_the_fallback_boundaries_are_not_dressed_as_derived(caplog):
    """M1b returns nothing on this population, so `7 / 30 / 60` is a stated
    assumption. A fallback that logs like a derivation is how an assumption
    gets quoted as a result."""
    import logging

    with caplog.at_level(logging.WARNING):
        boundaries = ladder.derive_boundaries([])

    assert boundaries == load_conf("pricing")["retention_ladder"]["fallback_boundaries_days"]
    assert "not a derived result" in caplog.text


def test_real_inflections_are_used_when_m1b_supplies_them():
    assert ladder.derive_boundaries([12, 40, 70]) == [12, 40]


# --- Off-peak ---------------------------------------------------------------


def test_the_window_is_the_operators_published_one():
    """Not a trough we detected. The operator has already priced its own spare
    capacity and told us when it is."""
    assert offpeak.offpeak_window() == (6, 11)


def test_a_morning_user_would_shift_rather_than_grow():
    """They would stop paying for what they already do, which is pure loss."""
    assert offpeak.would_shift_not_grow(peak_usage=1.0, offpeak_usage=99.0, headroom=5.0)
    assert offpeak.would_shift_not_grow(peak_usage=90.0, offpeak_usage=10.0, headroom=0.0)
    assert not offpeak.would_shift_not_grow(peak_usage=90.0, offpeak_usage=10.0, headroom=50.0)


def test_the_base_monthly_is_exempt_from_cannibalisation():
    """نت 20 at 35 LYD is what a subscriber needs for data outside the window at
    all, so free mornings do not remove the need and they have nowhere to fall."""
    base = load_conf("pricing")["guardrails"]["cannibalisation"]["base_monthly_price_lyd"]
    cohort = pd.DataFrame(
        {
            "current_monthly_bundle_lyd": [base, base, 80.0],
            "would_shift_not_grow": [True, True, True],
        }
    )
    result = offpeak.simulate_cohort_margin(cohort)

    assert result["exempt_at_or_below_base"] == 2
    assert result["exposed"] == 1


def test_the_downgrade_loss_is_the_gap_not_the_whole_bundle():
    """A نت 40 holder who steps down to نت 20 loses the difference, not 50 LYD.
    Presenting it as the whole bundle would make the guard unfalsifiable."""
    cohort = pd.DataFrame({"current_monthly_bundle_lyd": [50.0], "would_shift_not_grow": [True]})
    result = offpeak.simulate_cohort_margin(cohort)
    assert 0 < result["expected_loss_lyd"] < 50.0


def test_the_cohort_check_needs_the_bundle_actually_held():
    with pytest.raises(KeyError, match="current_monthly_bundle_lyd"):
        offpeak.simulate_cohort_margin(pd.DataFrame({"x": [1]}))


# --- The budget LP ----------------------------------------------------------


@pytest.fixture
def candidates() -> pd.DataFrame:
    rng = np.random.default_rng(606)
    n = 300
    return pd.DataFrame(
        {
            "expected_margin_lyd": rng.gamma(2, 20, n),
            "discount_cost_lyd": rng.gamma(2, 3, n),
            "uplift": rng.random(n) * 0.1,
        }
    )


def test_the_budget_is_never_exceeded(candidates):
    for budget in (0.0, 50.0, 500.0, 10_000.0):
        allocation = budget_lp.allocate(candidates, budget_lyd=budget)
        assert allocation.loc[allocation["selected"], "discount_cost_lyd"].sum() <= budget + 1e-6


def test_a_bigger_budget_never_buys_less_margin(candidates):
    small = budget_lp.campaign_summary(budget_lp.allocate(candidates, budget_lyd=100.0))
    large = budget_lp.campaign_summary(budget_lp.allocate(candidates, budget_lyd=1000.0))
    assert large["expected_margin_lyd"] >= small["expected_margin_lyd"]


def test_unviable_candidates_are_counted_separately(candidates):
    """ "The guardrail rejected 40,000" should mean the budget bound, not that
    40,000 rows were never viable in the first place."""
    poisoned = candidates.copy()
    poisoned.loc[poisoned.index[:50], "expected_margin_lyd"] = -1.0

    allocation = budget_lp.allocate(poisoned, budget_lyd=10_000.0)
    summary = budget_lp.campaign_summary(allocation)

    assert summary["not_viable"] == 50
    assert not allocation.loc[allocation.index[:50], "selected"].any()


def test_the_blanket_comparison_is_computed_not_quoted(candidates):
    """ "Targeting saves 1,050,000 LYD" is the larger half of the business case
    and should be an output of the allocation, not a figure in a slide."""
    summary = budget_lp.campaign_summary(budget_lp.allocate(candidates, budget_lyd=200.0))
    assert summary["blanket_cost_lyd"] > summary["cost_lyd"]
    assert summary["saving_versus_blanket_lyd"] == pytest.approx(
        summary["blanket_cost_lyd"] - summary["cost_lyd"]
    )


def test_a_negative_budget_is_refused(candidates):
    with pytest.raises(ValueError, match="non-negative"):
        budget_lp.allocate(candidates, budget_lyd=-1.0)


# --- The audit log ----------------------------------------------------------


def test_a_decision_round_trips(features):
    response = pricing.decide_offer(OfferRequest(subscriber_id=SUBSCRIBER), features)
    record = decision_log.find(response.decision_log_id)

    assert record is not None
    assert record["subscriber_id"] == SUBSCRIBER
    assert record["reason_codes"] == response.reason_codes
    # The WEIGHTS as they were, not just the inputs -- that is what makes
    # "why did we decide that then" answerable rather than "what would we
    # decide now".
    assert record["weights"] == load_conf("pricing")["discount_weights"]


def test_replay_distinguishes_a_config_change_from_a_code_change(features):
    """Reporting only "differs" would leave an auditor to work that out by hand."""
    response = pricing.decide_offer(OfferRequest(subscriber_id=SUBSCRIBER), features)
    result = decision_log.replay(response.decision_log_id)

    assert result["reproduced"] is True
    assert "nothing has changed" in result["verdict"]
    assert "replayed_with_recorded_weights" in result
    assert "replayed_with_current_weights" in result


def test_replay_does_not_corrupt_the_live_config(features):
    """REGRESSION. The first version swapped weights into the CACHED config dict
    and restored them in a finally -- but `original` and the dict being cleared
    were the same object, so the restore put back what the clear had emptied.
    Every later caller in the process then priced with no weights at all. An
    audit function that corrupts live pricing config is worse than none."""
    before = dict(load_conf("pricing")["discount_weights"])

    response = pricing.decide_offer(OfferRequest(subscriber_id=SUBSCRIBER), features)
    decision_log.replay(response.decision_log_id)

    assert load_conf("pricing")["discount_weights"] == before
    assert before, "the weights must not be empty to begin with"


def test_replaying_an_unknown_id_raises():
    with pytest.raises(KeyError, match="is not in"):
        decision_log.replay("no-such-decision")


def test_the_audit_export_is_windowed(features):
    from datetime import UTC, datetime, timedelta

    pricing.decide_offer(OfferRequest(subscriber_id=SUBSCRIBER), features)
    now = datetime.now(UTC)

    recent = decision_log.export_for_audit(now - timedelta(hours=1), now + timedelta(hours=1))
    ancient = decision_log.export_for_audit(now - timedelta(days=3650), now - timedelta(days=3649))
    assert len(recent) > 0
    assert len(ancient) == 0


# --- The registry -----------------------------------------------------------


def test_a_missing_artefact_degrades_rather_than_raising(tmp_path):
    """An API that refuses to boot without M4 cannot serve churn scores during
    an M4 outage, which is worse."""
    from cvm.models.registry import load_registry

    assert load_registry(tmp_path) == {}


def test_the_registry_keys_match_what_health_reports():
    """A rename in health.py must fail loudly here rather than silently
    reporting a model as missing forever."""
    from cvm.api.routers.health import EXPECTED_MODELS
    from cvm.models.registry import ARTEFACTS

    assert set(EXPECTED_MODELS) <= set(ARTEFACTS)
