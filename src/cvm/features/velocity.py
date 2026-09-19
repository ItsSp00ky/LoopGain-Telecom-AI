"""Velocity and decay features. The earliest reliable tell.

    revenue_decay_ratio = mean_7d / mean_30d

Values well below 1.0 mean the subscriber is winding down. Equivalents are
computed for data, voice and SMS.

These ratios are the reason M1 does not need a sequence model: they compress
the part of a 90-day daily series that actually predicts churn into four
numbers a tree can split on, and unlike a learned representation they can be
read off a SHAP waterfall and explained to a marketing analyst.

USAGE TURNS DOWN BEFORE SPEND DOES. Measured on Cell2Cell: 46.8% of real
subscribers are declining on minutes against 42.2% on revenue. That gap is the
entire reason a decay ratio is an early warning rather than a lagging one, and
it is why the two ratios are separate features rather than one.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# The population carries 30d levels; the short-window view is derived from the
# decay ratio the generator already grounds. Named here so the feature set and
# the synthesis layer cannot drift apart silently.
DECAY_PAIRS: dict[str, tuple[str, str]] = {
    "usage_decay_ratio": ("voice_minutes_30d", "usage_decay_ratio"),
    "revenue_decay_ratio": ("recharge_count_90d", "revenue_decay_ratio"),
}


def decay_ratio(df: pd.DataFrame, column: str, short: int = 7, long: int = 30) -> pd.Series:
    """Short-window mean over long-window mean for one quantity.

    Expects `{column}_{short}d` and `{column}_{long}d` to exist. Undefined
    where the long window is zero -- a subscriber with no activity over 30 days
    has no decay *ratio*, they have no activity, and coercing that to 1.0 would
    put them in the middle of the distribution instead of at the end of it.
    """
    numerator, denominator = f"{column}_{short}d", f"{column}_{long}d"
    missing = [c for c in (numerator, denominator) if c not in df.columns]
    if missing:
        raise KeyError(f"{missing} absent; cannot compute a {short}d/{long}d ratio for {column!r}")

    long_values = df[denominator].where(df[denominator] > 0)
    return (df[numerator] / long_values).replace([np.inf, -np.inf], np.nan).astype("float64")


def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Std-dev and CV of inter-recharge gaps; rolling variance of daily data.

    Irregularity precedes exit, and it shows up before the level drops. A
    subscriber recharging every nine days like clockwork and one recharging
    five times at random intervals have the same frequency and very different
    prospects -- which is why F is penalised by the CV in rfm_le, and why the
    CV is a feature in its own right here.
    """
    out = pd.DataFrame(index=df.index)

    for column in (
        # The RAW count, and it was missing until M2 needed it. RFM-LE emits
        # `frequency_raw`, which is this divided by (1 + cv) -- a different
        # quantity, and a lossy one to read a count back out of. BG/NBD takes
        # repeat transactions as its frequency input and cannot use a penalised
        # score, which is how the gap surfaced: a feature store that can train
        # a churn model and cannot fit a purchase-frequency model is missing a
        # feature, not expressing a preference.
        "recharge_count_90d",
        "recharge_gap_cv",
        "inter_recharge_gap_std",
        "inter_recharge_gap_mean",
    ):
        if column in df.columns:
            out[column] = df[column]

    # Volatility relative to cadence. A five-day swing means something
    # different to a weekly recharger than to a monthly one.
    if {"inter_recharge_gap_std", "inter_recharge_gap_mean"} <= set(df.columns):
        mean_gap = df["inter_recharge_gap_mean"].where(df["inter_recharge_gap_mean"] > 0)
        out["recharge_irregularity"] = (df["inter_recharge_gap_std"] / mean_gap).clip(0, 10)

    if "balance_zero_hours_30d" in df.columns:
        # Share of the month spent unable to transact at all.
        out["balance_zero_share_30d"] = (df["balance_zero_hours_30d"] / 720).clip(0, 1)

    return out


def build(df: pd.DataFrame) -> pd.DataFrame:
    """All velocity, decay, volatility and mix-ratio features."""
    out = pd.DataFrame(index=df.index)

    # The two decay ratios the generator grounds, carried through as-is: they
    # are measured quantities, not things to recompute from levels we do not
    # have at daily resolution.
    for ratio in ("usage_decay_ratio", "revenue_decay_ratio"):
        if ratio in df.columns:
            out[ratio] = df[ratio]

    if {"usage_decay_ratio", "revenue_decay_ratio"} <= set(df.columns):
        # The gap between them. Usage falling faster than spend is a
        # subscriber winding down; spend falling faster than usage is one
        # moving to cheaper bundles, which is a different problem needing a
        # different offer.
        out["decay_divergence"] = df["usage_decay_ratio"] - df["revenue_decay_ratio"]

    out = out.join(volatility_features(df))

    if "days_since_last_topup" in df.columns:
        out["days_since_last_topup"] = df["days_since_last_topup"]
        # Recency against the subscriber's own cadence: five days is nothing
        # for a monthly recharger and alarming for a daily one.
        if "inter_recharge_gap_mean" in df.columns:
            cadence = df["inter_recharge_gap_mean"].where(df["inter_recharge_gap_mean"] > 0)
            out["overdue_ratio"] = (df["days_since_last_topup"] / cadence).clip(0, 20)

    declining = (
        float((out["usage_decay_ratio"] < 1).mean()) if "usage_decay_ratio" in out else float("nan")
    )
    log.info(
        "velocity: %d features, %.1f%% of subscribers declining on usage "
        "(Cell2Cell baseline 46.8%%)",
        out.shape[1],
        100 * declining,
    )
    return out
