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

WHY QINI IS WRITTEN OUT HERE rather than imported from scikit-uplift, which is
installed and used in the tests. Two reasons, and neither is distrust of the
library. First, Criteo's arms are 85/15, and every Qini formula has a term that
rescales the control arm to the treated arm's size -- getting that term wrong
produces a curve that looks fine and is wrong by the ratio, which is a factor
of about 5.7 here. Writing it out makes the rescaling visible in the code
rather than hidden in a call. Second, the tests assert this implementation
against `sklift.metrics.qini_auc_score`, and an implementation that is only a
call to the thing it is checked against cannot disagree with it.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)

# numpy renamed `trapz` to `trapezoid` in 2.0 and kept the old name as a
# deprecated alias. Bound once here so the module works either side of that.
_trapezoid = getattr(np, "trapezoid", None) or np.trapz


def _conf() -> dict:
    return load_conf("models/m3_uplift")


def qini_curve(uplift_score, outcome, treated, _perfect: bool = True) -> pd.DataFrame:
    """Points for the Qini curve, and the coefficient.

    At each depth n, ranked by predicted uplift descending:

        Qini(n) = R_t(n) - R_c(n) * N_t(n) / N_c(n)

    THE RESCALING TERM IS THE WHOLE THING. `R_c(n)` counts responses in the
    control rows within the top n, and the control arm is a different size from
    the treated arm -- 15% against 85% on Criteo. Comparing the raw counts
    would report the arm imbalance as uplift. Multiplying the control responses
    by `N_t(n) / N_c(n)` asks the right question: how many responses would the
    control group have produced if it were as large as the treated group.

    The coefficient is the area between this curve and the straight line a
    random ranking would trace, divided by the area a PERFECT ranking would
    achieve over that same line. That denominator is the standard Radcliffe
    normalisation and it is what makes the number comparable to a published
    one; the tests assert it against `sklift.metrics.qini_auc_score`.

    Normalising by the total incremental response instead -- which was the
    first version here -- produces a number with the right sign and ordering
    and the wrong magnitude, roughly 3x too large on balanced arms. It would
    have been quoted in a report beside the word "Qini" and been incomparable
    to every other Qini ever published.

    Returns the curve with `coefficient` in `.attrs`.
    """
    score = np.asarray(uplift_score, dtype="float64")
    y = np.asarray(outcome, dtype="float64")
    t = np.asarray(treated, dtype="float64")

    if not (len(score) == len(y) == len(t)):
        raise ValueError(f"lengths differ: {len(score)}, {len(y)}, {len(t)}")
    if t.sum() == 0 or (1 - t).sum() == 0:
        raise ValueError("one arm is empty; no treatment effect is identifiable")

    order = np.argsort(-score, kind="stable")
    y, t = y[order], t[order]

    treated_cumulative = np.cumsum(t)
    control_cumulative = np.cumsum(1 - t)
    responses_treated = np.cumsum(y * t)
    responses_control = np.cumsum(y * (1 - t))

    # Where no control row has appeared yet the rescaling is undefined, so the
    # curve contributes nothing rather than dividing by zero.
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(control_cumulative > 0, treated_cumulative / control_cumulative, 0.0)
    qini = responses_treated - responses_control * ratio

    n = np.arange(1, len(y) + 1)
    curve = pd.DataFrame({"n": n, "fraction": n / len(y), "qini": qini})

    # The random line runs from the origin to the endpoint: a ranking with no
    # information still accumulates the population's overall incremental
    # response, linearly.
    endpoint = float(qini[-1])
    random_line = curve["fraction"].to_numpy() * endpoint
    curve["random"] = random_line

    area_model = float(_trapezoid(qini, curve["fraction"]))
    area_random = float(_trapezoid(random_line, curve["fraction"]))

    # The perfect ranking: +1 for a treated responder, -1 for a control
    # responder, 0 otherwise. Sorting by that puts every row the treatment
    # could possibly have helped at the front, which is the best any model
    # could do on this exact data -- so it is the right denominator.
    if _perfect:
        perfect_score = y * t - y * (1 - t)
        perfect = qini_curve(perfect_score, y, t, _perfect=False)
        area_perfect = perfect.attrs["area_model"] - perfect.attrs["area_random"]
    else:
        area_perfect = 0.0

    coefficient = (area_model - area_random) / area_perfect if area_perfect else 0.0

    curve.attrs["coefficient"] = float(coefficient)
    curve.attrs["endpoint"] = endpoint
    curve.attrs["area_model"] = area_model
    curve.attrs["area_random"] = area_random
    curve.attrs["area_perfect"] = float(area_perfect)

    if _perfect:  # the recursive call has no coefficient of its own to report
        log.info(
            "qini: coefficient %.4f over %d rows (total incremental response %.1f, "
            "treated share %.1f%%)",
            coefficient,
            len(y),
            endpoint,
            100 * t.mean(),
        )
    return curve


def qini_coefficient(uplift_score, outcome, treated) -> float:
    """Just the number."""
    return float(qini_curve(uplift_score, outcome, treated).attrs["coefficient"])


