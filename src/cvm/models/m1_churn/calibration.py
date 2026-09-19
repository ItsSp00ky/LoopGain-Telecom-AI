"""Probability calibration. Mandatory for both arms.

The pricing engine consumes probabilities as monetary expectations, so a 0.31
must actually mean 31%. An uncalibrated ranker would silently corrupt every
expected-margin figure downstream, and nothing in the guardrails would catch it.

Isotonic regression, fitted on a held-out temporal slice -- never on the
training fold.

WHY THIS IS NOT DECORATION. `E[gain] = uplift x CLV - offer_cost` is the
expression the whole decision engine turns on, and it multiplies a probability
by money. A model that ranks perfectly and is systematically overconfident
ranks the right subscribers and prices every one of them wrong -- and because
the ranking is right, every ranking metric says it is fine. Brier and the
reliability curve are the only things that see it.

`scale_pos_weight` makes this certain rather than likely. Every boosted model
here is trained with the positive class weighted up by about 27, which is the
correct thing to do for ranking at a 3.5% base rate and which deliberately
destroys the absolute scale of the output. The scores come out far too high.
Calibration is what puts them back.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def _conf() -> dict:
    return load_conf("models/m1_churn")["calibration"]


class CalibratedModel:
    """A fitted model plus the isotonic map from its scores to probabilities.

    A thin wrapper rather than `sklearn.CalibratedClassifierCV` because that
    class refits the base estimator internally on cross-validation folds, and
    those folds are random. Refitting a temporal model on random folds trains
    it on its own future, which is the one thing this project spends a whole
    module preventing. Here the base model is already fitted and is left alone;
    only the map is learned.
    """

    def __init__(self, model, mapper, columns: list[str] | None = None):
        self.model = model
        self.mapper = mapper
        self.columns = columns

    def predict_proba(self, X) -> np.ndarray:
        raw = _raw_probability(self.model, X)
        calibrated = self.mapper.predict(raw)
        return np.column_stack([1.0 - calibrated, calibrated])

    def predict(self, X, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= threshold).astype("int8")


def _raw_probability(model, X) -> np.ndarray:
    """The model's own score for the positive class, whatever its interface."""
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(X))[:, 1]
    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(X))
        return 1.0 / (1.0 + np.exp(-scores))
    raise TypeError(f"{type(model).__name__} exposes neither predict_proba nor decision_function")


def calibrate(model, X_cal, y_cal) -> CalibratedModel:
    """Fit an isotonic map on a HELD-OUT slice the model has not seen.

    Isotonic rather than Platt because it is non-parametric: Platt scaling
    assumes the distortion is a sigmoid, and the distortion produced by
    `scale_pos_weight` is not. Isotonic needs more data and there are 20,000
    rows in the validation split, which is comfortably enough.

    Monotone NON-DECREASING by construction, so it cannot REORDER anything: if
    one subscriber scored above another before, they do not score below them
    after. It can, however, map two distinct scores onto the same value, and
    those new ties move a rank metric slightly -- measured here, PR-AUC shifts
    by about 0.0014, which is tie-breaking and not reordering. Saying the AUCs
    are "identical" would be the easier sentence and it would be false.

    So: this step fixes the scale, not the order. Brier and the reliability
    curve are what should move, and they move a lot -- ECE 0.255 to 0.004 on
    the real test split.
    """
    method = _conf()["method"]
    if method != "isotonic":
        raise ValueError(f"conf asks for {method!r}; only isotonic is implemented")

    from sklearn.isotonic import IsotonicRegression

    y_cal = np.asarray(y_cal).astype(int)
    if y_cal.sum() < 10:
        raise ValueError(
            f"only {y_cal.sum()} positive case(s) in the calibration slice; an isotonic "
            "map fitted on that few is noise, and it would be applied to every score."
        )

    raw = _raw_probability(model, X_cal)
    mapper = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    mapper.fit(raw, y_cal)

    before, after = brier_score(y_cal, raw), brier_score(y_cal, mapper.predict(raw))
    log.info(
        "calibrated on %d held-out rows (%d positive): Brier %.5f -> %.5f, "
        "mean predicted %.4f -> %.4f against an observed %.4f",
        len(y_cal),
        int(y_cal.sum()),
        before,
        after,
        raw.mean(),
        mapper.predict(raw).mean(),
        y_cal.mean(),
    )
    columns = list(X_cal.columns) if hasattr(X_cal, "columns") else None
    return CalibratedModel(model, mapper, columns)


def brier_score(y_true, y_prob) -> float:
    """Mean squared error of the probabilities. Lower is better.

    A proper scoring rule, which is the property that matters: it is minimised
    only by reporting your true belief, so it cannot be gamed by being
    systematically timid or systematically bold the way a threshold metric can.
    """
    y_true = np.asarray(y_true, dtype="float64")
    y_prob = np.asarray(y_prob, dtype="float64")
    if y_true.shape != y_prob.shape:
        raise ValueError(f"shape mismatch: {y_true.shape} against {y_prob.shape}")
    return float(np.mean((y_prob - y_true) ** 2))


def calibration_curve_data(y_true, y_prob, n_bins: int = 10) -> pd.DataFrame:
    """Reliability-diagram data for the report and the benchmark slide.

    QUANTILE BINS, NOT EQUAL-WIDTH. At a 3.5% base rate almost every score
    lands in the lowest equal-width bin and the diagram shows one point --
    which looks like perfect calibration and is actually no information.
    Quantile bins put an equal number of subscribers in each, so the diagram
    shows where the model actually lives.

    Returns one row per bin: mean predicted, observed fraction, and the count.
    A perfectly calibrated model has predicted == observed in every row.
    """
    frame = pd.DataFrame(
        {"y": np.asarray(y_true, dtype="float64"), "p": np.asarray(y_prob, dtype="float64")}
    )

    # `duplicates="drop"` because ties at the bottom of the distribution are
    # the normal case here, and qcut raises on them rather than merging.
    frame["bin"] = pd.qcut(frame["p"], q=n_bins, labels=False, duplicates="drop")

    out = (
        frame.groupby("bin", observed=True)
        .agg(mean_predicted=("p", "mean"), observed_fraction=("y", "mean"), count=("y", "size"))
        .reset_index(drop=True)
    )
    out["gap"] = out["mean_predicted"] - out["observed_fraction"]

    # Expected Calibration Error: the count-weighted mean absolute gap. One
    # number for the benchmark table, where the full curve does not fit.
    ece = float(np.average(out["gap"].abs(), weights=out["count"]))
    out.attrs["ece"] = ece
    log.info(
        "reliability: %d bins, ECE %.4f, worst gap %+.4f", len(out), ece, out["gap"].abs().max()
    )
    return out


def expected_calibration_error(y_true, y_prob, n_bins: int = 10) -> float:
    """The count-weighted mean absolute gap between predicted and observed."""
    return float(calibration_curve_data(y_true, y_prob, n_bins).attrs["ece"])
