"""Explicit hazard function for label generation.

Documented here and in docs/architecture.md rather than buried, for two
reasons: the model needs recoverable signal, and the evaluation has to be
honest about being a simulation ground truth.

Any field used here is automatically excluded from the feature matrix. That
exclusion is enforced in tests/leakage/, not left to discipline.
"""

from __future__ import annotations

import pandas as pd

# Fields this module reads. features.yaml excludes every one of them.
LABEL_GENERATING_FIELDS: tuple[str, ...] = (
    "days_since_last_topup",
    "recharge_gap_cv",
    "balance_zero_hours_30d",
    "onnet_ratio",
    "incoming_outgoing_ratio",
    "cell_outage_hours_30d",
)


def hazard(df: pd.DataFrame, base_monthly_churn: float = 0.035) -> pd.Series:
    """Per-subscriber monthly churn hazard."""
    raise NotImplementedError("TODO(E1)")


def generate_labels(df: pd.DataFrame, seed: int | None = None) -> pd.DataFrame:
    """Draw silent_churn_30d from the hazard, respecting the 15-day gap."""
    raise NotImplementedError("TODO(E1)")