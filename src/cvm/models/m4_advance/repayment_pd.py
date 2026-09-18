"""Probability of repayment by the next recharge.  Owner: E2

Two heads, one per Almadar emergency product, because the debt sizes and the
eligible populations differ: 1/3/5 LYD airtime versus a flat 5 LYD for data.

Shares M1's feature matrix. Calibrated, because decision.advance_limit maps
the probability onto LYD exposure bands -- an uncalibrated score would set
real credit limits from meaningless numbers.
"""

from __future__ import annotations

import pandas as pd


def train(X: pd.DataFrame, y: pd.Series, product: str = "airtime", **params):
    """Target: settled by next recharge, censored at 14 days.

    ``product`` is "airtime" or "data" -- see conf/advance.yaml#targets.
    """
    raise NotImplementedError("TODO(E2)")


def predict_pd(model, X: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("TODO(E2)")


def predict_lockout_risk(model, X: pd.DataFrame, limit_lyd: pd.Series) -> pd.Series:
    """Probability this advance leaves unpaid debt at day 14.

    Unpaid debt blocks re-subscription, so the subscriber loses access to the
    very service they reached for -- and a subscriber locked out of emergency
    credit is a churn risk.

    Separate from PD on purpose: the system's job is to PREVENT that outcome,
    not to optimise recovery after it, so it needs its own number a reviewer
    can see.

    NOT the same as Libyana's line-reset outcome, which is undocumented for
    Almadar. Do not describe it as such.
    """
    raise NotImplementedError("TODO(E2)")