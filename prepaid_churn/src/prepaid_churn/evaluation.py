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
from sklearn.metrics import (
    average_precision_score,
    log_loss,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

from prepaid_churn.training import metrics, predict
from prepaid_churn.windows import HIGH_VALUE_QUANTILE, LABEL, SEED

CALIBRATION_METHODS = ("none", "sigmoid", "isotonic")
TOP_SHARES = (0.05, 0.10, 0.20)
EPSILON = 1e-6

# Success thresholds (decision 13): a model is fit for use only if it passes all four.
CAPTURE_SHARE = 0.10  # the riskiest 10% of customers ...
MIN_CAPTURE = 0.50  # ... must hold at least half of the churners
MIN_LIFT = 3.0  # PR-AUC at least 3 times the churn rate (random ranking scores about the rate)
MAX_CALIBRATION_GAP = 0.01  # mean prediction within 1 point of the observed churn rate
BASELINE = "logistic_regression"


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
    probabilities = {}
    for name, model in models.items():
        raw = predict(model, validation)
        calibrator, scores = choose_calibrator(raw, y)
        calibrated = calibrator.transform(raw)
        probabilities[name] = calibrated
        choices[name] = {
            "calibrator": calibrator,
            "calibration_log_loss": scores,
            "metrics": metrics(y, calibrated),
        }
    best = max(choices, key=lambda name: choices[name]["metrics"]["pr_auc"])
    calibrated = probabilities[best]
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


def success_thresholds(y, probability, baseline_probability=None) -> dict:
    """The four checks of decision 13, each with its value, its requirement and the verdict.

    `baseline_probability` is None when the champion is the baseline itself: the simpler
    model already won, so the third check has nothing to beat.
    """
    y, probability = np.asarray(y), np.asarray(probability)
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("Release checks need both churners and non-churners.")
    rate = float(y.mean())
    capture = float(top_share_metrics(probability, y, (CAPTURE_SHARE,))["recall"].iloc[0])
    pr_auc = float(average_precision_score(y, probability))
    gap = abs(float(probability.mean()) - rate)
    checks = {
        "capture": {
            "description": f"Share of churners among the riskiest {CAPTURE_SHARE:.0%} of customers",
            "value": capture,
            "required": f">= {MIN_CAPTURE}",
            "passed": capture >= MIN_CAPTURE,
        },
        "better_than_chance": {
            "description": "PR-AUC divided by the churn rate",
            "value": pr_auc / rate,
            "required": f">= {MIN_LIFT}",
            "passed": pr_auc >= MIN_LIFT * rate,
        },
        "better_than_baseline": {
            "description": "PR-AUC against the logistic regression baseline",
            "value": pr_auc,
            "required": "champion is the baseline",
            "passed": True,
        },
        "calibration": {
            "description": "Distance between mean predicted and observed churn rate",
            "value": gap,
            "required": f"<= {MAX_CALIBRATION_GAP}",
            "passed": gap <= MAX_CALIBRATION_GAP,
        },
    }
    if baseline_probability is not None:
        baseline = float(average_precision_score(y, baseline_probability))
        checks["better_than_baseline"] |= {
            "required": f"> {baseline:.4f}",
            "passed": pr_auc > baseline,
        }
    return checks


def release_gate(champion: Champion, choices: dict, models: dict, test: pd.DataFrame) -> dict:
    """Test metrics for every model and the success thresholds for the champion.

    Stored next to the frozen champion; T8 refuses to bundle a champion that fails a check.
    """
    y = test[LABEL]
    calibrated = {
        name: choices[name]["calibrator"].transform(predict(model, test))
        for name, model in models.items()
    }
    baseline = None if champion.name == BASELINE else calibrated[BASELINE]
    thresholds = success_thresholds(y, calibrated[champion.name], baseline)
    return {
        "champion": champion.name,
        "chosen_at": champion.chosen_at,
        "passed": all(check["passed"] for check in thresholds.values()),
        "thresholds": thresholds,
        "test_metrics": {name: metrics(y, p) for name, p in calibrated.items()},
    }


def thresholds_table(gate: dict) -> pd.DataFrame:
    return pd.DataFrame(
        {
            name: {
                "check": check["description"],
                "value": round(check["value"], 4),
                "required": check["required"],
                "passed": "yes" if check["passed"] else "no",
            }
            for name, check in gate["thresholds"].items()
        }
    ).T


def evaluation_report(
    champion: Champion, choices: dict, models: dict, test: pd.DataFrame, gate: dict
) -> str:
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
            "## Success thresholds (decision 13)",
            "",
            f"{champion.name} must pass all four before it is bundled for use (T8).",
            "",
            markdown_table(thresholds_table(gate), "threshold"),
            "",
            f"Release gate: **{'passed' if gate['passed'] else 'failed'}**.",
            "",
        ]
    )


