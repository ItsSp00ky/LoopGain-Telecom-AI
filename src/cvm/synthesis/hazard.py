"""Explicit hazard function for label generation.

Documented here and in docs/architecture.md rather than buried, for two
reasons: the model needs recoverable signal, and the evaluation has to be
honest about being a simulation ground truth.

Two categories, and confusing them breaks the project in opposite directions.
tests/leakage/ enforces the distinction.
"""

from __future__ import annotations

import pandas as pd

# --- DRIVERS: behavioural fields the hazard is a function of ----------------
#
# These STAY in the feature matrix, deliberately. The hazard is built from
# observable behaviour precisely so the signal is recoverable -- a model that
# cannot see any driver of the label has nothing to learn, and the whole
# exercise would be measuring noise.
#
# What makes this honest rather than circular is stated plainly in the report:
# these metrics are computed against a simulation whose ground truth we wrote,
# so they demonstrate that the pipeline and decision logic work. They are not
# evidence of production performance.
LABEL_DRIVER_FIELDS: tuple[str, ...] = (
    "days_since_last_topup",
    "recharge_gap_cv",
    "balance_zero_hours_30d",
    "onnet_ratio",
    "incoming_outgoing_ratio",
    "service_outage_hours_30d",
)

# --- ARTIFACTS: fields that trivially encode the outcome -------------------
#
# These MUST NEVER reach the feature matrix. Any one of them lets a model
# reconstruct the label directly, which is the subtlest and most damaging
# failure mode available to this project: a model that scores beautifully and
# knows nothing.
#
# conf/features.yaml#leakage_controls.excluded_columns must be a superset of
# this tuple, and tests/leakage/ fails the build if it drifts.
LABEL_ARTIFACT_FIELDS: tuple[str, ...] = (
    "hazard_score",
    "churn_date",
    "silent_churn_30d",
    "days_to_churn",
)


def hazard(df: pd.DataFrame, base_monthly_churn: float = 0.035) -> pd.Series:
    """Per-subscriber monthly churn hazard."""
    raise NotImplementedError("TODO(E1)")


def generate_labels(df: pd.DataFrame, seed: int | None = None) -> pd.DataFrame:
    """Draw silent_churn_30d from the hazard, respecting the 15-day gap."""
    raise NotImplementedError("TODO(E1)")