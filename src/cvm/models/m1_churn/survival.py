"""M1b -- time-to-churn.  Owner: E2

Classification answers *if*. Survival answers *when*. Retention economics are
timing-sensitive: intervening 40 days early wastes budget, 5 days late wastes
everything.

Cox Proportional Hazards (lifelines), with a Random Survival Forest challenger.
Reported metric: concordance index.

The hazard curve output DEFINES the retention ladder stage boundaries. Rather
than picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves
identify where recovery probability falls sharply, and those inflection points
become the cut-points -- recomputed per segment.

WHERE THE DURATION COMES FROM, AND WHY NOT THE FEATURE STORE. `days_to_churn`
is in LABEL_ARTIFACT_FIELDS and is dropped from the feature store on purpose:
as an input it reconstructs the outcome exactly. As an OUTCOME it is precisely
what this module models. So it is read from the labelled population and joined
on the hashed id, never taken from the features -- the same distinction the
target itself needs, met a second time. `build_survival_frame` asserts it never
lands on the feature side.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

DURATION = "duration_days"
EVENT = "event_observed"

# How far the bootstrapped boundaries may wander before they stop being
# boundaries. Three days is a working tolerance for a retention ladder: a stage
# that moves by less than that is the same stage, and one that moves by a week
# is a different piece of advice to a campaign manager.
MAX_BOUNDARY_SPREAD_DAYS = 3


def _conf() -> dict:
    return load_conf("models/m1_churn")["survival"]


def _horizon() -> int:
    """Last day of the outcome window -- where a survivor is censored."""
    w = load_conf("features")["windows"]
    return w["observation_days"] + w["gap_days"] + w["outcome_days"] - 1


def build_survival_frame(features: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """Join the duration and event onto the feature matrix.

    A subscriber who did not churn is CENSORED, not given a long duration.
    The distinction is the whole reason to use survival analysis: "left on day
    120" and "had not left by day 134, and we stopped looking" are different
    observations, and treating the second as the first would bias every
    estimate toward shorter lifetimes.
    """
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    target = load_conf("features")["target"]["name"]
    horizon = _horizon()

    leaked = [c for c in LABEL_ARTIFACT_FIELDS if c in features.columns and c != target]
    if leaked:
        raise AssertionError(
            f"{leaked} are already in the feature matrix. They are outcomes, so they may "
            "join as duration and event -- never as inputs."
        )

    # The target is on BOTH sides -- it is the feature store's label and the
    # population's outcome -- so it is dropped from the feature side before the
    # merge. Left in, pandas silently suffixes both to `_x` and `_y` and every
    # reference below fails on a name that no longer exists.
    outcome = population[["subscriber_id_hashed", "days_to_churn", target]].copy()
    frame = features.drop(columns=[target], errors="ignore").merge(
        outcome, on="subscriber_id_hashed", how="inner", validate="1:1"
    )

    event = frame[target].astype(int)
    duration = frame["days_to_churn"].where(event == 1, horizon).astype("float64")

    # The generator writes -1 for a subscriber who never churns; censoring is
    # carried by the event flag, so a negative duration here would be a bug
    # that lifelines reports as an unhelpful convergence failure.
    if (duration <= 0).any():
        raise ValueError(f"{int((duration <= 0).sum())} non-positive durations after censoring")

    frame[DURATION] = duration
    frame[EVENT] = event
    frame = frame.drop(columns=["days_to_churn", target])

    log.info(
        "survival frame: %d rows, %d events (%.2f%%), %d censored at day %d, "
        "median event time %.0f",
        len(frame),
        int(event.sum()),
        100 * event.mean(),
        int((event == 0).sum()),
        horizon,
        float(duration[event == 1].median()),
    )
    return frame


def _design(
    df: pd.DataFrame,
    max_features: int = 25,
    columns: list[str] | None = None,
    medians: pd.Series | None = None,
) -> pd.DataFrame:
    """Numeric design matrix for Cox, trimmed and complete.

    Cox will not fit through missing values and inverts a matrix the size of
    the feature count, so the full 50 columns at 3-6% nullity each leaves
    almost nothing complete and takes a long time to converge badly. Columns
    are ranked by univariate correlation with the event and the top
    `max_features` kept, then median-imputed.

    This is a modelling choice with a cost, and it is stated rather than
    hidden: the concordance below is Cox's on a reduced design, not Cox's on
    everything. The Random Survival Forest challenger takes the full matrix,
    which is part of why it is worth running.
    """
    from cvm.models.m1_churn.gradient_boosting import prepare_matrix

    X, _ = prepare_matrix(df.drop(columns=[DURATION, EVENT], errors="ignore"), target=None)

    if columns is None:
        event = df[EVENT]
        correlation = X.apply(lambda c: abs(c.corr(event)) if c.notna().any() else 0.0)
        keep = correlation.sort_values(ascending=False).head(max_features).index.tolist()
    else:
        # THE TEST SET DOES NOT GET TO PICK ITS OWN COLUMNS. Re-ranking by
        # correlation on held-out rows selects a different top 25, and
        # reindexing onto the training columns afterwards fills the difference
        # with zeros -- silently blanking real covariates and depressing the
        # held-out concordance for a reason that looks like model weakness.
        keep = [c for c in columns if c in X.columns]
        X = X.reindex(columns=columns)

    design = X[keep]
    # Imputed with TRAINING medians where they are supplied. Using the test
    # set's own medians would let it peek at its own distribution -- small
    # here, and the wrong habit to build into the one module that exists to
    # produce an honest held-out number.
    design = design.fillna(design.median() if medians is None else medians)

    # A constant column makes the information matrix singular.
    constant = [c for c in design.columns if design[c].nunique() <= 1]
    if constant and columns is None:
        design = design.drop(columns=constant)
        log.info("cox: dropped %d constant column(s)", len(constant))

    return design


def _holdout(df: pd.DataFrame, frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Temporal train/test halves for an honest concordance.

    IN-SAMPLE CONCORDANCE IS NOT A RESULT. lifelines' `concordance_index_` and
    scikit-survival's `.score()` both report the fit on the rows they were
    fitted to, which flatters a forest far more than a penalised linear model
    -- so an in-sample Cox-against-RSF comparison measures capacity to memorise
    and calls it skill. Both are scored here on rows neither has seen.
    """
    if "snapshot_date" in df.columns:
        order = pd.to_datetime(df["snapshot_date"]).sort_values().index
    else:
        order = df.index
    cut = int(len(order) * frac)
    return df.loc[order[:cut]], df.loc[order[cut:]]


