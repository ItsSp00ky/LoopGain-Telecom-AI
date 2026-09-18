"""Prepaid-adapted RFM-LE.  Owner: E1 / E3

Textbook RFM assumes purchase transactions. Prepaid has none, so each dimension
is redefined and two are added:

    R  Days since last REVENUE-GENERATING event (top-up or bundle purchase).
       Usage alone does not count -- a subscriber burning residual credit
       generates no revenue.
    F  Recharge count in 90d, PENALISED by recharge_gap_cv. Five regular
       recharges beat five erratic ones.
    M  Total LYD in 90d, PLUS the 30d-vs-prior-60d slope, so decline is
       visible inside the score itself.
    L  (added) 0.4*tenure + 0.3*consecutive_active_months + 0.3*lifetime_pct
    E  (added) Service breadth, normalised.

Quintile scoring 1-5 per dimension gives an R|F|M|L|E cell, collapsed into the
eight business segments in conf/features.yaml.
"""

from __future__ import annotations

import pandas as pd


def recency(df: pd.DataFrame) -> pd.Series:
    """Days since the last revenue-generating event. Not since last usage."""
    raise NotImplementedError("TODO(E1)")


def frequency(df: pd.DataFrame) -> pd.Series:
    """Recharge count over 90d, penalised by the coefficient of variation of gaps."""
    raise NotImplementedError("TODO(E1)")


def monetary(df: pd.DataFrame) -> pd.Series:
    """90d LYD total plus the 30d-vs-prior-60d slope."""
    raise NotImplementedError("TODO(E1)")


def loyalty(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("TODO(E1)")


def engagement(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("TODO(E1)")


def score_quintiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add R/F/M/L/E quintiles (1-5) and the concatenated cell string."""
    raise NotImplementedError("TODO(E1)")


def assign_segments(df: pd.DataFrame) -> pd.Series:
    """Collapse R|F|M|L|E cells into the eight business segments.

    Where these rules and the M2 K-Means clusters disagree, the disagreement is
    itself a dashboard insight -- surface it rather than reconciling it away.
    """
    raise NotImplementedError("TODO(E1/E3)")
