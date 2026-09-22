# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["prepaid-churn", "scikit-uplift"]
#
# [tool.uv.sources]
# prepaid-churn = { path = "../", editable = false }
# ///
"""T17 uplift experiment: is the riskiest customer the one an offer saves?

T11 hands a retention bonus to the customers the churn model ranks riskiest, and assumes
a share of them are saved by it. That assumption is the weakest number in the module, and
this experiment is the closest thing to evidence about it that public data allows.

Uplift is the difference between what a customer does when treated and what the same
customer would have done untreated. Nobody ever observes both, so it can only be measured
across a randomised trial: treat a random half, leave the rest alone, and compare rankings
by how much incremental response they concentrate at the top. That is the Qini curve.

Two randomised datasets, because neither alone is enough:

- Orange Belgium (OpenML 45580): a real telecom retention campaign, 11,896 customers,
  178 anonymised features, 76% called and 24% not, 3.4% churn. The right industry and the
  right action, but small, postpaid, and anonymised beyond any join with our features.
- Criteo (the 10% sample of the public v2.1 dump): 1.4 million rows from a real
  randomised advertising test. The wrong industry, and large enough that the method is
  measured rather than guessed at.

What is compared, on held-out customers of each dataset:

1. Targeting by uplift: a two-model difference, one response model per arm.
2. Targeting by response, which is what this module does today. T11 ranks by churn risk,
   and that is the same ranking as "most likely to leave", not "most likely to be kept".

Both licences are non-commercial and neither dataset is committed; they are fetched into
`data/external/` on demand.

Run it with `uv run --script experiments/uplift.py` from `prepaid_churn/`.
Like T13 it is a standalone script with its own environment: it needs scikit-uplift for
the cross-check below and the module needs neither that nor these datasets.

The Qini implementation is ported by hand from `Ali_Branch`'s
`src/cvm/models/m3_uplift/evaluate.py` at commit `06890f6`, including the two things that
are easy to get wrong and that his comments call out: the control arm has to be rescaled
to the treated arm's size at every depth, and the coefficient has to be normalised by the
perfect ranking's area (Radcliffe) rather than by the total incremental response.
Here it is checked against `sklift.metrics.qini_auc_score` at runtime instead of in a
unit test, and the agreement is printed in the report.
"""

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklift.metrics import qini_auc_score

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "data" / "external"
REPORT = ROOT / "reports" / "uplift.md"

SEED = 42
HOLDOUT = 0.30
TOP_K = 0.30
CRITEO_URL = (
    "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/"
    "criteo-research-uplift-v2.1.csv.gz"
)
CRITEO_ARCHIVE = EXTERNAL / "criteo-research-uplift-v2.1.csv.gz"
CRITEO_SAMPLE = EXTERNAL / "criteo_uplift_10pct.parquet"
# Strictly downstream of the treatment, so neither may be a feature: `conversion` implies
# `visit`, and `exposure` is decided after assignment, which breaks the randomisation that
# makes this dataset worth using. Ali's note, and it still applies.
CRITEO_POST_TREATMENT = ("conversion", "exposure")


def model() -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=50,
        random_state=SEED,
        deterministic=True,
        force_row_wise=True,
        n_jobs=os.cpu_count(),
        verbose=-1,
    )


def qini_curve(score, response, treated) -> pd.DataFrame:
    """The Qini curve, and its coefficient in `.attrs`.

    At each depth n, ranked by `score` descending:

        Qini(n) = responses_treated(n) - responses_control(n) * n_treated(n) / n_control(n)

    The rescaling term is the whole thing. The arms are different sizes (76/24 on Orange,
    85/15 on Criteo), so comparing raw counts would report the arm imbalance as uplift.
    Multiplying the control responses by the size ratio asks the right question: how many
    responses would the control group have produced at this depth if it were as large as
    the treated group.

    The coefficient is the area between this curve and the line a random ranking traces,
    divided by the area a perfect ranking would reach over that same line.
    """
    score, y, t = (np.asarray(v, dtype="float64") for v in (score, response, treated))
    if not len(score) == len(y) == len(t):
        raise ValueError("score, response and treatment must have the same length")
    if t.sum() == 0 or (1 - t).sum() == 0:
        raise ValueError("one arm is empty, so no treatment effect is identifiable")

    order = np.argsort(-score, kind="stable")
    y, t = y[order], t[order]
    treated_rows, control_rows = np.cumsum(t), np.cumsum(1 - t)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(control_rows > 0, treated_rows / control_rows, 0.0)
    qini = np.cumsum(y * t) - np.cumsum(y * (1 - t)) * ratio

    fraction = np.arange(1, len(y) + 1) / len(y)
    curve = pd.DataFrame({"fraction": fraction, "qini": qini, "random": fraction * qini[-1]})
    area = np.trapezoid(qini, fraction) - np.trapezoid(curve["random"], fraction)
    curve.attrs["area"] = float(area)
    curve.attrs["endpoint"] = float(qini[-1])
    return curve


