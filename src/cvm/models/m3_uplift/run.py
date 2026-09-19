"""Entry point: `python -m cvm.models.m3_uplift.run`  (phase 6)

Validates the method on Criteo's real randomised arms, then applies it to the
Almadar population and writes the expected-value table the decision engine
consumes.

THE ORDER IS NOT NEGOTIABLE HERE, more than anywhere else in the project:

    1. validate on CRITEO           real randomised arms, real Qini
    2. apply to the population      a PIPELINE TEST, not a performance claim
    3. join CLV from M2             uplift x CLV - cost
    4. assign a control holdout     so the campaign can be measured at all

Step 1 is the single strongest answer to "your data is generated, how do we
know any of this works?". Step 2 produces numbers that look like the same kind
of thing and are not: the population's treatment effect was injected by us, so
recovering it demonstrates that the pipeline is wired correctly and says
nothing whatever about whether uplift modelling works on Libyan prepaid
subscribers. The report has to keep those two claims apart, and so does this
file -- which is why the outputs are written to separate files with separate
names rather than one table with a source column.
"""

from __future__ import annotations

import argparse
import json
import logging

import joblib
import numpy as np
import pandas as pd

from cvm.config import load_conf, settings
from cvm.models.m3_uplift import evaluate, two_model

log = logging.getLogger(__name__)


def load_population() -> pd.DataFrame:
    """The latest snapshot per subscriber, with CLV joined from M2."""
    path = settings.feature_store_offline
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run `python -m cvm.features.run`")

    frame = pd.read_parquet(path)
    latest = (
        frame.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )

    clv_path = settings.processed_dir / "m2_clv.parquet"
    if not clv_path.exists():
        raise FileNotFoundError(
            f"{clv_path} does not exist. M3's expected value is uplift x CLV, so it "
            "needs M2; run `python -m cvm.models.m2_value.run` (phase 5)."
        )
    value = pd.read_parquet(clv_path)
    latest["clv_12m"] = value["clv_12m"].to_numpy()
    latest["retention_ceiling_lyd"] = value["retention_ceiling_lyd"].to_numpy()

    log.info("population: %d subscribers with CLV joined", len(latest))
    return latest


