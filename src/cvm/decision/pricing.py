"""Offer selection and pricing.  Owner: E4

The "with what" half of the decision. The "whether" half is upstream: M3
uplift decides who is movable, and E[gain] = uplift x CLV - cost decides
whether treating them is worthwhile at all.

The action space is the operator's real catalogue (conf/catalogue.yaml), so
every recommendation is executable and every cost is real.

    P(i,b) = P_base(b) * (1 - d(i,b))

    d(i,b) = clip( w1*ChurnRisk(i)                 <- urgency
                 + w2*LoyaltyIndex(i)              <- earned reward
                 + w3*PriceSensitivity(i,b)        <- elasticity
                 - w4*AffordabilityHeadroom(i)     <- don't discount those who can pay
                 , 0, d_max(tier(i)) )

Value-add before discount: a 15% headline cut permanently reduces realised ARPU
and is trivially matched by a competitor. A gigabyte of off-peak data costs
almost nothing on an idle sector, is perceived as generous, and leaves the
published price sheet intact. Where offpeak_data_ratio shows the subscriber will
actually use it, this module converts discount budget into off-peak capacity
rather than a price cut.

Weights live in conf/pricing.yaml. Do not inline them here -- an evaluator will
ask to change one during the demo.

NO ACTION IS A FIRST-CLASS OUTCOME. `decide_offer` returns an offer with
instrument "none" and a zero discount whenever the guardrails or the uplift
filter say so, rather than raising or returning the cheapest thing available.
Most of the value in this system is in the offers it does not make.
"""

from __future__ import annotations

import logging

import numpy as np

from cvm.api.schemas import (
    AppliedConstraint,
    Bundle,
    OfferRequest,
    OfferResponse,
)
from cvm.config import load_conf
from cvm.decision import guardrails

log = logging.getLogger(__name__)

NO_ACTION = "NO_ACTION"


def _conf() -> dict:
    return load_conf("pricing")


def compute_discount(
    churn_risk: float,
    loyalty_index: float,
    price_sensitivity: float,
    affordability_headroom: float,
    tier: str,
    weights: dict | None = None,
) -> float:
    """The d(i,b) formula, clipped to [0, d_max(tier)].

    AFFORDABILITY IS SUBTRACTED, and that sign is the interesting one. Every
    other term raises the discount; this one lowers it. A subscriber with room
    in their budget does not need a price cut to stay, so discounting them is
    margin given away for nothing -- the money should go to someone for whom
    price is actually the obstacle.

    THE TIER CEILING DOMINATES THIS FORMULA, MEASURED. The three positive
    weights sum to 0.90, so the raw value spans [-0.20, 0.90]; the tier
    ceilings are 0.05 to 0.20. Over uniform random inputs:

        bronze     96.8% clip at d_max, 1.9% land strictly inside
        platinum   80.9% clip at d_max, 17.7% land strictly inside

    So for most subscribers `d(i,b)` reduces to `d_max(tier(i))` and the four
    terms express nothing. That is a real limitation of the current
    parameterisation rather than a bug in this function -- conf/pricing.yaml
    specifies `clip`, and the weights and the ceilings were evidently chosen on
    different scales. Scaling the formula BY d_max instead of clipping AT it
    would let all four terms express themselves inside each tier's allowance,
    and it is a pricing-policy change rather than a refactor, so it is flagged
    here and in the roadmap instead of being made quietly.

    ``weights`` overrides the config, which is what `decision_log.replay` uses
    to re-run a decision under the weights recorded at the time.
    """
    weights = _conf()["discount_weights"] if weights is None else weights
    for name, value in (
        ("churn_risk", churn_risk),
        ("loyalty_index", loyalty_index),
        ("price_sensitivity", price_sensitivity),
        ("affordability_headroom", affordability_headroom),
    ):
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")

    raw = (
        weights["w1_churn_risk"] * churn_risk
        + weights["w2_loyalty_index"] * loyalty_index
        + weights["w3_price_sensitivity"] * price_sensitivity
        - weights["w4_affordability_headroom"] * affordability_headroom
    )
    return float(np.clip(raw, 0.0, guardrails.tier_max_discount(tier)))