def uplift_at_k(uplift_score, outcome, treated, k: float | None = None) -> float:
    """Realised uplift in the top k fraction by predicted uplift.

    This is the number the Campaign Builder actually needs: if we treat the top
    30%, what incremental retention do we get?

    A DIFFERENCE OF RATES, not of counts. Within the top k, the treated
    response rate minus the control response rate -- which is already
    size-invariant, so it needs no rescaling term and is directly readable as
    percentage points. Reporting it as a difference in counts would make it
    depend on the arm split, and a campaign manager would compare two numbers
    that are not comparable.
    """
    k = _conf()["validation"]["uplift_at_k_default"] if k is None else k
    if not 0 < k <= 1:
        raise ValueError(f"k must be a fraction in (0, 1], got {k}")

    score = np.asarray(uplift_score, dtype="float64")
    y = np.asarray(outcome, dtype="float64")
    t = np.asarray(treated, dtype="float64")

    cut = max(1, round(len(score) * k))
    top = np.argsort(-score, kind="stable")[:cut]
    y_top, t_top = y[top], t[top]

    n_treated, n_control = t_top.sum(), (1 - t_top).sum()
    if n_treated == 0 or n_control == 0:
        raise ValueError(
            f"the top {k:.0%} contains only one arm ({int(n_treated)} treated, "
            f"{int(n_control)} control), so no uplift can be measured there"
        )

    realised = float(y_top[t_top == 1].mean() - y_top[t_top == 0].mean())
    overall = float(y[t == 1].mean() - y[t == 0].mean())

    log.info(
        "uplift@%.0f%%: %+.4f pp against %+.4f pp overall -- %.2fx concentration",
        100 * k,
        100 * realised,
        100 * overall,
        realised / overall if overall else float("nan"),
    )
    return realised


def quadrant_counts(uplift, baseline_response) -> dict[str, int]:
    """How much of the base is persuadable, sure thing, lost cause, sleeping dog.

    Worth putting on a slide. In most retention programmes the persuadable
    share is far smaller than people expect, and that is the argument for
    targeting in one number.
    """
    from cvm.models.m3_uplift.two_model import QUADRANTS, classify_quadrant

    quadrant = classify_quadrant(uplift, baseline_response)
    counts = quadrant.value_counts().to_dict()
    return {name: int(counts.get(name, 0)) for name in QUADRANTS}


def expected_value_of_treatment(uplift, clv, cost):
    """Expected LYD gain from treating each subscriber.

        E[gain] = uplift x CLV - cost

    The bridge from M3 into the decision engine: a positive value means
    intervening is worthwhile before guardrails, a negative one means it is not
    regardless of how high the churn score is.

    BREAK-EVEN IS A DIVISION, and it is the number the whole business case
    rests on. At a 5 LYD blended incentive against a 480 LYD annual value, the
    uplift has to clear 5/480 = 1.0417 percentage points before treating anyone
    pays for itself. That is not a comfortable margin: it is above the effect
    size a lot of published retention campaigns report, which is precisely why
    the uplift model has to be good rather than merely present.
    """
    uplift = np.asarray(uplift, dtype="float64")
    clv = np.asarray(clv, dtype="float64")
    cost = np.asarray(cost, dtype="float64")
    value = uplift * clv - cost
    return float(value) if value.ndim == 0 else value


def break_even_uplift(clv: float, cost: float) -> float:
    """The uplift at which treating exactly pays for itself: cost / CLV."""
    if clv <= 0:
        raise ValueError(f"CLV must be positive, got {clv}")
    return cost / clv


def validate_on_criteo(sample_10pct: bool = True, test_fraction: float = 0.3) -> dict[str, float]:
    """Train and score the method on Criteo's real randomised arms.

    This is what separates "our uplift model scores well on data we made up"
    from "our uplift method is validated on real randomised data, then applied
    to a generated population". Run it before the method is trusted anywhere
    else, and quote the result in the report.

    Split before fitting, and score on the held-out part. Scoring on the
    training rows measures memorisation, and a two-model difference memorises
    readily -- both models are free to overfit their own arm, and the
    difference of two overfits looks like a strong signal.
    """
    from sklearn.model_selection import train_test_split

    from cvm.config import settings
    from cvm.ingest.criteo_uplift import assert_randomised, load
    from cvm.models.m3_uplift.two_model import (
        baseline_response,
        predict_uplift,
        train_two_model,
    )

    X, y, t = load(sample_10pct=sample_10pct)
    randomisation = assert_randomised(t, y)

    X_train, X_test, y_train, y_test, t_train, t_test = train_test_split(
        X, y, t, test_size=test_fraction, random_state=settings.random_seed, stratify=t
    )

    treated_model, control_model = train_two_model(X_train, y_train, t_train)
    uplift = predict_uplift(treated_model, control_model, X_test)
    baseline = baseline_response(control_model, X_test)

    curve = qini_curve(uplift, y_test, t_test)
    at_k = uplift_at_k(uplift, y_test, t_test)
    quadrants = quadrant_counts(uplift, baseline)

    metrics = {
        "rows_total": len(X),
        "rows_scored": len(X_test),
        "treated_share": float(t_test.mean()),
        "naive_lift_pp": float(randomisation["naive_lift_pp"]),
        "qini": float(curve.attrs["coefficient"]),
        "uplift_at_k": at_k,
        "uplift_at_k_pp": 100 * at_k,
        "k": _conf()["validation"]["uplift_at_k_default"],
        **{f"quadrant_{name}": count for name, count in quadrants.items()},
    }
    log.info(
        "criteo validation: Qini %.4f, uplift@%.0f%% %+.4f pp on %d held-out rows",
        metrics["qini"],
        100 * metrics["k"],
        metrics["uplift_at_k_pp"],
        metrics["rows_scored"],
    )
    return metrics