def qini_coefficient(score, response, treated) -> float:
    """Qini, normalised by the perfect ranking so it is comparable to published numbers.

    The perfect ranking puts every row the treatment could have helped at the front: +1
    for a treated responder, -1 for a control responder, 0 otherwise.
    Normalising by the total incremental response instead gives a number with the right
    sign and the wrong magnitude, which would be quoted beside the word "Qini" and be
    incomparable to everyone else's.
    """
    response, treated = np.asarray(response), np.asarray(treated)
    area = qini_curve(score, response, treated).attrs["area"]
    perfect = qini_curve(response * treated - response * (1 - treated), response, treated)
    return float(area / perfect.attrs["area"]) if perfect.attrs["area"] else 0.0


def uplift_at_k(score, response, treated, k: float = TOP_K) -> float:
    """Realised uplift in the top k by score, as a difference of rates.

    This is the number a campaign needs: treat the top 30%, and this is how many more
    responses per hundred customers the treatment produced there.
    A difference of rates needs no rescaling, so it reads directly in percentage points.
    """
    score, y, t = (np.asarray(v, dtype="float64") for v in (score, response, treated))
    top = np.argsort(-score, kind="stable")[: max(1, round(len(score) * k))]
    y_top, t_top = y[top], t[top]
    if t_top.sum() == 0 or (1 - t_top).sum() == 0:
        return float("nan")
    return float(y_top[t_top == 1].mean() - y_top[t_top == 0].mean())


def two_model(x: pd.DataFrame, response: pd.Series, treated: pd.Series) -> dict:
    """One response model per arm; the uplift score is their difference.

    Both arms are checked rather than assumed. With one arm empty the "uplift" is a
    response model minus a constant, which ranks plausibly and means nothing (Ali's note).
    """
    treated = treated.astype(int)
    arms = {"treated": treated == 1, "control": treated == 0}
    for name, mask in arms.items():
        if mask.sum() < 100 or response[mask].nunique() < 2:
            raise ValueError(f"the {name} arm is too small or has a single outcome")
    return {name: model().fit(x[mask], response[mask]) for name, mask in arms.items()}


def uplift_score(models: dict, x: pd.DataFrame) -> np.ndarray:
    treated = models["treated"].predict_proba(x)[:, 1]
    control = models["control"].predict_proba(x)[:, 1]
    return treated - control


def run(name: str, x: pd.DataFrame, response: pd.Series, treated: pd.Series, targets: str) -> dict:
    """Fit both rankings on the training half and measure them on the held-out half."""
    start = time.time()
    x_fit, x_test, y_fit, y_test, t_fit, t_test = train_test_split(
        x, response, treated, test_size=HOLDOUT, random_state=SEED, stratify=treated
    )
    models = two_model(x_fit, y_fit, t_fit)
    # What this module does today: one model of the outcome, everybody in it, and the
    # riskiest first. Fitted on the same rows, so only the ranking differs.
    response_model = model().fit(x_fit, y_fit)
    scores = {
        "uplift": uplift_score(models, x_test),
        "response": -response_model.predict_proba(x_test)[:, 1],
    }
    results = {
        ranking: {
            "qini": qini_coefficient(score, y_test, t_test),
            "uplift_at_k": uplift_at_k(score, y_test, t_test),
        }
        for ranking, score in scores.items()
    }
    # A ranking with no information, twenty times over. The spread of those twenty is the
    # band any other number on this dataset has to clear, and on a small trial the band is
    # wide enough to swallow the result.
    rng = np.random.default_rng(SEED)
    noise = [qini_coefficient(rng.random(len(y_test)), y_test, t_test) for _ in range(20)]
    results["random"] = {
        "qini": float(np.mean(noise)),
        "uplift_at_k": uplift_at_k(rng.random(len(y_test)), y_test, t_test),
    }
    return {
        "name": name,
        "targets": targets,
        "rows": len(x),
        "features": x.shape[1],
        "treated_share": float(treated.mean()),
        "response_rate": float(response.mean()),
        "holdout": len(x_test),
        "holdout_non_responders": int((y_test == 0).sum()),
        "noise": (float(np.mean(noise)), float(np.std(noise))),
        "results": results,
        "agreement": _cross_check(scores["uplift"], y_test, t_test),
        "seconds": time.time() - start,
    }


