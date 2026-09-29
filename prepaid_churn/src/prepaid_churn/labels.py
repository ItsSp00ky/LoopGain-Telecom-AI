"""Inactivity rules for prepaid churn.

T4 builds the training labels on top of these rules.
"""

import pandas as pd

# upGrad's definition: no incoming calls, no outgoing calls and no mobile data in the month.
USAGE_BASES = ("total_ic_mou", "total_og_mou", "vol_2g_mb", "vol_3g_mb")
# Revenue view of prepaid inactivity: no airtime recharge and no data recharge in the month.
RECHARGE_BASES = ("total_rech_num", "total_rech_data")


def _all_zero(df: pd.DataFrame, bases: tuple[str, ...], month: int) -> pd.Series:
    columns = [f"{base}_{month}" for base in bases]
    return df[columns].fillna(0).eq(0).all(axis=1)


def usage_inactive(df: pd.DataFrame, month: int) -> pd.Series:
    """True where the customer had no calls and no data in `month`. Missing counts as zero."""
    return _all_zero(df, USAGE_BASES, month)


def recharge_inactive(df: pd.DataFrame, month: int) -> pd.Series:
    """True where the customer made no recharge of any kind in `month`. Missing counts as zero."""
    return _all_zero(df, RECHARGE_BASES, month)
