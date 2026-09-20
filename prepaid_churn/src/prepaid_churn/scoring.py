"""Batch scoring and the subscriber output contract (ticket T8, decisions 10 and 12).

`score` turns an export that passes the data contract into one row per subscriber:
calibrated churn probability, risk band, the top three reasons in plain language,
model version and scoring time. Features come from the two latest contract months,
exactly like the test window B, and the model predicts the month after.

Customers already silent in the current month are not scored by the model; they get
the risk band `already_silent` (decision 12).
Nothing is estimated from the batch being scored, so one customer scored alone gets
the same answer as inside a batch of ten thousand.

Reasons are exact SHAP contributions: LightGBM computes them from its trees
(`pred_contrib`), and for the logistic regression each feature's share of the
log-odds is its coefficient times its standardised value. Only factors that raise
the risk are reported.
"""

import datetime
import os
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from prepaid_churn.bundle import Bundle, BundleError
from prepaid_churn.clean import clean
from prepaid_churn.data import LABEL_COLUMN
from prepaid_churn.evaluation import risk_band
from prepaid_churn.features import add_features
from prepaid_churn.schema import ID, summarize_failures, validate
from prepaid_churn.windows import WINDOW_B, active_in_current_month, window_features

SCORING_WINDOW = WINDOW_B  # the two latest contract months; the model predicts the next one
SILENT_BAND = "already_silent"
BANDS = ("high", "medium", "low", SILENT_BAND)
REASON_COUNT = 3
SILENT_REASON = "No calls and no mobile data this month"


@dataclass(frozen=True)
class OutputColumn:
    name: str
    kind: str
    meaning: str


OUTPUT_COLUMNS = (
    OutputColumn(
        "subscriber_id",
        "text, unique",
        "The pseudonymous subscriber ID from the export's `id` column (decision 17).",
    ),
    OutputColumn(
        "churn_probability",
        "number from 0 to 1; empty for `already_silent`",
        "Calibrated probability that the subscriber makes no calls and uses no mobile data "
        "next month. 0.3 means about 30 in 100 such subscribers go silent.",
    ),
    OutputColumn(
        "risk_band",
        "`high`, `medium`, `low` or `already_silent`",
        "`high`: at or above the best-F1 threshold chosen on validation customers. "
        "`medium`: above the validation churn rate. `low`: below it. "
        "`already_silent`: no calls and no data this month, so the model does not score "
        "the subscriber (decision 12).",
    ),
    *(
        OutputColumn(
            f"reason_{n}",
            "text; may be empty",
            f"The factor with the {rank} push towards churn for this subscriber, "
            "with its value. Empty when fewer factors raise the risk.",
        )
        for n, rank in zip((1, 2, 3), ("largest", "2nd largest", "3rd largest"), strict=True)
    ),
    OutputColumn("model_version", "text", "Version of the model bundle that scored the row."),
    OutputColumn("scored_at", "UTC time, ISO 8601", "When the row was scored."),
)
OUTPUT_COLUMN_NAMES = [column.name for column in OUTPUT_COLUMNS]
REASON_COLUMNS = [f"reason_{n}" for n in range(1, REASON_COUNT + 1)]

OUTPUT_SCHEMA = pa.DataFrameSchema(
    {
        "subscriber_id": pa.Column(str, unique=True),
        "churn_probability": pa.Column(float, pa.Check.in_range(0, 1), nullable=True),
        "risk_band": pa.Column(str, pa.Check.isin(BANDS)),
        **{name: pa.Column(str, nullable=True) for name in REASON_COLUMNS},
        "model_version": pa.Column(str),
        "scored_at": pa.Column(str),
    },
    checks=[
        pa.Check(
            lambda df: df["churn_probability"].isna() == (df["risk_band"] == SILENT_BAND),
            name="only already_silent subscribers have no probability",
        )
    ],
    strict=True,
    ordered=True,
)

