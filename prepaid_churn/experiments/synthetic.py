# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["sdv", "prepaid-churn"]
#
# [tool.uv.sources]
# prepaid-churn = { path = "../", editable = false }
# ///
"""T13 synthetic data experiment: can a synthetic copy stand in for the real customers?

The question is the operator's, not the model's.
Real prepaid data cannot leave a telecom operator, and a team that wants to build against
it has to work on something else.
So: if an operator fits a generator on its own customers and shares the generated copy,
is a churn model trained on that copy worth anything, and how much does the copy leak?

Three measurements, all on window A, and the frozen test window is never touched:

1. Utility. Train the same LightGBM on real customers and on each synthetic copy, then
   score all of them on the same real validation customers. Training on synthetic and
   testing on real is the only comparison that answers the operator's question; a model
   that scores its own generator's output is grading its own homework.
2. Detection. Ask a classifier to tell a real row from a synthetic one. 0.5 means it
   cannot, and the copy is realistic; 1.0 means the copy is obvious.
3. Fidelity. SDMetrics' quality report for the column shapes and the pairwise trends,
   plus the Almadar bundle mix of T18, which is the business-level version of the same
   question.

Run it with `uv run --script experiments/synthetic.py` from `prepaid_churn/`.
It is a standalone script on purpose: SDV caps pandas below 3, and this module is frozen
on pandas 3 (decision 27), so this experiment gets its own environment and the module's
own lockfile never moves. The package itself is imported from the path above, so the
Almadar rules and the LightGBM settings here are the module's own, not copies.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sdv.evaluation.single_table import evaluate_quality
from sdv.metadata import Metadata
from sdv.single_table import CTGANSynthesizer, GaussianCopulaSynthesizer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import cross_val_score

from prepaid_churn.almadar import bundle_held, load_market, load_offers, lyd_rate
from prepaid_churn.training import lightgbm, top_importances
from prepaid_churn.windows import LABEL

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "all"
REPORT = ROOT / "reports" / "synthetic.md"

SEED = 42
ROWS = 6000  # the operator's sample size here; CTGAN on a CPU is the binding constraint
TOP_FEATURES = 18
EPOCHS = 60
BATCH_SIZE = 500
DETECTION_FOLDS = 5

# What the Almadar view of T18 reads. They join the feature set so the synthetic copy can
# be shown in Almadar terms, which is the form an operator would actually look at.
ALMADAR_COLUMNS = [
    f"{step}_{base}"
    for step in ("prev", "cur")
    for base in ("total_rech_amt", "total_rech_data", "av_rech_amt_data")
] + ["cur_monthly_2g", "cur_monthly_3g", "cur_sachet_2g", "cur_sachet_3g"]


def experiment_columns(sample: pd.DataFrame) -> list[str]:
    """The features this experiment synthesises: the strongest ones, plus T18's.

    Every column costs CTGAN time on a CPU, so the whole 126-feature frame is out of
    reach here. The choice is made on training customers only, by the gain of a model
    fitted on this sample, and the same columns are used for every table in the
    comparison so nothing is decided by which columns a model was given.
    """
    features = [name for name in sample.columns if name not in ("id", LABEL)]
    booster = lightgbm(SEED, n_estimators=300).fit(sample[features], sample[LABEL])
    strongest = list(top_importances(booster, TOP_FEATURES).index)
    return sorted(set(strongest) | {c for c in ALMADAR_COLUMNS if c in features})


def synthesise(synthesizer, table: pd.DataFrame, rows: int) -> tuple[pd.DataFrame, float]:
    start = time.time()
    synthesizer.fit(table)
    return synthesizer.sample(rows), time.time() - start


def utility(train: pd.DataFrame, validation: pd.DataFrame, columns: list[str]) -> dict:
    """Train on this table, score the real validation customers."""
    model = lightgbm(SEED, n_estimators=300).fit(train[columns], train[LABEL])
    probability = model.predict_proba(validation[columns])[:, 1]
    y = validation[LABEL]
    return {
        "pr_auc": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "churn_rate": float(train[LABEL].mean()),
    }


def detection(real: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str]) -> float:
    """How well a classifier tells the two apart; 0.5 is indistinguishable."""
    x = pd.concat([real[columns], synthetic[columns]], ignore_index=True)
    y = np.r_[np.zeros(len(real)), np.ones(len(synthetic))]
    scores = cross_val_score(
        lightgbm(SEED, n_estimators=200), x, y, cv=DETECTION_FOLDS, scoring="roc_auc"
    )
    return float(scores.mean())


def almadar_mix(frame: pd.DataFrame, rate: float, offers: pd.DataFrame) -> pd.Series:
    """The share of customers on each kind of Almadar bundle (T18's rule)."""
    held = bundle_held(frame, rate, offers)
    kind = np.where(
        held.eq("PAYG"), "pay-as-you-go", np.where(held.str.startswith("MO_"), "monthly", "daily")
    )
    return pd.Series(kind).value_counts(normalize=True)


def impossible_columns(real: pd.DataFrame, columns: list[str]) -> list[str]:
    """Columns that are never negative in the real data, so a negative there is impossible.

    Not every amount qualifies. `diff_*` is a difference and is negative for half the real
    customers, and even `arpu` dips below zero for a fraction of a percent of them. Taking
    "negative amount" as an error without checking would have reported the real data as
    58% impossible, which is how this check was wrong the first time it was written.
    """
    return [name for name in columns if float(real[name].min()) >= 0]


def impossible_share(frame: pd.DataFrame, columns: list[str]) -> float:
    """Share of rows carrying a value the real data never shows."""
    return float((frame[columns] < 0).any(axis=1).mean()) if columns else 0.0


def main() -> None:
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    train = pd.read_parquet(DATA / "train.parquet")
    validation = pd.read_parquet(DATA / "validation.parquet")
    real = train.sample(ROWS, random_state=SEED).reset_index(drop=True)
    columns = experiment_columns(real)
    table = real[columns + [LABEL]]
    print(f"real sample {table.shape}, churn rate {table[LABEL].mean():.4f}")

    never_negative = impossible_columns(table, columns)
    metadata = Metadata.detect_from_dataframe(table, table_name="customers")
    synthesizers = {
        "ctgan": CTGANSynthesizer(
            metadata, epochs=EPOCHS, batch_size=BATCH_SIZE, cuda=False, verbose=False
        ),
        "copula": GaussianCopulaSynthesizer(metadata),
    }
    results, copies = {}, {}
    for name, synthesizer in synthesizers.items():
        copies[name], seconds = synthesise(synthesizer, table, ROWS)
        quality = evaluate_quality(table, copies[name], metadata, verbose=False)
        properties = quality.get_properties().set_index("Property")["Score"]
        results[name] = {
            "seconds": seconds,
            "utility": utility(copies[name], validation, columns),
            "detection": detection(table, copies[name], columns),
            "quality": float(quality.get_score()),
            "shapes": float(properties["Column Shapes"]),
            "trends": float(properties["Column Pair Trends"]),
            "impossible": impossible_share(copies[name], never_negative),
        }
        print(f"{name}: fitted in {seconds:.0f}s, detection {results[name]['detection']:.3f}")

    market, offers = (
        load_market(ROOT / "data" / "almadar" / "market.toml"),
        load_offers(ROOT / "data" / "almadar" / "offers.csv"),
    )
    rate = lyd_rate(market)
    mixes = {"real": almadar_mix(table, rate, offers)} | {
        name: almadar_mix(copy, rate, offers) for name, copy in copies.items()
    }
    real_utility = utility(table, validation, columns)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        report(results, real_utility, mixes, table, validation, columns, never_negative),
        encoding="utf-8",
    )
    print(f"report in {REPORT}")


