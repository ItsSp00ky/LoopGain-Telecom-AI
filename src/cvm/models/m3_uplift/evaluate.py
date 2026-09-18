"""Uplift evaluation. Owner: E4

Standard classification metrics do not work here. There is no ground-truth
uplift for any individual subscriber -- you never observe both the treated and
untreated outcome for the same person -- so the model is evaluated on ranking
quality across the treated/control split instead.

Reported:

    Qini curve and Qini coefficient    the standard uplift ranking measure
    uplift@k                           realised uplift in the top k% by score
    per-quadrant counts                how much of the base is persuadable

The honest framing for the report: these are computed on Criteo's real
randomised arms. On the generated population they measure whether the pipeline
reproduces the effect we injected, which is a pipeline test rather than a
performance claim.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def qini_curve(uplift_score: pd.Series, outcome: pd.Series, treated: pd.Series):
    """Points for the Qini curve, and the coefficient."""
    raise NotImplementedError("TODO(E4)")


def uplift_at_k(uplift_score: pd.Series, outcome: pd.Series, treated: pd.Series,
                k: float = 0.30) -> float:
    """Realised uplift in the top k fraction by predicted uplift.

    This is the number the Campaign Builder actually needs: if we treat the top
    30%, what incremental retention do we get?
    """
    raise NotImplementedError("TODO(E4)")


def quadrant_counts(uplift: pd.Series, baseline_response: pd.Series) -> dict[str, int]:
    """How much of the base is persuadable, sure thing, lost cause, sleeping dog.

    Worth putting on a slide. In most retention programmes the persuadable
    share is far smaller than people expect, and that is the argument for
    targeting in one number.
    """
    raise NotImplementedError("TODO(E4)")


def validate_on_criteo() -> dict[str, float]:
    """Train and score the method on Criteo's real randomised arms.

    This is what separates "our uplift model scores well on data we made up"
    from "our uplift method is validated on real randomised data, then applied
    to a generated population". Run it before the method is trusted anywhere
    else, and quote the result in the report.
    """
    raise NotImplementedError("TODO(E4)")


def expected_value_of_treatment(uplift: np.ndarray, clv: np.ndarray,
                                cost: np.ndarray) -> np.ndarray:
    """Expected LYD gain from treating each subscriber.

        E[gain] = uplift x CLV - cost

    The bridge from M3 into the decision engine: a positive value means
    intervening is worthwhile before guardrails, a negative one means it is not
    regardless of how high the churn score is.
    """
    raise NotImplementedError("TODO(E4)")
