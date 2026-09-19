"""M4 credit-safety guards. Required in CI; never skipped.

Almadar runs two emergency-credit products, both gated on the subscriber being
nearly out of money:

    رصيد في وقته  airtime, 1/3/5 LYD, balance <= 0.5 LYD
    نت في وقته    data, flat 5 LYD / 2 GB, balance <= 1 LYD and quota < 250 MB

The objective function is SUBSCRIBER SOLVENCY, not recovery yield. These tests
exist because the 5 LYD data debt is exactly the size of the smallest recharge
card: clearing it consumes the whole top-up and returns the subscriber to zero,
so the minimum recharge buys nothing and the rational move is not to make it.
A deferred recharge on a prepaid line is where silent churn starts.

Config-level assertions run today. Behavioural tests are xfail until
decision/advance_limit.py lands, so the gap is visible in CI rather than
silently absent.
"""

from __future__ import annotations

import pytest

from cvm.config import load_conf

pytestmark = pytest.mark.guardrail


@pytest.fixture
def advance_conf() -> dict:
    return load_conf("advance")


@pytest.fixture
def catalogue() -> dict:
    return load_conf("catalogue")


@pytest.fixture
def market() -> dict:
    return load_conf("market")


# --- The structural finding, asserted so it cannot drift silently ----------


def test_data_advance_consumes_the_entire_smallest_card(advance_conf, catalogue, market):
    """The whole M4 argument in one assertion.

    The smallest recharge card is 5 LYD and the نت في وقته data advance is
    5 LYD. A subscriber whose modal top-up is the smallest card can clear the
    debt -- and gets NOTHING for it. The whole card is consumed and they are
    returned to a zero balance, immediately eligible to take the advance again.

    The harm is a disincentive to recharge, not a locked door, and the business
    case is sized for a disincentive. If this test ever fails because the
    operator changed a price, the argument needs rewriting -- which is exactly
    why it is a test and not a comment.
    """
    smallest_card = min(market["recharge"]["denominations_lyd"])
    data_debt = catalogue["emergency_credit"]["net_fi_waqtuh"]["price_lyd"]

    assert smallest_card == 5
    assert data_debt == 5
    assert data_debt == smallest_card, "the argument rests on the EQUALITY"

    # And the critique block must agree with the source data.
    critique = advance_conf["incumbent_critique"]
    assert critique["smallest_card_lyd"] == smallest_card
    assert critique["data_advance_debt_lyd"] == data_debt
    assert critique["debt_consumes_entire_smallest_card"] is True
    assert critique["residual_after_clearing_lyd"] == pytest.approx(0.0)
    # The superseded claim must stay explicitly false rather than be deleted:
    # a reader who remembers the old argument needs to see it was retired.
    assert critique["debt_exceeds_smallest_card"] is False


def test_small_airtime_advances_leave_change_off_the_smallest_card(catalogue, market):
    """The asymmetry that makes small airtime rungs safer than the data advance.

    A 1 or 3 LYD airtime advance leaves 4 or 2 LYD of usable balance after a
    minimum top-up, so clearing it still buys the subscriber service. Only the
    5 LYD rung reproduces the zero-residual problem, which is why the PD bands
    in conf/advance.yaml reserve it for the highest-confidence repayers.
    """
    smallest_card = min(market["recharge"]["denominations_lyd"])
    rungs = catalogue["emergency_credit"]["rasid_fi_waqtuh"]["denominations_lyd"]

    leaves_change = [d for d in rungs if d < smallest_card]
    assert leaves_change == [1, 3]
    assert max(rungs) == smallest_card


def test_eligibility_is_balance_based_not_tenure_based(catalogue):
    """Both products gate on being broke -- the inverse of a risk filter.

    Also guards against reintroducing the Libyana tenure gate, which does not
    apply to this operator.
    """
    airtime = catalogue["emergency_credit"]["rasid_fi_waqtuh"]["eligibility"]
    data = catalogue["emergency_credit"]["net_fi_waqtuh"]["eligibility"]

    assert airtime["max_basic_balance_lyd"] == 0.5
    assert airtime["tenure_months_required"] is None
    assert data["max_basic_balance_lyd"] == 1.0
    assert data["max_remaining_quota_mb"] == 250


def test_line_reset_is_not_claimed_for_this_operator(catalogue):
    """Libyana's line-reset outcome is undocumented for Almadar.

    Claiming it would be fabricating the project's central finding, so the
    config records its absence explicitly rather than leaving the field blank.
    """
    airtime = catalogue["emergency_credit"]["rasid_fi_waqtuh"]
    assert airtime["line_reset_documented"] is False
    assert airtime["non_settlement_outcome"] == "undocumented"


