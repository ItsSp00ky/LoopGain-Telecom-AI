"""The Subscriber 360 view behind the Command Center screen.  Owner: E4

Lookup is by salted SHA-256 hash only. There is no endpoint anywhere in this
service that accepts or returns a raw MSISDN.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from cvm.api.schemas import SubscriberId, SubscriberProfile

router = APIRouter(tags=["subscriber"])


@router.get("/subscriber/{subscriber_id}", response_model=SubscriberProfile)
async def get_subscriber(subscriber_id: SubscriberId, request: Request) -> SubscriberProfile:
    """Everything the system knows and recommends for one subscriber.

    Assembles M1 (both arms), M1b survival, M2 RFM-LE and CLV, M3 offer and
    the M4 advance limit into the single payload the 360 screen renders.
    """
    import contextlib
    import math

    from cvm.api.deps import subscriber_features
    from cvm.api.schemas import (
        AdvanceLimitRequest,
        AdvanceProduct,
        ChurnScore,
        ChurnScoreRequest,
        OfferRequest,
        RfmLeScores,
    )
    from cvm.decision.advance_limit import decide_limit
    from cvm.decision.pricing import decide_offer

    features = subscriber_features(str(subscriber_id))
    if "segment" not in features:
        raise HTTPException(status_code=404, detail=f"{subscriber_id} is not in the feature store.")

    def number(name: str, default: float = 0.0) -> float:
        value = features.get(name, default)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return default if math.isnan(value) else value

    def quintile(name: str) -> int:
        return int(min(5, max(1, round(number(name, 3.0)))))

    # Churn comes from the real scoring path where M1 is loaded, and degrades
    # to the stored probability otherwise -- a 360 view that 503s because one
    # model is missing is less useful than one that renders what it has.
    models = getattr(request.app.state, "models", {})
    churn_probability = number("churn_probability")
    drivers: list = []
    if "m1_churn_lightgbm" in models:
        from cvm.models.m1_churn.predict import MODEL_KEY, score_batch

        bundle = models["m1_churn_lightgbm"]
        model = bundle["model"] if isinstance(bundle, dict) else bundle
        if isinstance(bundle, dict) and getattr(model, "columns", None) is None:
            model.columns = bundle["columns"]
        with contextlib.suppress(KeyError, RuntimeError):
            scored = score_batch(
                ChurnScoreRequest(subscriber_ids=[str(subscriber_id)]), {MODEL_KEY: model}
            )
            churn_probability = scored.scores[0].churn_probability
            drivers = scored.scores[0].top_drivers

    # A 360 view renders what it HAS. An offer or an advance that cannot be
    # computed for this subscriber leaves that panel empty rather than taking
    # the whole screen down -- the churn score and the RFM-LE cell are still
    # worth showing, and the demo runs through this page.
    offer = advance = None
    with contextlib.suppress(ValueError):
        offer = decide_offer(OfferRequest(subscriber_id=str(subscriber_id)), features)
    with contextlib.suppress(ValueError):
        advance = decide_limit(
            AdvanceLimitRequest(subscriber_id=str(subscriber_id), product=AdvanceProduct.AIRTIME),
            features,
        )

    stage = offer.retention_stage if offer else "none"
    return SubscriberProfile(
        subscriber_id=str(subscriber_id),
        tenure_months=int(number("tenure_months")),
        language_pref="ar-LY",
        rfm_le=RfmLeScores(
            recency=quintile("R"),
            frequency=quintile("F"),
            monetary=quintile("M"),
            loyalty=quintile("L"),
            engagement=quintile("E"),
            cell=str(features.get("rfmle_cell", "")),
        ),
        segment=str(features["segment"]),
        tier=features.get("tier", "bronze"),
        clv_12m_lyd=number("clv_12m"),
        churn=ChurnScore(
            subscriber_id=str(subscriber_id),
            churn_probability=churn_probability,
            decile=int(min(10, max(1, round(10 * (1 - churn_probability)) or 1))),
            top_drivers=drivers,
            model_version="m1-phase4",
        ),
        retention_stage=stage,
        leakage_score=number("leakage_score"),
        incoming_outgoing_ratio=number("incoming_outgoing_ratio"),
        onnet_ratio=number("onnet_ratio"),
        dropped_call_rate_30d=number("dropped_call_rate_30d"),
        service_outage_hours_30d=number("service_outage_hours_30d"),
        recommended_offer=offer,
        advance=advance,
    )
