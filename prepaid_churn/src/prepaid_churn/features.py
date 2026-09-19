"""Engineered features on a window frame (ticket T5).

Input columns are the `prev_<base>` and `cur_<base>` columns from T4. Every
feature here uses only those two months, so windows A and B stay comparable.
"""

import numpy as np
import pandas as pd

NEUTRAL_SHARE = 0.5  # share value when there is nothing to share (no minutes at all)

# Per-month measures built from raw columns, then compared between the two months.
MEASURES = (
    "arpu",
    "total_og_mou",
    "total_ic_mou",
    "total_mou",
    "data_mb",
    "total_rech_amt",
    "total_rech_num",
)
# ARPU can be negative, so a share of two months is meaningless for it.
TREND_MEASURES = tuple(measure for measure in MEASURES if measure != "arpu")

FEATURES = {
    "days_since_last_rech_window": (
        "Days from the last recharge to the current month end, looking back over both months."
    ),
    "days_since_last_rech_data_window": (
        "Days from the last data pack recharge to the current month end, over both months."
    ),
    **{f"diff_{m}": f"Current minus previous month: {m}." for m in MEASURES},
    **{
        f"trend_{m}": (
            f"Current month share of {m} over both months (0.5 = stable, 0 = dropped to zero)."
        )
        for m in TREND_MEASURES
    },
    "cur_onnet_share": (
        "Share of on-net minutes in the current month; a falling share can mean calls "
        "moving to a second SIM."
    ),
    "diff_onnet_share": "Change in on-net share from the previous month.",
    "cur_incoming_share": (
        "Share of incoming minutes in the current month; a rising share can mean a "
        "'receiving only' SIM."
    ),
    "diff_incoming_share": "Change in incoming share from the previous month.",
}


def _share(part: pd.Series, whole: pd.Series) -> pd.Series:
    return (part / whole.where(whole != 0)).fillna(NEUTRAL_SHARE)


def _measure(frame: pd.DataFrame, prefix: str, measure: str) -> pd.Series:
    if measure == "total_mou":
        return frame[f"{prefix}_total_og_mou"] + frame[f"{prefix}_total_ic_mou"]
    if measure == "data_mb":
        return frame[f"{prefix}_vol_2g_mb"] + frame[f"{prefix}_vol_3g_mb"]
    return frame[f"{prefix}_{measure}"]


def _window_recency(frame: pd.DataFrame, recency: str, count: str) -> pd.Series:
    """T3 encodes "no recharge this month" as the number of days in the month.

    So without a recharge in the current month, days since the last one are
    the whole current month plus the previous month's value.
    """
    current, previous = frame[f"cur_{recency}"], frame[f"prev_{recency}"]
    return current.where(frame[f"cur_{count}"] > 0, current + previous)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the window frame with every feature in FEATURES added."""
    new = {
        "days_since_last_rech_window": _window_recency(
            frame, "days_since_last_rech", "total_rech_num"
        ),
        "days_since_last_rech_data_window": _window_recency(
            frame, "days_since_last_rech_data", "total_rech_data"
        ),
    }
    for measure in MEASURES:
        current, previous = _measure(frame, "cur", measure), _measure(frame, "prev", measure)
        new[f"diff_{measure}"] = current - previous
        if measure in TREND_MEASURES:
            new[f"trend_{measure}"] = _share(current, current + previous)
    for prefix in ("prev", "cur"):
        onnet, offnet = frame[f"{prefix}_onnet_mou"], frame[f"{prefix}_offnet_mou"]
        incoming = frame[f"{prefix}_total_ic_mou"]
        total = incoming + frame[f"{prefix}_total_og_mou"]
        new[f"{prefix}_onnet_share"] = _share(onnet, onnet + offnet)
        new[f"{prefix}_incoming_share"] = _share(incoming, total)
    for share in ("onnet_share", "incoming_share"):
        new[f"diff_{share}"] = new[f"cur_{share}"] - new[f"prev_{share}"]
    del new["prev_onnet_share"], new["prev_incoming_share"]
    added = pd.DataFrame(new, index=frame.index).astype(np.float64)
    return pd.concat([frame, added[list(FEATURES)]], axis=1)
