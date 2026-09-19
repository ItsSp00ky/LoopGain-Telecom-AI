"""Entry point: `python -m cvm.models.m2_value.run`  (phase 5)

Validates BG/NBD on real purchases, fits CLV on the recharge base, discovers
segments three ways, and writes what the dashboard and the pricing guardrails
read.

THE ORDER IS THE POINT, once more:

    1. validate the TECHNIQUE on Online Retail II   real purchases, real holdout
    2. fit CLV on the recharge base                 reconstructed summary
    3. derive the retention budget ceiling          what M3 is allowed to spend
    4. discover segments three ways                 k-means, hierarchical, PCA
    5. compare the clusters against the rules       the disagreement is the insight

Step 1 comes first for the same reason Criteo does in uplift. Every CLV number
downstream is computed on generated recharges, so it cannot validate itself --
a good fit there would only mean the generator and the model agree with each
other. Online Retail II has real repeat purchases with real timestamps, so
fitting one period and scoring the next measures whether the technique works at
all. If step 1 fails there is no point running steps 2 to 5.
"""

from __future__ import annotations

import argparse
import json
import logging

import joblib
import numpy as np
import pandas as pd

from cvm.config import settings
from cvm.models.m2_value import clv, segmentation

log = logging.getLogger(__name__)


def load_base() -> pd.DataFrame:
    """The latest snapshot per subscriber -- CLV is a present-tense question."""
    path = settings.feature_store_offline
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Phase 5 reads what phase 3 writes; run "
            "`python -m cvm.features.run` first."
        )
    frame = pd.read_parquet(path)
    latest = (
        frame.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )
    log.info("base: %d subscribers from %d rows", len(latest), len(frame))
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit CLV and discover segments.")
    parser.add_argument(
        "--skip-validation", action="store_true", help="skip the Online Retail check"
    )
    parser.add_argument("--skip-hierarchical", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.ensure_dirs()
    reports, artefacts = settings.reports_dir, settings.models_dir

    # --- 1. The technique, on real purchases ---------------------------------
    validation: dict = {}
    if not args.skip_validation:
        validation = clv.validate_on_real_purchases()

    # --- 2. CLV on the recharge base -----------------------------------------
    base = load_base()
    summary = clv.summary_from_population(base)

    # Fit on complete cases, score everyone. A subscriber with no ceiling has
    # no constraint, which is worse than an estimated one -- but the parameters
    # should not be shaped by the imputation's own median.
    fit_on = clv.complete_cases(summary)
    bgf = clv.fit_bg_nbd(fit_on)
    ggf = clv.fit_gamma_gamma(fit_on)
    predicted = clv.predict_clv(bgf, ggf, summary)

    # --- 3. The ceiling the pricing engine obeys -----------------------------
    ceiling = clv.retention_budget_ceiling(predicted)

    value = pd.DataFrame(
        {"clv_12m": predicted, "retention_ceiling_lyd": ceiling, "segment": base["segment"].values}
    )
    value.to_parquet(settings.processed_dir / "m2_clv.parquet")

    ibm = _ibm_cltv()
    shape = clv.benchmark_against_ibm(predicted, ibm) if ibm is not None else {}

    # --- 4. Segments, three ways ---------------------------------------------
    kmeans, k_scores, by_elbow = segmentation.fit_kmeans(base)
    labels = pd.Series(kmeans.predict(segmentation.design(base)), index=base.index, name="cluster")
    k_scores.to_csv(reports / "m2_kmeans_scores.csv", index=False)

    _, projected, loadings = segmentation.fit_pca(base)
    loadings.to_csv(reports / "m2_pca_loadings.csv")

    natural = None
    if not args.skip_hierarchical:
        matrix, _ = segmentation.fit_hierarchical(base)
        dendrogram = segmentation.dendrogram_data(matrix)
        dendrogram.to_csv(reports / "m2_dendrogram.csv", index=False)
        natural = int(dendrogram.attrs["natural_clusters"])

    # --- 5. Rules against clusters -------------------------------------------
    crosstab = segmentation.compare_rules_vs_clusters(base["segment"], labels)
    crosstab.to_csv(reports / "m2_rules_vs_clusters.csv")

    # And again at MATCHED granularity. Adjusted Rand between 3 clusters and 8
    # segments is bounded below 1 by arithmetic rather than by disagreement, so
    # the honest comparison forces k to the number of business segments.
    n_segments = int(base["segment"].nunique())
    from sklearn.cluster import KMeans

    matched_labels = pd.Series(
        KMeans(n_clusters=n_segments, n_init=20, random_state=settings.random_seed).fit_predict(
            segmentation.design(base)
        ),
        index=base.index,
    )
    matched = segmentation.compare_rules_vs_clusters(base["segment"], matched_labels)
    matched.to_csv(reports / "m2_rules_vs_clusters_matched_k.csv")

    result = {
        "k_chosen": int(kmeans.n_clusters),
        "k_by_elbow": by_elbow,
        "silhouette": float(k_scores.loc[k_scores["k"] == kmeans.n_clusters, "silhouette"].iloc[0]),
        "disagreement_share": crosstab.attrs["disagreement_share"],
        "adjusted_rand": crosstab.attrs["adjusted_rand"],
        "normalised_mutual_info": crosstab.attrs["normalised_mutual_info"],
        "matched_k": n_segments,
        "matched_k_disagreement_share": matched.attrs["disagreement_share"],
        "matched_k_adjusted_rand": matched.attrs["adjusted_rand"],
        "matched_k_normalised_mutual_info": matched.attrs["normalised_mutual_info"],
        "cluster_purity": crosstab.attrs["cluster_purity"],
        "pca_explained_variance": float(
            (projected.std() ** 2 / segmentation.design(base).var().sum()).sum()
        ),
        "natural_clusters_from_dendrogram": natural,
        "declared_business_segments": int(base["segment"].nunique()),
    }
    (reports / "m2_segmentation.json").write_text(json.dumps(result, indent=2))

    clv_metrics = {
        "validation_on_real_purchases": validation,
        "ibm_quantile_shape": shape,
        "median_clv_lyd": float(predicted.median()),
        "mean_clv_lyd": float(predicted.mean()),
        "p90_clv_lyd": float(predicted.quantile(0.9)),
        "median_ceiling_lyd": float(ceiling.median()),
        "subscribers": len(predicted),
        "frequency_monetary_correlation": float(
            getattr(ggf, "frequency_monetary_correlation_", np.nan)
        ),
    }
    (reports / "m2_clv.json").write_text(json.dumps(clv_metrics, indent=2))

    # The lifetimes fitters go through their OWN serialiser. `fit()` leaves a
    # lambda on the instance, so joblib raises PicklingError on a model that is
    # otherwise perfectly good -- and it raises at the END of a fifteen-minute
    # run, after every number has been computed. `save_generate_data_method`
    # off because that is the attribute holding the lambda.
    bgf.save_model(str(artefacts / "m2_bg_nbd.pkl"), save_generate_data_method=False)
    ggf.save_model(str(artefacts / "m2_gamma_gamma.pkl"), save_generate_data_method=False)
    joblib.dump(kmeans, artefacts / "m2_kmeans.joblib")

    # --- Report ---------------------------------------------------------------
    if validation:
        print(f"\n{'BG/NBD ON REAL PURCHASES':<34}(Online Retail II, held out)")
        print("-" * 62)
        print(f"{'customers':<34}{validation['customers']:>12,}")
        print(f"{'holdout window':<34}{validation['holdout_days']:>12.0f} days")
        print(f"{'MAE':<34}{validation['mae']:>12.3f}")
        print(f"{'mean actual transactions':<34}{validation['mean_actual']:>12.3f}")
        print(f"{'Spearman':<34}{validation['spearman']:>12.3f}")

    print(f"\n{'CLV (12 months, discounted)':<34}")
    print("-" * 62)
    for label, key in (
        ("median", "median_clv_lyd"),
        ("mean", "mean_clv_lyd"),
        ("p90", "p90_clv_lyd"),
        ("median retention ceiling", "median_ceiling_lyd"),
    ):
        print(f"{label:<34}{clv_metrics[key]:>12.2f} LYD")

    print(f"\n{'SEGMENTS':<34}")
    print("-" * 62)
    print(f"{'k chosen (silhouette)':<34}{result['k_chosen']:>12}")
    print(f"{'k by elbow':<34}{result['k_by_elbow']:>12}")
    print(f"{'silhouette':<34}{result['silhouette']:>12.4f}")
    print(f"{'PCA variance in 2 components':<34}{result['pca_explained_variance']:>11.1%}")
    if natural is not None:
        print(f"{'dendrogram natural clusters':<34}{natural:>12}")
    print(f"{'rule/cluster disagreement':<34}{result['disagreement_share']:>11.1%}")
    print(f"{'adjusted Rand':<34}{result['adjusted_rand']:>12.3f}")
    print(f"{f'  ...at matched k={n_segments}':<34}{result['matched_k_adjusted_rand']:>12.3f}")

    print("\nNext: M3 -- see docs/ROADMAP.md#phase-6")


def _ibm_cltv() -> pd.Series | None:
    """The IBM Telco CLTV column, if the interim file is there."""
    path = settings.interim_dir / "ibm_telco.parquet"
    if not path.exists():
        log.warning("ibm_telco.parquet absent; skipping the quantile-shape benchmark")
        return None
    frame = pd.read_parquet(path)
    for name in ("CLTV", "cltv", "Customer Lifetime Value"):
        if name in frame.columns:
            return frame[name].astype("float64")
    log.warning("no CLTV column in ibm_telco.parquet (%s)", sorted(frame.columns)[:8])
    return None


if __name__ == "__main__":
    main()
