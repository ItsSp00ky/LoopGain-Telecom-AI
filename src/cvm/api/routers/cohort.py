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

    Example: the Copilot answering "which Benghazi subscribers are at risk
    because of coverage?" resolves to
    ``{district: "Benghazi", top_complaint_reason: "coverage",
       min_churn_probability: 0.5}``, then calls /v1/offer/next-best per
    subscriber for the recommendation.
    """
    # TODO(E4/Ali): from cvm.features.store import query_cohort
    raise HTTPException(status_code=501, detail="Cohort query not implemented yet.")