def fit_cox(df: pd.DataFrame, duration_col: str = DURATION, event_col: str = EVENT):
    """Cox Proportional Hazards. Returns the fitted model and a HELD-OUT concordance.

    Semi-parametric: it estimates how covariates SHIFT the hazard without
    assuming a shape for the baseline hazard itself, which is the right trade
    here because nobody knows the shape of a prepaid disengagement curve and
    assuming one would put the answer in the question.
    """
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index

    train, test = _holdout(df)
    design = _design(train)
    fit_frame = design.copy()
    fit_frame[duration_col] = train[duration_col].values
    fit_frame[event_col] = train[event_col].values

    # A small ridge penalty. The features are engineered from overlapping
    # windows and several are near-collinear by construction -- recency
    # against overdue ratio, on-net against off-net -- and unpenalised Cox
    # either fails to converge or returns coefficients with enormous standard
    # errors, which look like findings and are not.
    model = CoxPHFitter(penalizer=0.1)
    model.fit(fit_frame, duration_col=duration_col, event_col=event_col)

    held_out = _design(test, columns=list(design.columns), medians=design.median())
    concordance = float(
        concordance_index(
            test[duration_col], -model.predict_partial_hazard(held_out), test[event_col]
        )
    )
    log.info(
        "cox: %d covariates, held-out concordance %.4f (in-sample %.4f), log-likelihood %.1f",
        design.shape[1],
        concordance,
        model.concordance_index_,
        model.log_likelihood_,
    )

    # THE DESIGN THE MODEL WAS FITTED ON, CARRIED ON THE ARTEFACT.
    #
    # Serving has to rebuild this matrix from whatever a request supplies, and
    # without the training columns and medians it improvises. It did: the API
    # imputed with `design.median()` computed over THE BATCH BEING SCORED, and
    # a single-subscriber request is a one-row batch whose median of a NaN is
    # NaN. Two columns are undefined for anyone with fewer than two recharges
    # in 90 days -- inter_recharge_gap_std and recharge_irregularity -- so the
    # NaN survived the fillna, went through the linear predictor, and came out
    # of `.astype(int)` as -9223372036854775808 in the response body.
    #
    # Same class of fault as scoring with test-set medians, which _design()
    # already takes `medians=` to prevent. The statistics just never reached
    # the artefact, so the serving path could not use them.
    model.design_columns = list(design.columns)
    model.design_medians = design.median()

    return model, concordance


