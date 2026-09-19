"""Customer lifetime value: BG/NBD + Gamma-Gamma.  Owner: E3

Each RECHARGE is treated as a transaction. The non-contractual,
alive-or-dead-unobserved assumption behind BG/NBD is literally true in prepaid,
which makes this an unusually clean fit rather than a borrowed one -- worth
saying out loud in the report.

Benchmarked against the IBM CLTV field so the number is not self-graded.

CLV's real job in this system is as the BUDGET CEILING: total retention spend
on a subscriber never exceeds a configurable fraction of predicted 12-month CLV
(default 15%). That single constraint is what makes the pricing engine
defensible to a CFO, and it is why this module is a dependency of the
guardrails rather than a reporting nicety.

WHAT WE HAVE, AND WHAT BG/NBD WANTS. The model wants a transaction LOG -- the
timestamp of every purchase. The synthetic population carries one snapshot per
subscriber with 90-day aggregates, so the summary is RECONSTRUCTED:

    frequency = recharge_count_90d - 1      repeat transactions, so minus one
    T         = min(90, tenure_days)        the observation window, not tenure
    recency   = T - days_since_last_topup   age at the last transaction

That is an approximation and it is the main caveat on every number here. It
costs the WITHIN-window timing: two subscribers who each recharged six times
look identical to this summary whether one spread them evenly and the other
front-loaded all six into week one, and BG/NBD would score those very
differently from a real log. It is directionally right and it is not a
substitute for transaction data.

T is the OBSERVATION WINDOW and not tenure, which matters. BG/NBD reads
frequency as the count of repeats within [0, T]; pairing a 90-day count with a
five-year T tells the model that a weekly recharger transacts ten times a
decade, and every predicted value collapses. Subscribers newer than 90 days
get their true, shorter age.

Which is why `fit_bg_nbd` is validated on Online Retail II first -- real repeat
purchases with real timestamps and a calibration/holdout split. That is the
same move Criteo is for uplift: prove the technique on real data before
pointing it at generated data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

# What lifetimes expects, whatever the source.
FREQUENCY, RECENCY, AGE, MONETARY = "frequency", "recency", "T", "monetary_value"


def _conf() -> dict:
    return load_conf("models/m2_value")["clv"]


def summary_from_population(df: pd.DataFrame, window_days: int = 90) -> pd.DataFrame:
    """Reconstruct a BG/NBD summary from the 90-day aggregates.

    See the module docstring for what this approximation costs. Returns the
    four columns lifetimes wants, indexed by subscriber.
    """
    needed = {"recharge_count_90d", "days_since_last_topup", "modal_recharge_amount_lyd"}
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(
            f"{sorted(missing)} absent. BG/NBD needs the RAW recharge count -- "
            "`frequency_raw` is that count divided by (1 + cv) and cannot stand in."
        )

    # THE STORE CARRIES 3% MISSINGNESS BY DESIGN and lifetimes cannot take a
    # NaN -- it does not warn, it fails to converge on the FIRST likelihood
    # evaluation with `NaN result encountered`, which reads like a modelling
    # problem and is a data problem. Every input is imputed explicitly here and
    # the affected rows are flagged, so the fit can exclude them and the
    # dashboard can mark their ceiling as estimated.
    tenure = df.get("tenure_months", pd.Series(np.nan, index=df.index))
    incomplete = (
        tenure.isna()
        | df["days_since_last_topup"].isna()
        | df["recharge_count_90d"].isna()
        | df["modal_recharge_amount_lyd"].isna()
    )

    # Unknown tenure -> the full observation window. It is the maximum possible
    # age, which makes the implied transaction rate the LOWEST consistent with
    # the count -- the conservative direction for a spending ceiling.
    age = np.minimum(window_days, tenure.fillna(window_days / 30.0) * 30.0).clip(lower=1.0)

    # Repeat transactions: BG/NBD counts purchases AFTER the first.
    frequency = (df["recharge_count_90d"].fillna(0) - 1).clip(lower=0)

    # Age at the last transaction. Someone who has never repeated has recency 0.
    # Unknown recency with a known repeat count gets the population's median
    # position within its window rather than an arbitrary end of it.
    since = df["days_since_last_topup"]
    recency = (age - since).clip(lower=0)
    ratio = (recency / age).median()
    recency = recency.where(since.notna(), age * ratio)
    recency = np.minimum(recency, age).where(frequency > 0, 0.0)

    monetary = df["modal_recharge_amount_lyd"]
    monetary = monetary.fillna(monetary.median())

    out = pd.DataFrame(
        {
            FREQUENCY: frequency.astype("float64"),
            RECENCY: pd.Series(recency, index=df.index).astype("float64"),
            AGE: pd.Series(age, index=df.index).astype("float64"),
            MONETARY: monetary.astype("float64"),
            "is_imputed": incomplete.astype("int8"),
        },
        index=df.index,
    )
    if "subscriber_id_hashed" in df.columns:
        out.index = pd.Index(df["subscriber_id_hashed"], name="subscriber_id_hashed")

    residual = out[[FREQUENCY, RECENCY, AGE, MONETARY]].isna().sum().sum()
    if residual:
        raise ValueError(
            f"{residual} NaN survived the imputation. lifetimes will not converge on "
            "these and the error it raises names the optimiser, not the data."
        )

    log.info(
        "clv summary: %d subscribers, %.1f%% with a repeat, median frequency %.0f over "
        "T=%.0f days; %.1f%% had an input imputed and are excluded from the FIT",
        len(out),
        100 * (out[FREQUENCY] > 0).mean(),
        out[FREQUENCY].median(),
        out[AGE].median(),
        100 * out["is_imputed"].mean(),
    )
    return out


def complete_cases(rfm_summary: pd.DataFrame) -> pd.DataFrame:
    """The rows fit on. Parameters should not be estimated from imputed inputs.

    Scoring everyone is right -- a subscriber with no budget ceiling has no
    constraint, which is worse than an estimated one. Fitting on everyone is
    not: it would let the imputation's own median shape the parameters and then
    present the result as measurement.
    """
    if "is_imputed" not in rfm_summary.columns:
        return rfm_summary
    return rfm_summary[rfm_summary["is_imputed"] == 0]


def fit_bg_nbd(rfm_summary: pd.DataFrame, penalizer: float = 0.0):
    """Beta-Geometric / NBD on repeat-transaction counts.

    Models two things at once: how often a live customer transacts, and the
    probability they went permanently inactive after any given transaction.
    Prepaid is the textbook case -- nobody cancels, so "alive" is genuinely
    unobserved, which is exactly the assumption the model is built on rather
    than one it has to survive.

    THE PENALIZER IS ZERO, AND THAT WAS MEASURED RATHER THAN ASSUMED. The first
    version used 0.01 on the reasoning that the likelihood is flat in places
    and an unpenalised fit would wander. That reasoning is backwards here: the
    penalty shrinks `a` and `b` toward zero, and once b < 1 the dropout Beta is
    U-shaped and lifetimes' conditional expectation takes the log of a negative
    quantity. On Online Retail II:

        penalizer      a        b     NaN predictions    MAE
            0.0     0.157    3.317          0           1.085
            0.001   0.086    1.274          0           1.087
            0.01    0.047    0.570        844           1.139
            0.1     0.017    0.203        220           1.089

    So the value chosen to make the fit stable was the one that broke it, for
    844 of 4,933 customers -- every one of them a customer with no repeat
    purchase, which is the group a prepaid base has most of. The guard below
    exists because that failure returned NaN rather than raising.
    """
    from lifetimes import BetaGeoFitter

    frame = _require_columns(rfm_summary, (FREQUENCY, RECENCY, AGE))
    model = BetaGeoFitter(penalizer_coef=penalizer)
    model.fit(frame[FREQUENCY], frame[RECENCY], frame[AGE])

    a, b = model.params_["a"], model.params_["b"]
    log.info(
        "bg/nbd: r=%.4f alpha=%.4f a=%.4f b=%.4f on %d customers",
        model.params_["r"],
        model.params_["alpha"],
        a,
        b,
        len(frame),
    )

    # The degenerate region, checked on the fit rather than discovered later in
    # a column of NaNs. A silent NaN here propagates into CLV, into the budget
    # ceiling, and out to a subscriber who then has no ceiling at all.
    probe = model.predict(30.0, frame[FREQUENCY], frame[RECENCY], frame[AGE])
    unusable = int(np.isnan(np.asarray(probe, dtype="float64")).sum())
    if unusable:
        raise ValueError(
            f"bg/nbd returned NaN for {unusable} of {len(frame)} customers at a=%.4f, "
            f"b={b:.4f}. b < 1 makes the dropout Beta U-shaped and the conditional "
            f"expectation takes the log of a negative number. Lower the penalizer "
            f"(currently {penalizer}) -- 0.0 is the measured stable choice." % a
        )
    return model


def fit_gamma_gamma(rfm_summary: pd.DataFrame, penalizer: float = 0.01):
    """Gamma-Gamma on spend per transaction, for repeat customers only.

    ITS ONE ASSUMPTION IS CHECKABLE AND IS CHECKED. Gamma-Gamma requires
    frequency and monetary value to be uncorrelated -- if people who buy more
    often also spend more per purchase, the model's independence is violated
    and it will mis-price exactly the high-value subscribers the budget
    ceiling is meant to protect. The correlation is computed and logged, and
    anything above 0.1 is warned about rather than left for a reader to
    discover.

    Customers with no repeat purchase are excluded, because a conditional
    expectation over spend needs at least one observation to condition on.
    """
    from lifetimes import GammaGammaFitter

    frame = _require_columns(rfm_summary, (FREQUENCY, MONETARY))
    repeat = frame[(frame[FREQUENCY] > 0) & (frame[MONETARY] > 0)]
    if repeat.empty:
        raise ValueError("no repeat customers with positive spend; Gamma-Gamma cannot fit")

    correlation = float(repeat[FREQUENCY].corr(repeat[MONETARY]))
    if abs(correlation) > 0.1:
        log.warning(
            "gamma-gamma: frequency and monetary value correlate at %.3f. The model "
            "assumes they do not, so spend is mis-estimated where it matters most -- "
            "treat the high-value tail as indicative and say so in the report.",
            correlation,
        )
    else:
        log.info("gamma-gamma: frequency/monetary correlation %.3f, assumption holds", correlation)

    model = GammaGammaFitter(penalizer_coef=penalizer)
    model.fit(repeat[FREQUENCY], repeat[MONETARY])

    log.info(
        "gamma-gamma: p=%.4f q=%.4f v=%.4f on %d repeat customers (%.1f%% of the base)",
        model.params_["p"],
        model.params_["q"],
        model.params_["v"],
        len(repeat),
        100 * len(repeat) / len(frame),
    )
    model.frequency_monetary_correlation_ = correlation
    return model


def predict_clv(bgf, ggf, rfm_summary: pd.DataFrame, months: int | None = None) -> pd.Series:
    """Discounted expected value over the horizon, per subscriber.

    Discounted, at the configured monthly rate. An undiscounted twelve-month
    CLV overstates the ceiling by roughly 6% at 1% monthly, which sounds small
    until it is 15% of a number the pricing engine is allowed to spend.

    Subscribers with no repeat transaction get a value rather than a NaN:
    Gamma-Gamma cannot condition on their spend, so their modal recharge stands
    in for it and the BG/NBD side still supplies their expected transaction
    count. Dropping them would exclude a third of the base from a budget
    ceiling, which in practice means they get no ceiling at all.
    """
    conf = _conf()
    months = conf["horizon_months"] if months is None else months
    discount = conf["discount_rate_monthly"]

    frame = _require_columns(rfm_summary, (FREQUENCY, RECENCY, AGE, MONETARY))
    repeat = frame[FREQUENCY] > 0

    # lifetimes wants the monetary column filled for everyone it scores, so the
    # single-purchase rows carry their own observed spend.
    monetary = frame[MONETARY].where(frame[MONETARY] > 0, frame[MONETARY].median())

    value = ggf.customer_lifetime_value(
        bgf,
        frame[FREQUENCY],
        frame[RECENCY],
        frame[AGE],
        monetary,
        time=months,
        discount_rate=discount,
        freq="D",
    )
    value = pd.Series(value, index=frame.index, name="clv_12m").clip(lower=0.0)

    log.info(
        "clv: %d-month horizon at %.1f%%/month -- median %.1f LYD, p90 %.1f, "
        "mean %.1f (%.1f%% single-purchase, valued from their own spend)",
        months,
        100 * discount,
        value.median(),
        value.quantile(0.9),
        value.mean(),
        100 * (~repeat).mean(),
    )
    return value


def retention_budget_ceiling(clv: pd.Series) -> pd.Series:
    """The number the pricing engine is actually allowed to spend.

    THIS is what M2 exists for. Everything above is how the ceiling is
    estimated; this is the ceiling. Read from conf/pricing.yaml rather than
    conf/models/m2_value.yaml, because the guardrail owns the fraction and the
    model owns the estimate -- and the test that pins 15% of a 480 LYD annual
    value to 72 LYD reads the same key.
    """
    guard = load_conf("pricing")["guardrails"]["clv_ceiling"]
    if not guard.get("enabled", True):
        raise ValueError(
            "clv_ceiling is disabled in conf/pricing.yaml. It is the constraint that "
            "makes the pricing engine defensible; tests/guardrails/ asserts it is on."
        )
    fraction = guard["max_fraction_of_clv"]
    ceiling = (clv * fraction).rename("retention_ceiling_lyd")

    log.info(
        "budget ceiling: %.0f%% of CLV -- median %.2f LYD, p10 %.2f, p90 %.2f",
        100 * fraction,
        ceiling.median(),
        ceiling.quantile(0.1),
        ceiling.quantile(0.9),
    )
    return ceiling


def validate_on_real_purchases(calibration_end: str = "2011-06-01") -> dict[str, float]:
    """Fit on Online Retail II's calibration period, score its holdout.

    THE POINT OF THIS FUNCTION. Every CLV number for Almadar is computed on
    generated recharges from a reconstructed summary, so it cannot validate
    itself -- a good fit there would only mean the generator and the model
    agree. Online Retail II has real repeat purchases with real timestamps, so
    fitting on one period and scoring the next measures whether the TECHNIQUE
    works. It is the same role Criteo plays for uplift.

    Reports MAE on predicted against actual holdout transactions, and the
    Spearman correlation -- which is the more honest headline, because the
    ceiling only needs the ORDERING to be right.
    """
    from lifetimes.utils import calibration_and_holdout_data  # noqa: F401 -- see summary()
    from scipy.stats import spearmanr

    from cvm.ingest.online_retail import summary

    frame = summary(calibration_end=calibration_end)
    frame = frame[frame["frequency_cal"] >= 0]

    bgf = fit_bg_nbd(
        frame.rename(columns={"frequency_cal": FREQUENCY, "recency_cal": RECENCY, "T_cal": AGE})[
            [FREQUENCY, RECENCY, AGE]
        ]
    )

    holdout_days = float(frame["duration_holdout"].iloc[0])
    predicted = bgf.predict(
        holdout_days, frame["frequency_cal"], frame["recency_cal"], frame["T_cal"]
    )
    actual = frame["frequency_holdout"]

    mae = float(np.abs(predicted - actual).mean())
    rmse = float(np.sqrt(((predicted - actual) ** 2).mean()))
    rho = float(spearmanr(predicted, actual).statistic)

    metrics = {
        "customers": len(frame),
        "holdout_days": holdout_days,
        "mae": mae,
        "rmse": rmse,
        "spearman": rho,
        "mean_actual": float(actual.mean()),
        "mean_predicted": float(predicted.mean()),
    }
    log.info(
        "bg/nbd on REAL purchases: %d customers, %.0f-day holdout -- MAE %.3f against a "
        "mean actual of %.3f, Spearman %.3f",
        metrics["customers"],
        holdout_days,
        mae,
        metrics["mean_actual"],
        rho,
    )
    return metrics


def benchmark_against_ibm(predicted: pd.Series, ibm_cltv: pd.Series) -> dict[str, float]:
    """MAE, RMSE, MAPE and Spearman against the IBM CLTV field.

    WHAT THIS CAN AND CANNOT SHOW. IBM Telco is a postpaid US telco and its
    CLTV column is a vendor-computed number of undocumented provenance. These
    are different subscribers on a different continent under a different
    billing model, so the two series are NOT paired and an MAE between them
    would be meaningless.

    What can be compared is the SHAPE: whether a CLV distribution built this
    way has the same spread and skew as one a commercial vendor ships. So the
    errors are computed quantile-to-quantile -- our p10 against their p10 and
    so on -- after scaling each series by its own median, because LYD and USD
    are not the same unit.

    THERE IS DELIBERATELY NO SPEARMAN HERE, and the config asking for one is
    the reason to say so rather than quietly supply it. Two series can only be
    rank-correlated if they are PAIRED, and these are different people. The
    first version of this function correlated the two quantile vectors, which
    returns exactly 1.000 every time for any two distributions whatsoever --
    quantiles are sorted by construction. A metric that cannot fail is not
    evidence, and printing 1.000 beside the word "Spearman" would read as a
    perfect result.

    The accuracy claim rests on `validate_on_real_purchases`, and only there.
    """
    quantiles = np.linspace(0.05, 0.95, 19)
    ours = predicted.quantile(quantiles).to_numpy()
    theirs = pd.Series(ibm_cltv).dropna().quantile(quantiles).to_numpy()

    # Scale-free: both series are normalised by their own median before the
    # error, because LYD and USD are not the same unit and never will be.
    ours_scaled = ours / np.median(ours)
    theirs_scaled = theirs / np.median(theirs)

    ours_spread = float(predicted.quantile(0.9) / max(predicted.quantile(0.1), 1e-9))
    theirs_spread = float(
        pd.Series(ibm_cltv).quantile(0.9) / max(pd.Series(ibm_cltv).quantile(0.1), 1e-9)
    )

    metrics = {
        "quantiles": len(quantiles),
        "mae_scaled": float(np.abs(ours_scaled - theirs_scaled).mean()),
        "rmse_scaled": float(np.sqrt(((ours_scaled - theirs_scaled) ** 2).mean())),
        "our_p50": float(predicted.median()),
        "their_p50": float(pd.Series(ibm_cltv).median()),
        "our_p90_over_p10": ours_spread,
        "their_p90_over_p10": theirs_spread,
        "spread_ratio": ours_spread / max(theirs_spread, 1e-9),
    }
    log.info(
        "ibm shape check (NOT paired, no rank metric is possible): scaled MAE %.3f; "
        "spread p90/p10 ours %.2f against theirs %.2f -- ours is %.1fx more dispersed%s",
        metrics["mae_scaled"],
        ours_spread,
        theirs_spread,
        metrics["spread_ratio"],
        (
            ", which is a real difference and not a bug: a prepaid base ranges from "
            "5 LYD floor-rechargers to heavy users, where a postpaid contract base "
            "is compressed by its own tariff structure"
            if metrics["spread_ratio"] > 2
            else ""
        ),
    )
    return metrics


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise KeyError(
            f"{missing} absent from the summary. lifetimes expects "
            f"{list(columns)}; build it with `summary_from_population`."
        )
    return frame


def seed() -> int:
    return settings.random_seed
