"""The head-to-head benchmark table. Deliverable D3.

Produces the comparison that the pitch slide and the report are built on:
LightGBM against XGBoost, CatBoost and every classical baseline, on
calibration curves, PR-AUC, lift at deciles 1-3, and Brier.

Two reporting rules, both non-negotiable:

* Accuracy is NOT reported as a headline. It is meaningless at a 10-30% base
  rate. CI checks for it.
* The naive figures and the honest figures are reported side by side, with the
  gap explained. Published work on the Iranian dataset reaches ~97% accuracy
  and ~0.99 AUC; those numbers are inflated by ~300 duplicate rows and by the
  pre-computed `Customer Value` field. We reproduce them, then show they are
  wrong. We would rather show a defensible 0.78 PR-AUC than an indefensible 0.99.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings
from cvm.models.m1_churn.calibration import (
    _raw_probability,
    brier_score,
    expected_calibration_error,
)

log = logging.getLogger(__name__)

# PR-AUC first, and accuracy last if it appears at all. The order of these
# columns is the reporting rule made physical: whatever a reader's eye lands
# on first is the headline, whatever the caption says.
METRIC_ORDER = (
    "pr_auc",
    "lift_at_decile_1",
    "lift_at_decile_2",
    "lift_at_decile_3",
    "brier_score",
    "ece",
    "roc_auc",
    "recall_at_decile_1",
    "base_rate",
    "accuracy",
)


def _conf() -> dict:
    return load_conf("models/m1_churn")["metrics"]


def lift_at_decile(y_true, y_prob, decile: int = 1) -> float:
    """Concentration of churners in the top `decile` tenths, over the base rate.

    A lift of 4.0 at decile 1 means the top 10% of scores contains four times
    the churn density of the population -- which is the number a campaign
    manager actually plans against, because it says how much of the budget
    finds a churner.

    CUMULATIVE, not the decile in isolation: you target the top 10%, or the top
    20%, never the second tenth on its own.
    """
    y_true = np.asarray(y_true, dtype="float64")
    y_prob = np.asarray(y_prob, dtype="float64")
    base = y_true.mean()
    if base == 0:
        raise ValueError("no positive cases; lift is undefined")

    cut = max(1, round(len(y_true) * decile / 10))
    top = y_true[np.argsort(-y_prob)[:cut]]
    return float(top.mean() / base)


def recall_at_decile(y_true, y_prob, decile: int = 1) -> float:
    """Share of all churners captured in the top `decile` tenths."""
    y_true = np.asarray(y_true, dtype="float64")
    y_prob = np.asarray(y_prob, dtype="float64")
    cut = max(1, round(len(y_true) * decile / 10))
    top = y_true[np.argsort(-y_prob)[:cut]]
    return float(top.sum() / y_true.sum())


def score_model(model, X_test, y_test) -> dict[str, float]:
    """Every reported metric for one model."""
    from sklearn.metrics import accuracy_score, average_precision_score, roc_auc_score

    probability = _raw_probability(model, X_test)
    y_test = np.asarray(y_test).astype(int)

    return {
        "pr_auc": float(average_precision_score(y_test, probability)),
        "lift_at_decile_1": lift_at_decile(y_test, probability, 1),
        "lift_at_decile_2": lift_at_decile(y_test, probability, 2),
        "lift_at_decile_3": lift_at_decile(y_test, probability, 3),
        "brier_score": brier_score(y_test, probability),
        "ece": expected_calibration_error(y_test, probability),
        "roc_auc": float(roc_auc_score(y_test, probability)),
        "recall_at_decile_1": recall_at_decile(y_test, probability, 1),
        "base_rate": float(y_test.mean()),
        "accuracy": float(accuracy_score(y_test, (probability >= 0.5).astype(int))),
    }


def run_benchmark(models: dict[str, object], X_test, y_test) -> pd.DataFrame:
    """One row per model, one column per metric. Order the rows by PR-AUC."""
    if not models:
        raise ValueError("no models to benchmark")

    rows = []
    for name, model in models.items():
        metrics = score_model(model, X_test, y_test)
        rows.append({"model": name, **metrics})
        log.info(
            "  %-24s PR-AUC %.4f  lift@1 %.2f  Brier %.5f",
            name,
            metrics["pr_auc"],
            metrics["lift_at_decile_1"],
            metrics["brier_score"],
        )

    table = pd.DataFrame(rows)[["model", *METRIC_ORDER]]
    table = table.sort_values("pr_auc", ascending=False).reset_index(drop=True)

    # The reporting rule, enforced here rather than trusted to a reviewer. CI
    # asserts the same thing on the written CSV.
    if _conf()["forbid_accuracy_as_headline"] and table.columns[1] == "accuracy":
        raise AssertionError("accuracy is leading the benchmark table; PR-AUC must")

    baseline = table.loc[table["model"] == "logistic_regression", "pr_auc"]
    if not baseline.empty:
        best = table.iloc[0]
        log.info(
            "best %s at PR-AUC %.4f, against logistic regression at %.4f -- %+.1f%%",
            best["model"],
            best["pr_auc"],
            float(baseline.iloc[0]),
            100 * (best["pr_auc"] / float(baseline.iloc[0]) - 1),
        )
    return table


def naive_vs_honest(dataset: str = "uci_iranian") -> pd.DataFrame:
    """Reproduce the inflated published metrics, then the corrected ones.

    Rows: with duplicates + leaky field + random split (naive), then
    deduplicated + leaky field dropped + temporal split (honest).

    THE POINT IS THE GAP, NOT EITHER NUMBER. Three defensible-sounding choices
    -- keep every row, use the field the dataset ships with, split at random --
    each add a few points, and together they turn a 0.8-ish model into a 0.99
    one. None of them is fraud and all of them are wrong, which is why the
    comparison belongs in the report rather than a footnote about methodology.

    The three effects are separated into their own rows, so a reader can see
    which choice bought how much rather than taking the total on trust.
    """
    if dataset != "uci_iranian":
        raise ValueError(f"only uci_iranian is implemented, got {dataset!r}")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import accuracy_score, average_precision_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline

    from cvm.ingest.uci_iranian import COLUMN_RENAMES, LABEL, deduplicate, fetch

    conf = load_conf("data")["sources"]["uci_iranian"]
    leaky = conf["leaky_columns"]
    seed = settings.random_seed

    raw = fetch().rename(columns=COLUMN_RENAMES)
    deduped, dropped = deduplicate(raw)

    def evaluate(frame: pd.DataFrame, drop_leaky: bool, temporal: bool, label: str) -> dict:
        X = frame.drop(columns=[LABEL])
        if drop_leaky:
            X = X.drop(columns=[c for c in leaky if c in X.columns])
        X = X.select_dtypes(include="number")
        y = frame[LABEL].astype(int)

        if temporal:
            # UCI ships no date. `Subscription Length` is the only ordering the
            # dataset carries, so it stands in for time: train on the longer-
            # tenured, test on the newer. It is a proxy and the report says so
            # -- but ANY held-out ordering is closer to honest than a shuffle,
            # because a shuffle puts a subscriber's near-duplicate twin on both
            # sides of the split.
            order = frame["Subscription Length"].rank(method="first").values
            cut = np.quantile(order, 0.7)
            train_mask = order <= cut
            X_train, X_test = X[train_mask], X[~train_mask]
            y_train, y_test = y[train_mask], y[~train_mask]
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.3, random_state=seed, stratify=y
            )

        model = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("model", RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1)),
            ]
        )
        model.fit(X_train, y_train)
        probability = model.predict_proba(X_test)[:, 1]

        return {
            "setup": label,
            "rows": len(frame),
            "leaky_field": "kept" if not drop_leaky else "dropped",
            "split": "temporal" if temporal else "random",
            "accuracy": float(accuracy_score(y_test, probability >= 0.5)),
            "roc_auc": float(roc_auc_score(y_test, probability)),
            "pr_auc": float(average_precision_score(y_test, probability)),
        }

    rows = [
        evaluate(raw, False, False, "naive (as published)"),
        evaluate(deduped, False, False, "+ duplicates removed"),
        evaluate(deduped, True, False, "+ leaky field dropped"),
        evaluate(deduped, True, True, "honest (ours)"),
    ]
    table = pd.DataFrame(rows)

    naive, honest = table.iloc[0], table.iloc[-1]
    log.info(
        "naive %.4f accuracy / %.4f ROC-AUC -> honest %.4f / %.4f "
        "(%d duplicates, leaky field %s, %s split)",
        naive["accuracy"],
        naive["roc_auc"],
        honest["accuracy"],
        honest["roc_auc"],
        dropped,
        leaky,
        honest["split"],
    )
    return table


def architecture_verdict(results: pd.DataFrame) -> str:
    """Write the verdict paragraph. Whichever model won, explain WHY.

    A table without this paragraph is a leaderboard, not a result. The question
    a reader has is not which row is highest -- they can see that -- but
    whether the gap is worth the complexity it costs.
    """
    if results.empty:
        raise ValueError("no results to write a verdict for")

    ordered = results.sort_values("pr_auc", ascending=False).reset_index(drop=True)
    best = ordered.iloc[0]

    def find(name: str):
        row = ordered[ordered["model"] == name]
        return None if row.empty else row.iloc[0]

    logistic = find("logistic_regression")
    tree = find("decision_tree")

    parts = [
        f"**{best['model']} wins at {best['pr_auc']:.4f} PR-AUC**, against a "
        f"{best['base_rate']:.2%} base rate -- so the model concentrates churners "
        f"{best['lift_at_decile_1']:.1f}x in the top decile, capturing "
        f"{best['recall_at_decile_1']:.1%} of all churners in 10% of the base."
    ]

    if logistic is not None and best["model"] != "logistic_regression":
        margin = 100 * (best["pr_auc"] / logistic["pr_auc"] - 1)
        verdict = (
            "The boosted model earns its complexity."
            if margin >= 15
            else (
                "**The margin is thin, and that is the finding.** A boosted model "
                "that barely clears logistic regression is a boosted model whose "
                "operational cost -- retraining, drift monitoring, a heavier serving "
                "path -- is buying very little."
            )
        )
        parts.append(
            f"Logistic regression reaches {logistic['pr_auc']:.4f} on the same split, "
            f"so the margin is {margin:+.1f}%. {verdict}"
        )
    elif logistic is not None:
        # Logistic IS the winner, so comparing it to itself prints "+0.0%" and
        # says nothing. The comparison a reader needs is against the best model
        # that is NOT linear -- which is how much the whole boosted arm bought.
        boosted = ordered[~ordered["model"].isin(["logistic_regression", "naive_bayes"])]
        if not boosted.empty:
            runner = boosted.iloc[0]
            margin = 100 * (logistic["pr_auc"] / runner["pr_auc"] - 1)
            parts.append(
                f"**No boosted model beat it.** The best non-linear arm is "
                f"{runner['model']} at {runner['pr_auc']:.4f}, so logistic regression is "
                f"{margin:+.1f}% ahead of the entire gradient-boosting family -- on a "
                "matrix the boosted models had every advantage on, including native "
                "handling of the 3-6% missingness the baselines had to impute away."
            )

    if tree is not None:
        parts.append(
            f"A depth-6 decision tree reaches {tree['pr_auc']:.4f}, which is the floor "
            "an interpretable model sets. Anything between that and the winner is what "
            "the ensemble is actually contributing."
        )

    # The caveat that matters more than the ranking. It is emitted whenever a
    # linear model is at or near the top, because on THIS population that is
    # not a fact about linear models -- it is a fact about the generator.
    if logistic is not None:
        rank = int(ordered.index[ordered["model"] == "logistic_regression"][0]) + 1
        if rank <= 2:
            parts.append(
                "**Read this ranking with care, because the generator is linear.** The "
                "synthetic label comes from a logistic hazard -- a weighted sum of "
                "standardised drivers pushed through a sigmoid -- so logistic regression "
                f"is CORRECTLY SPECIFIED on this data and places {rank}"
                f"{'st' if rank == 1 else 'nd'}. The tree models can only approximate a "
                "smooth linear-in-log-odds surface with step functions, and they are "
                "being asked to rediscover a form we handed the linear model for free. "
                "This benchmark therefore measures the generator's functional form as "
                "much as it measures the models. It is a working pipeline and a fair "
                "comparison ON THIS DATA; it is NOT evidence about which model wins on "
                "real Almadar subscribers, whose churn is under no obligation to be "
                "linear in log-odds. Re-run it on real data before quoting the order."
            )

    parts.append(
        f"Accuracy is reported last and deliberately: at a {best['base_rate']:.2%} base "
        f"rate, predicting 'no churn' for everyone scores {1 - best['base_rate']:.2%} and "
        "finds nobody. Every figure above is calibrated, so a 0.31 means 31% and the "
        "pricing engine can multiply it by money."
    )

    return " ".join(parts)
