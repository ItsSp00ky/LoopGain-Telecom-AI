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

WHAT WE CAN AND CANNOT CLAIM. The ratio's DISTRIBUTION is grounded: Cell2Cell
carries received and placed voice as separate columns, 0% null across 100,000
rows, median 0.280. Its PREDICTIVE POWER is not. In that data it does not
separate churners at all -- 0.282 against 0.278 -- which is exactly what a
single-SIM postpaid market should look like, because there is no receiving-SIM
behaviour there to detect. The hypothesis is specific to dual-SIM prepaid and
is testable only on real Libyan data. The report says so.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def _leakage_conf() -> dict:
    return load_conf("features")["families"]["leakage"]


def incoming_outgoing_ratio(df: pd.DataFrame) -> pd.Series:
    """Primary leakage detector.

    Above 1.0 means a subscriber receives more than they place: other people
    still call them, and they do their calling elsewhere. That is what a
    receiving SIM looks like from the operator's side.
    """
    if "incoming_outgoing_ratio" in df.columns:
        return df["incoming_outgoing_ratio"].astype("float64")

    missing = [c for c in ("voice_received_30d", "voice_placed_30d") if c not in df.columns]
    if missing:
        raise KeyError(f"cannot compute the leakage ratio: {missing} absent")
    placed = df["voice_placed_30d"].where(df["voice_placed_30d"] > 0)
    return (df["voice_received_30d"] / placed).replace([np.inf, -np.inf], np.nan)


def onnet_ratio(df: pd.DataFrame) -> pd.Series:
    """Falling on-net share means the social graph is migrating.

    On-net calling is cheaper, so a subscriber whose contacts are all on
    Almadar has a reason to stay. As their circle moves to the competitor,
    their own off-net share rises before they do -- the graph leaves first.
    """
    if "onnet_ratio" in df.columns:
        return df["onnet_ratio"].astype("float64")
    if "offnet_share_30d" in df.columns:
        return (1 - df["offnet_share_30d"]).astype("float64")
    raise KeyError("neither onnet_ratio nor offnet_share_30d is present")


def calling_graph_contraction(df: pd.DataFrame) -> pd.Series:
    """Trend in distinct called numbers. Contraction precedes silent exit.

    Returned as a 0-1 contraction score rather than a raw count: the absolute
    number of contacts varies enormously between subscribers and says little,
    while a subscriber calling a narrowing set of numbers is a subscriber
    disengaging. Percentile-ranked within the population and inverted, so 1.0
    is the most contracted.
    """
    if "distinct_called_numbers_30d" not in df.columns:
        raise KeyError("distinct_called_numbers_30d is absent")
    breadth = df["distinct_called_numbers_30d"].rank(pct=True)
    return (1 - breadth).astype("float64")


def leakage_score(df: pd.DataFrame) -> pd.Series:
    """Composite 0-1 score. Surfaced on the Subscriber 360 screen and used by
    M3 to decide whether an on-net pack is the right instrument.

    Three components, combined on percentile ranks rather than raw values so
    no single heavy-tailed input dominates:

        ratio above 1.0     receives more than they place
        off-net share       their calling has moved off Almadar
        graph contraction   they are calling fewer people

    Equal weights. There is no fitted weighting because there is nothing
    honest to fit it against -- the predictive power is unvalidated (see the
    module docstring), so a learned weighting would be fitting to our own
    generated data and presenting it as knowledge.
    """
    components = pd.DataFrame(index=df.index)
    components["receives_more_than_places"] = incoming_outgoing_ratio(df).rank(pct=True)
    components["off_net_migration"] = (1 - onnet_ratio(df)).rank(pct=True)
    components["graph_contraction"] = calling_graph_contraction(df)

    score = components.mean(axis=1).clip(0, 1)
    log.info(
        "leakage score: median %.3f, %.1f%% above 0.75 (equal-weighted over %s)",
        score.median(),
        100 * (score > 0.75).mean(),
        list(components.columns),
    )
    return score


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Every leakage feature, plus the composite."""
    conf = _leakage_conf()
    out = pd.DataFrame(index=df.index)

    out["incoming_outgoing_ratio"] = incoming_outgoing_ratio(df)
    out["onnet_ratio"] = onnet_ratio(df)
    out["offnet_share_30d"] = 1 - out["onnet_ratio"]
    out["calling_graph_contraction"] = calling_graph_contraction(df)
    out["leakage_score"] = leakage_score(df)

    # The binary the Subscriber 360 screen shows. Above 1.0 is the interpretable
    # threshold -- "receives more than they place" needs no explanation.
    out["is_receiving_sim"] = (out["incoming_outgoing_ratio"] > 1).astype("int8")

    # DELIBERATELY ABSENT: any SMS on/off-net mix feature. Almadar charges
    # 0.050 LYD either way, so SMS carries no pricing signal and an SMS-based
    # leakage ratio would be noise dressed as insight. Voice does carry it.
    for excluded in conf.get("excluded_by_design", []):
        if excluded in out.columns:
            raise AssertionError(f"{excluded} is excluded by design but was built anyway")

    realised = float(out["is_receiving_sim"].mean())
    log.info(
        "leakage: %d features, %.1f%% flagged as receiving SIMs (single-SIM baseline %.1f%%)",
        out.shape[1],
        100 * realised,
        100 * conf["baseline_share_above_one"],
    )
    return out
