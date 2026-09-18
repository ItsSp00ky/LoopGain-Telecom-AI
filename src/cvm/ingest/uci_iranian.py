"""Dataset A -- Iranian Churn Dataset (UCI 563). PRIMARY source.  Owner: E1

Closest public analogue on four axes at once: prepaid, MENA-region, carries a
network-quality feature (call failures), and its 9-month observation / 3-month
prediction gap is exactly the operational framing a real campaign needs.

Two mandatory corrections before this data is usable:

* ~300 exact duplicate rows (~9.5%) -- deduplicate.
* The pre-computed `Customer Value` field partially encodes the outcome --
  drop it from the feature matrix. This is why our reported metrics are lower
  than the published ~97% accuracy / ~0.99 AUC, and that gap is a headline
  result, not an embarrassment.
"""

from __future__ import annotations

import pandas as pd


def fetch() -> pd.DataFrame:
    """Download via ucimlrepo (id=563). Cached under data/raw/."""
    raise NotImplementedError("TODO(E1): from ucimlrepo import fetch_ucirepo")


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop exact-match duplicates. Returns (clean_df, n_dropped).

    Log n_dropped to MLflow -- it is evidence for pitch point 4.
    """
    raise NotImplementedError("TODO(E1)")


def load(drop_leaky: bool = True) -> pd.DataFrame:
    """Fetch, validate, deduplicate, and optionally drop `Customer Value`.

    ``drop_leaky=False`` exists only to reproduce the inflated published
    figures for the honest-vs-naive comparison in the report.
    """
    raise NotImplementedError("TODO(E1)")
