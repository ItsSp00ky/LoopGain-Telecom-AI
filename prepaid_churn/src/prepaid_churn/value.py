"""Frozen prepaid value tiers and a 12-month revenue scenario (ticket T10).

The five dimensions adapt Ali's prepaid RFM design to the fields we actually
observe. All cutoffs come from training customers in window A, never from the
batch being scored. The churn model and its features stay unchanged.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from prepaid_churn.bundle import Bundle
from prepaid_churn.clean import clean
from prepaid_churn.data import LABEL_COLUMN
from prepaid_churn.evaluation import recharge_amount
from prepaid_churn.features import add_features
from prepaid_churn.operator_market import lyd_rate
from prepaid_churn.schema import ID, validate
from prepaid_churn.scoring import SCORING_WINDOW, SILENT_BAND, OutputColumn, score
from prepaid_churn.windows import active_in_current_month, window_features

DIMENSIONS = ("recency", "frequency", "monetary", "tenure", "engagement")
SCORE_COLUMNS = [f"{name}_score" for name in DIMENSIONS]
TIERS = ("very_low", "low", "medium", "high", "very_high")
QUANTILES = (0.2, 0.4, 0.6, 0.8)
SERVICES = {
    "voice": ("total_ic_mou", "total_og_mou"),
    "data": ("vol_2g_mb", "vol_3g_mb"),
    "packs": ("monthly_2g", "monthly_3g", "sachet_2g", "sachet_3g"),
    "roaming": ("roam_ic_mou", "roam_og_mou"),
}
HORIZON = 12
HAZARD_MULTIPLIERS = {"low": 1.5, "base": 1.0, "high": 0.5}
VALUE_COLUMNS = (
    OutputColumn(
        "recency",
        "nonnegative number",
        "Days since airtime or data recharge; censored "
        "at the two-month window length when none is observed.",
    ),
    OutputColumn(
        "frequency", "nonnegative number", "Mean monthly airtime plus data recharge count."
    ),
    OutputColumn(
        "monthly_spend_lyd",
        "nonnegative number",
        "Mean monthly recharge at the frozen T18 assumed LYD rate; not observed operator revenue.",
    ),
    OutputColumn("tenure", "nonnegative number", "Age-on-network snapshot in days."),
    OutputColumn(
        "engagement",
        "integer 0 to 4",
        "Count of voice, data, packs and roaming used in either feature month.",
    ),
    *(
        OutputColumn(
            f"{name}_score",
            "integer 1 to 5",
            f"Training-frozen {name} quintile score; "
            "larger is better, constant training dimensions stay at 3.",
        )
        for name in DIMENSIONS
    ),
    OutputColumn("value_score", "number 1 to 5", "Equal-weight mean of the five dimension scores."),
    OutputColumn(
        "value_tier",
        ", ".join(f"`{tier}`" for tier in TIERS),
        "Training-frozen quintile of value_score; ties stay in the lower interval.",
    ),
    OutputColumn("tier_version", "text", "Version fingerprint of cutoffs, rate and fit metadata."),
    OutputColumn(
        "expected_months_12m",
        "number 0 to 12; may be empty",
        "Sum of (1-p)^m over month ends m=1..12, assuming constant monthly churn hazard p.",
    ),
    *(
        OutputColumn(
            f"value_12m_{name}_lyd",
            "nonnegative number; may be empty",
            f"12-month revenue scenario with monthly hazard multiplied by {multiplier:g}.",
        )
        for name, multiplier in HAZARD_MULTIPLIERS.items()
    ),
    OutputColumn(
        "value_status",
        "`scenario`, `already_silent` or `risk_unavailable`",
        "Whether a risk-based value scenario is available; missing values are not zero.",
    ),
)


class ValueModelError(ValueError):
    """Invalid tier inputs or an incompatible tier artifact."""


@dataclass(frozen=True)
class TierModel:
    rate: float
    training_rows: int
    cutoffs: dict[str, list[float] | None]

    def payload(self) -> dict:
        return {
            "schema_version": 1,
            "training_window": "A",
            "rate": self.rate,
            "training_rows": self.training_rows,
            "cutoffs": self.cutoffs,
        }

    @property
    def version(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True, allow_nan=False).encode("utf-8")
        return "tiers-v1-" + hashlib.sha256(encoded).hexdigest()[:12]


def value_measures(frame: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Measures from a cleaned relative window, including the T5 recency features.

    No recharge in either month means recency is censored at the window length.
    Whole missing activity blocks have already become zero under the T3 contract;
    unexpected missing inputs here are errors, not low-value customers.
    """
    if not np.isfinite(rate) or rate <= 0:
        raise ValueModelError("The frozen LYD rate must be finite and positive.")
    required = {
        "tenure_days",
        "days_since_last_rech_window",
        "days_since_last_rech_data_window",
        *(
            f"{prefix}_{base}"
            for prefix in ("prev", "cur")
            for base in (
                "total_rech_num",
                "total_rech_data",
                "total_rech_amt",
                "av_rech_amt_data",
                *(base for bases in SERVICES.values() for base in bases),
            )
        ),
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueModelError(f"Value inputs are missing: {missing}")
    try:
        inputs = frame[sorted(required)].astype(float)
    except (TypeError, ValueError):
        raise ValueModelError("Value inputs must be numeric.") from None
    if not np.isfinite(inputs.to_numpy()).all() or (inputs < 0).any().any():
        raise ValueModelError("Value inputs must be finite, nonnegative and nonmissing.")
    breadth = sum(
        inputs[[f"{prefix}_{base}" for prefix in ("prev", "cur") for base in bases]]
        .gt(0)
        .any(axis=1)
        .astype(int)
        for bases in SERVICES.values()
    )
    frequency = (
        sum(
            inputs[f"{prefix}_{base}"]
            for prefix in ("prev", "cur")
            for base in ("total_rech_num", "total_rech_data")
        )
        / 2
    )
    measures = pd.DataFrame(
        {
            "recency": inputs[
                ["days_since_last_rech_window", "days_since_last_rech_data_window"]
            ].min(axis=1),
            "frequency": frequency,
            "monetary": recharge_amount(inputs) * rate,
            "tenure": inputs["tenure_days"],
            "engagement": breadth,
        },
        index=frame.index,
    )
    if not np.isfinite(measures.to_numpy()).all():
        raise ValueModelError("Value measures overflowed; check the recharge amounts.")
    return measures


def _cutoffs(values: pd.Series) -> list[float] | None:
    # A constant dimension carries no ranking information. Keep it neutral forever.
    return None if values.nunique() == 1 else values.quantile(QUANTILES).tolist()


def _quintiles(values: pd.Series, cutoffs: list[float] | None) -> np.ndarray:
    if cutoffs is None:
        return np.full(len(values), 3, dtype=np.int64)
    # Ties always go to the lower interval. We never split identical customers by row order.
    return np.searchsorted(cutoffs, values.to_numpy(), side="left") + 1


def dimension_scores(measures: pd.DataFrame, model: TierModel) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"{name}_score": _quintiles(
                -measures[name] if name == "recency" else measures[name], model.cutoffs[name]
            )
            for name in DIMENSIONS
        },
        index=measures.index,
    )


