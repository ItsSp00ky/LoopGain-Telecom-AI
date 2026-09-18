"""Sequence tensors for M1 Arm B.  Owner: E1

Per-subscriber 90 x k daily matrices of recharge, data, voice and SMS.

NO hand aggregation is applied. That is the entire point of the benchmark: we
want to know whether the LSTM learns the decay patterns that features/velocity.py
engineers explicitly. Pre-aggregating here would make the comparison
meaningless and the result unreportable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_tensors(
    daily: pd.DataFrame,
    length_days: int = 90,
    channels: tuple[str, ...] = ("recharge_lyd", "data_mb", "voice_min", "sms_count"),
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (X, y, subscriber_ids) with X shaped (n, length_days, k).

    Short histories are left-padded with the masking value so the Keras Masking
    layer can ignore them, rather than being dropped -- new SIMs are exactly
    the population we care about in the Bronze tier.
    """
    raise NotImplementedError("TODO(E1)")


def save_npz(path: str, X: np.ndarray, y: np.ndarray, ids: list[str]) -> None:
    raise NotImplementedError("TODO(E1)")