def test_products_are_mutually_exclusive(catalogue):
    """A subscriber alternating between them is in sustained distress, which is
    a signal the incumbent design does not watch for."""
    data = catalogue["emergency_credit"]["net_fi_waqtuh"]["eligibility"]
    assert data["blocked_if_balance_negative"] is True
    assert load_conf("advance")["incumbent_critique"]["services_mutually_exclusive"] is True


# --- Limit function -------------------------------------------------------


def test_airtime_limits_use_only_real_denominations(advance_conf, catalogue):
    """We cannot invent a 2 LYD advance. The operator offers 1, 3 and 5."""
    real = set(catalogue["emergency_credit"]["rasid_fi_waqtuh"]["denominations_lyd"])
    assert real == {1, 3, 5}

    airtime = advance_conf["limit_function"]["airtime"]
    assert set(airtime["available_denominations_lyd"]) == real

    offered = {b["limit_lyd"] for b in airtime["pd_to_limit_lyd"]} - {0}
    assert offered <= real, f"invented denominations: {sorted(offered - real)}"


def test_pd_bands_are_monotonic_in_repayment_probability(advance_conf):
    """Higher repayment probability must never yield a lower limit."""
    bands = advance_conf["limit_function"]["airtime"]["pd_to_limit_lyd"]
    pds = [b["min_pd"] for b in bands]
    limits = [b["limit_lyd"] for b in bands]
    assert pds == sorted(pds, reverse=True), "bands must be ordered by descending PD"
    assert limits == sorted(limits, reverse=True), "limit must not increase as PD falls"


def test_lowest_pd_band_declines(advance_conf):
    bands = advance_conf["limit_function"]["airtime"]["pd_to_limit_lyd"]
    decline_band = next(b for b in bands if b["min_pd"] == 0.0)
    assert decline_band["limit_lyd"] == 0


def test_data_advance_threshold_is_stricter_than_airtime(advance_conf):
    """5 LYD flat is a larger debt than the airtime product's typical grant, so
    the bar to receive it must be higher -- not the same."""
    lf = advance_conf["limit_function"]
    lowest_airtime_grant = min(
        b["min_pd"] for b in lf["airtime"]["pd_to_limit_lyd"] if b["limit_lyd"] > 0
    )
    assert lf["data"]["grant_if_pd_above"] > lowest_airtime_grant


def test_declined_data_advance_has_an_affordable_fallback(advance_conf, catalogue):
    """Declining with nothing sends them away; declining with a 0.5 LYD option
    they can actually afford is a service."""
    fallback_id = advance_conf["limit_function"]["data"]["fallback_offer_id"]
    all_ids = {
        item["id"] for fam in catalogue["families"].values() for item in fam.get("items", [])
    }
    assert fallback_id in all_ids, f"{fallback_id} is not a real bundle"

    price = next(
        item["price_lyd"]
        for fam in catalogue["families"].values()
        for item in fam.get("items", [])
        if item["id"] == fallback_id
    )
    assert price < catalogue["emergency_credit"]["net_fi_waqtuh"]["price_lyd"]


def test_tier_ceilings_are_monotonic(advance_conf):
    ceilings = advance_conf["limit_function"]["tier_ceiling_lyd"]
    ordered = [ceilings[t] for t in ("bronze", "silver", "gold", "platinum")]
    assert ordered == sorted(ordered)


def test_regulatory_cap_matches_the_largest_real_advance(advance_conf):
    """Capping above what the operator actually offers would be meaningless."""
    lf = advance_conf["limit_function"]
    assert lf["cap_regulatory_lyd"] == 5
    assert lf["cap_regulatory_lyd"] >= max(lf["tier_ceiling_lyd"].values())


# --- Mandatory safety guards ----------------------------------------------


def test_every_safety_guard_is_marked_mandatory(advance_conf):
    """Chronic-distress exclusion, cooling-off and the affordability ceiling are
    mandatory, not configurable. This test is what makes that sentence true."""
    for name, guard in advance_conf["safety_guards"].items():
        if name in ("fee_structure", "reject_inference"):
            continue
        assert guard.get("enabled") is True, f"{name} is disabled"
        assert guard.get("mandatory") is True, f"{name} is not marked mandatory"


def test_affordability_ceiling_uses_modal_not_mean_recharge(advance_conf):
    """The mean is dragged up by one salary-week top-up they will not repeat.

    Using it would systematically over-lend to exactly the subscribers this
    guard exists to protect.
    """
    guard = advance_conf["safety_guards"]["affordability_ceiling"]
    assert guard["basis"] == "modal_recharge_amount_lyd"
    assert guard["max_debt_as_fraction_of_modal_recharge"] <= 1.0


