"""Dataset C -- IBM Telco Customer Churn (extended).  Owner: E1

Three roles, all small and fast so the Week-1 baseline is never blocked on
pipeline work:

* CLTV -- an independent lifetime-value benchmark for M2.
* Churn Reason -- a labelled categorical explanation, useful for sanity-
  checking that our churn drivers look like real ones.
* Churn Score -- a vendor baseline to beat.
"""

from __future__ import annotations

import pandas as pd


def fetch() -> None:
    """Download the extended IBM sample into data/raw/."""
    raise NotImplementedError("TODO(E1)")


def load() -> pd.DataFrame:
    raise NotImplementedError("TODO(E1)")


def reason_taxonomy() -> dict[str, str]:
    """Map IBM's free-text Churn Reason values onto our six reason codes."""
    raise NotImplementedError("TODO(E1/E6)")