def choose_instrument(tier: str, offpeak_data_ratio: float, leakage_score: float) -> str:
    """Pick between price_discount, bonus_mb, offpeak_data and onnet_minutes.

    Leakage changes the answer: a subscriber whose on-net share is falling needs
    an on-net pack, not cheaper data -- the social graph is what is migrating.

    Ordered by what the evidence says, not by cost. Leakage first because a
    cheaper bundle does nothing for someone whose contacts have moved to the
    competitor; off-peak second because it is near-free on an idle sector and
    leaves the price sheet intact; a headline cut last, because it permanently
    lowers realised ARPU and any competitor can match it the same afternoon.
    """
    conf = _conf()
    leakage_threshold = conf["guardrails"].get("leakage_onnet_threshold", 0.6)
    minimum_ratio = conf["offpeak"]["min_offpeak_data_ratio_to_qualify"]

    if float(leakage_score) >= leakage_threshold:
        # The morning pass carries unlimited VOICE as well, so for the top
        # tiers it is the on-net instrument too.
        return "onnet_minutes"
    if float(offpeak_data_ratio) >= minimum_ratio and conf["offpeak"]["value_add_before_discount"]:
        return "offpeak_data"
    if str(tier).lower() in ("silver", "gold", "platinum"):
        return "bonus_mb"
    return "price_discount"


