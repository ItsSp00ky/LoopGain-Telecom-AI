"""M4 -- the learned advance limit.  Owner: E2 / E4

    Limit(i) = min( f(PD(i))            <- repayment probability, learned
                  , g(LoyaltyTier(i))   <- tier ceiling
                  , h(CLV(i))           <- never beyond recoverable value
                  , affordability(i) )  <- what one top-up can actually clear

Then every mandatory safety guard in conf/advance.yaml is applied, and each
one can only REDUCE the limit.

THE HEADLINE INSIGHT, and it falls straight out of Almadar's own numbers:

    smallest recharge card ......... 3 LYD
    نت في وقته data advance ........ 5 LYD, flat, for everyone

A subscriber who can only afford the smallest card cannot clear a data
advance in one top-up. The debt persists, and because re-subscription
requires the debt cleared, they are locked out of the service they reached
for. Both products gate on balance <= 0.5-1 LYD, so the eligible population
is selected on being broke -- the inverse of a risk filter. And because the
two products are mutually exclusive, distressed subscribers alternate between
them, a pattern nothing in the current design watches for.

The `affordability` term is the one the incumbent lacks entirely: never
advance more than the subscriber's own recharge behaviour shows they can
clear. Use the MODAL recharge, not the mean -- the mean is dragged up by one
salary-week top-up they will not repeat.

The objective function is SUBSCRIBER SOLVENCY, not recovery yield. If you
find yourself optimising recovery after a default, you are working on the
wrong problem.
"""

from __future__ import annotations

from cvm.api.schemas import AdvanceLimitRequest, AdvanceLimitResponse


def limit_from_pd(repayment_probability: float, product: str = "airtime") -> float:
    """f(PD): map calibrated repayment probability onto an LYD band.

    Airtime is constrained to the operator's real denominations (1, 3, 5) --
    we cannot invent a 2 LYD advance. Data is flat 5 LYD, so the only
    decision available there is grant or decline.
    """
    raise NotImplementedError("TODO(E2)")


def affordability_ceiling(modal_recharge_lyd: float) -> float:
    """Never issue a debt larger than one typical top-up can clear.

    The guard the incumbent has no equivalent of, and the one that catches the
    3-LYD-card / 5-LYD-debt trap.
    """
    raise NotImplementedError("TODO(E4)")


def limit_from_tier(tier: str) -> float:
    """g(tier): the tier ceiling."""
    raise NotImplementedError("TODO(E4)")


def limit_from_clv(predicted_clv_lyd: float) -> float:
    """h(CLV): never advance beyond a fraction of recoverable lifetime value."""
    raise NotImplementedError("TODO(E4)")


def apply_safety_guards(limit_lyd: float, features) -> tuple[float, list]:
    """Apply every mandatory guard. Returns (adjusted_limit, checks).

    Guards may only reduce the limit. A guard that increases it is a bug.

    - affordability_ceiling: never exceed what one modal top-up clears
    - chronic_distress_exclusion: sustained shortfall -> excluded regardless
      of PD, including alternation between the two emergency products
    - cooling_off: minimum interval, monthly count and cumulative exposure caps
    - clv_bounded_exposure: re-checks the final number, not the input
    - lockout_risk: flag and step down a denomination when the risk is material
    """
    raise NotImplementedError("TODO(E2/E4)")


def decide_limit(payload: AdvanceLimitRequest) -> AdvanceLimitResponse:
    """Full path. Declining with a clear reason is a valid, often correct outcome."""
    raise NotImplementedError("TODO(E2/E4)")