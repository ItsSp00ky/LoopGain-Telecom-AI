"""Prepaid-adapted RFM-LE.  Owner: E1 / E3

Textbook RFM assumes purchase transactions. Prepaid has none, so each dimension
is redefined and two are added:

    R  Days since last REVENUE-GENERATING event (top-up or bundle purchase).
       Usage alone does not count -- a subscriber burning residual credit
       generates no revenue.
    F  Recharge count in 90d, PENALISED by recharge_gap_cv. Five regular
       recharges beat five erratic ones.
    M  Total LYD in 90d, PLUS the 30d-vs-prior-60d slope, so decline is
       visible inside the score itself.
    L  (added) 0.4*tenure + 0.3*consecutive_active_months + 0.3*lifetime_pct
    E  (added) Service breadth, normalised.

Quintile scoring 1-5 per dimension gives an R|F|M|L|E cell, collapsed into the
eight business segments in conf/features.yaml.

EVERY REDEFINITION EARNS ITS PLACE. Textbook RFM applied unchanged to prepaid
gives three dimensions that mostly measure the same thing -- how recently and
how much someone topped up -- and misses the two that decide a retention offer:
whether they have been here long enough to be worth keeping, and whether they
use enough of the product to have anything to lose. L and E are the difference
between "high value" and "high value AND retainable".
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)

DIMENSIONS = ("recency", "frequency", "monetary", "loyalty", "engagement")

SERVICE_COLUMNS = {
    "voice": "voice_minutes_30d",
    "sms": "sms_count_30d",
    "data": "data_mb_30d",
    "bundles": "bundle_purchases_90d",
    "transfers": "credit_transfers_90d",
    "advances": "airtime_advance_count_90d",
}


def _conf() -> dict:
    return load_conf("features")["rfm_le"]


def _scaled(series: pd.Series) -> pd.Series:
    """Percentile rank in [0, 1]. Robust to the heavy tails throughout here."""
    return pd.to_numeric(series, errors="coerce").rank(pct=True).fillna(0.0)


def recency(df: pd.DataFrame) -> pd.Series:
    """Days since the last revenue-generating event. Not since last usage.

    The distinction is the whole point and it has no postpaid equivalent: a
    subscriber burning through residual credit looks active on every usage
    metric and has generated no revenue for three weeks. Usage-based recency
    would score them healthy.
    """
    if "days_since_last_topup" not in df.columns:
        raise KeyError(
            "days_since_last_topup is absent. Recency must be measured from a "
            "REVENUE event; there is no usage-based fallback, because that is "
            "precisely the mistake this definition exists to avoid."
        )
    return df["days_since_last_topup"].astype("float64")


def frequency(df: pd.DataFrame) -> pd.Series:
    """Recharge count over 90d, penalised by the coefficient of variation of gaps.

    Five regular recharges beat five erratic ones, so the raw count is divided
    down by irregularity. A subscriber recharging every nine days like
    clockwork is predictable revenue; one recharging five times at random is
    already wobbling, and the count alone cannot tell them apart.
    """
    if "recharge_count_90d" not in df.columns:
        raise KeyError("recharge_count_90d is absent")
    count = df["recharge_count_90d"].astype("float64")
    if "recharge_gap_cv" not in df.columns:
        log.warning("recharge_gap_cv absent: frequency is unpenalised and F means less")
        return count
    # CV of 0 is perfectly regular, so the penalty is 1.0 and the count stands.
    return count / (1.0 + df["recharge_gap_cv"].clip(lower=0).astype("float64"))


def monetary(df: pd.DataFrame) -> pd.Series:
    """90d LYD total plus the 30d-vs-prior-60d slope.

    The slope is inside the score rather than beside it, so a declining
    high-spender does not sit in the same M quintile as a stable one. Without
    it, M is a lagging indicator and the segment reads "Champion" right up to
    the month they leave.
    """
    if "modal_recharge_amount_lyd" not in df.columns or "recharge_count_90d" not in df.columns:
        raise KeyError("monetary needs modal_recharge_amount_lyd and recharge_count_90d")

    total = df["modal_recharge_amount_lyd"].astype("float64") * df["recharge_count_90d"]

    # The slope, where the generator supplies one. revenue_decay_ratio is
    # exactly mean-recent over mean-longer, so it is the slope already.
    if "revenue_decay_ratio" in df.columns:
        trend = df["revenue_decay_ratio"].fillna(1.0).clip(0.2, 2.0)
        return total * trend
    log.warning("revenue_decay_ratio absent: M is a level with no trend and lags decline")
    return total


def loyalty(df: pd.DataFrame) -> pd.Series:
    """Tenure, continuity and lifetime spend, weighted per config.

    Added because tenure changes what a retention offer should be. Two
    subscribers with identical R, F and M are different propositions if one
    joined last month and the other has been here four years -- the second has
    a habit worth protecting and the first has not formed one.
    """
    weights = _conf()["dimensions"]["loyalty"]["weights"]
    parts, used = [], {}

    for key, column in (
        ("tenure", "tenure_months"),
        ("consecutive_active_months", "tenure_months"),
        ("lifetime_recharge_percentile", "modal_recharge_amount_lyd"),
    ):
        if column in df.columns:
            parts.append(weights[key] * _scaled(df[column]))
            used[key] = column

    if not parts:
        raise KeyError(f"loyalty needs at least one of {sorted(weights)}; none are present")

    log.info("loyalty: built from %s", used)
    return sum(parts) / sum(weights[k] for k in used)


def engagement(df: pd.DataFrame) -> pd.Series:
    """Service breadth, normalised over the six service types.

    A subscriber using voice, data and bundles has three things to lose; one
    using voice only has one. Breadth is what makes an offer relevant -- there
    is no point offering a data bundle to someone who has never bought data.
    """
    declared = _conf()["dimensions"]["engagement"]["service_types"]
    present = {s: SERVICE_COLUMNS[s] for s in declared if SERVICE_COLUMNS.get(s) in df.columns}

    if not present:
        raise KeyError(
            f"engagement needs at least one of {[SERVICE_COLUMNS[s] for s in declared]}; "
            "none are present"
        )

    used = pd.DataFrame(
        {service: (df[column].fillna(0) > 0).astype(int) for service, column in present.items()}
    )
    # Normalised by the services we can OBSERVE, not by the six declared, so a
    # missing column does not silently depress everyone's E score.
    breadth = used.sum(axis=1) / len(present)

    log.info(
        "engagement: %d of %d service types observable (%s), mean breadth %.3f",
        len(present),
        len(declared),
        sorted(present),
        breadth.mean(),
    )
    return breadth.astype("float64")


def score_quintiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add R/F/M/L/E quintiles (1-5) and the concatenated cell string.

    RECENCY IS INVERTED and the others are not. Fewer days since the last
    top-up is better, so R=5 means recent; more recharges, more spend, longer
    tenure and broader use are all better as they rise. Getting this backwards
    silently inverts every segment, and the segments would still look
    plausible, which is why it is stated here rather than left to the reader.
    """
    n = _conf()["quintiles"]
    raw = pd.DataFrame(
        {
            "recency": recency(df),
            "frequency": frequency(df),
            "monetary": monetary(df),
            "loyalty": loyalty(df),
            "engagement": engagement(df),
        },
        index=df.index,
    )

    midpoint = (n + 1) // 2
    out = pd.DataFrame(index=df.index)
    unknown: dict[str, int] = {}

    for dimension in DIMENSIONS:
        ranked = raw[dimension].rank(pct=True, method="average", na_option="keep")
        if dimension == "recency":
            ranked = 1 - ranked  # fewer days is better

        # `clip` rather than qcut: qcut raises on ties, and recharge counts and
        # service breadth are both heavily tied by construction.
        quintile = np.ceil(ranked * n).clip(1, n)

        # A MISSING VALUE GETS THE MIDDLE QUINTILE, not the worst one. The
        # population carries 3% injected missingness by design, and ranking
        # leaves those rows NaN. Dropping them would quietly shrink every
        # cohort; putting them at 1 would assert that an unknown recency is a
        # bad recency, which is a claim the data does not support. The middle
        # says what is true -- we do not know -- and the count is logged so it
        # cannot grow unnoticed.
        missing = int(quintile.isna().sum())
        if missing:
            unknown[dimension] = missing
            quintile = quintile.fillna(midpoint)

        out[f"{dimension}_raw"] = raw[dimension]
        out[dimension[0].upper()] = quintile.astype("int8")

    if unknown:
        log.info(
            "rfm_le: %s assigned the middle quintile (%d) for a missing input",
            {k: f"{v / len(df):.1%}" for k, v in unknown.items()},
            midpoint,
        )

    out["rfmle_cell"] = (
        out[["R", "F", "M", "L", "E"]].astype(str).agg("".join, axis=1).astype("string")
    )
    log.info(
        "rfm_le: %d distinct cells of a possible %d, mean scores %s",
        out["rfmle_cell"].nunique(),
        n**5,
        {d[0].upper(): round(float(out[d[0].upper()].mean()), 2) for d in DIMENSIONS},
    )
    return out


