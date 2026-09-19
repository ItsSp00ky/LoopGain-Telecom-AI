"""M3 -- next-best offer and price quote.  Owner: E4

Every response passes the six guardrails in conf/pricing.yaml before it leaves
this module: margin floor, CLV ceiling, budget LP, cannibalisation guard,
fairness, auditability. A response that skipped one is a bug, not a fast path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.deps import subscriber_features
from cvm.api.schemas import OfferRequest, OfferResponse
from cvm.decision.guardrails import GuardrailBreach

router = APIRouter(tags=["offer"])


@router.post("/offer/next-best", response_model=OfferResponse)
async def next_best_offer(payload: OfferRequest) -> OfferResponse:
    """Choose and price the best offer for this subscriber.

    Value-add before discount: where offpeak_data_ratio shows the subscriber
    will actually use it, discount budget is converted into off-peak capacity
    rather than a headline price cut that permanently erodes ARPU.
    """
    from cvm.decision.pricing import decide_offer

    try:
        return decide_offer(payload, subscriber_features(str(payload.subscriber_id)))
    except GuardrailBreach as exc:
        # A breach reaching here is a bug, not a decision: `decide_offer` runs
        # the guardrails with raise_on_breach=False and returns NO_ACTION. 422
        # rather than 500 so the detail is visible to the caller.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/price/quote", response_model=OfferResponse)
async def price_quote(payload: OfferRequest) -> OfferResponse:
    """Price a specific bundle for a specific subscriber.

    Same guardrails as next-best; the only difference is that the bundle is
    given rather than chosen.
    """
    if payload.bundle_id is None:
        raise HTTPException(
            status_code=422,
            detail="bundle_id is required for a quote. Use /offer/next-best instead.",
        )
    from cvm.decision.pricing import quote_bundle

    try:
        return quote_bundle(payload, subscriber_features(str(payload.subscriber_id)))
    except (GuardrailBreach, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