def simulate_campaign(population: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """A randomised treatment arm over the population, and its outcome.

    THIS IS A PIPELINE TEST AND THE FUNCTION IS NAMED SO NOBODY FORGETS. There
    is no observed campaign on this base, so one is simulated: a random half
    treated, and a treatment effect injected that is larger for subscribers the
    retention story says are movable. Recovering that effect shows the two-model
    pipeline is wired correctly end to end. It is not evidence that uplift
    modelling works on Libyan prepaid subscribers -- Criteo is the evidence, and
    this is the wiring diagram.

    The effect is deliberately made HETEROGENEOUS, including a negative tail.
    A uniform effect would be recovered by any method at all, including a
    constant, and would test nothing.
    """
    rng = np.random.default_rng(settings.random_seed)
    n = len(population)
    treated = pd.Series((rng.random(n) < 0.5).astype(int), index=population.index)

    # Baseline retention, and a heterogeneous effect keyed to behaviour the
    # retention story already claims matters.
    recency = population["days_since_last_topup"].fillna(30.0).to_numpy()
    leakage = population["leakage_score"].fillna(0.5).to_numpy()
    distress = population["chronic_distress"].fillna(0).to_numpy()

    baseline = 1.0 / (1.0 + np.exp(-(1.2 - 0.03 * recency)))
    effect = 0.06 * np.exp(-recency / 30.0) - 0.05 * (leakage > 0.8) - 0.04 * distress

    probability = np.clip(baseline + effect * treated.to_numpy(), 0.01, 0.99)
    outcome = pd.Series((rng.random(n) < probability).astype(int), index=population.index)

    log.info(
        "simulated campaign: %.1f%% treated, outcome %.4f treated vs %.4f control, "
        "injected effect mean %+.4f (%.1f%% negative by construction)",
        100 * treated.mean(),
        outcome[treated == 1].mean(),
        outcome[treated == 0].mean(),
        effect.mean(),
        100 * (effect < 0).mean(),
    )
    return treated, outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and apply the uplift model.")
    parser.add_argument("--skip-criteo", action="store_true", help="skip the real-data validation")
    args = parser.parse_args()

    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.ensure_dirs()
    reports, artefacts = settings.reports_dir, settings.models_dir

    # --- 1. The method, on real randomised arms -------------------------------
    criteo: dict = {}
    if not args.skip_criteo:
        criteo = evaluate.validate_on_criteo()
        (reports / "m3_criteo_validation.json").write_text(json.dumps(criteo, indent=2))

    # --- 2. The pipeline, on the generated population -------------------------
    population = load_population()
    treated, outcome = simulate_campaign(population)

    from sklearn.model_selection import train_test_split

    from cvm.models.m1_churn.gradient_boosting import prepare_matrix

    # M2's outputs are NOT features. `clv_12m` is what the uplift gets
    # multiplied by two steps later, so feeding it in as a predictor makes the
    # expected value partly a function of itself; `retention_ceiling_lyd` is
    # 0.15 x CLV and the collinearity guard was already dropping it.
    X, _ = prepare_matrix(population.drop(columns=["clv_12m", "retention_ceiling_lyd"]))

    # SPLIT, AND SCORE ON THE HELD-OUT PART. The first version trained and
    # scored on the same rows -- the exact mistake `validate_on_criteo` has a
    # docstring warning about, made two functions later. A two-model difference
    # memorises readily because both arms are free to overfit independently and
    # the difference of two overfits looks like signal: it reported uplift@30%
    # of +50.8 pp from an injected effect of at most +6 pp, and a Qini of
    # 0.2745 against Criteo's 0.0771. Numbers that good are the symptom.
    index_train, index_test = train_test_split(
        X.index, test_size=0.3, random_state=settings.random_seed, stratify=treated
    )
    treated_model, control_model = two_model.train_two_model(
        X.loc[index_train], outcome.loc[index_train], treated.loc[index_train]
    )

    held_out = X.loc[index_test]
    uplift_test = two_model.predict_uplift(treated_model, control_model, held_out)
    baseline_test = two_model.baseline_response(control_model, held_out)

    pipeline = {
        "rows_scored": len(index_test),
        "qini": evaluate.qini_coefficient(
            uplift_test, outcome.loc[index_test], treated.loc[index_test]
        ),
        "uplift_at_k": evaluate.uplift_at_k(
            uplift_test, outcome.loc[index_test], treated.loc[index_test]
        ),
        **{
            f"quadrant_{k}": v
            for k, v in evaluate.quadrant_counts(uplift_test, baseline_test).items()
        },
    }

    # The decision table covers everyone, because everyone needs a decision --
    # but the METRICS above are the held-out ones and only those are reported.
    uplift = two_model.predict_uplift(treated_model, control_model, X)
    baseline = two_model.baseline_response(control_model, X)
    quadrant = two_model.classify_quadrant(uplift, baseline)

    # --- 3. Expected value: the bridge into the decision engine ---------------
    incentive = float(load_conf("market")["base"]["blended_incentive_lyd"])

    expected = evaluate.expected_value_of_treatment(
        uplift.to_numpy(), population["clv_12m"].to_numpy(), incentive
    )
    # TWO BREAK-EVENS, and the gap between them matters. The proposal quotes
    # 5 / 480 = 1.04 pp, where 480 is twelve months at the headline 40 LYD
    # ARPU. M2's fitted median CLV is lower than that, so the break-even on the
    # MEDIAN subscriber is higher -- the offer has to work harder on a typical
    # subscriber than the headline figure implies. Both are reported.
    annual_arpu = float(load_conf("market")["base"]["monthly_arpu_lyd"]) * 12
    break_even_headline = evaluate.break_even_uplift(annual_arpu, incentive)
    break_even = evaluate.break_even_uplift(float(population["clv_12m"].median()), incentive)

    decisions = pd.DataFrame(
        {
            "subscriber_id_hashed": population["subscriber_id_hashed"],
            "uplift": uplift.to_numpy(),
            "baseline_response": baseline.to_numpy(),
            "quadrant": quadrant.to_numpy(),
            "clv_12m": population["clv_12m"].to_numpy(),
            "retention_ceiling_lyd": population["retention_ceiling_lyd"].to_numpy(),
            "expected_value_lyd": expected,
        }
    )

    # --- 4. The holdout that makes the campaign measurable --------------------
    decisions["is_control"] = two_model.assign_control_holdout(decisions).to_numpy()

    # Who would actually be treated: persuadable, positive expected value, and
    # not in the holdout. Every other row is excluded for a stated reason.
    eligible = (
        (decisions["quadrant"] == "persuadable")
        & (
            decisions["expected_value_lyd"]
            > load_conf("models/m3_uplift")["min_expected_value_lyd"]
        )
        & (~decisions["is_control"])
    )
    decisions["would_treat"] = eligible.astype("int8")
    decisions.to_parquet(settings.processed_dir / "m3_uplift.parquet")

    summary = {
        "criteo_validation": criteo,
        "pipeline_test_on_generated_population": pipeline,
        "break_even_uplift_pp": 100 * break_even,
        "break_even_uplift_pp_at_headline_arpu": 100 * break_even_headline,
        "blended_incentive_lyd": incentive,
        "median_clv_lyd": float(population["clv_12m"].median()),
        "would_treat": int(eligible.sum()),
        "would_treat_share": float(eligible.mean()),
        "expected_value_of_campaign_lyd": float(
            decisions.loc[eligible, "expected_value_lyd"].sum()
        ),
        "control_holdout": int(decisions["is_control"].sum()),
    }
    (reports / "m3_uplift.json").write_text(json.dumps(summary, indent=2))
    joblib.dump(
        {"treated": treated_model, "control": control_model}, artefacts / "m3_uplift.joblib"
    )

    # --- Report ---------------------------------------------------------------
    if criteo:
        print(f"\n{'CRITEO -- REAL RANDOMISED ARMS':<40}(this is the evidence)")
        print("-" * 66)
        print(f"{'rows scored':<40}{criteo['rows_scored']:>14,}")
        print(f"{'treated share':<40}{criteo['treated_share']:>13.1%}")
        print(f"{'naive lift':<40}{criteo['naive_lift_pp']:>+13.3f} pp")
        print(f"{'Qini coefficient':<40}{criteo['qini']:>+14.4f}")
        print(f"{'uplift@30%':<40}{criteo['uplift_at_k_pp']:>+13.3f} pp")

    print(f"\n{'GENERATED POPULATION':<40}(pipeline test, NOT a claim)")
    print("-" * 66)
    print(f"{'rows scored (held out)':<40}{pipeline['rows_scored']:>14,}")
    print(f"{'Qini coefficient':<40}{pipeline['qini']:>+14.4f}")
    print(f"{'uplift@30%':<40}{100 * pipeline['uplift_at_k']:>+13.3f} pp")

    print(f"\n{'QUADRANTS':<40}")
    print("-" * 66)
    # Over the HELD-OUT rows, which is what `pipeline` counted. Dividing by the
    # full population would have reported 22.1% persuadable where the measured
    # figure is 73.6% -- a third of the truth, from the wrong denominator.
    for name in two_model.QUADRANTS:
        count = pipeline[f"quadrant_{name}"]
        print(f"{name:<40}{count:>14,}{count / pipeline['rows_scored']:>9.1%}")

    print(f"\n{'DECISION':<40}")
    print("-" * 66)
    print(
        f"{'break-even at headline ARPU':<40}"
        f"{summary['break_even_uplift_pp_at_headline_arpu']:>13.4f} pp"
    )
    print(f"{'break-even at median fitted CLV':<40}{summary['break_even_uplift_pp']:>13.4f} pp")
    print(f"{'blended incentive':<40}{incentive:>13.2f} LYD")
    print(f"{'would treat':<40}{summary['would_treat']:>14,}{summary['would_treat_share']:>9.1%}")
    print(f"{'control holdout':<40}{summary['control_holdout']:>14,}")
    print(f"{'expected campaign value':<40}{summary['expected_value_of_campaign_lyd']:>13,.0f} LYD")

    print("\nNext: M4 -- see docs/ROADMAP.md#phase-7")


if __name__ == "__main__":
    main()