def fit_rsf(df: pd.DataFrame, duration_col: str = DURATION, event_col: str = EVENT):
    """Random Survival Forest challenger. Returns the fitted model and concordance.

    No proportional-hazards assumption, which is the point of running it: if
    the RSF materially beats Cox, the assumption that covariate effects are
    constant over time is not holding, and that is worth knowing before the
    hazard curve is used to set ladder boundaries.

    Fitted on a subsample. The forest is O(n log n) per tree with a survival
    split criterion that is far heavier than a classification one, and on
    100,000 rows it does not finish in a sensible time.
    """
    from sksurv.ensemble import RandomSurvivalForest
    from sksurv.util import Surv

    cap = 20_000
    frame = df
    if len(df) > cap:
        rng = np.random.default_rng(settings.random_seed)
        # Stratified on the event, because at a 3.5% rate a naive subsample of
        # 20,000 can come back with very few events and the forest would have
        # almost nothing to split on.
        events = df.index[df[event_col] == 1]
        censored = df.index[df[event_col] == 0]
        take = min(len(censored), cap - len(events))
        chosen = np.concatenate([events, rng.choice(censored, take, replace=False)])
        frame = df.loc[chosen]
        log.info("rsf: subsampled to %d rows keeping all %d events", len(frame), len(events))

    train, test = _holdout(frame)
    X = _design(train, max_features=25)
    y = Surv.from_arrays(
        event=train[event_col].astype(bool).values, time=train[duration_col].values
    )

    model = RandomSurvivalForest(
        n_estimators=100,
        min_samples_leaf=25,
        n_jobs=-1,
        random_state=settings.random_seed,
    )
    model.fit(X, y)

    X_test = _design(test, columns=list(X.columns), medians=X.median())
    y_test = Surv.from_arrays(
        event=test[event_col].astype(bool).values, time=test[duration_col].values
    )
    concordance = float(model.score(X_test, y_test))
    log.info(
        "rsf: 100 trees on %d x %d, held-out concordance %.4f (in-sample %.4f)",
        *X.shape,
        concordance,
        model.score(X, y),
    )
    return model, concordance


