"""SHAP explainability.  Owner: E2

Per-subscriber waterfall plots surfaced in the Subscriber 360 screen, rendered
in PLAIN LANGUAGE -- "has not topped up in 23 days", not "days_since_last_topup
= 23, shap = +0.14". Every offer carries a human-readable reason; an opaque
personalised price is exactly what section 6.5 commits us not to ship.

Every model in M1 is a tree model, so this is exact SHAP rather than an
approximation -- which is part of why the module's scope is tabular. There is
no score in this component whose reasoning we cannot surface.

SHAP contribution shares are also how we attribute churn risk to causes --
network quality, pricing, declining engagement -- which is what makes the
Subscriber 360 explanation more than a number.
"""

from __future__ import annotations

import pandas as pd


def tree_explainer(model, X: pd.DataFrame):
    raise NotImplementedError("TODO(E2)")


def top_drivers(explainer, row: pd.Series, k: int = 5) -> list[dict]:
    raise NotImplementedError("TODO(E2)")


def to_plain_language(feature: str, value: float, contribution: float) -> str:
    """Render one SHAP contribution as a sentence a marketing analyst can read."""
    raise NotImplementedError("TODO(E2)")


def attribution_by_family(explainer, X: pd.DataFrame) -> pd.DataFrame:
    """Share of churn risk attributable to each feature family, per subscriber.

    Families are defined in conf/features.yaml: velocity/decay, distress,
    leakage, network quality, credit. Aggregating SHAP to the family level is
    what makes the explanation legible to a marketing analyst -- eighty
    individual contributions are not.
    """
    raise NotImplementedError("TODO(E2)")
