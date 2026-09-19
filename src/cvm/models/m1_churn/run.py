"""Entry point: `python -m cvm.models.m1_churn.run`  (phase 4)

Trains the benchmark, calibrates every model, fits M1b, and writes the
artefacts the report and the API read.

THE ORDER IS THE POINT, again:

    1. read the offline store        (the label is in it, the artefacts are not)
    2. split temporally              train / validation / test
    3. train on TRAIN                every model, boosted and classical
    4. calibrate on VALIDATION       a slice no model trained on
    5. evaluate on TEST              which nothing has touched until now

Step 4 is why there are three splits rather than two. Isotonic regression
fitted on training predictions would learn the model's memorised scores and
map them near-perfectly, producing a calibration curve that looks flawless in
the report and is wrong on every subscriber it ever sees. Fitting it on
validation and evaluating on test keeps the two jobs on separate data.
"""

from __future__ import annotations

import argparse
import json
import logging

import joblib
import pandas as pd

from cvm.config import load_conf, settings
from cvm.features import splits
from cvm.models.m1_churn import benchmark, calibration, explain, gradient_boosting, survival

log = logging.getLogger(__name__)


def load_splits() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = settings.feature_store_offline
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Phase 4 reads what phase 3 writes; run "
            "`python -m cvm.features.run` first."
        )
    frame = pd.read_parquet(path)
    log.info("feature store: %d x %d from %s", *frame.shape, path)
    return splits.temporal_split(frame)


def train_all(train: pd.DataFrame, validation: pd.DataFrame, trials: int, timeout: int) -> dict:
    """Every model in the benchmark, fitted on train and stopped on validation."""
    X_train, y_train = gradient_boosting.prepare_matrix(train)
    X_val, y_val = gradient_boosting.prepare_matrix(validation)
    X_val = X_val.reindex(columns=X_train.columns, fill_value=0.0)

    models: dict[str, object] = {}

    if trials > 0:
        log.info("tuning lightgbm: up to %d trials, %ds wall", trials, timeout)
        best, _ = gradient_boosting.tune(X_train, y_train, n_trials=trials, timeout=timeout)
    else:
        best = {}
        log.info("tuning skipped (--trials 0); using the configured defaults")

    models["lightgbm"] = gradient_boosting.train(
        X_train, y_train, X_val, y_val, kind="lightgbm", **best
    )
    for kind in load_conf("models/m1_churn")["gradient_boosting"]["challengers"]:
        models[kind] = gradient_boosting.train(X_train, y_train, X_val, y_val, kind=kind)

    models.update(gradient_boosting.train_baselines(X_train, y_train))

    log.info("trained %d models: %s", len(models), sorted(models))
    return models