def decide_offer(payload: OfferRequest, features: dict | None = None) -> OfferResponse:
    """Full next-best-offer path: features -> uplift filter -> price -> guardrails
    -> reason codes -> decision log."""
    from cvm.decision import decision_log, ladder

    features = {} if features is None else dict(features)
    tier = str(features.get("tier", "bronze")).lower()
    churn = float(features.get("churn_probability", 0.0))
    uplift = float(features.get("uplift", 0.0))
    clv = float(features.get("clv_12m", 0.0))

    bundle = _bundle(payload.bundle_id or features.get("bundle_id"))
    base_price = float(bundle.base_price_lyd)
    variable_cost = float(features.get("variable_cost_lyd", base_price * 0.35))

    stage = ladder.assign_stage(
        int(features.get("days_since_last_topup", 0) or 0),
        float(features.get("inter_recharge_gap_mean", 0.0) or 0.0),
        ladder.derive_boundaries(features.get("hazard_inflections", [])),
    )

    # --- The uplift filter. "No action" before anything is priced. ----------
    incentive = float(load_conf("market")["base"]["blended_incentive_lyd"])
    expected_gain = uplift * clv - incentive
    quadrant = str(features.get("quadrant", "persuadable"))

    if quadrant == "sleeping_dog":
        return _no_action(payload, bundle, tier, stage, "sleeping_dog", clv)
    if expected_gain <= 0 and payload.bundle_id is None:
        return _no_action(payload, bundle, tier, stage, "negative_expected_value", clv)

    # --- The discount, scaled by the ladder's inverted-U --------------------
    discount = compute_discount(
        churn_risk=churn,
        loyalty_index=float(features.get("loyalty_index", 0.0)),
        price_sensitivity=float(features.get("price_sensitivity", 0.0)),
        affordability_headroom=float(features.get("affordability_headroom", 0.0)),
        tier=tier,
        weights=features.get("discount_weights"),
    ) * ladder.spend_multiplier(stage)

    instrument = choose_instrument(
        tier,
        float(features.get("offpeak_data_ratio", 0.0)),
        float(features.get("leakage_score", 0.0)),
    )
    # Value-add before discount: where the instrument is capacity rather than
    # price, the discount budget is spent as data and the price sheet is left
    # alone. The margin floor then binds on the full price, which is the point.
    if instrument in ("offpeak_data", "bonus_mb", "onnet_minutes"):
        bonus_mb = round(discount * base_price * 1000)
        discount = 0.0
    else:
        bonus_mb = 0

    price = base_price * (1.0 - discount)

    # --- Guardrails. Never bypassed, and every verdict is recorded. ---------
    verdicts = guardrails.evaluate_offer(
        price_lyd=price,
        base_price_lyd=base_price,
        variable_cost_lyd=variable_cost,
        discount_pct=discount,
        tier=tier,
        churn_probability=churn,
        value_decile=int(features.get("value_decile", 5)),
        predicted_clv_lyd=clv,
        cumulative_spend_lyd_12m=float(features.get("cumulative_spend_lyd_12m", 0.0)),
        pricing_features=list(features.get("pricing_features", [])),
        peak_usage_would_shift=bool(features.get("peak_usage_would_shift", False)),
        current_monthly_bundle_lyd=features.get("current_monthly_bundle_lyd"),
        raise_on_breach=False,
    )
    failed = [v for v in verdicts if not v.passed]
    if failed:
        return _no_action(payload, bundle, tier, stage, failed[0].name, clv, verdicts=verdicts)

    constraints = _constraints(verdicts)
    reasons = [f"stage:{stage.value}", f"instrument:{instrument}", f"tier:{tier}"]
    reasons += [f"binding:{c.name}" for c in constraints if c.binding]

    log_id = decision_log.log_decision(
        subscriber_id=str(payload.subscriber_id),
        decision_type="offer",
        inputs=features,
        weights=features.get("discount_weights") or _conf()["discount_weights"],
        constraints=[c.model_dump() for c in constraints],
        reason_codes=reasons,
        outcome={
            "offer_id": bundle.bundle_id,
            "price_lyd": price,
            "discount_pct": discount,
            "bonus_mb": bonus_mb,
            "instrument": instrument,
        },
        model_versions=features.get("model_versions", {}),
    )

    window = _conf()["offpeak"]["window"] if instrument == "offpeak_data" else None
    return OfferResponse(
        subscriber_id=str(payload.subscriber_id),
        offer_id=bundle.bundle_id,
        bundle=bundle,
        base_price_lyd=base_price,
        price_lyd=price,
        discount_pct=discount,
        bonus_mb=bonus_mb,
        valid_from_hour=window["start_hour"] if window else None,
        valid_to_hour=window["end_hour"] if window else None,
        tier=tier,
        retention_stage=stage,
        instrument=instrument,
        reason_codes=reasons,
        customer_facing_reason_ar=_reason_ar(instrument, tier, discount),
        customer_facing_reason_en=_reason_en(instrument, tier, discount),
        expected_margin_lyd=float(price - variable_cost),
        constraints=constraints,
        decision_log_id=log_id,
    )


def quote_bundle(payload: OfferRequest, features: dict | None = None) -> OfferResponse:
    """Price a specific bundle. Same guardrails; the bundle is given.

    The ONLY difference from `decide_offer` is that the action space is one
    item. The guardrails are identical, deliberately: a quote a subscriber
    asked for is still an offer the operator makes, and "they requested it" has
    never been a defence for a loss-making price.
    """
    if payload.bundle_id is None:
        raise ValueError("quote_bundle needs a bundle_id; use decide_offer to let the engine pick")
    return decide_offer(payload, features)


# --- Helpers ---------------------------------------------------------------


def _catalogue_items() -> list[dict]:
    catalogue = load_conf("catalogue")
    return [item for family in catalogue["families"].values() for item in family.get("items", [])]


def _bundle(bundle_id: str | None) -> Bundle:
    """Resolve a real catalogue item. Never invents one."""
    items = _catalogue_items()
    if bundle_id:
        match = next((i for i in items if i["id"] == bundle_id), None)
        if match is None:
            raise ValueError(
                f"{bundle_id!r} is not in conf/catalogue.yaml. "
                "forbid_synthetic_offers is set: an offer we invented would have a cost "
                "we invented, and the margin floor would enforce one made-up number "
                "against another."
            )
    else:
        # Default to the base monthly -- the bundle most of the base holds.
        base_id = _conf()["guardrails"]["cannibalisation"]["base_monthly_offer_id"]
        match = next((i for i in items if i["id"] == base_id), items[0])

    return Bundle(
        bundle_id=match["id"],
        name_en=match.get("name_en", match["id"]),
        name_ar=match.get("name_ar", match["id"]),
        base_price_lyd=float(match["price_lyd"]),
        data_mb=int(match.get("data_mb", 0) or 0),
        voice_min_onnet=int(match.get("voice_min_onnet", 0) or 0),
        voice_min_offnet=int(match.get("voice_min_offnet", 0) or 0),
        sms_count=int(match.get("sms_count", 0) or 0),
        validity_days=int(match.get("validity_days", 0) or 0),
    )


