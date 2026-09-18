"""Uplift targeting.  Owner: E4

Budget goes only to PERSUADABLES. Never to sure things, never to lost causes.

Method: a simple two-model difference (treated response model minus control
response model), not a causal-inference library. At this data scale the extra
machinery of EconML buys precision we cannot validate on synthetic response
anyway, and the simpler method is defensible in a three-minute pitch. That is a
deliberate choice, recorded in docs/adr/, not an omission.

SLEEPING-DOGS GUARD: contacting a dormant-but-not-departing subscriber can
remind them to leave. The negative-effect quadrant is excluded from all three
retention-ladder stages.
"""

from __future__ import annotations

import pandas as pd


def train_two_model(X: pd.DataFrame, y: pd.Series, treated: pd.Series) -> tuple:
    """Fit the treated-response and control-response models separately."""
    raise NotImplementedError("TODO(E4)")


def predict_uplift(model_treated, model_control, X: pd.DataFrame) -> pd.Series:
    """Estimated treatment effect per subscriber."""
    raise NotImplementedError("TODO(E4)")


def classify_quadrant(uplift: pd.Series, baseline_response: pd.Series) -> pd.Series:
    """persuadable | sure_thing | lost_cause | sleeping_dog."""
    raise NotImplementedError("TODO(E4)")


def assign_control_holdout(cohort: pd.DataFrame, fraction: float = 0.10) -> pd.Series:
    """Randomised holdout. Without it there is no way to isolate net margin
    impact, which is exactly pain point P4."""
    raise NotImplementedError("TODO(E4)")
