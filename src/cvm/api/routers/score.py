"""M1 -- silent churn probability and time-to-churn.  Owner: E2

Probabilities are isotonic-calibrated because the pricing engine consumes them
as monetary expectations: a 0.31 must mean 31%.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request

from cvm.api.schemas import ChurnScore, ChurnScoreRequest, ChurnScoreResponse

router = APIRouter(tags=["score"])


@router.post("/score/churn", response_model=ChurnScoreResponse)
async def score_churn(payload: ChurnScoreRequest, request: Request) -> ChurnScoreResponse:
    """Score one or many subscribers for silent churn within 30 days.

    Target: zero revenue-generating events for >= 30 consecutive days in the
    prediction window. Framing is 90d observation -> 15d gap -> 30d outcome.
    """
    models = getattr(request.app.state, "models", {})

    # TODO(E2): replace with the real inference path.
    #   from cvm.models.m1_churn.predict import score_batch
    #   return score_batch(payload, models)
    if not models:
        raise HTTPException(
            status_code=503,
            detail=(
                "No churn model loaded. Train M1 and place the artefact in "
                "artifacts/models/, or run `pwsh tasks.ps1 pipeline` first."
            ),
        )

    scores = [
        ChurnScore(
            subscriber_id=sid,
            churn_probability=0.0,
            decile=10,
            model_version="stub",
        )
        for sid in payload.subscriber_ids
    ]
    return ChurnScoreResponse(
        scores=scores,
        scored_at=datetime.now(UTC),
        as_of=payload.as_of or date.today(),
    )