def fit_tiers(train: pd.DataFrame, market: dict) -> TierModel:
    """Fit on the existing active training split in window A; labels are never read."""
    if train.empty:
        raise ValueModelError("Cannot fit tiers without training customers.")
    rate = lyd_rate(market)
    measures = value_measures(train, rate)
    cutoffs = {
        name: _cutoffs(-measures[name] if name == "recency" else measures[name])
        for name in DIMENSIONS
    }
    model = TierModel(rate, len(train), cutoffs)
    composite = dimension_scores(measures, model).mean(axis=1)
    return TierModel(rate, len(train), {**cutoffs, "composite": _cutoffs(composite)})


def apply_tiers(frame: pd.DataFrame, model: TierModel) -> pd.DataFrame:
    measures = value_measures(frame, model.rate)
    scores = dimension_scores(measures, model)
    result = pd.concat([measures, scores], axis=1)
    result["value_score"] = scores.mean(axis=1)
    tier = _quintiles(result["value_score"], model.cutoffs["composite"]) - 1
    result["value_tier"] = pd.Series(np.asarray(TIERS)[tier], index=frame.index, dtype="str")
    result["tier_version"] = model.version
    return result.rename(columns={"monetary": "monthly_spend_lyd"})


def save_tiers(model: TierModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**model.payload(), "version": model.version}
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_tiers(path: Path) -> TierModel:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            set(payload)
            != {"schema_version", "training_window", "rate", "training_rows", "cutoffs", "version"}
            or type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or payload["training_window"] != "A"
        ):
            raise ValueError("unknown artifact schema or training window")
        rate, rows, cutoffs = payload["rate"], payload["training_rows"], payload["cutoffs"]
        if type(rate) not in (int, float) or not np.isfinite(rate) or rate <= 0:
            raise ValueError("invalid LYD rate")
        if type(rows) is not int or rows < 1:
            raise ValueError("invalid training row count")
        if set(cutoffs) != {*DIMENSIONS, "composite"}:
            raise ValueError("missing or unknown cutoffs")
        for name, values in cutoffs.items():
            if values is None:
                continue
            if not isinstance(values, list) or len(values) != 4:
                raise ValueError(f"invalid {name} cutoffs")
            if any(type(v) not in (int, float) for v in values):
                raise ValueError(f"nonnumeric {name} cutoffs")
            if not np.isfinite(values).all() or values != sorted(values):
                raise ValueError(f"nonfinite or unsorted {name} cutoffs")
            if name == "composite" and not all(1 <= v <= 5 for v in values):
                raise ValueError("composite cutoffs must be between 1 and 5")
        model = TierModel(rate, rows, cutoffs)
        if payload["version"] != model.version:
            raise ValueError("artifact version does not match its contents")
        return model
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueModelError(f"Invalid tier artifact {path}: {error}") from None