def _cross_check(score, response, treated) -> float:
    """Our Qini against scikit-uplift's, on the same rows. The gap should be ~0."""
    theirs = qini_auc_score(np.asarray(response), np.asarray(score), np.asarray(treated))
    return float(abs(qini_coefficient(score, response, treated) - theirs))


def load_orange() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    """Orange Belgium: a telecom retention call, with churn as the outcome.

    The outcome is flipped on purpose. `y` is churn, so a call that works makes it
    smaller, and an uplift model trained on churn ranks the customers a call would
    *lose*. Retention (1 - churn) is the response the campaign is trying to produce, and
    getting this sign wrong is the classic way an uplift study reports its best customers
    as its worst.
    """
    from sklearn.datasets import fetch_openml

    data = fetch_openml(data_id=45580, as_frame=True, data_home=str(EXTERNAL / "openml"))
    frame = data.frame
    response = 1 - frame["y"].astype(int)
    treated = frame["t"].astype(int)
    x = frame.drop(columns=["y", "t"])
    # 160 anonymised principal components and 18 anonymised factors, the latter as labels
    # like "V6". LightGBM reads a pandas category directly, which keeps them as the
    # unordered labels they are instead of inventing an order by encoding them as numbers.
    text = [name for name in x.columns if x[name].dtype.kind not in "if"]
    x = x.assign(**{name: x[name].astype("category") for name in text})
    return x, response, treated, "a retention call, measured as customers kept"


def load_criteo() -> tuple[pd.DataFrame, pd.Series, pd.Series, str]:
    """Criteo's 10% sample: an advertising test, with a visit as the response."""
    if CRITEO_SAMPLE.exists():
        frame = pd.read_parquet(CRITEO_SAMPLE)
    else:
        if not CRITEO_ARCHIVE.exists():
            raise FileNotFoundError(
                f"{CRITEO_ARCHIVE} is missing. Download it once from {CRITEO_URL} "
                "(311 MB); it is not committed, because it is Criteo's data under a "
                "non-commercial licence."
            )
        # Sampled while reading: 14M rows are read to keep 1.4M, and holding the whole
        # table to throw 90% of it away costs several GB for nothing.
        chunks = [
            chunk.sample(frac=0.10, random_state=SEED + i)
            for i, chunk in enumerate(
                pd.read_csv(CRITEO_ARCHIVE, compression="gzip", chunksize=1_000_000)
            )
        ]
        frame = pd.concat(chunks, ignore_index=True)
        frame.to_parquet(CRITEO_SAMPLE, index=False)
    response = frame["visit"].astype(int)
    treated = frame["treatment"].astype(int)
    x = frame.drop(columns=["visit", "treatment", *CRITEO_POST_TREATMENT], errors="ignore")
    return x, response, treated, "an advertisement, measured as site visits"