def assign_segments(df: pd.DataFrame) -> pd.Series:
    """Collapse R|F|M|L|E cells into the eight business segments.

    Where these rules and the M2 K-Means clusters disagree, the disagreement is
    itself a dashboard insight -- surface it rather than reconciling it away.

    Ordered most-specific first, because the rules overlap by design: a
    Champion also satisfies Loyal High-Value, and the first match wins. Written
    as explicit predicates rather than a lookup table so each one can be read
    as the sentence it implements and argued with.

    `At-Risk Valuable` is the one the whole decision engine is aimed at: high
    monetary and loyalty, poor recency. Worth money, and going.
    """
    declared = _conf()["segments"]
    # E is deliberately absent from the rules below. Engagement says how much a
    # subscriber has to lose, which decides WHICH OFFER is relevant -- M3's
    # question, not this one. The segments answer who is worth keeping and who
    # is leaving, and adding breadth to that would blur two decisions together.
    # It is still in the cell string and still a feature in its own right.
    r, f, m, ll, _e = (df[c] for c in ("R", "F", "M", "L", "E"))

    rules: list[tuple[str, pd.Series]] = [
        ("Champions", (r >= 4) & (f >= 4) & (m >= 4) & (ll >= 3)),
        ("Loyal High-Value", (m >= 4) & (ll >= 4) & (r >= 3)),
        ("At-Risk Valuable", (m >= 4) & (ll >= 3) & (r <= 2)),
        ("Needs Attention", (r <= 2) & (f >= 3) & (m >= 3)),
        ("Potential Loyalists", (r >= 4) & (f >= 3) & (ll <= 3)),
        ("Promising New", (r >= 3) & (ll <= 2)),
        # Lost BEFORE Hibernating. Every Lost subscriber also satisfies
        # Hibernating, so the looser rule first would swallow the tighter one
        # and the Lost segment would silently never fire -- which is exactly
        # what happened on the first run.
        ("Lost", (r == 1) & (f == 1) & (m <= 2)),
        ("Hibernating", (r <= 2) & (f <= 2)),
    ]
    unknown = [name for name, _ in rules if name not in declared]
    if unknown:
        raise ValueError(f"{unknown} are not in conf/features.yaml#rfm_le.segments")

    segment = pd.Series("Hibernating", index=df.index, dtype="object")
    assigned = pd.Series(False, index=df.index)
    for name, predicate in rules:
        match = predicate & ~assigned
        segment[match] = name
        assigned |= predicate

    counts = segment.value_counts()
    log.info(
        "segments: %s",
        {k: f"{v / len(segment):.1%}" for k, v in counts.items()},
    )
    if len(counts) < 4:
        log.warning(
            "only %d segments populated -- the rules may not fit this population", len(counts)
        )
    return segment.astype("string")


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Quintiles, the cell string and the segment, in one frame."""
    out = score_quintiles(df)
    out["segment"] = assign_segments(out)
    return out
