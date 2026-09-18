"""Dual-SIM share-of-wallet leakage detection.  Owner: E1

Carrying both an Almadar and a Libyana SIM is normal, driven by patchy
coverage and on-net pricing. "Active" therefore misleads: a subscriber can stay
technically active while 80% of their spend has moved. Conventional churn
models score them as retained; in revenue terms they are half-lost.

The leading indicator is measurable and currently unmeasured:

    incoming-call volume holding steady
    while outgoing volume AND off-net share both rise

That subscriber has quietly made this their RECEIVING SIM.

Note this module is about WALLET leakage (a commercial phenomenon). Data
leakage -- the methodological problem -- lives in features/splits.py and
tests/leakage/. Two different things that share a word.
"""

from __future__ import annotations

import pandas as pd


def incoming_outgoing_ratio(df: pd.DataFrame) -> pd.Series:
    """Primary leakage detector."""
    raise NotImplementedError("TODO(E1)")


def onnet_ratio(df: pd.DataFrame) -> pd.Series:
    """Falling on-net share means the social graph is migrating."""
    raise NotImplementedError("TODO(E1)")


def calling_graph_contraction(df: pd.DataFrame) -> pd.Series:
    """Trend in distinct called numbers. Contraction precedes silent exit."""
    raise NotImplementedError("TODO(E1)")


def leakage_score(df: pd.DataFrame) -> pd.Series:
    """Composite 0-1 score. Surfaced on the Subscriber 360 screen and used by
    M3 to decide whether an on-net pack is the right instrument."""
    raise NotImplementedError("TODO(E1)")
