"""Model API tool -- call the scoring and decision endpoints.

Allowlisted endpoints only, and no write path. The agent may READ a pricing or
credit decision and explain it; it may not create or alter one.
"""

from __future__ import annotations

ALLOWED_ENDPOINTS = (
    "/v1/score/churn",
    "/v1/offer/next-best",
    "/v1/price/quote",
    "/v1/advance/limit",
    "/v1/subscriber/{id}",
    "/v1/network/site-risk",
    "/v1/text/classify",
)


def call_endpoint(path: str, payload: dict | None = None):
    raise NotImplementedError("TODO(E5)")


def build_tool():
    raise NotImplementedError("TODO(E5)")