def calibrate_all(models: dict, validation: pd.DataFrame, columns) -> dict:
    """Isotonic map per model, fitted on the validation split."""
    X_val, y_val = gradient_boosting.prepare_matrix(validation)
    X_val = X_val.reindex(columns=columns, fill_value=0.0)
    return {name: calibration.calibrate(m, X_val, y_val) for name, m in models.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and benchmark M1.")
    parser.add_argument("--trials", type=int, default=25, help="Optuna trials; 0 skips tuning")
    parser.add_argument("--timeout", type=int, default=600, help="tuning wall-clock seconds")
    parser.add_argument("--skip-survival", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.ensure_dirs()
    reports, artefacts = settings.reports_dir, settings.models_dir

    train, validation, test = load_splits()
    models = train_all(train, validation, args.trials, args.timeout)

    X_train, _ = gradient_boosting.prepare_matrix(train)
    columns = list(X_train.columns)
    calibrated = calibrate_all(models, validation, columns)

    X_test, y_test = gradient_boosting.prepare_matrix(test)
    X_test = X_test.reindex(columns=columns, fill_value=0.0)

    # --- The benchmark, on calibrated scores --------------------------------
    table = benchmark.run_benchmark(calibrated, X_test, y_test)
    table.to_csv(reports / "m1_benchmark.csv", index=False)

    verdict = benchmark.architecture_verdict(table)
    (reports / "m1_verdict.md").write_text(verdict, encoding="utf-8")

    # --- Calibration: raw against calibrated, for the headline claim --------
    best_name = str(table.iloc[0]["model"])
    raw_probability = calibration._raw_probability(models[best_name], X_test)
    cal_probability = calibrated[best_name].predict_proba(X_test)[:, 1]

    calibration_metrics = {
        "model": best_name,
        "brier_raw": calibration.brier_score(y_test, raw_probability),
        "brier_calibrated": calibration.brier_score(y_test, cal_probability),
        "ece_raw": calibration.expected_calibration_error(y_test, raw_probability),
        "ece_calibrated": calibration.expected_calibration_error(y_test, cal_probability),
        "mean_predicted_raw": float(raw_probability.mean()),
        "mean_predicted_calibrated": float(cal_probability.mean()),
        "observed_rate": float(y_test.mean()),
        "n_test": len(y_test),
    }
    (reports / "m1_calibration.json").write_text(json.dumps(calibration_metrics, indent=2))
    calibration.calibration_curve_data(y_test, cal_probability).to_csv(
        reports / "m1_reliability.csv", index=False
    )

    # --- The honest-metrics disclosure --------------------------------------
    disclosure = benchmark.naive_vs_honest("uci_iranian")
    disclosure.to_csv(reports / "m1_naive_vs_honest.csv", index=False)

    # --- SHAP attribution ----------------------------------------------------
    explainer = explain.explainer_for(calibrated[best_name], X_test)
    sample = X_test.sample(min(2000, len(X_test)), random_state=settings.random_seed)
    attribution = explain.attribution_by_family(explainer, sample)
    attribution.to_csv(reports / "m1_shap_attribution.csv", index=False)

    # --- M1b -----------------------------------------------------------------
    boundaries: list[int] = []
    concordance: dict[str, float] = {}
    if not args.skip_survival:
        population = pd.read_parquet(settings.synthetic_dir / "population.parquet")
        frame = survival.build_survival_frame(
            pd.read_parquet(settings.feature_store_offline), population
        )
        _cox, concordance["cox"] = survival.fit_cox(frame)
        _, concordance["rsf"] = survival.fit_rsf(frame)
        boundaries = survival.hazard_inflection_points(frame)

        json.dump(
            {"concordance": concordance, "ladder_boundary_days": boundaries},
            (reports / "m1b_survival.json").open("w"),
            indent=2,
        )
        joblib.dump(_cox, artefacts / "m1b_cox.joblib")

    # THE SHAP BACKGROUND TRAVELS WITH THE MODEL. An attribution is measured
    # against a reference population -- "tops up less than a typical
    # subscriber" -- and serving cannot reconstruct that from a request, which
    # is often one row. Explaining a one-row batch against itself returns
    # exactly zero for every feature, which is what both serving callers did.
    # 500 rows is enough for a stable mean over 53 columns and costs ~200 KB.
    joblib.dump(
        {
            "model": calibrated[best_name],
            "columns": columns,
            "name": best_name,
            "background": X_train.reindex(columns=columns, fill_value=0.0).sample(
                min(500, len(X_train)), random_state=settings.random_seed
            ),
        },
        artefacts / "m1_churn.joblib",
    )

    # PER-SUBSCRIBER SCORES FOR THE WHOLE BASE. The cohort query and the
    # Executive Overview both need "who is at risk" across 100,000 subscribers,
    # and re-scoring that on every dashboard filter is a screen nobody uses
    # twice. Written once here, where the model already exists.
    everyone = pd.read_parquet(settings.feature_store_offline)
    latest = (
        everyone.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )
    X_all, _ = gradient_boosting.prepare_matrix(latest)
    X_all = X_all.reindex(columns=columns, fill_value=0.0)
    probability = calibrated[best_name].predict_proba(X_all)[:, 1]

    pd.DataFrame(
        {
            "subscriber_id_hashed": latest["subscriber_id_hashed"].astype(str),
            "churn_probability": probability,
            # 1 is the HIGHEST risk, matching the API contract.
            "risk_decile": pd.Series(probability)
            .rank(pct=True, ascending=False)
            .mul(10)
            .apply(lambda v: int(min(10, max(1, -(-v // 1))))),
        }
    ).to_parquet(settings.processed_dir / "m1_scores.parquet", index=False)
    log.info(
        "scores: %d subscribers written, mean %.4f, top-decile mean %.4f",
        len(latest),
        probability.mean(),
        probability[probability >= pd.Series(probability).quantile(0.9)].mean(),
    )

    # --- Report --------------------------------------------------------------
    print(f"\n{table.to_string(index=False, float_format=lambda v: f'{v:.4f}')}")
    print(f"\n{'CALIBRATION':<22}{'raw':>12}{'calibrated':>14}")
    print("-" * 48)
    for key in ("brier", "ece"):
        print(
            f"{key.upper():<22}{calibration_metrics[f'{key}_raw']:>12.5f}"
            f"{calibration_metrics[f'{key}_calibrated']:>14.5f}"
        )
    print(
        f"{'mean predicted':<22}{calibration_metrics['mean_predicted_raw']:>12.4f}"
        f"{calibration_metrics['mean_predicted_calibrated']:>14.4f}"
        f"   (observed {calibration_metrics['observed_rate']:.4f})"
    )

    print(f"\n{'NAIVE VS HONEST':<22}")
    print(disclosure.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    if concordance:
        print(f"\n{'SURVIVAL':<22}{'concordance':>12}")
        print("-" * 34)
        for name, value in concordance.items():
            print(f"{name:<22}{value:>12.4f}")
        print(f"{'ladder boundaries':<22}{boundaries!s:>12}")

    print(f"\n{'VERDICT':<22}\n{verdict}\n")
    print("Next: M2 -- see docs/ROADMAP.md#phase-5")


if __name__ == "__main__":
    main()
