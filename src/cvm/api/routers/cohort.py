"""Cohort query -- the integration surface for the Copilot and Chatbot.

Those two components are owned by other team members and live outside this
branch. This endpoint is how they reach CVM: filter a population, get back
hashed IDs plus the aggregate, then call the scoring endpoints for detail.

It exists so that neither of them has to write SQL against our feature store or
import our package. If the store moves from DuckDB to a warehouse, this
contract does not change.

Read-only. Nothing here creates or mutates a decision.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.schemas import CohortFilter, CohortResponse

router = APIRouter(tags=["cohort"])


@router.post("/cohort/query", response_model=CohortResponse)
async def query_cohort(payload: CohortFilter) -> CohortResponse:
    """Return the hashed IDs matching a filter, plus the aggregate at risk.

    Example: the Copilot answering "which high-value subscribers are at risk
    and have poor service?" resolves to
    ``{min_churn_probability: 0.5, min_clv_lyd: 300, min_dropped_call_rate: 0.04}``,
    then calls /v1/offer/next-best per subscriber for the recommendation.

    There is no `district` filter -- geography is out of scope, so a caller
    asking for one gets a 422 rather than a silently-ignored field.
    """
    import pandas as pd

    from cvm.config import settings

    path = settings.feature_store_offline
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"{path.name} does not exist; run `python -m cvm.features.run`.",
        )

    frame = pd.read_parquet(path)
    frame = (
        frame.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )

    # CLV and churn come from the model outputs rather than being recomputed
    # per query. A cohort filter that re-scores 100,000 subscribers is a cohort
    # filter nobody will use twice.
    clv_path = settings.processed_dir / "m2_clv.parquet"
    if clv_path.exists():
        frame["clv_12m"] = pd.read_parquet(clv_path)["clv_12m"].to_numpy()
    scores_path = settings.processed_dir / "m1_scores.parquet"
    if scores_path.exists():
        scores = pd.read_parquet(scores_path)
        frame = frame.merge(scores, on="subscriber_id_hashed", how="left")

    mask = pd.Series(True, index=frame.index)
    if payload.segment is not None:
        mask &= frame["segment"].astype(str) == str(payload.segment)
    if payload.min_churn_probability is not None:
        mask &= frame.get("churn_probability", 0.0) >= payload.min_churn_probability
    if payload.max_churn_probability is not None:
        mask &= frame.get("churn_probability", 0.0) <= payload.max_churn_probability
    if payload.min_clv_lyd is not None:
        mask &= frame.get("clv_12m", 0.0) >= payload.min_clv_lyd
    if payload.min_dropped_call_rate is not None:
        mask &= frame.get("dropped_call_rate_30d", 0.0) >= payload.min_dropped_call_rate
    if payload.tier is not None:
        mask &= frame["tenure_months"].map(_tier_of).astype(str) == str(payload.tier)

    matched = frame[mask]

    # Revenue at risk is CLV WEIGHTED BY churn probability, not the CLV of
    # everyone who matched. A cohort of 40,000 subscribers at 5% risk is not
    # 40,000 CLVs at risk, and reporting it that way would inflate the headline
    # on the Executive Overview by an order of magnitude.
    at_risk = float((matched.get("clv_12m", 0.0) * matched.get("churn_probability", 0.0)).sum())

    ids = matched["subscriber_id_hashed"].astype(str).head(payload.limit).tolist()
    return CohortResponse(
        subscriber_ids=ids,
        total_matched=len(matched),
        returned=len(ids),
        total_revenue_at_risk_lyd=at_risk,
        filter_applied=payload,
    )


def _tier_of(tenure_months) -> str:
    """Loyalty tier from tenure, per conf/pricing.yaml#tiers."""
    tenure = 0.0 if tenure_months is None else float(tenure_months)
    if tenure >= 84:
        return "platinum"
    if tenure >= 36:
        return "gold"
    if tenure >= 12:
        return "silver"
    return "bronze"
