"""Serving path for M1. Called by the API, must stay inside 200 ms p95."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from cvm.api.schemas import ChurnScore, ChurnScoreRequest, ChurnScoreResponse, ShapContribution

log = logging.getLogger(__name__)

MODEL_KEY = "m1_churn"


def score_batch(payload: ChurnScoreRequest, models: dict[str, Any]) -> ChurnScoreResponse:
    """Score a batch of subscribers from the feature store.

    Features are READ, never recomputed. A serving path that rebuilds features
    is a serving path that will eventually compute them differently from the
    training path, and training/serving skew of that kind is silent -- the
    model returns plausible numbers that are wrong.

    `as_of` goes to the offline store and returns each subscriber's latest
    snapshot at or before that date. Without it the online store answers, which
    is one row per subscriber and the production path.
    """
    from cvm.features import store
    from cvm.models.m1_churn.gradient_boosting import prepare_matrix

    model = models.get(MODEL_KEY)
    if model is None:
        raise RuntimeError(f"{MODEL_KEY} is not loaded; the API must load it at startup")

    ids = [str(s) for s in payload.subscriber_ids]
    as_of = payload.as_of.isoformat() if payload.as_of else None
    features = store.get_features(subscriber_ids=ids, as_of=as_of)

    missing = set(ids) - set(features["subscriber_id_hashed"].astype(str))
    if missing:
        # Named rather than silently skipped. A caller that asked for 500 and
        # got 480 back with no explanation cannot tell a cold subscriber from
        # a bug, and will assume the latter.
        raise KeyError(
            f"{len(missing)} subscriber(s) not in the feature store: {sorted(missing)[:5]}"
        )

    columns = getattr(model, "columns", None)
    X, _ = prepare_matrix(features, columns=columns)
    probability = model.predict_proba(X)[:, 1]

    # Deciles over THIS BATCH, which is a deliberate limitation and a real one:
    # a batch of 10 subscribers has a meaningless decile. The population
    # reference cut-points belong in the model artefact and are a phase 8
    # concern, when the decision engine needs them to be stable across calls.
    decile = _deciles(probability)

    # Always. ChurnScoreRequest has no opt-out and forbids extra fields, and
    # section 6.5 commits to a reason for every score -- an endpoint that can
    # return a bare probability is one that eventually will.
    drivers = _explain(model, X)

    survival_window = _survival(models, X) if payload.include_survival else None

    scores = [
        ChurnScore(
            subscriber_id=str(subscriber),
            churn_probability=float(probability[i]),
            calibrated=True,
            decile=int(decile[i]),
            time_to_churn_days=_days(survival_window, i),
            top_drivers=drivers[i],
            model_version=getattr(model, "version", "m1-dev"),
        )
        for i, subscriber in enumerate(features["subscriber_id_hashed"].astype(str))
    ]

    latest = pd.to_datetime(features["snapshot_date"]).max().date()
    log.info(
        "scored %d subscribers as of %s, mean probability %.4f",
        len(scores),
        latest,
        probability.mean(),
    )

    return ChurnScoreResponse(scores=scores, scored_at=datetime.now(UTC), as_of=latest)


def _deciles(probability: np.ndarray) -> np.ndarray:
    """1 is the highest risk. Ties share a decile rather than splitting."""
    if len(probability) == 1:
        return np.array([1])
    ranked = pd.Series(probability).rank(pct=True, method="average")
    return np.ceil((1 - ranked) * 10).clip(1, 10).astype(int).to_numpy()


def _explain(model, X: pd.DataFrame) -> list[list[ShapContribution]]:
    """Top drivers per row. Degrades to empty rather than failing the request.

    An explanation is required for every offer that reaches a subscriber, and
    it is produced at decision time in phase 8 -- not here. A scoring call that
    503s because SHAP could not load would take the whole dashboard down for a
    cosmetic reason, so this path logs and returns nothing.
    """
    from cvm.models.m1_churn.explain import drivers_for_batch, explainer_for

    background = getattr(model, "background", None)
    if background is None:
        # Explaining a batch against itself is what produced five zero bars on
        # a subscriber scored at 1.0000. Loud, because the request still
        # succeeds -- it just stops carrying a reason, and section 6.5 commits
        # to one for every score.
        log.error(
            "m1_churn carries no SHAP background; retrain M1 so the bundle stores one. "
            "Drivers will be omitted rather than computed against the request itself."
        )

    try:
        explainer = explainer_for(model, X, background=background)
        # ONCE FOR THE BATCH, not once per row. Calling shap_values on a single
        # row 500 times measured 2,188 ms for 500 subscribers against a 200 ms
        # p95 budget; batching it is 20x faster and returns the same numbers,
        # because the explainer is stateless over rows.
        return [
            [
                ShapContribution(
                    feature=d["feature"],
                    value=d["value"],
                    contribution=d["contribution"],
                    plain_language=d["explanation"],
                )
                for d in row
            ]
            for row in drivers_for_batch(explainer, X)
        ]
    except Exception as exc:
        log.warning("shap unavailable, serving scores without drivers: %s", exc)
        return [[] for _ in range(len(X))]


def _days(window: np.ndarray | None, i: int) -> int | None:
    """None rather than an integer when the expectation is not finite.

    `np.asarray(np.nan).astype(int)` is -9223372036854775808, and an API that
    answers "we do not know" with INT64_MIN is worse than one that answers
    nothing: the value is well-formed, satisfies the schema, survives every
    type check, and is wrong by nine quintillion days. A consumer rendering it
    on a screen shows a date in the year -25 billion; one summing it over a
    cohort gets an overflow. None is the honest answer and the contract already
    allows it.
    """
    if window is None:
        return None
    value = float(window[i])
    if not np.isfinite(value):
        log.warning("m1b returned a non-finite expectation for row %d; reporting None", i)
        return None
    return round(value)


def _survival(models: dict[str, Any], X: pd.DataFrame) -> np.ndarray | None:
    """Expected days to churn from M1b, where the model is loaded.

    Imputed with the TRAINING medians the artefact carries, never with the
    batch's own. The batch is frequently one row, and the median of one NaN is
    that same NaN -- see fit_cox for what that produced.
    """
    model = models.get("m1b_survival")
    if model is None:
        log.warning("include_survival was requested but m1b_survival is not loaded")
        return None

    columns = getattr(model, "design_columns", None)
    medians = getattr(model, "design_medians", None)
    if columns is None or medians is None:
        # An artefact trained before fit_cox carried its design. Say so rather
        # than improvising from the request, which is what produced INT64_MIN.
        log.error(
            "m1b_survival carries no training design; retrain M1b. "
            "Falling back to the request's own statistics, which is unsound."
        )
        columns, medians = list(X.columns), None

    design = X.reindex(columns=columns, fill_value=0.0)
    design = design.fillna(design.median() if medians is None else medians)
    # A column that was entirely absent in training has no median either. Zero
    # is the neutral value for this matrix -- every column is a count, a ratio
    # or an amount -- and it keeps one missing feature from voiding the row.
    design = design.fillna(0.0)

    return np.asarray(model.predict_expectation(design), dtype=float)
