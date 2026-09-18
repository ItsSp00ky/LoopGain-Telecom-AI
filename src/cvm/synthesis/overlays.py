"""Business-rule overlays: the constructs real data cannot supply.

Cell2Cell is US postpaid. It has no concept of a scratch card, a zero-balance
night, an emergency airtime advance, or a 06:00-11:00 morning pass. Those are
the parts of a Libyan prepaid subscriber that no public dataset carries, so the
generator learns the behavioural *shape* from real data and these overlays add
the prepaid layer on top.

Two overlays are anchored to confirmed Almadar products rather than guessed:
the 06:00-11:00 morning usage bump (عروض الصبح exists and is time-boxed to
exactly that window) and emergency-credit behaviour for both رصيد في وقته and
نت في وقته. See conf/catalogue.yaml.

RAMADAN SEASONALITY IS NOT HERE, and its absence is deliberate. It needs real
per-year dates, the window moves ~11 days annually, and the effect we would
have applied -- night data up, daytime voice down -- was a guess with a large
magnitude. A large guessed effect is worse than none: it puts structure in the
data that the models will happily learn and that nothing validates.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings
from cvm.synthesis.quantile_map import assert_on_ladder, recharge_ladder

log = logging.getLogger(__name__)


def _overlay_conf() -> dict:
    return load_conf("data")["synthesis"]["business_overlays"]


def _rng(offset: int = 0) -> np.random.Generator:
    """One generator per overlay, seeded off the global seed.

    Separate streams so adding an overlay does not change the draws of the
    ones before it -- otherwise every population is irreproducible the moment
    the pipeline grows.
    """
    return np.random.default_rng(settings.random_seed + offset)


# ---------------------------------------------------------------------------
# Network quality -- subscriber level, no geography
# ---------------------------------------------------------------------------


def apply_service_outage_exposure(df: pd.DataFrame) -> pd.DataFrame:
    """Power- and fuel-driven downtime, at SUBSCRIBER level.

    No geographic variation: all subscribers are drawn from one distribution.
    Geography was dropped, so there are no districts to weight by.

    Heavy-tailed rather than normal. Most subscribers see almost no outage and
    a minority see a great deal, which is what makes this a churn signal at
    all -- a symmetric distribution around a mean would give every subscriber
    roughly the same experience and nothing to discriminate on.
    """
    conf = _overlay_conf()["service_outage_exposure"]
    if not conf.get("enabled", True):
        return df
    if conf.get("level") != "subscriber":
        raise ValueError(
            f"service_outage_exposure.level is {conf.get('level')!r}; only "
            "'subscriber' is supported since geography was dropped (Q9)."
        )

    rng = _rng(1)
    out = df.copy()
    n = len(out)

    # Lognormal hours over 30 days, clipped at a fortnight: beyond that the
    # subscriber has no service at all and would not be in an active base.
    out["service_outage_hours_30d"] = np.clip(rng.lognormal(1.2, 1.1, n), 0, 336).round(2)

    # Dropped calls and data failures rise with outage exposure but are not
    # determined by it -- a subscriber can have a bad cell without an outage.
    #
    # Cell2Cell measures both (drop_vce_Mean, drop_dat_Mean), so where the
    # generator supplied them the outage exposure is ADDED to what it learned
    # rather than replacing it. Only `service_outage_hours_30d` is wholly ours:
    # a US postpaid network does not lose power for six hours.
    exposure = out["service_outage_hours_30d"] / 336
    for column, (alpha, beta, weight) in {
        "dropped_call_rate_30d": (2, 60, 0.25),
        "data_session_failure_rate": (2, 45, 0.30),
    }.items():
        learned = (
            pd.to_numeric(out[column], errors="coerce").fillna(0).to_numpy()
            if column in out.columns
            else rng.beta(alpha, beta, n)
        )
        out[column] = np.clip(learned + weight * exposure * rng.random(n), 0, 1).round(4)

    log.info(
        "overlay service_outage: median %.1f h, p90 %.1f h, dropped-call median %.4f",
        out["service_outage_hours_30d"].median(),
        out["service_outage_hours_30d"].quantile(0.90),
        out["dropped_call_rate_30d"].median(),
    )
    return out


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def apply_salary_week_spike(df: pd.DataFrame) -> pd.DataFrame:
    """Public-sector salary disbursement drives a pronounced recharge spike.

    Days 25-30. The flag is what the feature set consumes (`is_salary_week`);
    the multiplier shapes how much of a subscriber's month-end recharge lands
    in that window, which is what makes `modal_recharge_amount_lyd` differ
    from the mean -- and that difference is the basis of M4's affordability
    ceiling.
    """
    conf = _overlay_conf()["salary_week_spike"]
    if not conf.get("enabled", True):
        return df

    start, end = conf["day_of_month_window"]
    multiplier = load_conf("market")["calendar"]["salary_week"]["recharge_multiplier"]

    rng = _rng(2)
    out = df.copy()
    n = len(out)

    day_of_month = rng.integers(1, 29, n)
    out["is_salary_week"] = ((day_of_month >= start) & (day_of_month <= end)).astype("int8")

    # Share of the subscriber's recharges that fall in the salary window. A
    # public-sector household concentrates there; others do not.
    salary_dependent = rng.random(n) < 0.45
    out["salary_week_recharge_share"] = np.where(
        salary_dependent,
        np.clip(rng.beta(4, 3, n) * (multiplier / 1.8), 0, 1),
        np.clip(rng.beta(2, 6, n), 0, 1),
    ).round(4)

    log.info(
        "overlay salary_week: %.1f%% flagged, salary-dependent share median %.3f",
        100 * out["is_salary_week"].mean(),
        out.loc[salary_dependent, "salary_week_recharge_share"].median(),
    )
    return out


def apply_weekend_rhythm(df: pd.DataFrame) -> pd.DataFrame:
    """Friday-Saturday rhythm. A derived share only, NO usage multiplier.

    Libya's weekend is a public fact, not an operator figure we are estimating,
    which is why it survived the cull of unsupported seasonality. What was
    deliberately not kept is a multiplier: that would have been the guessed
    part. `weekend_usage_share_30d` is a property of the subscriber -- whether
    their mornings are free -- and it is the feature the 06:00-11:00 morning
    pass turns on.

    Two-sevenths (0.286) is the share a subscriber with no weekly pattern would
    show, so the distribution is centred there and spread around it.
    """
    conf = _overlay_conf()["weekend_rhythm"]
    if not conf.get("enabled", True):
        return df
    if conf.get("apply_usage_multiplier", False):
        raise ValueError(
            "weekend_rhythm.apply_usage_multiplier is true. It must stay false: "
            "the weekend flag is a public fact, a usage multiplier on top of it "
            "would be a guess, and conf/market.yaml records that decision."
        )

    rng = _rng(3)
    out = df.copy()
    flat = 2 / 7

    # Beta centred near 2/7, so most subscribers are weekly-flat and the tails
    # are the commuters (low weekend share) and the weekend-heavy.
    out["weekend_usage_share_30d"] = np.clip(rng.beta(4, 10, len(out)), 0.01, 0.99).round(4)
    out["is_weekend_heavy"] = (out["weekend_usage_share_30d"] > flat * 1.5).astype("int8")

    log.info(
        "overlay weekend: share median %.3f (flat would be %.3f), %.1f%% weekend-heavy",
        out["weekend_usage_share_30d"].median(),
        flat,
        100 * out["is_weekend_heavy"].mean(),
    )
    return out


# ---------------------------------------------------------------------------
# Prepaid mechanics
# ---------------------------------------------------------------------------


def apply_prepaid_recharge_behaviour(df: pd.DataFrame) -> pd.DataFrame:
    """Recharge cadence, balance exhaustion, and the affordability basis.

    Cell2Cell has none of this: a postpaid subscriber never runs out of credit.
    Every field here is a prepaid construct, and three of them are hazard
    drivers, so this overlay must run before labels are generated.

    `modal_recharge_amount_lyd` is the one M4 leans on. The MODE, not the mean:
    the mean is inflated by a single salary-week top-up a subscriber will not
    repeat, and lending against it would systematically over-extend to exactly
    the subscribers the affordability guard exists to protect.
    """
    rng = _rng(4)
    out = df.copy()
    n = len(out)
    ladder = np.asarray(recharge_ladder(), dtype=float)

    # Recharge count over 90 days, from heavy users to the nearly dormant.
    out["recharge_count_90d"] = np.clip(rng.negative_binomial(4, 0.28, n), 0, 90).astype("int16")

    # Gap cadence. The CV matters more than the count: five regular recharges
    # is a healthy subscriber, five erratic ones is a wobbling one.
    mean_gap = np.where(
        out["recharge_count_90d"] > 0, 90 / np.maximum(out["recharge_count_90d"], 1), 90
    )
    out["inter_recharge_gap_mean"] = mean_gap.round(2)
    out["recharge_gap_cv"] = np.clip(rng.gamma(2.2, 0.28, n), 0, 3).round(4)
    out["inter_recharge_gap_std"] = (out["inter_recharge_gap_mean"] * out["recharge_gap_cv"]).round(
        2
    )

    # Days since the last top-up. Correlated with the gap, plus a tail of
    # subscribers who have simply stopped -- the population churn comes from.
    out["days_since_last_topup"] = np.clip(
        rng.exponential(np.maximum(mean_gap, 1) * 0.7), 0, 180
    ).round(0)

    # Modal denomination, weighted toward the bottom of the ladder.
    weights = np.asarray(load_conf("market")["recharge"]["denomination_weights"]["values"])
    out["modal_recharge_amount_lyd"] = rng.choice(ladder, size=n, p=weights / weights.sum())
    assert_on_ladder(out["modal_recharge_amount_lyd"])

    out["consecutive_sub_5_lyd_recharges"] = np.where(
        out["modal_recharge_amount_lyd"] <= ladder.min(),
        rng.integers(0, 8, n),
        rng.integers(0, 2, n),
    ).astype("int8")

    # Hours at a zero balance over 30 days. Strongly tied to modal recharge:
    # a 5 LYD recharger spends far more of the month at zero than a 100 LYD one.
    affordability = 1 - (
        np.searchsorted(ladder, out["modal_recharge_amount_lyd"]) / max(len(ladder) - 1, 1)
    )
    out["balance_zero_hours_30d"] = np.clip(
        rng.gamma(1.6, 40 * (0.25 + affordability), n), 0, 720
    ).round(1)

    out["failed_bundle_attempts_30d"] = rng.poisson(1.8 * affordability, n).astype("int8")

    log.info(
        "overlay prepaid: recharges/90d median %d, days_since_last_topup median %.0f, "
        "zero-balance hours median %.0f, modal ladder shares %s",
        int(out["recharge_count_90d"].median()),
        out["days_since_last_topup"].median(),
        out["balance_zero_hours_30d"].median(),
        {
            int(k): round(v, 3)
            for k, v in out["modal_recharge_amount_lyd"]
            .value_counts(normalize=True)
            .sort_index()
            .items()
        },
    )
    return out


def apply_dual_sim_leakage(df: pd.DataFrame) -> pd.DataFrame:
    """The share-of-wallet signal, deviating from a measured baseline.

    Cell2Cell gives the real shape: median `incoming_outgoing_ratio` 0.280,
    3.0% above 1.0. But that is a SINGLE-SIM POSTPAID market, so it is the
    baseline to deviate FROM, not to reproduce. At 85% dual-SIM penetration
    the right tail must be far fatter -- a ratio above 1.0 means a subscriber
    receives more than they place, which is what a receiving SIM looks like.

    The measured median is preserved; the tail is thickened deliberately, and
    the deviation is documented rather than hidden.
    """
    leakage = load_conf("features")["families"]["leakage"]
    baseline_median = float(leakage["baseline_median"])
    baseline_tail = float(leakage["baseline_share_above_one"])
    dual_sim = float(load_conf("market")["base"]["dual_sim_penetration"])

    rng = _rng(5)
    out = df.copy()
    n = len(out)

    # DEVIATE FROM THE GENERATOR'S RATIO, do not replace it. If the generator
    # produced this column it learned the real Cell2Cell shape, and that shape
    # is the grounding claim -- overwriting it with a fresh draw would make the
    # claim false while leaving the sentence in the proposal intact.
    #
    # The deviation is a rank-preserving stretch: each subscriber keeps their
    # position in the distribution, and the upper tail is pushed out in
    # proportion to dual-SIM penetration. A ratio above 1.0 means a subscriber
    # receives more than they place, which is what a receiving SIM looks like,
    # and at 85% dual-SIM far more of the base must sit there than in a
    # single-SIM market.
    stretch = 1.0 + 1.6 * dual_sim
    if "incoming_outgoing_ratio" in out.columns:
        learned = pd.to_numeric(out["incoming_outgoing_ratio"], errors="coerce")
        learned = learned.fillna(learned.median()).clip(lower=0.01)
        # Stretch on the log scale about the measured median, so the median is
        # preserved and the tails move.
        deviated = baseline_median * np.exp(stretch * np.log(learned / baseline_median))
        out["incoming_outgoing_ratio"] = np.clip(deviated, 0.01, 20).round(4)
        log.info(
            "overlay dual_sim: stretched the generator's ratio by %.2fx on the log scale", stretch
        )
    else:
        sigma = 0.75 + 0.9 * dual_sim
        out["incoming_outgoing_ratio"] = np.clip(
            rng.lognormal(np.log(baseline_median), sigma, n), 0.01, 20
        ).round(4)
        log.info("overlay dual_sim: no learned ratio present, drew one from the baseline")

    # On-net share has no Cell2Cell equivalent: it is a single-operator US
    # dataset, so there is no off-net to measure. Purely generated, and said so.
    if "onnet_ratio" not in out.columns:
        out["onnet_ratio"] = np.clip(rng.beta(5, 3, n), 0.01, 0.99).round(4)
    out["offnet_share_30d"] = (1 - out["onnet_ratio"]).round(4)
    out["distinct_called_numbers_30d"] = np.clip(rng.negative_binomial(6, 0.22, n), 0, 300).astype(
        "int16"
    )

    realised_tail = float((out["incoming_outgoing_ratio"] > 1).mean())
    log.info(
        "overlay dual_sim: median %.3f (baseline %.3f), share>1.0 %.3f "
        "(baseline %.3f, deliberately fatter at %.0f%% dual-SIM)",
        out["incoming_outgoing_ratio"].median(),
        baseline_median,
        realised_tail,
        baseline_tail,
        100 * dual_sim,
    )
    if realised_tail <= baseline_tail:
        raise ValueError(
            f"share above 1.0 is {realised_tail:.4f}, no fatter than the single-SIM "
            f"baseline {baseline_tail:.4f}. The whole point of this overlay is the "
            "deviation; without it the population is a US postpaid market in LYD."
        )
    return out


def apply_morning_offpeak_usage(df: pd.DataFrame) -> pd.DataFrame:
    """Put a 06:00-11:00 usage bump on subscribers who buy عروض الصبح.

    Without this, offpeak_data_ratio is noise and M3 cannot tell who would
    actually use a morning pass.

    Anchored on two real things: Cell2Cell's measured off-peak share (median
    0.424) and the fact that Almadar sells a 1 LYD pass valid only 06:00-11:00.
    The operator priced its own spare capacity and told us when it is, which is
    unusually strong evidence for an assumption of this kind.

    The bump is applied to the subscribers whose mornings are actually free --
    `weekend_usage_share_30d` from the weekend overlay is the proxy -- so
    `offpeak_data_ratio` correlates with something rather than being uniform
    noise dressed as a feature.
    """
    if not _overlay_conf().get("morning_offpeak_usage", True):
        return df
    if "weekend_usage_share_30d" not in df.columns:
        raise KeyError(
            "apply_weekend_rhythm must run before apply_morning_offpeak_usage: "
            "the morning bump is applied to subscribers whose mornings are free, "
            "and the weekend share is how we identify them."
        )

    window = load_conf("pricing")["offpeak"]["window"]
    ratios = load_conf("features")["families"]["ratios_mix"]
    if "offpeak_data_ratio" not in ratios:
        raise ValueError("offpeak_data_ratio is no longer a declared feature")

    rng = _rng(6)
    out = df.copy()
    n = len(out)

    # Free mornings: below-average weekend share means a weekday-flat pattern,
    # which in practice is someone not tied to an office.
    free_mornings = out["weekend_usage_share_30d"] < out["weekend_usage_share_30d"].median()

    # Same principle as the leakage overlay: keep the generator's learned
    # off-peak share where there is one, and ADD the morning bump on top. The
    # 0.424 median is measured; the bump is the Libyan product effect.
    # The generator supplies `offpeak_activity_ratio` -- measured off-peak share
    # of VOICE minutes. The data ratio is derived from it rather than equated
    # with it: the transferable claim is that a subscriber active in the
    # off-peak window stays that kind of subscriber, not that their voice and
    # data split the day identically.
    if "offpeak_activity_ratio" in out.columns:
        activity = pd.to_numeric(out["offpeak_activity_ratio"], errors="coerce")
        base = activity.fillna(activity.median()).clip(0.01, 0.99).to_numpy()
        source = "derived from the measured off-peak activity share"
    else:
        base = rng.beta(4, 5.5, n)  # centred near the measured 0.424
        source = "drawn from the measured baseline"

    out["offpeak_data_ratio"] = np.clip(
        base + np.where(free_mornings, rng.beta(2, 6, n) * 0.35, 0), 0.01, 0.99
    ).round(4)

    out["morning_pass_propensity"] = np.clip(
        0.15 + 0.55 * out["offpeak_data_ratio"] + rng.normal(0, 0.08, n), 0, 1
    ).round(4)

    log.info(
        "overlay morning_offpeak: window %02d:00-%02d:00, base from %s, ratio median %.3f "
        "(measured baseline 0.424), free-mornings median %.3f vs %.3f",
        window["start_hour"],
        window["end_hour"],
        source,
        out["offpeak_data_ratio"].median(),
        out.loc[free_mornings, "offpeak_data_ratio"].median(),
        out.loc[~free_mornings, "offpeak_data_ratio"].median(),
    )
    return out


def apply_emergency_credit_behaviour(df: pd.DataFrame) -> pd.DataFrame:
    """Generate the M4 label surface for both Almadar emergency products.

    Fields: airtime_advance_count_90d, data_advance_count_90d, days_to_settle,
    unpaid_advance_days, emergency_service_alternations_90d.

    Three things the overlay MUST reproduce, or M4 has nothing to find:

    1. **Eligibility is balance-based, not tenure-based.** Advances happen when
       balance falls to <= 0.5 LYD (airtime) or <= 1 LYD with < 250 MB left
       (data). The eligible population is therefore selected on being broke --
       the inverse of a risk filter.
    2. **The 5 LYD data advance is exactly the size of the 5 LYD smallest
       card.** Clearing it consumes the whole minimum top-up and returns the
       subscriber to a zero balance, so the recharge buys nothing and the
       rational move is to defer it. Some subscribers must therefore show a
       long `unpaid_advance_days` AND a rising `days_since_last_topup`: the
       harm is a disincentive to recharge, not a locked door.
    3. **The two products are mutually exclusive**, so distressed subscribers
       alternate between them. That alternation must be visible in the data.
    """
    if not _overlay_conf().get("emergency_credit_behaviour", True):
        return df
    for required in ("balance_zero_hours_30d", "modal_recharge_amount_lyd"):
        if required not in df.columns:
            raise KeyError(
                f"{required} is missing; apply_prepaid_recharge_behaviour must run first. "
                "Emergency credit is conditioned on being broke, which is what that "
                "overlay establishes."
            )

    catalogue = load_conf("catalogue")["emergency_credit"]
    airtime_rungs = np.asarray(catalogue["rasid_fi_waqtuh"]["denominations_lyd"], dtype=float)
    data_debt = float(catalogue["net_fi_waqtuh"]["price_lyd"])
    smallest_card = float(min(recharge_ladder()))

    rng = _rng(7)
    out = df.copy()
    n = len(out)

    # 1. Eligibility follows exhaustion, not tenure.
    broke = out["balance_zero_hours_30d"] / 720
    eligibility = np.clip(broke * 1.4 + rng.normal(0, 0.1, n), 0, 1)

    out["airtime_advance_count_90d"] = rng.poisson(3.2 * eligibility, n).astype("int8")
    out["data_advance_count_90d"] = rng.poisson(1.4 * eligibility, n).astype("int8")
    took_any = (out["airtime_advance_count_90d"] + out["data_advance_count_90d"]) > 0

    # 2. The zero-residual trap. A subscriber whose modal card equals the debt
    #    gains nothing by clearing it, so settlement stretches out.
    zero_residual = (out["modal_recharge_amount_lyd"] <= smallest_card) & (
        out["data_advance_count_90d"] > 0
    )
    out["days_to_settle"] = np.where(
        took_any, np.clip(rng.gamma(2.0, 2.2, n) + zero_residual * 6.0, 0, 60).round(1), -1
    )
    out["unpaid_advance_days"] = np.where(
        took_any,
        np.clip(rng.gamma(1.3, 3.0, n) + zero_residual * rng.gamma(2.0, 6.0, n), 0, 120).round(1),
        0,
    )

    # The disincentive, made measurable: deferred recharge, not a locked line.
    out.loc[zero_residual, "days_since_last_topup"] = np.clip(
        out.loc[zero_residual, "days_since_last_topup"]
        * rng.uniform(1.2, 2.4, int(zero_residual.sum())),
        0,
        180,
    ).round(0)

    # 3. Alternation between mutually exclusive products = sustained distress.
    both = (out["airtime_advance_count_90d"] > 0) & (out["data_advance_count_90d"] > 0)
    out["emergency_service_alternations_90d"] = np.where(
        both,
        rng.integers(1, 9, n),
        0,
    ).astype("int8")

    out["exceeds_modal_recharge"] = (data_debt > out["modal_recharge_amount_lyd"]).astype("int8")

    log.info(
        "overlay emergency_credit: %.1f%% took an advance, %.1f%% hit the zero-residual "
        "case, %.1f%% alternated between products, airtime rungs %s",
        100 * took_any.mean(),
        100 * zero_residual.mean(),
        100 * both.mean(),
        tuple(int(r) for r in airtime_rungs),
    )
    if zero_residual.sum() == 0:
        raise ValueError(
            "no subscriber hit the zero-residual case, so M4's central finding has "
            "no population to detect. Check the modal recharge distribution."
        )
    return out


def apply_diaspora_roaming(df: pd.DataFrame) -> pd.DataFrame:
    """A small roaming population, because Cell2Cell's `roam_Mean` is domestic.

    Kept minimal and flagged: it is a plausible Libyan feature rather than a
    measured one, so it gets one field and no weight in the hazard.
    """
    if not _overlay_conf().get("diaspora_roaming", True):
        return df

    rng = _rng(8)
    out = df.copy()
    n = len(out)
    roams = rng.random(n) < 0.06
    out["roaming_days_90d"] = np.where(roams, rng.integers(1, 45, n), 0).astype("int16")
    log.info("overlay diaspora_roaming: %.1f%% roamed", 100 * roams.mean())
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Order matters and is asserted by the overlays themselves: the morning bump
# needs the weekend share, and emergency credit needs the prepaid mechanics.
OVERLAY_ORDER = (
    apply_service_outage_exposure,
    apply_salary_week_spike,
    apply_weekend_rhythm,
    apply_prepaid_recharge_behaviour,
    apply_dual_sim_leakage,
    apply_morning_offpeak_usage,
    apply_emergency_credit_behaviour,
    apply_diaspora_roaming,
)


def apply_all(df: pd.DataFrame) -> pd.DataFrame:
    """Run every enabled overlay, in dependency order."""
    out = df
    for overlay in OVERLAY_ORDER:
        out = overlay(out)
    log.info("overlays: %d applied, frame is now %d x %d", len(OVERLAY_ORDER), *out.shape)
    return out
