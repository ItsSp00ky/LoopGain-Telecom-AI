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
    40,000 rows were never viable in the first place.

    Viability is NET: a candidate returning 3 LYD for a 5 LYD offer is not
    viable, and `margin > 0` used to wave them through. The count is therefore
    the 50 poisoned rows PLUS however many random ones fail to clear their own
    cost -- derived from the fixture rather than pinned to whatever number its
    seed happens to produce.
    """
    poisoned = candidates.copy()
    poisoned.loc[poisoned.index[:50], "expected_margin_lyd"] = -1.0

    allocation = budget_lp.allocate(poisoned, budget_lyd=10_000.0)
    summary = budget_lp.campaign_summary(allocation)

    assert not allocation.loc[allocation.index[:50], "viable"].any()
    assert not allocation.loc[allocation.index[:50], "selected"].any()

    below_cost = poisoned["expected_margin_lyd"] <= poisoned["discount_cost_lyd"]
    assert summary["not_viable"] == int(below_cost.sum())
    assert summary["not_viable"] >= 50

    # The budget is generous enough that nothing else was declined, which is
    # the distinction the count exists to preserve.
    assert summary["selected"] == len(candidates) - summary["not_viable"]


def test_a_candidate_who_cannot_repay_their_own_offer_is_not_viable():
    """3 LYD of retained value against a 5 LYD offer destroys 2 LYD."""
    frame = pd.DataFrame(
        {
            "expected_margin_lyd": [3.0, 5.0, 7.0],
            "discount_cost_lyd": [5.0, 5.0, 5.0],
        }
    )
    allocation = budget_lp.allocate(frame, budget_lyd=1_000.0)

    assert list(allocation["viable"]) == [False, False, True]
    assert list(allocation["selected"]) == [False, False, True]


def test_the_blanket_comparison_is_computed_not_quoted(candidates):
    """ "Targeting saves 1,050,000 LYD" is the larger half of the business case
    and should be an output of the allocation, not a figure in a slide."""
    summary = budget_lp.campaign_summary(budget_lp.allocate(candidates, budget_lyd=200.0))
    assert summary["blanket_cost_lyd"] > summary["cost_lyd"]
    assert summary["saving_versus_blanket_lyd"] == pytest.approx(
        summary["blanket_cost_lyd"] - summary["cost_lyd"]
    )


def test_the_blanket_baseline_is_the_cohort_not_what_survived_the_guardrails(candidates):
    """The bug this comparison had: it measured targeting against itself.

    The Campaign Builder removes sleeping dogs, negative expected value and
    sub-ceiling CLV BEFORE calling allocate. With the baseline taken from the
    allocation frame, "blanket" meant "everyone the guardrails already
    approved" -- so whenever the budget did not bind the two populations were
    identical and the screen reported a saving of 0 LYD, directly beneath a
    chart saying 227 of 497 had been removed.
    """
    cohort = candidates.copy()
    # Pre-filtered to the viable, which is precisely what the screen did before
    # calling allocate -- and precisely why the naive baseline collapsed onto
    # the campaign itself.
    viable = candidates["expected_margin_lyd"] > candidates["discount_cost_lyd"]
    survivors = candidates[viable].head(100)

    allocation = budget_lp.allocate(survivors, budget_lyd=100_000.0)

    naive = budget_lp.campaign_summary(allocation)
    honest = budget_lp.campaign_summary(allocation, cohort=cohort)

    # Everything affordable, so the naive baseline IS the campaign.
    assert naive["saving_versus_blanket_lyd"] == pytest.approx(0.0)
    assert naive["blanket_baseline"] == "allocation"

    # Against the real cohort it is the other subscribers' worth of offers.
    assert honest["blanket_baseline"] == "cohort"
    assert honest["blanket_candidates"] == len(cohort)
    assert honest["saving_versus_blanket_lyd"] > 0


def test_the_saving_splits_into_guardrails_and_budget(candidates):
    """One number cannot say which mechanism declined whom, and the two are not
    interchangeable: a guardrail rejection is a decision, a budget rejection is
    a shortage."""
    cohort = candidates.copy()
    survivors = candidates.head(100)

    generous = budget_lp.campaign_summary(
        budget_lp.allocate(survivors, budget_lyd=100_000.0), cohort=cohort
    )
    assert generous["saving_from_budget_lyd"] == pytest.approx(0.0)
    assert generous["saving_from_guardrails_lyd"] == pytest.approx(
        generous["saving_versus_blanket_lyd"]
    )

    tight = budget_lp.campaign_summary(
        budget_lp.allocate(survivors, budget_lyd=50.0), cohort=cohort
    )
    assert tight["saving_from_budget_lyd"] > 0

    for summary in (generous, tight):
        total = summary["saving_from_guardrails_lyd"] + summary["saving_from_budget_lyd"]
        assert total == pytest.approx(summary["saving_versus_blanket_lyd"])


def test_the_headline_counts_damage_avoided_and_not_only_money_saved(candidates):
    """Targeting buys two things and the cost saving shows only one.

    What makes skipping a sleeping dog worth something is the expected value
    NOT destroyed. A discount-saved figure cannot see that at all.
    """
    cohort = candidates.copy()
    # Part of the cohort reacts badly: treating them is actively destructive.
    cohort.loc[cohort.index[:150], "expected_margin_lyd"] = -40.0
    survivors = cohort[cohort["expected_margin_lyd"] > cohort["discount_cost_lyd"]]

    summary = budget_lp.campaign_summary(
        budget_lp.allocate(survivors, budget_lyd=100_000.0), cohort=cohort
    )

    assert summary["blanket_net_margin_lyd"] < summary["net_margin_lyd"]
    assert summary["net_margin_versus_blanket_lyd"] == pytest.approx(
        summary["net_margin_lyd"] - summary["blanket_net_margin_lyd"]
    )
    # Strictly the larger claim, because it adds damage avoided to money saved.
    assert summary["net_margin_versus_blanket_lyd"] > summary["saving_versus_blanket_lyd"]


def test_the_margin_column_is_gross_and_the_cost_comes_off_once():
    """The Campaign Builder passed M3's expected_value_lyd, which is already
    `uplift x CLV - cost`, so the campaign was charged twice and net margin was
    understated by exactly the campaign cost -- 1,220 LYD on the default
    cohort."""
    frame = pd.DataFrame({"expected_margin_lyd": [100.0, 80.0], "discount_cost_lyd": [5.0, 5.0]})
    summary = budget_lp.campaign_summary(budget_lp.allocate(frame, budget_lyd=1_000.0))

    assert summary["cost_lyd"] == pytest.approx(10.0)
    assert summary["expected_margin_lyd"] == pytest.approx(180.0)
    assert summary["net_margin_lyd"] == pytest.approx(170.0)


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


def test_the_same_budget_comparison_holds_spend_constant(candidates):
    """Comparing a budgeted campaign against an unconstrained one measures the
    budget, not the targeting.

    The unconstrained figure went to -2,075 LYD on the phase-8 fixture, which
    reads as "targeting lost money" and means "targeting was given 1,000 LYD
    and blanket was given 2,400". Holding spend constant isolates the part that
    is actually about targeting, and that part should never be negative: the
    LP picks the best net margin per LYD available, so it cannot do worse than
    the cohort average on the same money.
    """
    cohort = candidates.copy()
    viable = candidates["expected_margin_lyd"] > candidates["discount_cost_lyd"]
    survivors = candidates[viable]

    tight = budget_lp.campaign_summary(
        budget_lp.allocate(survivors, budget_lyd=50.0), cohort=cohort
    )

    # The budget binds hard, so the unconstrained comparison is unflattering...
    assert tight["net_margin_versus_blanket_lyd"] < 0
    # ...and the fair one is not.
    assert tight["net_margin_versus_same_budget_lyd"] > 0

    # The untargeted arm spends the same money, give or take one indivisible
    # subscriber.
    mean_cost = float(cohort["discount_cost_lyd"].mean())
    assert abs(tight["blanket_same_budget_treated"] * mean_cost - tight["cost_lyd"]) <= mean_cost


def test_targeting_cannot_lose_to_the_cohort_average_on_equal_money(candidates):
    """Swept, because a single budget can hide a sign error."""
    cohort = candidates.copy()
    viable = candidates["expected_margin_lyd"] > candidates["discount_cost_lyd"]
    survivors = candidates[viable]

    for budget in (50.0, 200.0, 1_000.0, 100_000.0):
        summary = budget_lp.campaign_summary(
            budget_lp.allocate(survivors, budget_lyd=budget), cohort=cohort
        )
        assert (
            summary["net_margin_versus_same_budget_lyd"] >= -1e-6
        ), f"at a {budget} LYD budget, targeting did worse than the cohort average"
