"""Calibration, frozen choices and the one-time test evaluation (ticket T7).

Everything is chosen on validation customers (window A): the calibration
method, the champion model and the risk thresholds. Only then is the test
window (B, a later month and unseen customers) scored, once.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, precision_recall_curve
from sklearn.model_selection import StratifiedKFold

from prepaid_churn.training import metrics, predict
from prepaid_churn.windows import HIGH_VALUE_QUANTILE, LABEL, SEED

CALIBRATION_METHODS = ("none", "sigmoid", "isotonic")
TOP_SHARES = (0.05, 0.10, 0.20)
EPSILON = 1e-6


class Calibrator:
    """Maps raw model probabilities to calibrated ones with one of CALIBRATION_METHODS."""

    def __init__(self, method: str):
        if method not in CALIBRATION_METHODS:
            raise ValueError(f"Unknown calibration method {method!r}")
        self.method = method

    def fit(self, probability, y):
        if self.method == "sigmoid":
            self.mapper_ = LogisticRegression().fit(_logit(probability), y)
        elif self.method == "isotonic":
            self.mapper_ = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(
                probability, y
            )
        return self

    def transform(self, probability) -> np.ndarray:
        probability = np.asarray(probability, dtype=float)
        if self.method == "sigmoid":
            probability = self.mapper_.predict_proba(_logit(probability))[:, 1]
        elif self.method == "isotonic":
            probability = self.mapper_.predict(probability)
        return np.clip(probability, EPSILON, 1 - EPSILON)


def _logit(probability) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, dtype=float), EPSILON, 1 - EPSILON)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def cross_validated_log_loss(probability, y, method: str, folds: int = 5, seed: int = SEED):
    """Log loss of a calibration method, fitted and scored on different folds."""
    probability, y = np.asarray(probability), np.asarray(y)
    calibrated = np.empty_like(probability, dtype=float)
    for fit_rows, score_rows in StratifiedKFold(folds, shuffle=True, random_state=seed).split(
        probability, y
    ):
        calibrator = Calibrator(method).fit(probability[fit_rows], y[fit_rows])
        calibrated[score_rows] = calibrator.transform(probability[score_rows])
    return log_loss(y, calibrated)


def choose_calibrator(probability, y) -> tuple[Calibrator, dict[str, float]]:
    """The method with the lowest cross-validated log loss, refit on all given rows."""
    scores = {m: cross_validated_log_loss(probability, y, m) for m in CALIBRATION_METHODS}
    best = min(scores, key=scores.get)
    return Calibrator(best).fit(probability, y), scores


def best_f1_threshold(probability, y) -> float:
    precision, recall, thresholds = precision_recall_curve(y, probability)
    f1 = 2 * precision * recall / np.maximum(precision + recall, EPSILON)
    return float(thresholds[np.argmax(f1[:-1])])


def top_share_metrics(probability, y, shares=TOP_SHARES) -> pd.DataFrame:
    """Precision and recall when contacting only the riskiest share of customers."""
    order = np.argsort(-np.asarray(probability), kind="stable")
    y = np.asarray(y)[order]
    rows = {}
    for share in shares:
        contacted = max(int(round(share * len(y))), 1)
        caught = y[:contacted].sum()
        rows[f"top {share:.0%}"] = {
            "customers": contacted,
            "precision": caught / contacted,
            "recall": caught / max(y.sum(), 1),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def reliability_table(probability, y, bins: int = 10) -> pd.DataFrame:
    """Mean predicted vs observed churn in equal-size bins of predicted probability."""
    frame = pd.DataFrame({"predicted": probability, "observed": np.asarray(y)})
    frame["bin"] = pd.qcut(frame["predicted"].rank(method="first"), bins, labels=False)
    table = frame.groupby("bin").agg(
        customers=("observed", "size"),
        predicted=("predicted", "mean"),
        observed=("observed", "mean"),
    )
    table.index = table.index + 1
    return table


def risk_band(probability, high: float, medium: float) -> np.ndarray:
    probability = np.asarray(probability)
    return np.where(probability >= high, "high", np.where(probability >= medium, "medium", "low"))


def recharge_amount(frame: pd.DataFrame) -> pd.Series:
    """Average airtime plus data recharge amount over the window (same rule as T4)."""
    total = 0
    for prefix in ("prev", "cur"):
        data = frame[f"{prefix}_total_rech_data"] * frame[f"{prefix}_av_rech_amt_data"]
        total = total + frame[f"{prefix}_total_rech_amt"] + data
    return total / 2


@dataclass
class Champion:
    """Everything frozen before the test set is opened."""

    name: str
    model: object
    calibrator: Calibrator
    high_threshold: float
    medium_threshold: float
    chosen_at: str
    validation: dict = field(default_factory=dict)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.calibrator.transform(predict(self.model, frame))


def freeze(models: dict, validation: pd.DataFrame, chosen_at: str) -> tuple[Champion, dict]:
    """Calibrate every model on validation, pick the champion by PR-AUC, set thresholds."""
    y = validation[LABEL]
    choices = {}
    for name, model in models.items():
        calibrator, scores = choose_calibrator(predict(model, validation), y)
        calibrated = calibrator.transform(predict(model, validation))
        choices[name] = {
            "calibrator": calibrator,
            "calibration_log_loss": scores,
            "metrics": metrics(y, calibrated),
        }
    best = max(choices, key=lambda name: choices[name]["metrics"]["pr_auc"])
    calibrated = choices[best]["calibrator"].transform(predict(models[best], validation))
    champion = Champion(
        name=best,
        model=models[best],
        calibrator=choices[best]["calibrator"],
        high_threshold=best_f1_threshold(calibrated, y),
        medium_threshold=float(y.mean()),
        chosen_at=chosen_at,
        validation=choices[best]["metrics"],
    )
    return champion, choices


def evaluation_report(champion: Champion, choices: dict, models: dict, test: pd.DataFrame) -> str:
    from prepaid_churn.profile import markdown_table

    y = test[LABEL]
    calibrated = {
        name: choices[name]["calibrator"].transform(predict(model, test))
        for name, model in models.items()
    }
    probability = calibrated[champion.name]
    bands = pd.Series(risk_band(probability, champion.high_threshold, champion.medium_threshold))
    band_table = pd.DataFrame(
        {
            "customers": bands.value_counts(),
            "churn_rate": pd.Series(np.asarray(y)).groupby(bands.values).mean(),
        }
    ).reindex(["high", "medium", "low"])
    high = probability >= champion.high_threshold
    high_value = (
        recharge_amount(test) >= recharge_amount(test).quantile(HIGH_VALUE_QUANTILE)
    ).values
    calibration_choice = pd.DataFrame(
        {name: choice["calibration_log_loss"] for name, choice in choices.items()}
    ).T
    return "\n".join(
        [
            "# T7 calibration and test evaluation",
            "",
            "Generated by `uv run churn evaluate`.",
            f"All choices were frozen on the validation customers on {champion.chosen_at}, "
            "before the test window was scored.",
            "",
            "## Frozen choices (validation customers, window A)",
            "",
            f"- Champion: **{champion.name}** (highest validation PR-AUC after calibration).",
            f"- Calibration: **{champion.calibrator.method}** "
            "(lowest 5-fold cross-validated log loss among none, sigmoid and isotonic).",
            f"- High-risk threshold: {champion.high_threshold:.4f} (best F1 on validation).",
            f"- Medium-risk threshold: {champion.medium_threshold:.4f} "
            "(the validation churn rate: above-average risk).",
            "",
            "Cross-validated log loss of each calibration method:",
            "",
            markdown_table(calibration_choice, "model"),
            "",
            "## Test results (window B: months 7 and 8, Kaggle's month 9 label, unseen customers)",
            "",
            markdown_table(
                pd.DataFrame({name: metrics(y, p) for name, p in calibrated.items()}).T, "model"
            ),
            "",
            f"### {champion.name}: contacting the riskiest customers",
            "",
            markdown_table(top_share_metrics(probability, y), "contact"),
            "",
            f"High-risk threshold on test: precision {y[high].mean():.4f}, "
            f"recall {y[high].sum() / max(y.sum(), 1):.4f}, {int(high.sum())} customers.",
            "",
            "### Risk bands on test",
            "",
            markdown_table(band_table, "band"),
            "",
            "### Reliability (10 equal-size bins of predicted probability)",
            "",
            markdown_table(reliability_table(probability, y), "bin"),
            "",
            "### High-value slice (top 30% by recharge amount)",
            "",
            markdown_table(
                pd.DataFrame({"high value": metrics(y[high_value], probability[high_value])}).T,
                "slice",
            ),
            "",
        ]
    )
