"""Shared FastAPI dependencies.

Models and the feature-store connection are attached to ``app.state`` at
startup and read from here. Nothing in this module may open a connection or
load an artefact per request -- that is how the 200 ms p95 budget dies.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request


def get_models(request: Request) -> dict[str, Any]:
    return getattr(request.app.state, "models", {})


def require_model(request: Request, name: str) -> Any:
    models = get_models(request)
    if name not in models:
        raise HTTPException(
            status_code=503,
            detail=f"Model {name!r} is not loaded. Check /health for what is missing.",
        )
    return models[name]


def get_feature_store(request: Request):
    store = getattr(request.app.state, "feature_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Feature store is not connected.")
    return store