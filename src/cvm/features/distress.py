"""Financial-distress features. Feed M1, and gate M4 hard.

    balance_zero_hours_30d        hours at zero balance; no postpaid equivalent
    failed_bundle_attempts_30d    purchases rejected for insufficient balance
    consecutive_sub_5_lyd_recharges

These are the signals behind the chronic-distress exclusion in
conf/advance.yaml. A subscriber showing SUSTAINED rather than temporary
shortfall is excluded from advances regardless of their repayment probability.
Repeated advancing to the most financially stressed subscribers is how digital
credit has gone wrong elsewhere; the exclusion is mandatory, not tunable.

THE EXCLUSION FIRES AGAINST A HIGH REPAYMENT PROBABILITY, NOT ALONGSIDE IT.
That is the whole design. A chronically distressed subscriber often *does*
repay -- out of the next top-up, which then buys them nothing, which is the
zero-residual trap M4 exists to interrupt. A credit model optimising recovery
yield would lend to exactly these people. The objective here is solvency, so
affordability declines what PD would approve.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def _guards() -> dict:
    return load_conf("advance")["safety_guards"]


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Every distress signal, plus the composite the advance limit consumes."""
    out = pd.DataFrame(index=df.index)

    for column in (
        "balance_zero_hours_30d",
        "failed_bundle_attempts_30d",
        "consecutive_sub_5_lyd_recharges",
        "modal_recharge_amount_lyd",
        "airtime_advance_count_90d",
        "data_advance_count_90d",
        "days_to_settle",
        "unpaid_advance_days",
        "emergency_service_alternations_90d",
    ):
        if column in df.columns:
            out[column] = df[column]

    if "balance_zero_hours_30d" in df.columns:
        out["balance_zero_share_30d"] = (df["balance_zero_hours_30d"] / 720).clip(0, 1)

    # THE ZERO-RESIDUAL FLAG. The smallest card is 5 LYD and so is the data
    # advance, so a subscriber whose modal top-up is the floor clears the debt
    # and receives nothing: the whole card goes to the debt and they are back
    # at zero. This is the population M4's central finding is about, and it has
    # to be a feature before it can be a decision.
    if {"modal_recharge_amount_lyd"} <= set(df.columns):
        smallest = float(min(load_conf("market")["recharge"]["denominations_lyd"]))
        debt = float(load_conf("catalogue")["emergency_credit"]["net_fi_waqtuh"]["price_lyd"])
        out["at_recharge_floor"] = (df["modal_recharge_amount_lyd"] <= smallest).astype("int8")
        out["data_advance_leaves_nothing"] = (
            (df["modal_recharge_amount_lyd"] <= debt).astype("int8")
            if debt >= smallest
            else pd.Series(0, index=df.index, dtype="int8")
        )

    # Alternating between two mutually exclusive products is sustained
    # distress, and nothing in the incumbent design watches for it.
    if "emergency_service_alternations_90d" in df.columns:
        out["alternates_between_products"] = (df["emergency_service_alternations_90d"] > 0).astype(
            "int8"
        )

    out["chronic_distress"] = is_chronic_distress(df).astype("int8")

    log.info(
        "distress: %d features, %.1f%% chronically distressed, %.1f%% at the recharge floor",
        out.shape[1],
        100 * out["chronic_distress"].mean(),
        (
            100 * out.get("at_recharge_floor", pd.Series(dtype=float)).mean()
            if "at_recharge_floor" in out
            else float("nan")
        ),
    )
    return out


def is_chronic_distress(df: pd.DataFrame) -> pd.Series:
    """Sustained shortfall, not a single bad month. See conf/advance.yaml.

    Three independent signals, and TWO must fire. One alone is a bad month --
    anyone can run out of credit once, and excluding on that would deny the
    facility to most of the base for no benefit. Two together is a pattern:

      * at a zero balance for a large share of the month
      * repeatedly recharging at the very bottom of the ladder
      * carrying unpaid advance debt for a long time, or alternating between
        the two mutually exclusive products

    Deliberately conservative in the direction of exclusion. The asymmetry is
    intentional: wrongly declining a subscriber costs a small amount of
    revenue, and wrongly lending to a chronically distressed one is how this
    kind of product causes harm.
    """
    exclusion = _guards()["chronic_distress_exclusion"]
    if not exclusion.get("enabled", True):
        raise ValueError(
            "chronic_distress_exclusion is disabled in conf/advance.yaml. It is marked "
            "mandatory there for a reason and tests/guardrails/ asserts it."
        )

    # Thresholds read from config, never inlined. Each is `<field>_above`, so
    # the config reads as the sentence the guard implements.
    thresholds: dict[str, int] = exclusion["signals"]
    signals = pd.DataFrame(index=df.index)

    for key, limit in thresholds.items():
        if not key.endswith("_above"):
            continue  # declining_recharge_trend_months needs a panel we do not hold
        column = key[: -len("_above")]
        if column not in df.columns:
            continue
        signals[column] = df[column] > limit

    if signals.empty:
        raise KeyError(
            f"none of {sorted(thresholds)} are present, so no distress signal can fire "
            "and the exclusion would silently pass everyone."
        )

    # TWO signals, not one. Anyone can run out of credit once; excluding on a
    # single bad month would deny the facility to most of the base for no
    # benefit. Two together is a pattern.
    #
    # The asymmetry is deliberate: wrongly declining costs a little revenue,
    # wrongly lending to a chronically distressed subscriber is how this kind
    # of product causes harm. `require_sustained_months` in the config says the
    # same thing across time, and needs a panel this branch does not yet hold.
    chronic = signals.sum(axis=1) >= 2

    log.info(
        "chronic distress: %.1f%% excluded on %d of %d configured signals -- %s",
        100 * chronic.mean(),
        signals.shape[1],
        len(thresholds),
        {c: f"{signals[c].mean():.1%}" for c in signals.columns},
    )
    return chronic