# ---------------------------------------------------------------------------
# Uncertainty on the frozen test metrics
# ---------------------------------------------------------------------------
#
# The test window was scored once, on 2026-09-19, and every figure in the evaluation
# report is a single number from one draw of 9,677 customers. Resampling those same
# frozen predictions says how much the numbers would move had a different set of
# customers landed in the test group. It trains, calibrates and chooses nothing, and
# nothing it reports may be used to justify a change to a model, feature or threshold.

BOOTSTRAP_REPEATS = 2000
INTERVAL = (0.025, 0.975)
MEASURES = ("pr_auc", "roc_auc", "capture", "lift", "calibration_gap")


def frozen_test_probabilities(
    models: dict, saved: Champion, validation: pd.DataFrame, test: pd.DataFrame
) -> dict[str, np.ndarray]:
    """Every model's calibrated test predictions, exactly as they were frozen.

    Only the champion's calibrator is saved, so the baseline's is re-derived by
    repeating the validation-only freeze with the recorded date. The freeze is
    deterministic, and this refuses to continue unless the repeat reproduces the saved
    champion's predictions exactly: an interval around different predictions would be
    an interval around a model nobody evaluated.
    """
    champion, choices = freeze(models, validation, saved.chosen_at)
    if champion.name != saved.name or not np.array_equal(
        champion.predict(test), saved.predict(test)
    ):
        raise ValueError(
            "Repeating the freeze did not reproduce the saved champion, so these would not "
            "be the frozen predictions. Rebuild with `churn evaluate --chosen-at "
            f"{saved.chosen_at}` first."
        )
    return {
        name: choices[name]["calibrator"].transform(predict(model, test))
        for name, model in models.items()
    }


def _score(y: np.ndarray, probabilities: dict) -> dict[str, float]:
    """The published test measures, computed the same way the release gate computes them."""
    rate = float(y.mean())
    row = {"churn_rate": rate}
    for name, probability in probabilities.items():
        pr_auc = float(average_precision_score(y, probability))
        row[f"{name}.pr_auc"] = pr_auc
        row[f"{name}.roc_auc"] = float(roc_auc_score(y, probability))
        row[f"{name}.capture"] = float(
            top_share_metrics(probability, y, (CAPTURE_SHARE,))["recall"].iloc[0]
        )
        row[f"{name}.lift"] = pr_auc / rate
        row[f"{name}.calibration_gap"] = abs(float(np.mean(probability)) - rate)
    return row


def resample_metrics(
    y, probabilities: dict, repeats: int = BOOTSTRAP_REPEATS, seed: int = SEED
) -> pd.DataFrame:
    """The test measures on `repeats` bootstrap resamples of the same frozen predictions.

    Every model is scored on the same resampled customers each time, so a difference
    between two models is paired: it reflects how they rank the same people rather
    than which people happened to be drawn. A resample with only one class cannot be
    scored and is drawn again; the generator is seeded, so the result is reproducible.
    """
    y = np.asarray(y)
    probabilities = {name: np.asarray(p) for name, p in probabilities.items()}
    rng = np.random.default_rng(seed)
    rows = []
    while len(rows) < repeats:
        index = rng.integers(0, len(y), len(y))
        sample = y[index]
        if sample.min() == sample.max():
            continue
        rows.append(_score(sample, {name: p[index] for name, p in probabilities.items()}))
    return pd.DataFrame(rows)


def interval(samples: pd.Series) -> tuple[float, float]:
    low, high = samples.quantile(list(INTERVAL))
    return float(low), float(high)