# Plain-language names of the monthly base columns (see the data contract). The month
# ("this month" or "last month") goes where `{month}` is, or at the end.
BASE_LABELS = {
    "arpu": "Revenue per user (ARPU)",
    "arpu_2g": "2G data revenue",
    "arpu_3g": "3G data revenue",
    "av_rech_amt_data": "Average data pack recharge amount",
    "count_rech_2g": "2G data pack recharges",
    "count_rech_3g": "3G data pack recharges",
    "days_since_last_rech": "Days since the last recharge, at the end of {month}",
    "days_since_last_rech_data": "Days since the last data recharge, at the end of {month}",
    "fb_user": "Uses a social-network pack",
    "ic_others": "Other incoming minutes",
    "incoming_share": "Share of minutes that are incoming",
    "isd_ic_mou": "International incoming minutes",
    "isd_og_mou": "International outgoing minutes",
    "last_day_rch_amt": "Amount recharged on the last recharge day",
    "loc_ic_mou": "Local incoming minutes",
    "loc_ic_t2f_mou": "Local incoming minutes from fixed lines",
    "loc_ic_t2m_mou": "Local incoming minutes from other networks",
    "loc_ic_t2t_mou": "Local incoming minutes from the same network",
    "loc_og_mou": "Local outgoing minutes",
    "loc_og_t2c_mou": "Minutes to the call centre",
    "loc_og_t2f_mou": "Local outgoing minutes to fixed lines",
    "loc_og_t2m_mou": "Local outgoing minutes to other networks",
    "loc_og_t2t_mou": "Local outgoing minutes to the same network",
    "max_rech_amt": "Largest recharge",
    "max_rech_data": "Largest data pack recharge",
    "monthly_2g": "Monthly 2G packs bought",
    "monthly_3g": "Monthly 3G packs bought",
    "night_pck_user": "Uses a night pack",
    "no_voice_record": "No voice record",
    "offnet_mou": "Minutes with other networks",
    "og_others": "Other outgoing minutes",
    "onnet_mou": "Minutes within the same network",
    "onnet_share": "Share of minutes within the same network",
    "roam_ic_mou": "Incoming roaming minutes",
    "roam_og_mou": "Outgoing roaming minutes",
    "sachet_2g": "Short 2G packs bought",
    "sachet_3g": "Short 3G packs bought",
    "spl_ic_mou": "Special incoming minutes",
    "spl_og_mou": "Special outgoing minutes",
    "std_ic_mou": "Long-distance incoming minutes",
    "std_ic_t2f_mou": "Long-distance incoming minutes from fixed lines",
    "std_ic_t2m_mou": "Long-distance incoming minutes from other networks",
    "std_ic_t2t_mou": "Long-distance incoming minutes from the same network",
    "std_og_mou": "Long-distance outgoing minutes",
    "std_og_t2f_mou": "Long-distance outgoing minutes to fixed lines",
    "std_og_t2m_mou": "Long-distance outgoing minutes to other networks",
    "std_og_t2t_mou": "Long-distance outgoing minutes to the same network",
    "total_ic_mou": "Incoming minutes",
    "total_og_mou": "Outgoing minutes",
    "total_rech_amt": "Recharge amount",
    "total_rech_data": "Data pack recharges",
    "total_rech_num": "Number of recharges",
    "vbc_3g": "Pay-per-use 3G data cost",
    "vol_2g_mb": "2G data used (MB)",
    "vol_3g_mb": "3G data used (MB)",
}
MONTH_LABELS = {"prev": "last month", "cur": "this month"}
MEASURE_LABELS = {
    "arpu": "revenue per user (ARPU)",
    "total_og_mou": "outgoing minutes",
    "total_ic_mou": "incoming minutes",
    "total_mou": "total minutes",
    "data_mb": "mobile data used (MB)",
    "total_rech_amt": "recharge amount",
    "total_rech_num": "number of recharges",
}
# Engineered features (T4, T5) that do not follow the `<month>_<base>` pattern.
FEATURE_LABELS = {
    "tenure_days": "Days on the network",
    "days_since_last_rech_window": "Days since the last recharge",
    "days_since_last_rech_data_window": "Days since the last data recharge",
    "diff_onnet_share": "Change in the share of same-network minutes since last month",
    "diff_incoming_share": "Change in the share of incoming minutes since last month",
    **{f"diff_{m}": f"Change in {label} since last month" for m, label in MEASURE_LABELS.items()},
    **{
        f"trend_{m}": f"This month's share of the last two months' {label} (50% = stable)"
        for m, label in MEASURE_LABELS.items()
    },
}
YES_NO_BASES = ("fb_user", "night_pck_user", "no_voice_record")


def feature_label(feature: str) -> str:
    if feature in FEATURE_LABELS:
        return FEATURE_LABELS[feature]
    prefix, _, base = feature.partition("_")
    label, month = BASE_LABELS[base], MONTH_LABELS[prefix]
    return label.format(month=month) if "{month}" in label else f"{label} {month}"


def format_value(feature: str, value: float) -> str:
    if feature.partition("_")[2] in YES_NO_BASES:
        return "yes" if value >= 0.5 else "no"
    if "share" in feature or feature.startswith("trend_"):
        return f"{value:+.0%}" if feature.startswith("diff_") else f"{value:.0%}"
    if float(value).is_integer():
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def contributions(model, x: pd.DataFrame) -> np.ndarray:
    """Each feature's exact contribution to the log-odds of churn, one row per customer."""
    if isinstance(model, lgb.LGBMClassifier):
        # Training pins one thread for reproducibility; each row's SHAP values are computed
        # independently, so all cores give identical numbers about 9 times faster.
        contribution = model.predict(x, pred_contrib=True, num_threads=os.cpu_count())
        return contribution[:, :-1]  # the last column is the base value
    standardised = model[:-1].transform(x)  # signed log and scaling, centred on train customers
    return standardised * model[-1].coef_[0]


