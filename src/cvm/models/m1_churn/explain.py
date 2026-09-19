"""SHAP explainability.  Owner: E2

Per-subscriber waterfall plots surfaced in the Subscriber 360 screen, rendered
in PLAIN LANGUAGE -- "has not topped up in 23 days", not "days_since_last_topup
= 23, shap = +0.14". Every offer carries a human-readable reason; an opaque
personalised price is exactly what section 6.5 commits us not to ship.

EVERY SERVABLE MODEL HERE IS EXACTLY EXPLAINABLE, which is part of why the
module's scope is tabular. Trees get exact TreeSHAP; a linear pipeline gets
exact linear attribution, which for a linear model IS the SHAP value. Neither
is an approximation and neither needs a sampled background.

That covers both families because the benchmark is genuinely allowed to be won
by either -- on the current synthetic population it is won by logistic
regression, and a serving path that could only explain the tree arms would have
dropped explanations silently on the day that happened.

SHAP contribution shares are also how we attribute churn risk to causes --
network quality, pricing, declining engagement -- which is what makes the
Subscriber 360 explanation more than a number.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Which family each feature belongs to, by prefix or exact name. Aggregating
# eighty contributions to five families is what makes the explanation legible;
# a marketing analyst cannot act on eighty numbers and can act on "most of this
# subscriber's risk is network quality".
FAMILY_PATTERNS: dict[str, tuple[str, ...]] = {
    "velocity": (
        "usage_decay_ratio",
        "revenue_decay_ratio",
        "decay_divergence",
        "recharge_gap_cv",
        "recharge_irregularity",
        "inter_recharge_gap",
        "days_since_last_topup",
        "overdue_ratio",
    ),
    "distress": (
        "balance_zero",
        "failed_bundle_attempts",
        "consecutive_sub_5_lyd",
        "chronic_distress",
        "at_recharge_floor",
        "data_advance_leaves_nothing",
        "advance_count",
        "unpaid_advance_days",
        "days_to_settle",
        "alternates_between_products",
        "emergency_service_alternations",
    ),
    "leakage": (
        "incoming_outgoing_ratio",
        "onnet_ratio",
        "offnet_share",
        "calling_graph_contraction",
        "leakage_score",
        "is_receiving_sim",
    ),
    "network_quality": ("dropped_call_rate", "data_session_failure", "service_outage"),
    "value": (
        "recency_raw",
        "recharge_count_90d",
        "frequency_raw",
        "monetary_raw",
        "modal_recharge_amount",
        "tenure_months",
        "segment",
        "R",
        "F",
        "M",
        "L",
        "E",
    ),
    "calendar": (
        "is_salary_week",
        "weekend_usage_share",
        "is_weekend_heavy",
        "morning_pass_propensity",
        "offpeak_data_ratio",
    ),
}

# How to say each feature in a sentence. `{v}` is the value, already rounded.
# Anything absent falls back to a readable version of the column name, so a new
# feature degrades to "recharge count 90d is 4" rather than to a KeyError.
PHRASING: dict[str, str] = {
    "days_since_last_topup": "has not topped up in {v:.0f} days",
    "usage_decay_ratio": "usage is at {v:.0%} of its recent average",
    "revenue_decay_ratio": "spend is at {v:.0%} of its recent average",
    "decay_divergence": "usage and spend are diverging by {v:+.2f}",
    "recharge_gap_cv": "recharges are irregular (variation {v:.2f})",
    "overdue_ratio": "is {v:.1f}x past their usual recharge interval",
    "balance_zero_hours_30d": "spent {v:.0f} hours at zero balance last month",
    "balance_zero_share_30d": "spent {v:.0%} of the month unable to transact",
    "failed_bundle_attempts_30d": "had {v:.0f} bundle purchases rejected",
    "consecutive_sub_5_lyd_recharges": "made {v:.0f} recharges in a row at the floor",
    "chronic_distress": "shows sustained financial distress",
    "at_recharge_floor": "tops up at the smallest card",
    "incoming_outgoing_ratio": "receives {v:.1f}x more calls than they place",
    "is_receiving_sim": "looks like a receiving-only SIM",
    "leakage_score": "shows a {v:.0%} share-of-wallet leakage signal",
    "onnet_ratio": "makes {v:.0%} of calls on-net",
    "calling_graph_contraction": "is calling a narrowing set of numbers",
    "dropped_call_rate_30d": "had a {v:.1%} dropped-call rate",
    "data_session_failure_rate": "had a {v:.1%} data session failure rate",
    "service_outage_hours_30d": "experienced {v:.0f} hours of outage",
    "tenure_months": "has been a subscriber for {v:.0f} months",
    "modal_recharge_amount_lyd": "usually tops up {v:.0f} LYD",
    "recharge_count_90d": "recharged {v:.0f} times in 90 days",
    "offpeak_data_ratio": "uses {v:.0%} of their data off-peak",
    "is_salary_week": "is in the salary week",
    # The RFM-LE quintiles. Without these the fallback renders "E is 2", which
    # is not a sentence a marketing analyst can act on -- it is the column name
    # with a number after it.
    "R": "scores {v:.0f} of 5 on recency",
    "F": "scores {v:.0f} of 5 on recharge regularity",
    "M": "scores {v:.0f} of 5 on spend",
    "L": "scores {v:.0f} of 5 on loyalty",
    "E": "uses {v:.0f} of 5 on service breadth",
    # `recency_raw` IS `days_since_last_topup`, so the fallback produced the
    # same fact twice in one waterfall, phrased two different ways.
    "recency_raw": "has not topped up in {v:.0f} days",
    "frequency_raw": "recharges {v:.1f} times per 90 days, adjusted for regularity",
    "monetary_raw": "has spent about {v:,.0f} LYD over 90 days",
    "loyalty_raw": "sits in the {v:.0%} percentile for tenure and lifetime spend",
    "engagement_raw": "uses {v:.0%} of the services available to them",
    # The remainder, so nothing reaches a Subscriber 360 screen on the generic
    # fallback. The fallback stays because a NEW feature must degrade to a
    # sentence rather than a KeyError -- but a shipped feature should not rely
    # on it, and an audit over the matrix is what keeps that honest.
    "airtime_advance_count_90d": "took {v:.0f} airtime advances in 90 days",
    "data_advance_count_90d": "took {v:.0f} data advances in 90 days",
    "unpaid_advance_days": "has carried advance debt for {v:.0f} days",
    "days_to_settle": "takes about {v:.0f} days to repay an advance",
    "emergency_service_alternations_90d": (
        "switched between the two emergency products {v:.0f} times"
    ),
    "alternates_between_products": "alternates between the two emergency credit products",
    "inter_recharge_gap_mean": "recharges about every {v:.0f} days",
    "inter_recharge_gap_std": "recharge timing varies by about {v:.0f} days",
    "recharge_irregularity": "recharge timing swings {v:.1f}x their own cadence",
    "weekend_usage_share_30d": "does {v:.0%} of their usage at the weekend",
    "is_weekend_heavy": "uses the service mostly at weekends",
    "morning_pass_propensity": "has a {v:.0%} propensity for the morning pass",
}


def family_of(feature: str) -> str:
    """Which family a column belongs to. Unmatched columns go to `other`."""
    for family, patterns in FAMILY_PATTERNS.items():
        for pattern in patterns:
            if feature == pattern or feature.startswith(pattern):
                return family
    return "other"


class LinearExplainer:
    """Exact per-feature attribution for a linear model in a sklearn pipeline.

    For a linear model the SHAP value of a feature IS `coef_j * (x_j - E[x_j])`
    -- no sampling, no approximation, no background dataset to argue about.
    Computing it directly is both exact and faster than asking shap to
    rediscover it.

    This exists because the benchmark is allowed to be won by logistic
    regression, and section 6.5 commits to an explanation for every score. A
    serving path that can only explain the model we expected to win is a
    serving path that silently drops explanations the day the benchmark
    changes its mind -- which is exactly what happened on the first run.
    """

    def __init__(self, pipeline, X: pd.DataFrame):
        self.pipeline = pipeline
        self.steps = pipeline[:-1]
        self.model = pipeline[-1]
        if not hasattr(self.model, "coef_"):
            raise TypeError(f"{type(self.model).__name__} has no coef_; it is not linear")
        self.coef = np.asarray(self.model.coef_).ravel()

        # A ONE-ROW BACKGROUND IS NOT A BACKGROUND. The attribution is
        # `coef_j * (x_j - E[x_j])`, so if E[x] is computed from the single row
        # being explained, every term is `coef_j * 0` and the whole explanation
        # is exactly zero -- silently, with the right shape and the right
        # dtype. Both callers did this: the API explained a one-subscriber
        # batch against itself, and Subscriber 360 drew a SHAP waterfall whose
        # every bar was 0.0 while the plain-language text read "lowers churn
        # risk" for a subscriber scored at 1.0000.
        #
        # Raising is deliberate. The serving path catches it and returns no
        # drivers, and no explanation is strictly better than a confident
        # wrong one: an empty panel gets reported, five zero bars get believed.
        if len(X) < 2:
            raise ValueError(
                f"background has {len(X)} row(s); a linear SHAP background must describe a "
                "population, not the row being explained. Pass the training background "
                "carried on the model bundle."
            )
        self.background = np.asarray(self.steps.transform(X)).mean(axis=0)

    def shap_values(self, X) -> np.ndarray:
        transformed = np.asarray(self.steps.transform(X))
        return (transformed - self.background) * self.coef


def explainer_for(model, X: pd.DataFrame, background: pd.DataFrame | None = None):
    """The right explainer for whatever model won. Trees get exact TreeSHAP,
    linear pipelines get exact linear attribution, and anything else says so
    rather than returning a plausible approximation nobody asked for.

    `background` is the reference population an attribution is measured
    AGAINST -- "compared to a typical subscriber, this one tops up less". It
    belongs to training and is carried on the model bundle. It defaults to `X`
    only for the batch case at training time, where X is the test matrix and
    the distinction does not bite; every serving caller must pass it, because
    a serving batch can be one row and a one-row background yields exactly
    zero for every feature.
    """
    from cvm.models.m1_churn.calibration import CalibratedModel

    base = model.model if isinstance(model, CalibratedModel) else model
    reference = X if background is None else background

    if hasattr(base, "named_steps"):
        final = base[-1]
        if hasattr(final, "coef_"):
            log.info("shap: exact linear attribution over %s", type(final).__name__)
            return LinearExplainer(base, reference)
        raise TypeError(
            f"{type(final).__name__} is neither a tree nor linear. KNN, SVM and Naive "
            "Bayes are in the benchmark for comparison, not for serving: nothing "
            "explains them to a subscriber, and an unexplainable score cannot carry an "
            "offer. If one of them wins, that is a finding to report, not a model to ship."
        )
    return tree_explainer(base, reference)


def tree_explainer(model, X: pd.DataFrame):
    """Exact SHAP for a tree model.

    Unwraps a CalibratedModel first: the isotonic map is monotone, so it does
    not change which features drive a score or in what order -- only the scale
    of the output. Explaining the underlying tree is therefore correct, and it
    is also the only option, because an isotonic map has no tree structure to
    explain.
    """
    import shap

    from cvm.models.m1_churn.calibration import CalibratedModel

    base = model.model if isinstance(model, CalibratedModel) else model
    if hasattr(base, "named_steps"):
        raise TypeError(
            "this is a pipeline, not a tree model. SHAP here is exact only for the "
            "tree arms; the classical baselines are in the benchmark for comparison, "
            "not for serving, and nothing explains them to a subscriber."
        )

    explainer = shap.TreeExplainer(base)
    log.info("shap: TreeExplainer over %s on %d x %d", type(base).__name__, *X.shape)
    return explainer


def _positive_class(values) -> np.ndarray:
    """Normalise SHAP's three output shapes to one (n, k) array.

    It returns (n, k) for a single-output model, (n, k, 2) for some binary
    classifiers, and a LIST of two (n, k) arrays for others -- LightGBM changed
    to the list form, which is why this is a function and not an index. Getting
    it wrong does not raise where it matters; it silently explains the NEGATIVE
    class, and every contribution comes out with the wrong sign.
    """
    if isinstance(values, list):
        return np.asarray(values[1] if len(values) == 2 else values[0])
    values = np.asarray(values)
    return values[:, :, 1] if values.ndim == 3 else values


def top_drivers(explainer, row: pd.Series, k: int = 5) -> list[dict]:
    """The k features contributing most to one subscriber's score.

    Ranked by ABSOLUTE contribution and returned with sign, so a driver that
    pushes risk DOWN can still be in the list. A waterfall that shows only the
    reasons someone is at risk is a waterfall that cannot explain why a
    high-risk-looking subscriber was not contacted.
    """
    frame = row.to_frame().T if isinstance(row, pd.Series) else row
    values = _positive_class(explainer.shap_values(frame))[0]

    order = np.argsort(-np.abs(values))[:k]
    return [
        {
            "feature": str(frame.columns[i]),
            "value": float(frame.iloc[0, i]),
            "contribution": float(values[i]),
            "direction": "increases risk" if values[i] > 0 else "reduces risk",
            "family": family_of(str(frame.columns[i])),
            "explanation": to_plain_language(
                str(frame.columns[i]), float(frame.iloc[0, i]), float(values[i])
            ),
        }
        for i in order
    ]


def drivers_for_batch(explainer, X: pd.DataFrame, k: int = 5) -> list[list[dict]]:
    """`top_drivers` for every row, with SHAP computed ONCE.

    The serving path needs drivers for a whole batch, and calling the per-row
    function in a loop recomputes the explanation from scratch each time. The
    explainer is stateless across rows, so one call over the matrix gives
    identical numbers -- measured 20x faster on a 500-subscriber batch.
    """
    values = _positive_class(explainer.shap_values(X))
    columns = list(X.columns)

    out: list[list[dict]] = []
    for position in range(len(X)):
        row = values[position]
        order = np.argsort(-np.abs(row))[:k]
        out.append(
            [
                {
                    "feature": columns[i],
                    "value": float(X.iloc[position, i]),
                    "contribution": float(row[i]),
                    "direction": "increases risk" if row[i] > 0 else "reduces risk",
                    "family": family_of(columns[i]),
                    "explanation": to_plain_language(
                        columns[i], float(X.iloc[position, i]), float(row[i])
                    ),
                }
                for i in order
            ]
        )
    return out


def to_plain_language(feature: str, value: float, contribution: float) -> str:
    """Render one SHAP contribution as a sentence a marketing analyst can read.

    The feature name and the SHAP number are both dropped from the output. A
    sentence containing `days_since_last_topup = 23, shap = +0.14` has not been
    translated, it has been annotated, and the person reading the Subscriber
    360 screen still cannot act on it.
    """
    if pd.isna(value):
        clause = f"has no recorded {feature.replace('_', ' ')}"
    else:
        template = PHRASING.get(feature)
        if template is not None:
            clause = template.format(v=value)
        else:
            # Readable fallback. A new feature should degrade to a plain
            # sentence, never to a KeyError on the serving path.
            readable = feature.replace("_", " ").replace(" 30d", " last month")
            readable = readable.replace(" 90d", " over 90 days").replace(" lyd", " LYD")
            clause = f"{readable} is {value:,.2f}".replace(".00", "")

    direction = "raises" if contribution > 0 else "lowers"
    return f"{clause} — {direction} churn risk"


def attribution_by_family(explainer, X: pd.DataFrame) -> pd.DataFrame:
    """Share of churn risk attributable to each feature family, per subscriber.

    Families are defined in conf/features.yaml: velocity/decay, distress,
    leakage, network quality, credit. Aggregating SHAP to the family level is
    what makes the explanation legible to a marketing analyst -- eighty
    individual contributions are not.

    Shares are over ABSOLUTE contributions and sum to 1.0 per subscriber. The
    signed sum would let a family that pushes risk strongly in both directions
    across its features cancel itself to zero and look irrelevant, when it is
    in fact the thing the model is paying most attention to.
    """
    values = _positive_class(explainer.shap_values(X))
    magnitude = pd.DataFrame(np.abs(values), columns=X.columns, index=X.index)

    families = {}
    for family in sorted({family_of(c) for c in X.columns}):
        members = [c for c in X.columns if family_of(c) == family]
        families[family] = magnitude[members].sum(axis=1)

    out = pd.DataFrame(families, index=X.index)
    total = out.sum(axis=1).replace(0.0, np.nan)
    out = out.div(total, axis=0).fillna(0.0)

    out["dominant_family"] = out.idxmax(axis=1)
    log.info(
        "attribution: population mean share %s",
        {c: f"{out[c].mean():.1%}" for c in out.columns if c != "dominant_family"},
    )
    return out
