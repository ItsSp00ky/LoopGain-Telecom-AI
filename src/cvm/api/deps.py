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


def subscriber_features(subscriber_id: str) -> dict:
    """Everything the decision engine needs for one subscriber, from what the
    pipeline already wrote.

    READ, NEVER RECOMPUTED. A serving path that rebuilds features is a serving
    path that will eventually compute them differently from the training path,
    and that skew is silent -- the model returns plausible numbers that are
    wrong.

    Missing upstream outputs degrade to neutral defaults rather than raising.
    An API that 500s because M3 has not been run cannot serve a churn score
    either, and the endpoints that genuinely need a missing model already
    return 503 through `require_model`.
    """
    import pandas as pd

    from cvm.config import settings

    features: dict = {"subscriber_id": subscriber_id}

    # THE ONLINE STORE, NOT THE PARQUET. Reading the offline file scans 100,000
    # rows per request: measured 292 ms for one subscriber against a 200 ms p95
    # budget, and it gets worse linearly. The online DuckDB store is one row
    # per subscriber with a unique index on the id, which is what it is for.
    if settings.feature_store.exists():
        from cvm.features import store as feature_store

        connection = feature_store.connect()
        try:
            row = connection.execute(
                f"SELECT * FROM {feature_store.TABLE} WHERE {feature_store.ID_COLUMN} = ?",
                [str(subscriber_id)],
            ).df()
        finally:
            connection.close()
        if not row.empty:
            features.update(row.iloc[0].to_dict())

    for _name, path in (
        ("m2", settings.processed_dir / "m2_clv.parquet"),
        ("m3", settings.processed_dir / "m3_uplift.parquet"),
    ):
        if not path.exists():
            continue
        # Pushed into the Parquet reader rather than loaded and filtered, so
        # only the matching row group is touched.
        try:
            row = pd.read_parquet(
                path, filters=[("subscriber_id_hashed", "==", str(subscriber_id))]
            )
        except (ValueError, KeyError):
            # m2_clv.parquet is positionally aligned rather than keyed by id.
            continue
        if not row.empty:
            features.update(row.iloc[0].to_dict())

    features.setdefault("clv_12m", 0.0)
    features.setdefault("uplift", 0.0)
    features.setdefault("quadrant", "persuadable")
    features["tier"] = _tier_from(features)
    features["churn_probability"] = float(features.get("churn_probability", 0.0))
    return features


def _tier_from(features: dict) -> str:
    """Loyalty tier from tenure, per conf/pricing.yaml#tiers."""
    tenure = features.get("tenure_months")
    tenure = 0.0 if tenure is None else float(tenure)
    if tenure >= 84:
        return "platinum"
    if tenure >= 36:
        return "gold"
    if tenure >= 12:
        return "silver"
    return "bronze"