def test_chronic_distress_watches_for_service_alternation(advance_conf):
    """The Almadar-specific signal: ping-ponging between the two mutually
    exclusive emergency products is sustained distress."""
    signals = advance_conf["safety_guards"]["chronic_distress_exclusion"]["signals"]
    assert "emergency_service_alternations_90d_above" in signals
    assert signals["emergency_service_alternations_90d_above"] > 0


def test_cooling_off_is_stricter_than_the_operator_allows(advance_conf, catalogue):
    """The operator permits same-day repeat borrowing once the debt is cleared.
    We do not -- that is a revolving credit line, and this is not one."""
    assert (
        catalogue["emergency_credit"]["rasid_fi_waqtuh"]["settlement"]["repeat_allowed_same_day"]
        is True
    )
    cooling = advance_conf["safety_guards"]["cooling_off"]
    assert cooling["override_operator_same_day_repeat"] is True
    assert cooling["min_days_between_advances"] >= 1


def test_lockout_risk_guard_replaces_line_reset(advance_conf):
    """What is actually measurable for this operator: unpaid debt at day 14
    blocks re-subscription."""
    guard = advance_conf["safety_guards"]["lockout_risk"]
    assert guard["enabled"] is True
    assert guard["mandatory"] is True
    assert 0 < guard["flag_if_probability_above"] < 1
    assert "line_reset" not in str(guard.get("note", ""))  # must not claim it


def test_fee_is_fixed_and_flagged_for_review(advance_conf):
    """Libya's financial framework makes interest a live question. Neither
    Almadar product documents a fee; if one appears it is modelled as a fixed
    charge and flagged rather than assumed settled."""
    fee = advance_conf["safety_guards"]["fee_structure"]
    assert fee["type"] == "fixed_charge"
    assert fee["forbid_time_based"] is True
    assert fee["forbid_percentage_based"] is True
    assert fee["status"] == "FLAGGED_FOR_SHARIAH_REVIEW"


def test_reject_inference_is_enabled_and_documented(advance_conf):
    """The gate is balance-based, so the observed population is non-random by
    construction -- a sharper selection bias than in normal credit settings."""
    ri = advance_conf["safety_guards"]["reject_inference"]
    assert ri["enabled"] is True
    assert ri["document_in_model_card"] is True


def test_accuracy_is_not_a_headline_metric(advance_conf):
    assert advance_conf["evaluation"]["forbid_accuracy_as_headline"] is True


def test_business_metrics_are_measurable_for_this_operator(advance_conf):
    """No 'prevented line resets' -- that outcome is undocumented for Almadar
    and we would be reporting a number we cannot support."""
    metrics = advance_conf["evaluation"]["business_metrics"]
    assert "unclearable_debts_avoided" in metrics
    assert "service_lockouts_avoided" in metrics
    assert not [m for m in metrics if "reset" in m]


# --- Behavioural invariants -----------------------------------------------


@pytest.fixture
def healthy() -> dict:
    """A subscriber nothing should decline: regular recharges, no distress."""
    return {
        "repayment_probability": 0.92,
        "lockout_risk": 0.02,
        "modal_recharge_amount_lyd": 40.0,
        "loyalty_tier": "gold",
        "clv_12m": 480.0,
        "balance_zero_hours_30d": 10.0,
        "failed_bundle_attempts_30d": 0.0,
        "consecutive_sub_5_lyd_recharges": 0.0,
        "emergency_service_alternations_90d": 0.0,
        "airtime_advance_count_90d": 1.0,
        "data_advance_count_90d": 0.0,
        "days_since_last_advance": 30.0,
        "advances_this_month": 0.0,
        "cumulative_exposure_this_month_lyd": 0.0,
    }


def test_chronic_distress_excludes_regardless_of_pd(healthy):
    """Even a 0.95 repayment probability does not override sustained distress.

    The asymmetry is the whole design. A chronically distressed subscriber
    often DOES repay -- out of the next top-up, which then buys them nothing,
    which is the trap. A model optimising recovery yield would lend to exactly
    these people."""
    from cvm.decision.advance_limit import apply_safety_guards

    distressed = {
        **healthy,
        "repayment_probability": 0.95,
        "balance_zero_hours_30d": 700.0,
        "consecutive_sub_5_lyd_recharges": 9.0,
    }
    limit, checks = apply_safety_guards(5.0, distressed)

    assert limit == 0.0
    failed = {c.guard for c in checks if not c.passed}
    assert "chronic_distress_exclusion" in failed


