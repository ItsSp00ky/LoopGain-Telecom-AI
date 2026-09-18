"""M3 pricing guardrails. Required in CI; never skipped.

Every test here maps to a commitment in the proposal. If one fails, the system
is doing something we told an evaluator it would not do.
"""

from __future__ import annotations

import pytest

from cvm.decision.guardrails import (
    GuardrailBreach,
    audit_redlining,
    check_budget,
    check_cannibalisation,
    check_clv_ceiling,
    check_fairness,
    check_margin_floor,
    check_tier_ceiling,
    evaluate_offer,
    max_discount_within_margin,
)

pytestmark = pytest.mark.guardrail


# --- 1. Margin floor: no loss-making offer, ever ---------------------------


def test_margin_floor_passes_above_the_floor():
    # cost 5.00 x 1.15 = 5.75; price 9.00 clears it
    assert check_margin_floor(9.0, 5.0).passed


def test_margin_floor_fails_below_the_floor():
    v = check_margin_floor(5.50, 5.0)
    assert not v.passed
    assert "5.750" in v.detail


def test_margin_floor_is_exactly_binding_at_the_floor():
    v = check_margin_floor(5.75, 5.0)
    assert v.passed and v.binding


def test_max_discount_within_margin_never_produces_a_breach():
    base, cost = 10.0, 5.0
    d = max_discount_within_margin(base, cost)
    assert check_margin_floor(base * (1 - d), cost).passed


def test_max_discount_is_zero_when_cost_already_exceeds_price():
    assert max_discount_within_margin(5.0, 10.0) == 0.0


# --- 2. CLV ceiling: total spend <= 15% of predicted CLV -------------------


def test_clv_ceiling_passes_within_budget():
    # CLV 144 -> ceiling 21.60
    assert check_clv_ceiling(1.0, 0.0, 144.0).passed


def test_clv_ceiling_fails_when_exceeded():
    assert not check_clv_ceiling(25.0, 0.0, 144.0).passed


def test_clv_ceiling_counts_cumulative_spend_not_just_this_offer():
    """Twelve small offers, each individually fine, is the classic way this
    constraint gets defeated."""
    assert check_clv_ceiling(1.0, 21.0, 144.0).passed is False


def test_clv_ceiling_handles_zero_clv():
    assert not check_clv_ceiling(0.01, 0.0, 0.0).passed


# --- 3. Budget ------------------------------------------------------------


def test_budget_respected():
    assert check_budget(140_000.0, 144_000.0).passed


def test_budget_breach_detected():
    assert not check_budget(150_000.0, 144_000.0).passed


# --- 4. Cannibalisation ---------------------------------------------------


def test_low_risk_high_value_subscriber_is_excluded():
    """They would have paid full price."""
    v = check_cannibalisation(churn_probability=0.05, value_decile=10)
    assert not v.passed


def test_low_risk_low_value_is_not_excluded():
    assert check_cannibalisation(churn_probability=0.05, value_decile=3).passed


def test_high_risk_high_value_is_not_excluded():
    """The At-Risk Valuable segment is exactly who we want to reach."""
    assert check_cannibalisation(churn_probability=0.70, value_decile=10).passed


def test_non_additive_night_pack_is_excluded():
    v = check_cannibalisation(0.70, 5, peak_usage_would_shift=True)
    assert not v.passed
    assert "additive" in v.detail


# --- 5. Fairness ----------------------------------------------------------


@pytest.mark.parametrize("attr", ["district", "age_group", "language_pref", "gender"])
def test_protected_attributes_cannot_reach_pricing(attr: str):
    v = check_fairness(["churn_probability", attr])
    assert not v.passed


def test_clean_feature_list_passes_fairness():
    assert check_fairness(["churn_probability", "loyalty_index"]).passed


def test_redlining_audit_flags_a_wide_district_gap():
    assert not audit_redlining({"Tripoli": 0.02, "Sabha": 0.14}).passed


def test_redlining_audit_passes_a_narrow_gap():
    assert audit_redlining({"Tripoli": 0.09, "Sabha": 0.10}).passed


# --- 6. Tier ceiling ------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "d_max"), [("bronze", 0.05), ("silver", 0.10), ("gold", 0.15), ("platinum", 0.20)]
)
def test_tier_ceilings_match_the_proposal(tier: str, d_max: float):
    assert check_tier_ceiling(d_max, tier).passed
    assert not check_tier_ceiling(d_max + 0.01, tier).passed


def test_unknown_tier_raises():
    with pytest.raises(KeyError):
        check_tier_ceiling(0.05, "diamond")


# --- Composite ------------------------------------------------------------


def test_clean_offer_passes_every_guardrail(offer_inputs):
    verdicts = evaluate_offer(**offer_inputs)
    assert all(v.passed for v in verdicts)
    assert {v.name for v in verdicts} == {
        "margin_floor",
        "tier_d_max",
        "clv_ceiling",
        "cannibalisation",
        "fairness",
    }


def test_composite_raises_on_a_loss_making_price(offer_inputs):
    offer_inputs["price_lyd"] = 4.0
    with pytest.raises(GuardrailBreach, match="margin_floor"):
        evaluate_offer(**offer_inputs)


def test_composite_raises_when_district_is_used_for_pricing(offer_inputs):
    offer_inputs["pricing_features"] = ["churn_probability", "district"]
    with pytest.raises(GuardrailBreach, match="fairness"):
        evaluate_offer(**offer_inputs)


def test_simulator_can_collect_breaches_without_raising(offer_inputs):
    """The campaign simulator needs to count how many candidates each guardrail
    rejects, which it cannot do if the first breach aborts the run."""
    offer_inputs["price_lyd"] = 4.0
    verdicts = evaluate_offer(**offer_inputs, raise_on_breach=False)
    assert any(not v.passed for v in verdicts)