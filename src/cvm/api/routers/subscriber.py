"""The Subscriber 360 view behind the Command Center screen.  Owner: E4

Lookup is by salted SHA-256 hash only. There is no endpoint anywhere in this
service that accepts or returns a raw MSISDN.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.schemas import SubscriberId, SubscriberProfile

router = APIRouter(tags=["subscriber"])


@router.get("/subscriber/{subscriber_id}", response_model=SubscriberProfile)
async def get_subscriber(subscriber_id: SubscriberId) -> SubscriberProfile:
    """Everything the system knows and recommends for one subscriber.

    Assembles M1 (both arms), M1b survival, M2 RFM-LE and CLV, M3 offer and
    the M4 advance limit into the single payload the 360 screen renders.
    """
    # TODO(E4): assemble from the feature store + decision engine.
    raise HTTPException(status_code=501, detail="Subscriber 360 assembly not implemented yet.")