def hazard_inflection_points(df: pd.DataFrame, segment: str | None = None) -> list[int]:
    """Day indices where recovery probability falls sharply.

    Consumed by cvm.decision.ladder to set stage boundaries.

    The method: take the Kaplan-Meier survival curve, difference it to get the
    per-day drop, and return the days where the drop is largest. Those are the
    points where waiting another day costs the most, which is exactly what a
    ladder stage boundary should mark.

    NO MODEL IS TAKEN, and the roadmap's declared signature said one would be.
    Kaplan-Meier is the right estimator here precisely because it assumes
    nothing: it reads the observed curve rather than a fitted one. Cox's
    baseline survival is the curve for a hypothetical subscriber at the mean of
    every covariate, which is a different object and not the one a ladder
    boundary should be cut from -- and it cannot be computed per segment, so
    the population and per-segment boundaries would come from two different
    methods and not be comparable. A vestigial parameter kept for the sake of
    a signature written before the method was chosen would be worse than this
    note.

    A BOUNDARY DERIVED IS BETTER THAN A BOUNDARY CHOSEN, but only just, and
    only because it is reproducible. 7 / 30 / 60 is a guess; these are a guess
    with a curve behind it, computed on generated data. On real Libyan data
    the curve moves and so do the boundaries -- which is the intended
    behaviour, not a caveat.
    """
    frame = df
    if segment is not None:
        if "segment" not in df.columns:
            raise KeyError("segment is absent; cannot compute per-segment boundaries")
        frame = df[df["segment"] == segment]
        if frame[EVENT].sum() < 20:
            raise ValueError(
                f"segment {segment!r} has only {int(frame[EVENT].sum())} events; a curve "
                "fitted on that few would put a ladder boundary on noise"
            )

    event_days = frame.loc[frame[EVENT] == 1, DURATION].astype(int).to_numpy()
    boundaries = _largest_drops(event_days)

    # ARE THESE BOUNDARIES REPRODUCIBLE? That is the question, and it is not the
    # same as "is the curve exactly uniform". A chi-square was tried first and
    # is the wrong test: with 3,523 events it rejects uniformity on trivial
    # overdispersion (chi2=45.7, p=0.025) while the boundaries it then blesses
    # are still noise. Significance and stability are different properties.
    #
    # So: resample and see whether the same days come back. On the current
    # synthetic population they do not -- two halves of the same events return
    # [115, 125, 134] and [115, 122, 130], and only day 115 recurs -- because
    # the generator places churn dates uniformly across the 30-day outcome
    # window and there is no inflection to find. Returning the three largest
    # random fluctuations as derived ladder boundaries would be false
    # precision, and worse than saying the data cannot answer.
    spread = _boundary_spread(event_days)
    if spread > MAX_BOUNDARY_SPREAD_DAYS:
        log.warning(
            "hazard inflections%s: boundaries are not reproducible -- bootstrap spread "
            "%.1f days against a %d-day tolerance, so the curve has no inflection the "
            "resampling agrees on. NO boundaries returned. On real Libyan data this "
            "check passes and the cut-points mean something; here the generator places "
            "churn dates uniformly in the outcome window. (Unstable candidates: %s.)",
            f" for {segment}" if segment else "",
            spread,
            MAX_BOUNDARY_SPREAD_DAYS,
            boundaries,
        )
        return []

    log.info(
        "hazard inflections%s: days %s, bootstrap spread %.1f days",
        f" for {segment}" if segment else "",
        boundaries,
        spread,
    )
    return boundaries


def _largest_drops(event_days: np.ndarray, n: int = 3, apart: int = 5) -> list[int]:
    """The `n` days with the steepest fall in survival, at least `apart` apart.

    Separated so the bootstrap can call exactly the same procedure it is
    checking -- a stability test that resamples a DIFFERENT calculation from
    the one being reported would prove nothing about the reported one.
    """
    from lifelines import KaplanMeierFitter

    if len(event_days) < 30:
        return []

    kmf = KaplanMeierFitter()
    kmf.fit(event_days, event_observed=np.ones(len(event_days)))
    drop = -kmf.survival_function_.iloc[:, 0].diff().fillna(0.0)

    chosen: list[int] = []
    for day in drop.sort_values(ascending=False).index:
        day = int(day)
        if day <= 0:
            continue
        if all(abs(day - b) >= apart for b in chosen):
            chosen.append(day)
        if len(chosen) == n:
            break
    return sorted(chosen)


def _boundary_spread(event_days: np.ndarray, draws: int = 40) -> float:
    """Mean per-rank standard deviation of the boundaries across bootstraps.

    Small means the same cut-points keep coming back; large means they are
    wherever this particular sample's noise happened to pile up.
    """
    rng = np.random.default_rng(settings.random_seed)
    samples = []
    for _ in range(draws):
        resampled = rng.choice(event_days, size=len(event_days), replace=True)
        found = _largest_drops(resampled)
        if len(found) == 3:
            samples.append(found)

    if len(samples) < draws // 2:
        return float("inf")  # too unstable to even produce three boundaries
    return float(np.mean(np.std(np.array(samples), axis=0)))
