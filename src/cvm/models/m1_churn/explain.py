"""SHAP explainability for Arm A.  Owner: E2

Per-subscriber waterfall plots surfaced in the Subscriber 360 screen, rendered
in PLAIN LANGUAGE -- "has not topped up in 23 days", not "days_since_last_topup
= 23, shap = +0.14". Every offer carries a human-readable reason; an opaque
personalised price is exactly what section 6.5 commits us not to ship.

Arm B is compared on calibration and lift, not interpretability, and the gap is
discussed in the report rather than papered over.

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