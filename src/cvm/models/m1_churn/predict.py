"""Serving path for M1. Called by the API, must stay inside 200 ms p95."""

from __future__ import annotations

from typing import Any

from cvm.api.schemas import ChurnScoreRequest, ChurnScoreResponse


def score_batch(payload: ChurnScoreRequest, models: dict[str, Any]) -> ChurnScoreResponse:
    raise NotImplementedError("TODO(E2)")