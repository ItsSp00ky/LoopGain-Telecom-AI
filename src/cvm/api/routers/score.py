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
    from cvm.models.m1_churn.predict import MODEL_KEY, score_batch

    models = getattr(request.app.state, "models", {})
    if not models:
        raise HTTPException(
            status_code=503,
            detail=(
                "No churn model loaded. Train M1 and place the artefact in "
                "artifacts/models/, or run `pwsh tasks.ps1 pipeline` first."
            ),
        )

    # The registry stores M1 as a bundle -- the calibrated model plus the
    # training column list. `score_batch` wants the model with `.columns` set,
    # which is how it aligns a serving batch to the training matrix.
    bundle = models.get("m1_churn_lightgbm")
    if bundle is None:
        raise HTTPException(status_code=503, detail="m1_churn_lightgbm is not loaded.")
    model = bundle["model"] if isinstance(bundle, dict) else bundle
    if isinstance(bundle, dict) and getattr(model, "columns", None) is None:
        model.columns = bundle["columns"]

    try:
        return score_batch(payload, {MODEL_KEY: model, **models})
    except KeyError as exc:
        # A subscriber the store has never seen. 404 rather than a silent gap:
        # a caller that asked for 500 and got 480 back cannot tell a cold
        # subscriber from a bug, and will assume the latter.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    scores: list[ChurnScore] = []
    return ChurnScoreResponse(
        scores=scores,
        scored_at=datetime.now(UTC),
        as_of=payload.as_of or date.today(),
    )
