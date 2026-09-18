"""Financial-distress features. Feed M1, and gate M4 hard.

    balance_zero_hours_30d        hours at zero balance; no postpaid equivalent
    failed_bundle_attempts_30d    purchases rejected for insufficient balance
    consecutive_sub_5_lyd_recharges

These are the signals behind the chronic-distress exclusion in
conf/advance.yaml. A subscriber showing SUSTAINED rather than temporary
shortfall is excluded from advances regardless of their repayment probability.
Repeated advancing to the most financially stressed subscribers is how digital
credit has gone wrong elsewhere; the exclusion is mandatory, not tunable.
"""

from __future__ import annotations

import pandas as pd


def build(df: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError("TODO(E1)")


def is_chronic_distress(df: pd.DataFrame) -> pd.Series:
    """Sustained shortfall, not a single bad month. See conf/advance.yaml."""
    raise NotImplementedError("TODO(E1/E2)")
