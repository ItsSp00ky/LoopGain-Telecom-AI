"""Probability of repayment by the next recharge.  Owner: E2

Two heads, one per Almadar emergency product, because the debt sizes and the
eligible populations differ: 1/3/5 LYD airtime versus a flat 5 LYD for data.

Shares M1's feature matrix. Calibrated, because decision.advance_limit maps
the probability onto LYD exposure bands -- an uncalibrated score would set
real credit limits from meaningless numbers.

THE LABEL IS ONLY OBSERVED FOR BORROWERS, and that is not a data-quality
complaint, it is the shape of the problem. 38% of the population took an
advance in the window; the other 62% have no settlement outcome because they
never had a debt to settle. Training on the 38% alone teaches the model that
almost everyone repays, because the gate already removed the people who would
not have. `reject_inference` is the correction and it is mandatory in config.

CALIBRATION IS NOT OPTIONAL HERE FOR A DIFFERENT REASON THAN IN M1. There, an
uncalibrated probability corrupted an expected-value calculation. Here it is
compared against literal thresholds -- 0.85, 0.65, 0.45 -- so a model that is
systematically overconfident does not merely mis-rank, it moves subscribers
into higher credit bands and issues money against a number that does not mean
what it says.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

PRODUCTS = ("airtime", "data")
COUNT_COLUMN = {"airtime": "airtime_advance_count_90d", "data": "data_advance_count_90d"}


def _conf() -> dict:
    return load_conf("advance")["limit_function"]


def build_label(population: pd.DataFrame, product: str = "airtime") -> pd.DataFrame:
    """Settled by the next recharge, censored at 14 days.

    Returns only the rows with an OBSERVED outcome -- the subscribers who
    actually took an advance of this kind. `days_to_settle` carries a negative
    sentinel for everyone else, and coercing that to "repaid" or "defaulted"
    would invent 62,000 observations.
    """
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}; expected one of {PRODUCTS}")

    horizon = _conf()["censor_at_days"]
    count = COUNT_COLUMN[product]
    missing = [c for c in (count, "days_to_settle") if c not in population.columns]
    if missing:
        raise KeyError(f"{missing} absent; the repayment label cannot be built")

    took = (population[count].fillna(0) > 0) & (population["days_to_settle"] >= 0)
    observed = population[took].copy()
    observed["repaid_by_next_recharge"] = (observed["days_to_settle"] <= horizon).astype("int8")

    log.info(
        "%s label: %d of %d observed (%.1f%%), repayment rate %.4f at a %d-day horizon",
        product,
        len(observed),
        len(population),
        100 * took.mean(),
        observed["repaid_by_next_recharge"].mean(),
        horizon,
    )
    return observed


def train(
    X: pd.DataFrame,
    y: pd.Series,
    product: str = "airtime",
    sample_weight=None,
    calibration: tuple[pd.DataFrame, pd.Series] | None = None,
    **params,
):
    """Target: settled by next recharge, censored at 14 days.

    ``product`` is "airtime" or "data" -- see conf/advance.yaml#targets.

    Returns a CALIBRATED model. The bands in conf/advance.yaml are absolute
    probability thresholds, so this reuses M1's isotonic wrapper rather than
    returning a raw ranker: a score that ranks correctly and reads 0.9 where
    the truth is 0.6 would issue the largest advance to the wrong people.

    ``calibration`` SUPPLIES AN EXPLICIT SLICE, AND THE REJECT-INFERENCE PATH
    MUST USE IT. Fuzzy augmentation gives every never-borrowed subscriber two
    rows, one labelled repaid and one defaulted, so the augmented set is close
    to 50/50 by construction however the weights fall. Fitting is fine -- the
    weights carry the information. Calibrating is not: an isotonic map fitted
    against those labels learns to map every score toward 0.5, and it does it
    silently.

    Measured on the airtime head: calibrating on the augmented labels moved the
    mean PD from 0.97 to 0.61 and the shift was reported as a bias correction.
    It was the calibrator learning the shape of the augmentation. The only rows
    with an OBSERVED outcome are the accepted ones, and those are the only rows
    a calibrator may see.
    """
    from cvm.models.m1_churn.calibration import calibrate
    from cvm.models.m1_churn.gradient_boosting import train as train_boosted

    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}; expected one of {PRODUCTS}")

    y = pd.Series(y).astype(int)
    if y.nunique() < 2:
        raise ValueError(
            f"the {product} repayment label has a single value ({y.iloc[0]}). Nothing to "
            "learn, and a constant model would be handed to a credit decision."
        )
    if len(y) < 500:
        log.warning("only %d observed %s outcomes; the PD head will be noisy", len(y), product)

    # A temporal split would be better and the observed borrowers do not carry
    # enough distinct snapshots per product to make one. Stratified instead,
    # and the report says so rather than implying a temporal guarantee.
    from sklearn.model_selection import train_test_split

    weight = (
        np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype="float64")
    )

    if calibration is not None:
        # Fit on everything given, calibrate on the observed rows supplied.
        X_fit, y_fit, w_fit = X, y, weight
        X_cal, y_cal = calibration
        source = "a held-out slice of the OBSERVED outcomes"
    else:
        # The weights are split WITH the rows. Splitting the frame and then
        # applying the original weight vector would misalign every weight to a
        # different subscriber, which raises nothing and silently scrambles it.
        X_fit, X_cal, y_fit, y_cal, w_fit, _ = train_test_split(
            X, y, weight, test_size=0.3, random_state=settings.random_seed, stratify=y
        )
        source = "a stratified 30% of the same rows"

    raw = train_boosted(
        X_fit, y_fit, kind="lightgbm", n_estimators=200, sample_weight=w_fit, **params
    )
    model = calibrate(raw, X_cal, y_cal)

    log.info(
        "%s PD head: fitted on %d rows, calibrated on %d from %s",
        product,
        len(X_fit),
        len(X_cal),
        source,
    )
    return model


def predict_pd(model, X: pd.DataFrame) -> pd.Series:
    """Calibrated probability of repayment by the next recharge."""
    probability = model.predict_proba(X)[:, 1]
    series = pd.Series(probability, index=X.index, name="repayment_probability")
    log.info(
        "PD: mean %.4f, p10 %.4f, p90 %.4f over %d subscribers",
        series.mean(),
        series.quantile(0.1),
        series.quantile(0.9),
        len(series),
    )
    return series


def predict_lockout_risk(model, X: pd.DataFrame, limit_lyd: pd.Series) -> pd.Series:
    """Probability this advance leaves unpaid debt at day 14.

    Unpaid debt blocks re-subscription, so the subscriber loses access to the
    very service they reached for -- and a subscriber locked out of emergency
    credit is a churn risk.

    Separate from PD on purpose: the system's job is to PREVENT that outcome,
    not to optimise recovery after it, so it needs its own number a reviewer
    can see.

    NOT the same as Libyana's line-reset outcome, which is undocumented for
    Almadar. Do not describe it as such.

    IT IS NOT SIMPLY 1 - PD, and if it were this function would not exist. PD
    asks whether they settle; lockout asks whether *this particular debt*, at
    *this size*, against *their* recharge behaviour, is still outstanding at
    day 14. A subscriber with a 0.8 repayment probability and a 5 LYD modal
    recharge is far safer at a 1 LYD advance than at 5, and PD alone cannot
    see the difference because it never saw the amount.
    """
    base = 1.0 - np.asarray(predict_pd(model, X))
    limit = np.asarray(pd.Series(limit_lyd), dtype="float64")

    modal = (
        X["modal_recharge_amount_lyd"].to_numpy(dtype="float64")
        if "modal_recharge_amount_lyd" in X.columns
        else np.full(len(X), np.nan)
    )
    # Burden: what share of one typical top-up this debt would consume. At or
    # above 1.0 the recharge clears the debt and buys nothing, which is the
    # zero-residual case, so the risk is scaled up sharply there.
    with np.errstate(divide="ignore", invalid="ignore"):
        burden = np.where(modal > 0, limit / modal, 1.0)
    burden = np.nan_to_num(burden, nan=1.0, posinf=1.0)

    risk = np.clip(base * (0.5 + burden), 0.0, 1.0)
    series = pd.Series(risk, index=X.index, name="lockout_risk")

    threshold = load_conf("advance")["safety_guards"]["lockout_risk"]["flag_if_probability_above"]
    log.info(
        "lockout risk: mean %.4f, %.1f%% above the %.2f flag threshold (mean burden %.2f)",
        series.mean(),
        100 * (series > threshold).mean(),
        threshold,
        float(np.nanmean(burden)),
    )
    return series
