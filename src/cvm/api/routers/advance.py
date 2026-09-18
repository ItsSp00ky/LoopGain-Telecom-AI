"""M4 -- learned emergency-credit limit.  Owner: E2 / E4

Covers both Almadar products: رصيد في وقته (airtime, 1/3/5 LYD, *140#) and
نت في وقته (data, flat 5 LYD, *000#).

Replaces allocation rules that gate on the subscriber being nearly out of money
and then size the advance by "consumption", with
min(f(PD), g(tier), h(CLV), affordability).

The objective function is SUBSCRIBER SOLVENCY, not recovery yield. A 5 LYD data
advance against a 3 LYD smallest recharge card cannot be cleared in one top-up;
the debt persists and blocks re-subscription, locking the subscriber out of the
service they reached for. Every safety guard in conf/advance.yaml is mandatory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.schemas import AdvanceLimitRequest, AdvanceLimitResponse

router = APIRouter(tags=["advance"])


@router.post("/advance/limit", response_model=AdvanceLimitResponse)
async def advance_limit(payload: AdvanceLimitRequest) -> AdvanceLimitResponse:
    """Compute a safe advance limit, or decline with a reason.

    Declining is a valid and often correct outcome. A limit of 0 with a clear
    reason protects the line; a generous limit the subscriber cannot settle
    destroys it.
    """
    # TODO(E2/E4): from cvm.decision.advance_limit import decide_limit
    #              return decide_limit(payload)
    raise HTTPException(status_code=501, detail="M4 advance engine not implemented yet.")