def _constraints(verdicts) -> list[AppliedConstraint]:
    """Only the names the schema declares. An unmapped guard is dropped rather
    than crashing the response, and logged so it is not lost."""
    allowed = set(AppliedConstraint.model_fields["name"].annotation.__args__)
    out = []
    for v in verdicts:
        if v.name in allowed:
            out.append(AppliedConstraint(name=v.name, binding=v.binding, detail=v.detail))
        else:
            log.warning("guardrail %r has no AppliedConstraint name; not surfaced", v.name)
    return out


def _no_action(
    payload, bundle, tier, stage, reason: str, clv: float, verdicts=None
) -> OfferResponse:
    """The right answer more often than anyone expects.

    Returned as a full OfferResponse rather than a null so the decision is
    logged, auditable and replayable like any other. A decision not to spend is
    still a decision, and section 6.5 commits to explaining every one.
    """
    from cvm.decision import decision_log

    reasons = [f"no_action:{reason}", f"stage:{stage.value}"]
    constraints = _constraints(verdicts) if verdicts else []

    log_id = decision_log.log_decision(
        subscriber_id=str(payload.subscriber_id),
        decision_type="offer",
        inputs={"reason": reason, "clv_12m": clv},
        weights=_conf()["discount_weights"],
        constraints=[c.model_dump() for c in constraints],
        reason_codes=reasons,
        outcome={"offer_id": NO_ACTION, "price_lyd": 0.0, "discount_pct": 0.0},
        model_versions={},
    )
    return OfferResponse(
        subscriber_id=str(payload.subscriber_id),
        offer_id=NO_ACTION,
        bundle=bundle,
        base_price_lyd=float(bundle.base_price_lyd),
        price_lyd=float(bundle.base_price_lyd),
        discount_pct=0.0,
        bonus_mb=0,
        tier=tier,
        retention_stage=stage,
        instrument="none",
        reason_codes=reasons,
        customer_facing_reason_ar="لا يوجد عرض مناسب في الوقت الحالي.",
        customer_facing_reason_en="No offer is appropriate at this time.",
        expected_margin_lyd=0.0,
        constraints=constraints,
        decision_log_id=log_id,
    )


def _reason_ar(instrument: str, _tier: str, discount: float) -> str:
    """The Arabic copy does not name the tier. "مكافأة على ولائك" (a reward for
    your loyalty) reads naturally; "مكافأة العضوية الذهبية" reads like a
    translated marketing term and tells the subscriber nothing they can act on.
    The parameter stays so the two renderers keep the same signature."""
    if instrument == "offpeak_data":
        return "هدية إنترنت مجاني صباحاً من 6 إلى 11، شكراً لولائك."
    if instrument == "onnet_minutes":
        return "باقة مكالمات داخل الشبكة، هدية لك."
    if instrument == "bonus_mb":
        return "ميجابايت إضافية مجاناً، مكافأة على ولائك."
    return f"خصم {discount:.0%} مكافأة على ولائك."


def _reason_en(instrument: str, tier: str, discount: float) -> str:
    if instrument == "offpeak_data":
        return "Free morning data, 06:00-11:00 - a thank-you for your loyalty."
    if instrument == "onnet_minutes":
        return "An on-net minutes pack, on us."
    if instrument == "bonus_mb":
        return f"Bonus data, a {tier} loyalty reward."
    return f"A {discount:.0%} loyalty discount."