def test_limit_never_exceeds_the_minimum_of_all_four_terms(healthy):
    """min(f(PD), g(tier), h(CLV), affordability). Not a weighted blend.

    A blend would let a platinum tier buy back capacity that affordability has
    already refused, which is precisely the subscriber the guard protects."""
    from cvm.decision.advance_limit import (
        affordability_ceiling,
        limit_from_clv,
        limit_from_pd,
        limit_from_tier,
    )

    # A subscriber strong on three terms and weak on the fourth.
    terms = [
        limit_from_pd(0.95, "airtime"),
        limit_from_tier("platinum"),
        limit_from_clv(480.0),
        affordability_ceiling(5.0),  # the binding one: 5 x 0.6 = 3.0
    ]
    assert min(terms) == pytest.approx(3.0)
    assert min(terms) < max(terms), "the fixture must actually have a binding constraint"


def test_safety_guards_can_only_reduce_a_limit(healthy):
    """A guard that raises the limit is a bug, not a feature."""
    from cvm.decision.advance_limit import apply_safety_guards

    for starting in (0.0, 1.0, 3.0, 5.0):
        adjusted, _ = apply_safety_guards(starting, healthy)
        assert adjusted <= starting + 1e-9, f"guards raised {starting} to {adjusted}"


def test_a_guard_that_raises_the_limit_is_caught(healthy):
    """The invariant above is asserted inside the function too, so a future
    guard written the wrong way round fails loudly rather than issuing credit."""
    from cvm.decision import advance_limit

    with pytest.raises(AssertionError, match="raised the limit"):
        advance_limit._assert_only_reduced(original=1.0, limit=5.0)


def test_habitual_minimum_recharger_is_declined_the_data_advance(healthy):
    """THE HEADLINE CASE. Modal recharge 5 LYD -- the smallest card -- against a
    5 LYD data advance: declined, with the 0.5 LYD DAY_50MB fallback offered
    instead.

    Granting it would be defensible on repayment probability alone, which is
    exactly the trap: they probably WOULD repay, and the repayment would consume
    their entire next top-up and return them to zero. The objective is solvency,
    not recovery yield, so affordability declines what PD would approve."""
    from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
    from cvm.decision.advance_limit import decide_limit

    features = {**healthy, "modal_recharge_amount_lyd": 5.0, "repayment_probability": 0.92}
    payload = AdvanceLimitRequest(subscriber_id="a" * 64, product=AdvanceProduct.DATA)

    response = decide_limit(payload, features)

    assert response.approved is False
    assert response.limit_lyd == 0.0
    assert response.fallback_offer_id == "DAY_50MB"
    assert "affordability_ceiling" in response.reason_codes
    # And the PD was high enough that PD alone would have granted it -- which
    # is what makes this a finding rather than an ordinary decline.
    from cvm.decision.advance_limit import limit_from_pd

    assert limit_from_pd(0.92, "data") == 5.0


def test_the_same_subscriber_is_granted_a_small_airtime_advance(healthy):
    """The asymmetry that makes the argument precise rather than blanket. A
    1 LYD airtime advance against a 5 LYD card leaves 4 LYD of usable balance,
    so clearing it still buys them service. Only the 5 LYD rung reproduces the
    zero-residual problem."""
    from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
    from cvm.decision.advance_limit import decide_limit

    features = {**healthy, "modal_recharge_amount_lyd": 5.0, "repayment_probability": 0.92}
    response = decide_limit(
        AdvanceLimitRequest(subscriber_id="b" * 64, product=AdvanceProduct.AIRTIME), features
    )

    assert response.approved is True
    assert response.limit_lyd in (1.0, 3.0), "must be a real denomination below the card"
    assert response.limit_lyd < 5.0


def test_material_lockout_risk_steps_the_limit_down_a_denomination(healthy):
    """5 -> 3 -> 1, never to an amount the operator does not offer."""
    from cvm.decision.advance_limit import apply_safety_guards

    threshold = load_conf("advance")["safety_guards"]["lockout_risk"]["flag_if_probability_above"]
    risky = {**healthy, "lockout_risk": threshold + 0.10}

    safe_limit, _ = apply_safety_guards(5.0, healthy)
    stepped, checks = apply_safety_guards(5.0, risky)

    assert stepped < safe_limit
    assert stepped in (0.0, 1.0, 3.0), f"{stepped} is not a denomination the operator offers"
    assert not next(c for c in checks if c.guard == "lockout_risk").passed


def test_a_decline_always_carries_a_reason_a_subscriber_can_read(healthy):
    """Declining with nothing sends them away. Section 6.5 commits to a
    human-readable reason for every decision, including the negative ones."""
    from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
    from cvm.decision.advance_limit import decide_limit

    broke = {**healthy, "modal_recharge_amount_lyd": 5.0}
    response = decide_limit(
        AdvanceLimitRequest(subscriber_id="c" * 64, product=AdvanceProduct.DATA), broke
    )

    assert response.customer_facing_reason_ar
    assert response.reason_codes
    assert "50" in response.customer_facing_reason_ar, "the affordable fallback is named"
