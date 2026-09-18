"""Explicit hazard function for label generation.

Documented here and in docs/architecture.md rather than buried, for two
reasons: the model needs recoverable signal, and the evaluation has to be
honest about being a simulation ground truth.

Two categories, and confusing them breaks the project in opposite directions.
tests/leakage/ enforces the distinction.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

# --- DRIVERS: behavioural fields the hazard is a function of ----------------
#
# These STAY in the feature matrix, deliberately. The hazard is built from
# observable behaviour precisely so the signal is recoverable -- a model that
# cannot see any driver of the label has nothing to learn, and the whole
# exercise would be measuring noise.
#
# What makes this honest rather than circular is stated plainly in the report:
# these metrics are computed against a simulation whose ground truth we wrote,
# so they demonstrate that the pipeline and decision logic work. They are not
# evidence of production performance.
LABEL_DRIVER_FIELDS: tuple[str, ...] = (
    "days_since_last_topup",
    "recharge_gap_cv",
    "balance_zero_hours_30d",
    "onnet_ratio",
    "incoming_outgoing_ratio",
    "service_outage_hours_30d",
)

# --- ARTIFACTS: fields that trivially encode the outcome -------------------
#
# These MUST NEVER reach the feature matrix. Any one of them lets a model
# reconstruct the label directly, which is the subtlest and most damaging
# failure mode available to this project: a model that scores beautifully and
# knows nothing.
#
# conf/features.yaml#leakage_controls.excluded_columns must be a superset of
# this tuple, and tests/leakage/ fails the build if it drifts.
LABEL_ARTIFACT_FIELDS: tuple[str, ...] = (
    "hazard_score",
    "churn_date",
    "silent_churn_30d",
    "days_to_churn",
)


def _conf() -> dict:
    return load_conf("data")["synthesis"]["hazard_function"]


def _standardise(column: pd.Series) -> pd.Series:
    """Zero mean, unit variance, robust to a constant column.

    A constant driver contributes nothing rather than producing NaN for the
    whole population, which is what dividing by a zero standard deviation
    would do -- and it would do it silently, poisoning every row.
    """
    values = pd.to_numeric(column, errors="coerce").astype("float64")
    values = values.fillna(values.median())
    spread = values.std(ddof=0)
    if not np.isfinite(spread) or spread == 0:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - values.mean()) / spread


def _solve_intercept(linear: np.ndarray, target_rate: float) -> float:
    """Find the intercept that makes the mean sigmoid equal the target rate.

    Bisection rather than a formula: the mean of a sigmoid has no closed-form
    inverse, and bisection on a monotone function is both exact enough and
    impossible to get subtly wrong.
    """

    def mean_probability(intercept: float) -> float:
        # Parenthesise the WHOLE sigmoid before taking the mean. Without the
        # outer brackets this reads as 1 / mean(1 + exp(...)), which is a
        # different quantity entirely -- and it converges happily to the wrong
        # answer, giving a 9.9% churn rate against a 3.5% target.
        return float((1.0 / (1.0 + np.exp(-(intercept + linear)))).mean())

    low, high = -40.0, 40.0
    for _ in range(200):
        middle = (low + high) / 2
        if mean_probability(middle) < target_rate:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def hazard(df: pd.DataFrame, base_monthly_churn: float | None = None) -> pd.Series:
    """Per-subscriber monthly churn hazard.

    A logistic function of the standardised drivers, with the intercept solved
    so the population mean equals the configured base rate. Both halves matter:

    * The **weights** make the label a function of observable behaviour, so a
      model has something to find. Their signs are claims about prepaid churn
      and live in conf/data.yaml where they can be read and argued with.
    * The **solved intercept** keeps the realised rate pinned to
      conf/market.yaml's 3.5%. Without it, changing any weight would quietly
      move the base rate, and the calibration claim -- a 0.31 means 31% --
      would be measured against a prior nobody chose.

    Returns a probability per subscriber, not a binary outcome. Drawing from it
    is `generate_labels`.
    """
    conf = _conf()
    target = base_monthly_churn if base_monthly_churn is not None else conf["base_monthly_churn"]
    weights: dict[str, float] = conf["driver_weights"]
    scale = float(conf.get("logit_scale", 1.0))

    missing = [field for field in weights if field not in df.columns]
    if missing:
        raise KeyError(
            f"hazard drivers absent from the frame: {missing}. The overlays in "
            "cvm.synthesis.overlays must run before labels are generated."
        )
    unweighted = [f for f in LABEL_DRIVER_FIELDS if f not in weights]
    if unweighted:
        raise ValueError(
            f"{unweighted} are declared LABEL_DRIVER_FIELDS but carry no weight. "
            "A driver with no weight is not a driver, and tests/leakage/ would "
            "then be protecting a field that does nothing."
        )

    linear = np.zeros(len(df), dtype="float64")
    for field, weight in weights.items():
        linear += float(weight) * _standardise(df[field]).to_numpy()
    linear *= scale

    intercept = _solve_intercept(linear, float(target))
    probability = 1.0 / (1.0 + np.exp(-(intercept + linear)))

    log.info(
        "hazard: intercept %.4f -> mean %.4f (target %.4f), p10 %.4f p90 %.4f",
        intercept,
        probability.mean(),
        target,
        np.quantile(probability, 0.10),
        np.quantile(probability, 0.90),
    )
    return pd.Series(probability, index=df.index, name="hazard_score")


def generate_labels(df: pd.DataFrame, seed: int | None = None) -> pd.DataFrame:
    """Draw silent_churn_30d from the hazard, respecting the 15-day gap.

    THE GAP IS THE POINT. Features are observed over 90 days, then nothing is
    observed for 15, then the outcome is measured over 30. A label drawn as
    "churned at some point after the observation window" would let a model
    exploit behaviour from inside the gap that it would not have at scoring
    time. So `churn_date` is placed strictly inside the outcome window:

        day 0 ............ 90        90 .......... 105      105 ........ 135
        observation                 gap                     outcome

    Returns the frame with four added columns, all of them
    LABEL_ARTIFACT_FIELDS: they exist so the pipeline can be evaluated and must
    never reach a feature matrix.
    """
    windows = load_conf("features")["windows"]
    observation, gap, outcome = (
        windows["observation_days"],
        windows["gap_days"],
        windows["outcome_days"],
    )

    rng = np.random.default_rng(settings.random_seed if seed is None else seed)
    out = df.copy()

    probability = hazard(out)
    churned = rng.random(len(out)) < probability.to_numpy()

    # Uniform within the outcome window. A subscriber who churns does so on
    # some day in it; which day is not something the hazard claims to know.
    window_start = observation + gap
    day = rng.integers(window_start, window_start + outcome, size=len(out))

    out["hazard_score"] = probability
    out["silent_churn_30d"] = churned.astype("int8")
    out["days_to_churn"] = np.where(churned, day, -1).astype("int16")

    snapshot = (
        pd.to_datetime(out["snapshot_date"]) if "snapshot_date" in out else pd.Timestamp.now()
    )
    out["churn_date"] = pd.Series(
        np.where(churned, snapshot + pd.to_timedelta(day, unit="D"), pd.NaT), index=out.index
    )

    log.info(
        "labels: %d of %d churned (%.4f), churn dates in days %d-%d after snapshot",
        int(churned.sum()),
        len(out),
        churned.mean(),
        window_start,
        window_start + outcome - 1,
    )
    return out


def assert_label_is_learnable(df: pd.DataFrame, min_abs_correlation: float = 0.05) -> None:
    """Fail if no driver correlates with the drawn label.

    The opposite failure to leakage, and much harder to notice. If the hazard
    spread is too narrow the draw is effectively a coin flip, every model
    scores at chance, and the cause looks like a modelling problem for days.
    """
    if "silent_churn_30d" not in df.columns:
        raise KeyError("no label to check; run generate_labels first")

    correlations = {
        field: float(pd.to_numeric(df[field], errors="coerce").corr(df["silent_churn_30d"]))
        for field in LABEL_DRIVER_FIELDS
        if field in df.columns
    }
    strongest = max(abs(v) for v in correlations.values() if pd.notna(v))
    if strongest < min_abs_correlation:
        raise ValueError(
            f"no driver correlates with the label above {min_abs_correlation} "
            f"(strongest |r| = {strongest:.4f}). The hazard spread is too narrow "
            "to draw a rankable label -- raise logit_scale in conf/data.yaml. "
            f"Correlations: { {k: round(v, 4) for k, v in correlations.items()} }"
        )
    log.info(
        "labels: learnable, strongest driver |r| = %.4f  %s",
        strongest,
        {k: round(v, 4) for k, v in sorted(correlations.items(), key=lambda kv: -abs(kv[1]))},
    )
