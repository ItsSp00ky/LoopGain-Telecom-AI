"""The head-to-head benchmark table. Deliverable D3.

Produces the comparison that the pitch slide and the report are built on:
LightGBM vs LSTM vs every classical baseline, on calibration curves, PR-AUC,
lift at deciles 1-3, and Brier.

Two reporting rules, both non-negotiable:

* Accuracy is NOT reported as a headline. It is meaningless at a 10-30% base
  rate. CI checks for it.
* The naive figures and the honest figures are reported side by side, with the
  gap explained. Published work on the Iranian dataset reaches ~97% accuracy
  and ~0.99 AUC; those numbers are inflated by ~300 duplicate rows and by the
  pre-computed `Customer Value` field. We reproduce them, then show they are
  wrong. We would rather show a defensible 0.78 PR-AUC than an indefensible 0.99.
"""

from __future__ import annotations

import pandas as pd


def run_benchmark(arm_a, arm_b, X_test, y_test, sequences_test) -> pd.DataFrame:
    raise NotImplementedError("TODO(E2)")


def naive_vs_honest(dataset: str = "uci_iranian") -> pd.DataFrame:
    """Reproduce the inflated published metrics, then the corrected ones.

    Rows: with duplicates + leaky field + random split (naive), then
    deduplicated + leaky field dropped + temporal split (honest).
    """
    raise NotImplementedError("TODO(E2)")


def architecture_verdict(results: pd.DataFrame) -> str:
    """Write the verdict paragraph. Whichever arm won, explain WHY."""
    raise NotImplementedError("TODO(E2)")