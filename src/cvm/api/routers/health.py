"""Liveness and readiness. Docker healthchecks poll this."""

from __future__ import annotations

from fastapi import APIRouter, Request

from cvm import __version__
from cvm.api.schemas import HealthResponse
from cvm.config import settings

router = APIRouter(tags=["health"])

# The model artefacts the system is complete with. Reported individually so a
# partial deploy is visible rather than silently degraded.
EXPECTED_MODELS = (
    "m1_churn_lightgbm",
    "m1b_survival",
    "m2_clv",
    "m3_uplift",
    "m4_repayment_pd",
)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    loaded: dict[str, bool] = {
        name: name in getattr(request.app.state, "models", {}) for name in EXPECTED_MODELS
    }
    store_ok = settings.feature_store.exists()

    # "ok" only when every model is loaded AND the feature store is readable.
    # A degraded API that reports "ok" is worse than one that reports nothing.
    status = "ok" if all(loaded.values()) and store_ok else "degraded"

    return HealthResponse(
        status=status,
        version=__version__,
        env=settings.env,
        models_loaded=loaded,
        feature_store_reachable=store_ok,
    )