def _release_rows(point: dict, samples: pd.DataFrame, champion: str, baseline) -> dict:
    """Each release check at the unfavourable end of its interval."""
    checks = [
        ("capture", f"{champion}.capture", f">= {MIN_CAPTURE}", "low", MIN_CAPTURE),
        ("better_than_chance", f"{champion}.lift", f">= {MIN_LIFT}", "low", MIN_LIFT),
        (
            "calibration",
            f"{champion}.calibration_gap",
            f"<= {MAX_CALIBRATION_GAP}",
            "high",
            MAX_CALIBRATION_GAP,
        ),
    ]
    rows = {}
    for check, column, required, worst, limit in checks:
        low, high = interval(samples[column])
        holds = low >= limit if worst == "low" else high <= limit
        rows[check] = {
            "estimate": round(point[column], 4),
            "95% interval": f"[{low:.4f}, {high:.4f}]",
            "required": required,
            "holds at the worst end": "yes" if holds else "no",
        }
    if baseline is not None:
        difference = samples[f"{champion}.pr_auc"] - samples[f"{baseline}.pr_auc"]
        low, high = interval(difference)
        rows["better_than_baseline"] = {
            "estimate": round(point[f"{champion}.pr_auc"] - point[f"{baseline}.pr_auc"], 4),
            "95% interval": f"[{low:.4f}, {high:.4f}]",
            "required": "> 0",
            "holds at the worst end": "yes" if low > 0 else "no",
        }
    return rows


def uncertainty_report(
    y,
    probabilities: dict,
    champion: str,
    chosen_at: str,
    repeats: int = BOOTSTRAP_REPEATS,
    seed: int = SEED,
) -> str:
    """The frozen test measures with 95% intervals, and whether each release check holds."""
    from prepaid_churn.profile import markdown_table

    y = np.asarray(y)
    point = _score(y, probabilities)
    samples = resample_metrics(y, probabilities, repeats, seed)
    names = [champion, *[name for name in probabilities if name != champion]]
    baseline = BASELINE if BASELINE in probabilities and BASELINE != champion else None

    labels = {
        "pr_auc": "PR-AUC (primary)",
        "roc_auc": "ROC-AUC",
        "capture": f"Churners in the riskiest {CAPTURE_SHARE:.0%}",
        "lift": "PR-AUC divided by the churn rate",
        "calibration_gap": "Gap between mean prediction and churn rate",
    }

    def cell(name: str, measure: str) -> str:
        column = f"{name}.{measure}"
        low, high = interval(samples[column])
        return f"{point[column]:.4f} [{low:.4f}, {high:.4f}]"

    table = pd.DataFrame(
        {name: {labels[measure]: cell(name, measure) for measure in MEASURES} for name in names}
    )

    lines = [
        "# Uncertainty on the frozen test metrics",
        "",
        "Generated by `uv run churn uncertainty`.",
        f"The test predictions frozen on {chosen_at} are resampled {repeats:,} times: "
        f"{len(y):,} customers drawn with replacement each time, seed {seed}.",
        "Each cell is the published estimate followed by its 95% interval.",
        "",
        "**This analysis changes nothing.**",
        "It trains, calibrates and chooses nothing, and it re-derives exactly the predictions "
        "that were scored once for `evaluation_all.md`.",
        "It puts error bars on numbers that are already published, and none of its results "
        "may be used to justify a change to a model, feature or threshold.",
        "",
        "## 95% intervals",
        "",
        markdown_table(table),
        "",
    ]

    if baseline is not None:
        difference = samples[f"{champion}.pr_auc"] - samples[f"{baseline}.pr_auc"]
        low, high = interval(difference)
        wins = int((difference > 0).sum())
        estimate = point[f"{champion}.pr_auc"] - point[f"{baseline}.pr_auc"]
        lines += [
            f"## Is {champion} really better than the baseline?",
            "",
            f"PR-AUC difference: {estimate:.4f}, 95% interval [{low:.4f}, {high:.4f}].",
            f"{champion} scored higher in {wins:,} of {repeats:,} resamples "
            f"({wins / repeats:.1%}).",
            "Both models are scored on the same resampled customers every time, so the "
            "difference is paired and does not depend on which customers were drawn.",
            "",
        ]

    lines += [
        "## Do the four release checks still hold at the unlucky end?",
        "",
        "Each check passed on the published estimate (decision 13).",
        "This asks whether it would still pass at the unfavourable end of its interval: the "
        "lower end for capture, lift and the baseline difference, the upper end for the "
        "calibration gap.",
        "",
        markdown_table(pd.DataFrame(_release_rows(point, samples, champion, baseline)).T),
        "",
        "## What these intervals cover, and what they do not",
        "",
        "They cover test sampling: how much the numbers depend on which customers happened "
        "to land in the test group.",
        "They do not cover training randomness, which would need models retrained on other "
        "splits and each scored on the spent test window; the project forbids that.",
        "They do not cover a different month or a different operator, which only new data "
        "can measure.",
        "",
    ]
    return "\n".join(lines)
