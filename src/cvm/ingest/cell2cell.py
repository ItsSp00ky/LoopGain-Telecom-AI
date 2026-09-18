"""Dataset B -- Cell2Cell (Duke / Teradata).  Owner: E1

Supplies volume and, critically, trend and degradation features: changem
(percent change in minutes of use), changer (percent change in revenue),
dropvce, blckvce, unansvce. These are the direct ancestors of our
revenue_decay_ratio_7d_30d.

Also the reason the M1 LSTM benchmark is meaningful at all -- an LSTM on 3,000
rows would prove nothing. The 19,999-row unlabelled holdout doubles as the
inference load test for the p95 latency evidence.
"""

from __future__ import annotations

import pandas as pd


def fetch() -> None:
    """Download from Kaggle (jpacse/datasets-for-churn-telecom) into data/raw/."""
    raise NotImplementedError("TODO(E1): kaggle API; needs KAGGLE_USERNAME/KAGGLE_KEY")


def load(split: str = "labelled") -> pd.DataFrame:
    """Load the labelled split (51,048 rows) or the holdout (19,999 rows)."""
    raise NotImplementedError("TODO(E1)")