def expected_months(probability: np.ndarray) -> np.ndarray:
    """Sum survival over the next 12 month ends under a constant monthly hazard.

    Missing risk stays missing, notably for customers already silent. This is a
    sensitivity scenario, not a fitted survival model or validated customer CLV.
    """
    probability = np.asarray(probability, dtype=float)
    if np.isinf(probability).any() or ((probability < 0) | (probability > 1)).any():
        raise ValueModelError("Churn probabilities must be in [0, 1] or missing.")
    return ((1 - probability[..., None]) ** np.arange(1, HORIZON + 1)).sum(axis=-1)


def value_scenarios(spend: pd.Series, probability: pd.Series) -> pd.DataFrame:
    if not spend.index.equals(probability.index):
        raise ValueModelError("Spend and risk must have identical row indices.")
    if not np.isfinite(spend).all() or (spend < 0).any():
        raise ValueModelError("Monthly spend must be finite and nonnegative.")
    months = expected_months(probability.to_numpy())
    result = pd.DataFrame({"expected_months_12m": months}, index=spend.index)
    for name, multiplier in HAZARD_MULTIPLIERS.items():
        risk = (probability * multiplier).clip(0, 1).to_numpy()
        result[f"value_12m_{name}_lyd"] = spend * expected_months(risk)
    if np.isinf(result.to_numpy()).any():
        raise ValueModelError("Value scenarios overflowed; check the monthly spend.")
    return result


def tier_export(
    export: pd.DataFrame,
    model: TierModel,
    bundle: Bundle | None = None,
    scored_at: str | None = None,
) -> pd.DataFrame:
    """Extend live T8 scores, or explicitly return tiers without a risk estimate.

    Scoring the same export here prevents stale CSV probabilities being joined
    to another month's value measures. No churn model is fitted by this path.
    """
    cleaned = clean(validate(export.drop(columns=LABEL_COLUMN, errors="ignore"), labeled=False))
    frame = add_features(window_features(cleaned, SCORING_WINDOW))
    tiers = apply_tiers(frame, model)
    active = active_in_current_month(cleaned, SCORING_WINDOW).to_numpy()
    if bundle is None:
        result = pd.DataFrame({"subscriber_id": cleaned[ID].astype(str)})
        probability = pd.Series(np.nan, index=result.index)
    else:
        result = score(export, bundle, scored_at)
        probability = result["churn_probability"]
    scenarios = value_scenarios(tiers["monthly_spend_lyd"], probability)
    scenarios["value_status"] = pd.Series(
        np.where(active, "scenario" if bundle is not None else "risk_unavailable", SILENT_BAND),
        dtype="str",
    )
    return pd.concat([result, tiers, scenarios], axis=1)
