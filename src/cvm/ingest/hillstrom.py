"""Dataset G -- Hillstrom MineThatData email challenge.  VALIDATION SOURCE.

64,000 customers, randomised three ways: men's email, women's email, no email.
Small enough to iterate on in seconds, which is why M3 is warmed up here before
it touches Criteo's 25 million rows.

WHY BOTH. Criteo is the credible number; Hillstrom is the one that shows the
four quadrants clearly. Its treatment effect is large and the arms are balanced
at a third each, so persuadables, sure things, lost causes and sleeping dogs
separate visibly -- which makes it the right data for the quadrant chart in the
report and for catching a wiring bug before spending 300 MB on the real thing.

THREE ARMS, NOT TWO. Collapsing both email arms into "treated" is the default
and it is fine for a warm-up, but it throws away the comparison that makes this
dataset interesting: the same person can be persuadable under one creative and
a sleeping dog under another. `load(arm=...)` keeps that available.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

TREATMENT = "segment"
ARMS = ("Mens E-Mail", "Womens E-Mail", "No E-Mail")
CONTROL_ARM = "No E-Mail"

# `visit` over `conversion` for the same reason as Criteo: conversion is ~0.9%
# here, and a warm-up that cannot resolve its own effect teaches nothing.
OUTCOME = "visit"


def _conf() -> dict:
    return load_conf("data")["sources"]["hillstrom"]


def fetch() -> pd.DataFrame:
    """Download via scikit-uplift, cached under data/external/."""
    from sklift.datasets import fetch_hillstrom

    settings.external_dir.mkdir(parents=True, exist_ok=True)
    bunch = fetch_hillstrom(
        target_col=OUTCOME,
        data_home=str(settings.external_dir),
        return_X_y_t=False,
    )
    df = pd.concat(
        [bunch.data, bunch.treatment.rename(TREATMENT), bunch.target.rename(OUTCOME)], axis=1
    )
    log.info("hillstrom: %d rows, %d features", len(df), bunch.data.shape[1])
    return df


def load(arm: str | None = None) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, treatment) with treatment as 0/1.

    ``arm=None`` collapses both email arms into treated -- the usual warm-up
    framing. Passing one of ARMS keeps only that arm against the control, which
    is what the per-creative quadrant comparison needs.
    """
    df = fetch()

    if arm is not None:
        if arm not in ARMS or arm == CONTROL_ARM:
            raise ValueError(f"arm must be one of {ARMS[:2]} or None, not {arm!r}")
        df = df[df[TREATMENT].isin([arm, CONTROL_ARM])].reset_index(drop=True)

    t = (df[TREATMENT] != CONTROL_ARM).astype(int)
    y = df[OUTCOME].astype(int)
    x = df.drop(columns=[TREATMENT, OUTCOME])

    # One-hot the categoricals so the frame is model-ready; sklift's two-model
    # wrapper passes straight through to the base learner.
    x = pd.get_dummies(x, drop_first=True)

    log.info(
        "hillstrom: arm=%s | %d rows | treated %.1f%% | outcome %.4f treated vs %.4f control",
        arm or "both email arms",
        len(df),
        t.mean() * 100,
        y[t == 1].mean(),
        y[t == 0].mean(),
    )
    return x, y, t
