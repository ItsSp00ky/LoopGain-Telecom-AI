"""Probability calibration. Mandatory for both arms.

The pricing engine consumes probabilities as monetary expectations, so a 0.31
must actually mean 31%. An uncalibrated ranker would silently corrupt every
expected-margin figure downstream, and nothing in the guardrails would catch it.

Isotonic regression, fitted on a held-out temporal slice -- never on the
training fold.
"""

from __future__ import annotations

import numpy as np


def calibrate(model, X_cal, y_cal):
    raise NotImplementedError("TODO(E2)")


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    raise NotImplementedError("TODO(E2)")


def calibration_curve_data(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10):
    """Reliability-diagram data for the report and the benchmark slide."""
    raise NotImplementedError("TODO(E2)")