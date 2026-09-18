"""M3 -- personalised pricing.  Owner: E4

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
"""

from __future__ import annotations

from cvm.api.schemas import OfferRequest, OfferResponse


def compute_discount(
    churn_risk: float,
    loyalty_index: float,
    price_sensitivity: float,
    affordability_headroom: float,
    tier: str,
) -> float:
    """The d(i,b) formula, clipped to [0, d_max(tier)]."""
    raise NotImplementedError("TODO(E4)")


def choose_instrument(tier: str, offpeak_data_ratio: float, leakage_score: float) -> str:
    """Pick between price_discount, bonus_mb, offpeak_data and onnet_minutes.

    Leakage changes the answer: a subscriber whose on-net share is falling needs
    an on-net pack, not cheaper data -- the social graph is what is migrating.
    """
    raise NotImplementedError("TODO(E4)")


def decide_offer(payload: OfferRequest) -> OfferResponse:
    """Full next-best-offer path: features -> uplift filter -> price -> guardrails
    -> reason codes -> decision log."""
    raise NotImplementedError("TODO(E4)")


def quote_bundle(payload: OfferRequest) -> OfferResponse:
    """Price a specific bundle. Same guardrails; the bundle is given."""
    raise NotImplementedError("TODO(E4)")