"""M1b -- time-to-churn.  Owner: E2

Classification answers *if*. Survival answers *when*. Retention economics are
timing-sensitive: intervening 40 days early wastes budget, 5 days late wastes
everything.

Cox Proportional Hazards (lifelines), with a Random Survival Forest challenger.
Reported metric: concordance index.

The hazard curve output DEFINES the retention ladder stage boundaries. Rather
than picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves
identify where recovery probability falls sharply, and those inflection points
become the cut-points -- recomputed per segment.
"""

from __future__ import annotations

import pandas as pd


def fit_cox(df: pd.DataFrame, duration_col: str, event_col: str):
    raise NotImplementedError("TODO(E2)")


def fit_rsf(df: pd.DataFrame, duration_col: str, event_col: str):
    raise NotImplementedError("TODO(E2)")


def hazard_inflection_points(model, segment: str | None = None) -> list[int]:
    """Day indices where recovery probability falls sharply.

    Consumed by cvm.decision.ladder to set stage boundaries.
    """
    raise NotImplementedError("TODO(E2)")