def top_reasons(x: pd.DataFrame, contribution: np.ndarray) -> list[list[str | None]]:
    """Up to REASON_COUNT factors that raise each customer's risk the most, as sentences."""
    order = np.argsort(-contribution, axis=1, kind="stable")[:, :REASON_COUNT]
    features = x.columns.to_numpy()
    values = x.to_numpy()
    reasons = []
    for row, columns in enumerate(order):
        texts = [
            f"{feature_label(features[c])}: {format_value(features[c], values[row, c])}"
            for c in columns
            if contribution[row, c] > 0
        ]
        reasons.append(texts + [None] * (REASON_COUNT - len(texts)))
    return reasons


def validate_output(scores: pd.DataFrame) -> pd.DataFrame:
    try:
        return OUTPUT_SCHEMA.validate(scores, lazy=True)
    except SchemaErrors as errors:
        raise BundleError(
            summarize_failures(errors.failure_cases, "Scores break the output contract")
        ) from None


def score(export: pd.DataFrame, bundle: Bundle, scored_at: str | None = None) -> pd.DataFrame:
    """One output-contract row per subscriber of an export that passes the data contract."""
    scored_at = scored_at or datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    cleaned = clean(validate(export.drop(columns=LABEL_COLUMN, errors="ignore"), labeled=False))
    frame = add_features(window_features(cleaned, SCORING_WINDOW))
    missing = [feature for feature in bundle.features if feature not in frame.columns]
    if missing:
        raise BundleError(f"The export lacks features the bundle needs: {missing[:5]}")
    x = frame[bundle.features]
    active = active_in_current_month(cleaned, SCORING_WINDOW).to_numpy()

    probability = np.full(len(x), np.nan)
    band = np.full(len(x), SILENT_BAND, dtype=object)
    reasons = [[SILENT_REASON] + [None] * (REASON_COUNT - 1) for _ in range(len(x))]
    if active.any():
        champion = bundle.champion
        probability[active] = champion.predict(x[active])
        band[active] = risk_band(
            probability[active], champion.high_threshold, champion.medium_threshold
        )
        for position, texts in zip(
            np.flatnonzero(active),
            top_reasons(x[active], contributions(champion.model, x[active])),
            strict=True,
        ):
            reasons[position] = texts

    # Text columns get an explicit dtype: pandas infers `object` for a column that is all
    # empty and `str` otherwise, so a one-row batch would change the output's types.
    text = {
        "subscriber_id": cleaned[ID].astype(str).to_numpy(),
        "risk_band": band,
        **{name: [row[i] for row in reasons] for i, name in enumerate(REASON_COLUMNS)},
        "model_version": [bundle.version] * len(x),
        "scored_at": [scored_at] * len(x),
    }
    scores = pd.DataFrame({name: pd.Series(values, dtype="str") for name, values in text.items()})
    scores.insert(1, "churn_probability", probability)
    return validate_output(scores)


def output_contract_markdown() -> str:
    """The subscriber output contract as Markdown, generated from OUTPUT_COLUMNS."""
    lines = [
        "# Output contract: subscriber scores",
        "",
        "Generated by `uv run churn output-contract` from `src/prepaid_churn/scoring.py`.",
        "Do not edit it by hand.",
        "",
        "`uv run churn score` and the Python function `prepaid_churn.scoring.score` write one "
        "row per subscriber of an export that passes the data contract (`docs/data_contract.md`).",
        "The file is CSV in UTF-8.",
        "Later tickets add the value tier (T10) and the recommended offer (T11) to the same rows.",
        "",
        "| Column | Type | Meaning |",
        "|---|---|---|",
        *(f"| `{c.name}` | {c.kind} | {c.meaning} |" for c in OUTPUT_COLUMNS),
        "",
        "## Rules",
        "",
        "- One row per subscriber of the export, in the export's order.",
        "- `churn_probability` is empty exactly when `risk_band` is `already_silent`.",
        "- Reasons name a factor and its value, for example "
        "`Days since the last recharge: 23`; only factors that raise the risk are listed.",
        "- The customer chatbot never shows `churn_probability` or the reasons to a customer "
        "(decision 17); they are for employees and the retention team.",
        "",
    ]
    return "\n".join(lines)
