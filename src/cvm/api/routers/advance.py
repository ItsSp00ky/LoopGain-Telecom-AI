"""M4 -- learned emergency-credit limit.  Owner: E2 / E4

Covers both Almadar products: رصيد في وقته (airtime, 1/3/5 LYD, *140#) and
نت في وقته (data, flat 5 LYD, *000#).

Replaces allocation rules that gate on the subscriber being nearly out of money
and then size the advance by "consumption", with
min(f(PD), g(tier), h(CLV), affordability).

The objective function is SUBSCRIBER SOLVENCY, not recovery yield. The 5 LYD
data advance is exactly the size of the 5 LYD smallest recharge card, so
clearing it consumes the whole top-up and returns the subscriber to zero: the
minimum recharge buys nothing and the rational move is not to make it. A
deferred recharge on a prepaid line is where silent churn starts. Every safety
guard in conf/advance.yaml is mandatory.

(An earlier version of this docstring argued the debt EXCEEDED the card and
locked the subscriber out. That rested on a 3 LYD card and is retired -- see
decision/advance_limit.py for the full note.)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.deps import subscriber_features
from cvm.api.schemas import AdvanceLimitRequest, AdvanceLimitResponse

router = APIRouter(tags=["advance"])


@router.post("/advance/limit", response_model=AdvanceLimitResponse)
async def advance_limit(payload: AdvanceLimitRequest) -> AdvanceLimitResponse:
    """Compute a safe advance limit, or decline with a reason.

    Declining is a valid and often correct outcome. A limit of 0 with a clear
    reason protects the line; a generous limit the subscriber cannot settle
    destroys it.
    """
    from cvm.decision.advance_limit import decide_limit

    try:
        return decide_limit(payload, subscriber_features(str(payload.subscriber_id)))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
