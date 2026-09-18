"""Customer lifetime value: BG/NBD + Gamma-Gamma.  Owner: E3

Each RECHARGE is treated as a transaction. The non-contractual,
alive-or-dead-unobserved assumption behind BG/NBD is literally true in prepaid,
which makes this an unusually clean fit rather than a borrowed one -- worth
saying out loud in the report.

Benchmarked against the IBM CLTV field so the number is not self-graded.

CLV's real job in this system is as the BUDGET CEILING: total retention spend
on a subscriber never exceeds a configurable fraction of predicted 12-month CLV
(default 15%). That single constraint is what makes the pricing engine
defensible to a CFO, and it is why this module is a dependency of the
guardrails rather than a reporting nicety.
"""

from __future__ import annotations

import pandas as pd


def fit_bg_nbd(rfm_summary: pd.DataFrame):
    raise NotImplementedError("TODO(E3)")


def fit_gamma_gamma(rfm_summary: pd.DataFrame):
    raise NotImplementedError("TODO(E3)")


def predict_clv(bgf, ggf, rfm_summary: pd.DataFrame, months: int = 12) -> pd.Series:
    raise NotImplementedError("TODO(E3)")


def benchmark_against_ibm(predicted: pd.Series, ibm_cltv: pd.Series) -> dict[str, float]:
    """MAE, RMSE, MAPE and Spearman against the IBM CLTV field."""
    raise NotImplementedError("TODO(E3)")