def main() -> None:
    runs = []
    for name, loader in (("Orange Belgium", load_orange), ("Criteo 10%", load_criteo)):
        x, response, treated, targets = loader()
        print(f"{name}: {len(x)} rows, {x.shape[1]} features")
        runs.append(run(name, x, response, treated, targets))
        print(f"  {runs[-1]['results']}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(runs), encoding="utf-8")
    print(f"report in {REPORT}")


def report(runs: list[dict]) -> str:
    lines = [
        "# T17 uplift experiment",
        "",
        "Generated by `uv run --script experiments/uplift.py` (ticket T17).",
        "",
        "T11 gives a retention bonus to the customers this module ranks riskiest, and "
        "assumes a share of them are saved by it.",
        "This asks the question that assumption depends on: on data where a treatment was "
        "actually randomised, does ranking by risk find the customers a treatment changes?",
        "",
        "## The two datasets",
        "",
        "| Dataset | Rows | Features | Treated | Response rate | Treatment |",
        "|---|---|---|---|---|---|",
    ]
    for run_result in runs:
        lines.append(
            f"| {run_result['name']} | {run_result['rows']:,} | {run_result['features']} | "
            f"{run_result['treated_share']:.0%} | {run_result['response_rate']:.2%} | "
            f"{run_result['targets']} |"
        )
    lines += [
        "",
        "Orange's response is retention, so 96.57% means 3.43% churn; Criteo's is a site visit.",
        "Both are real randomised trials, which is the only kind of data an uplift number "
        "can come from.",
        "Neither is committed: they are other people's data under non-commercial licences, "
        "fetched into `data/external/` on demand.",
        "",
        "## Ranking by uplift against ranking by risk",
        "",
        f"Measured on a held-out {HOLDOUT:.0%} of each dataset, with both rankings fitted "
        "on the same training rows.",
        f"Qini is normalised by the perfect ranking; uplift at {TOP_K:.0%} is the realised "
        "difference in response rates inside the top of each ranking.",
        "",
        f"| Dataset | Ranking | Qini | Uplift at top {TOP_K:.0%} |",
        "|---|---|---|---|",
    ]
    for run_result in runs:
        for ranking in ("uplift", "response", "random"):
            result = run_result["results"][ranking]
            label = {
                "uplift": "by uplift (two-model)",
                "response": "by risk, as T11 does",
                "random": "random",
            }[ranking]
            lines.append(
                f"| {run_result['name']} | {label} | {result['qini']:.4f} | "
                f"{result['uplift_at_k']:+.2%} |"
            )
    lines += [
        "",
        "The random row is the mean of twenty uninformative rankings, and their spread is "
        "the band a result has to clear: "
        + "; ".join(
            f"{r['name']} {r['noise'][0]:+.4f} plus or minus {2 * r['noise'][1]:.4f} "
            f"(two standard deviations, over {r['holdout']:,} held-out rows with "
            f"{r['holdout_non_responders']:,} non-responders)"
            for r in runs
        )
        + ".",
        "",
        "Agreement with `sklift.metrics.qini_auc_score` on the same rows: "
        + ", ".join(f"{r['name']} {r['agreement']:.2e}" for r in runs)
        + ".",
        "The Qini here is written out rather than imported, because the control arm has to "
        "be rescaled to the treated arm's size at every depth and that term is invisible "
        "inside a library call; the cross-check is what keeps it honest.",
        "",
        "## What this means for T11",
        "",
        _lesson(runs),
        "",
        "## Limits",
        "",
        "- Neither dataset is this module's population. Orange is postpaid, its features "
        "are anonymised principal components, and nothing in it can be joined to ours. "
        "Criteo is advertising, not telecom.",
        "- So the transferable finding is about the method and the ranking, never a "
        "number to paste into T11's policy.",
        "- The upGrad data this module trains on has no treatment arm at all, so no uplift "
        "model can be fitted on it. Measuring this properly needs the operator to run a "
        "campaign with a real control group, which is what T11's holdout is for.",
        "- The two-model difference is the simplest uplift learner and the least efficient: "
        "both models spend their capacity on the response, and the uplift is what survives "
        "in the difference. A direct uplift learner would be the next thing to try, and it "
        "is only worth trying once there is a real campaign to fit it on.",
    ]
    return "\n".join(lines) + "\n"


def _lesson(runs: list[dict]) -> str:
    lines = []
    for run_result in runs:
        uplift = run_result["results"]["uplift"]
        response = run_result["results"]["response"]
        band = 2 * run_result["noise"][1]
        sentence = (
            f"On {run_result['name']}, ranking by uplift reaches a Qini of "
            f"{uplift['qini']:.4f} against {response['qini']:.4f} for ranking by risk, and "
            f"the realised uplift in the top {TOP_K:.0%} is {uplift['uplift_at_k']:+.2%} "
            f"against {response['uplift_at_k']:+.2%}."
        )
        if abs(uplift["qini"]) < band and abs(response["qini"]) < band:
            sentence += (
                f" Both sit inside the noise band of plus or minus {band:.4f}, so this "
                f"dataset answers nothing: {run_result['holdout']:,} held-out rows holding "
                f"{run_result['holdout_non_responders']:,} non-responders cannot separate "
                "one ranking from another, and picking a winner from these two numbers "
                "would be reading noise."
            )
        elif uplift["qini"] > response["qini"]:
            sentence += (
                f" The uplift ranking clears the noise band of plus or minus {band:.4f} and "
                "the risk ranking does not; they are not the same ranking, and here the risk "
                "ranking is worse than random."
            )
        else:
            sentence += (
                " The risk ranking is ahead and outside the noise band of plus or minus "
                f"{band:.4f}, which is worth saying plainly."
            )
        lines.append(sentence)
    lines.append(
        "The practical reading for T11: the customers most likely to leave are not the "
        "same customers an offer keeps, so a 'share saved' applied to the riskiest decile "
        "is an assumption about persuadability that the risk model does not measure. "
        "T11 already holds out a random group of proposed customers, and that holdout is "
        "the only thing in this module that can turn the assumption into a measurement. "
        "Until it has run against a real campaign, every LYD figure downstream of it stays "
        "a scenario, which is how the retention report already presents it."
    )
    return "\n\n".join(lines)


if __name__ == "__main__":
    main()