def report(results, real_utility, mixes, table, validation, columns, never_negative) -> str:
    names = list(results)
    lines = [
        "# T13 synthetic data experiment",
        "",
        "Generated by `uv run --script experiments/synthetic.py` (ticket T13).",
        "",
        "The question is the operator's: real prepaid data cannot leave a telecom operator, "
        "so can it share a generated copy of its customers and still hand out a model worth "
        "training?",
        "",
        "## What was run",
        "",
        f"- {len(table)} real training customers (window A), {len(columns)} features: the "
        f"{TOP_FEATURES} strongest by LightGBM gain plus the columns the Almadar view needs.",
        "- CTGAN, the generative adversarial model for tables from the syllabus chapter, and a "
        "Gaussian copula as the simple baseline that any GAN has to beat.",
        f"- CTGAN ran {EPOCHS} epochs at batch {BATCH_SIZE} on a laptop CPU.",
        "  That is a budget, not a tuned setting: a longer fit would probably produce a better "
        "copy, and the numbers below are a floor rather than the best CTGAN can do.",
        "- Nothing here touches the frozen test window, and no synthetic row has ever trained "
        "the production model.",
        "",
        "## Utility: train on synthetic, score real customers",
        "",
        f"Every model is the same LightGBM on the same {len(columns)} columns, scored on the "
        f"same {len(validation)} real validation customers.",
        "",
        "| Trained on | Churn rate of the training table | PR-AUC on real customers | ROC-AUC |",
        "|---|---|---|---|",
        f"| Real customers | {real_utility['churn_rate']:.4f} | {real_utility['pr_auc']:.4f} "
        f"| {real_utility['roc_auc']:.4f} |",
    ]
    for name in names:
        u = results[name]["utility"]
        lines.append(
            f"| {name} synthetic | {u['churn_rate']:.4f} | {u['pr_auc']:.4f} | {u['roc_auc']:.4f} |"
        )
    lines += [
        "",
        f"Real training keeps {_share(real_utility['pr_auc'], real_utility['pr_auc'])} of its own "
        "PR-AUC by definition; each synthetic copy keeps "
        + ", ".join(
            f"{_share(results[name]['utility']['pr_auc'], real_utility['pr_auc'])} ({name})"
            for name in names
        )
        + ".",
        "",
        "## Detection and fidelity",
        "",
        "| Copy | Detection ROC-AUC (0.5 = indistinguishable) | SDMetrics quality | Column "
        "shapes | Pair trends | Rows with an impossible value | Fitting time |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in names:
        r = results[name]
        lines.append(
            f"| {name} | {r['detection']:.3f} | {r['quality']:.3f} | {r['shapes']:.3f} | "
            f"{r['trends']:.3f} | {r['impossible']:.1%} | {r['seconds']:.0f}s |"
        )
    lines += [
        "",
        f'"Impossible" means a negative value in one of the {len(never_negative)} columns '
        "that are never negative in the real sample, such as a recharge amount. "
        "Differences are excluded, because half of the real customers have a negative one.",
        _impossible_note(results),
        "",
        "## The same copies in Almadar terms (T18)",
        "",
        "| Bundle held | " + " | ".join(mixes) + " |",
        "|---" * (len(mixes) + 1) + "|",
    ]
    kinds = sorted({kind for mix in mixes.values() for kind in mix.index})
    for kind in kinds:
        lines.append(
            f"| {kind} | " + " | ".join(f"{mixes[name].get(kind, 0):.1%}" for name in mixes) + " |"
        )
    lines += [
        "",
        "This is the business-level version of the fidelity question: a copy whose customers "
        "sit on the wrong packages is useless for offer work whatever its column shapes say.",
        "",
        "## Verdict",
        "",
        _verdict(results, real_utility),
        "",
        "## Limits",
        "",
        "- A subset of features, a sample of customers and a short fit. Every one of those "
        "makes the copy worse than a serious attempt would be, and the report says so rather "
        "than presenting a floor as a ceiling.",
        "- Fidelity is not privacy. A copy that passes a detection test can still memorise a "
        "rare customer, and nothing here measures that. Before an operator shared anything, "
        "the question to answer is membership inference, not column shapes.",
        "- The copy is of the model's feature frame, not of the raw export. An operator "
        "sharing data would generate the raw 170-column monthly file, which is a bigger fit "
        "than this experiment.",
        "- Synthetic data never trains the production model here, and this experiment does not "
        "change a single T7 choice (decision 6).",
    ]
    return "\n".join(lines) + "\n"


def _impossible_note(results: dict) -> str:
    """What the impossible-value column means once the numbers are in."""
    if all(result["impossible"] == 0 for result in results.values()):
        return (
            "Neither generator produced one, because SDV keeps every column inside the range "
            "it learnt. That is a floor and not a sign of sense: the Almadar mix below is "
            "where the copies come apart, and it is made of columns that are all individually "
            "in range."
        )
    return (
        "A generator producing them is showing that it learnt a distribution and not the "
        "rules behind it, which is a thing to check before anyone is handed a copy."
    )


def _share(value: float, reference: float) -> str:
    return f"{value / reference:.0%}" if reference else "n/a"


def _verdict(results: dict, real_utility: dict) -> str:
    best = max(results, key=lambda name: results[name]["utility"]["pr_auc"])
    kept = results[best]["utility"]["pr_auc"] / real_utility["pr_auc"]
    detections = ", ".join(f"{name} {results[name]['detection']:.3f}" for name in results)
    rate_gap = ", ".join(
        f"{name} {results[name]['utility']['churn_rate']:.3f}"
        for name in results
        if abs(results[name]["utility"]["churn_rate"] - real_utility["churn_rate"]) > 0.01
    )
    verdict = (
        f"The best copy here is {best}, and a model trained on it keeps {kept:.0%} of the "
        f"PR-AUC that the same model reaches when it is trained on the real customers. "
        f"Detection: {detections}."
    )
    if rate_gap:
        verdict += (
            f" The churn rate itself did not survive the copy ({rate_gap} against "
            f"{real_utility['churn_rate']:.3f} real), and a model trained on the wrong base "
            "rate is wrong before it has learnt anything."
        )
    if kept < 0.6:
        return (
            verdict
            + " That is not a copy an operator could hand out in place of its data: the model "
            "it produces is materially worse, so the person receiving it would be building "
            "against a weaker signal without knowing by how much. The honest use of a copy "
            "this good is a demo, a schema and a pipeline test, which is real value and is "
            "how this module uses it."
        )
    return (
        verdict
        + " That is close enough to be interesting, and the next question is not utility but "
        "privacy: how much of a real customer does the copy carry? Nothing here measures that, "
        "and it has to be answered before any copy leaves an operator."
    )


if __name__ == "__main__":
    main()
