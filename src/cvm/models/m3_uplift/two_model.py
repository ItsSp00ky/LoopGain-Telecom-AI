"""Uplift targeting.  Owner: E4

Budget goes only to PERSUADABLES. Never to sure things, never to lost causes.

Method: a simple two-model difference (treated response model minus control
response model), not a causal-inference library. At this data scale the extra
machinery of EconML buys precision we cannot validate on synthetic response
anyway, and the simpler method is defensible in a three-minute pitch. That is a
deliberate choice, recorded in docs/adr/, not an omission.

SLEEPING-DOGS GUARD: contacting a dormant-but-not-departing subscriber can
remind them to leave. The negative-effect quadrant is excluded from all three
retention-ladder stages.

WHAT THE TWO-MODEL DIFFERENCE COSTS, stated once. Each model is fitted to
predict a RESPONSE, and the quantity we want is their DIFFERENCE -- so both
models spend their capacity on the part of the signal that is common to treated
and control, which cancels, and the uplift is whatever survives in the
residual. The errors of the two models add while the signal subtracts. It is
biased toward noise in exactly the way a direct uplift learner is not.

The answer is not to pretend otherwise; it is to measure. Qini on Criteo's real
randomised arms says whether the ranking works despite that, and it is the only
statement about this method in the whole project that is a measurement rather
than an argument.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

QUADRANTS = ("persuadable", "sure_thing", "lost_cause", "sleeping_dog")


def _conf() -> dict:
    return load_conf("models/m3_uplift")


def train_two_model(X: pd.DataFrame, y: pd.Series, treated: pd.Series) -> tuple:
    """Fit the treated-response and control-response models separately.

    BOTH ARMS MUST BE POPULATED, and it is checked rather than assumed. A
    single-arm fit produces a control model trained on nothing, which does not
    raise -- LightGBM will happily fit a constant -- and every uplift score
    becomes the treated probability with a constant subtracted. That is a churn
    model wearing an uplift model's name, and it would rank plausibly.
    """
    from lightgbm import LGBMClassifier

    treated = pd.Series(treated).astype(int)
    y = pd.Series(y).astype(int)

    n_treated, n_control = int(treated.sum()), int((1 - treated).sum())
    if n_treated < 100 or n_control < 100:
        raise ValueError(
            f"{n_treated} treated and {n_control} control rows. Both arms must be "
            "populated; with one arm empty the 'uplift' is a response model minus a "
            "constant, which ranks plausibly and means nothing."
        )
    for arm, mask in (("treated", treated == 1), ("control", treated == 0)):
        if y[mask].nunique() < 2:
            raise ValueError(f"the {arm} arm has a single outcome value; nothing to learn")

    params = {
        "objective": "binary",
        "metric": "average_precision",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 100,
        "n_estimators": 300,
        "random_state": settings.random_seed,
        "n_jobs": -1,
        "verbose": -1,
    }
    model_treated = LGBMClassifier(**params).fit(X[treated == 1], y[treated == 1])
    model_control = LGBMClassifier(**params).fit(X[treated == 0], y[treated == 0])

    log.info(
        "two-model: treated %d rows (%.4f response), control %d rows (%.4f response), "
        "naive lift %+.4f pp",
        n_treated,
        y[treated == 1].mean(),
        n_control,
        y[treated == 0].mean(),
        100 * (y[treated == 1].mean() - y[treated == 0].mean()),
    )
    return model_treated, model_control


def predict_uplift(model_treated, model_control, X: pd.DataFrame) -> pd.Series:
    """Estimated treatment effect per subscriber.

    P(respond | treated) - P(respond | control). Positive means treating helps;
    NEGATIVE means treating hurts, and that is not a rounding artefact to be
    clipped away -- it is the sleeping-dog signal and the reason this module
    exists.
    """
    treated_p = model_treated.predict_proba(X)[:, 1]
    control_p = model_control.predict_proba(X)[:, 1]
    uplift = pd.Series(treated_p - control_p, index=X.index, name="uplift")

    log.info(
        "uplift: mean %+.5f, p10 %+.5f, p90 %+.5f, %.1f%% negative",
        uplift.mean(),
        uplift.quantile(0.1),
        uplift.quantile(0.9),
        100 * (uplift < 0).mean(),
    )
    return uplift


def baseline_response(model_control, X: pd.DataFrame) -> pd.Series:
    """P(respond | untreated). The other axis of the quadrant grid.

    From the CONTROL model, deliberately. It answers "what happens if we leave
    them alone", which is what separates a sure thing from a lost cause, and
    the treated model cannot answer it.
    """
    return pd.Series(model_control.predict_proba(X)[:, 1], index=X.index, name="baseline")


def classify_quadrant(uplift: pd.Series, baseline_response: pd.Series) -> pd.Series:
    """persuadable | sure_thing | lost_cause | sleeping_dog.

    Two axes: does treating CHANGE the outcome, and what happens if we do
    nothing. The uplift threshold comes from config; the baseline split is the
    population median, because "high" and "low" baseline response have no
    absolute meaning -- a 5% response rate is high in one campaign and low in
    another, and hard-coding a number would make the quadrants incomparable
    between datasets.

        sleeping_dog  uplift < -0.005          treating makes them leave
        persuadable   uplift > +0.005          treating is what keeps them
        sure_thing    flat, high baseline      stays either way
        lost_cause    flat, low baseline       leaves either way

    ONLY PERSUADABLES GET BUDGET. The other three are, in order, waste, waste,
    and active harm.
    """
    conf = _conf()
    negative = conf["sleeping_dog_threshold"]
    positive = abs(negative)

    uplift = pd.Series(uplift)
    baseline = pd.Series(baseline_response)
    if len(uplift) != len(baseline):
        raise ValueError(f"{len(uplift)} uplift scores against {len(baseline)} baselines")

    cut = baseline.median()
    quadrant = pd.Series("lost_cause", index=uplift.index, dtype="object")
    quadrant[baseline >= cut] = "sure_thing"
    quadrant[uplift > positive] = "persuadable"
    # LAST, so it wins. A subscriber can look persuadable on a noisy positive
    # tail and still be a sleeping dog; the harmful call is the one to get
    # wrong, so it takes precedence.
    quadrant[uplift < negative] = "sleeping_dog"

    counts = quadrant.value_counts()
    log.info(
        "quadrants: %s (threshold +/-%.4f, baseline split at %.4f)",
        {k: f"{v / len(quadrant):.1%}" for k, v in counts.items()},
        positive,
        cut,
    )
    if "sleeping_dog" not in counts:
        log.warning(
            "NO sleeping dogs at a %.4f threshold. That usually means the threshold is "
            "wrong for this data rather than that none exist -- check the uplift spread "
            "before concluding the campaign is safe.",
            negative,
        )
    return quadrant.astype("string")


def assign_control_holdout(cohort: pd.DataFrame, fraction: float | None = None) -> pd.Series:
    """Randomised holdout. Without it there is no way to isolate net margin
    impact, which is exactly pain point P4.

    RANDOM, not a convenience slice. Holding out the last 10% by subscriber id,
    or by region, or by whoever the campaign tool happened to skip, gives a
    control group that differs systematically from the treated one -- and the
    measured "impact" then includes that difference. Seeded, so the same cohort
    produces the same holdout across runs and the measurement is reproducible.

    Mandatory by config. A campaign that cannot be measured is a campaign whose
    ROI is an assertion, and the proposal makes a specific ROI claim.
    """
    conf = _conf()
    fraction = conf["control_holdout_fraction"] if fraction is None else fraction

    if conf.get("holdout_is_mandatory", True) and fraction <= 0:
        raise ValueError(
            "holdout_is_mandatory is set in conf/models/m3_uplift.yaml. Without a "
            "randomised control arm there is no counterfactual, so net margin impact "
            "cannot be isolated and every ROI figure becomes an assertion."
        )
    if not 0 < fraction < 1:
        raise ValueError(f"the holdout fraction must be in (0, 1), got {fraction}")

    rng = np.random.default_rng(settings.random_seed)
    held = pd.Series(rng.random(len(cohort)) < fraction, index=cohort.index, name="is_control")

    log.info(
        "control holdout: %d of %d (%.1f%%, target %.1f%%), seeded and reproducible",
        int(held.sum()),
        len(held),
        100 * held.mean(),
        100 * fraction,
    )
    return held
