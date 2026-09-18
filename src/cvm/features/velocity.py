"""Velocity and decay features. The earliest reliable tell.

    revenue_decay_ratio = mean_7d / mean_30d

Values well below 1.0 mean the subscriber is winding down. Equivalents are
computed for data, voice and SMS. These are the hand-engineered features that
Arm A gets and Arm B (the LSTM) deliberately does not -- the benchmark asks
whether the network can learn them from raw daily sequences instead.
"""

from __future__ import annotations

import pandas as pd


def decay_ratio(df: pd.DataFrame, column: str, short: int = 7, long: int = 30) -> pd.Series:
    raise NotImplementedError("TODO(E1)")


def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Std-dev and CV of inter-recharge gaps; rolling variance of daily data.

    Irregularity precedes exit, and it shows up before the level drops.
    """
    raise NotImplementedError("TODO(E1)")


def build(df: pd.DataFrame) -> pd.DataFrame:
    """All velocity, decay, volatility and mix-ratio features."""
    raise NotImplementedError("TODO(E1)")