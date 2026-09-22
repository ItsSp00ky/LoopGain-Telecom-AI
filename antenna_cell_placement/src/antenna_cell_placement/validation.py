"""
Validation for the H3 expansion need score.

1. Known-site recovery: hide a random share of real existing sites, recompute the
   network-gap features without them, and check whether the score ranks the hexes
   that contained the hidden sites near the top. A population-only baseline is
   reported alongside so the contribution of the network-gap component is visible.
2. Weight sensitivity: perturb each weight and measure how stable the ranking is.
"""

import json
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from antenna_cell_placement.config import (
    DEFAULT_PILOT_CITY,
    H3_RESOLUTION,
    H3_FEATURE_TABLE_PARQUET_TEMPLATE,
    H3_VALIDATION_JSON_TEMPLATE,
    CLEANED_PHYSICAL_SITES_CSV,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
)
from antenna_cell_placement.expansion_score import (
    DEFAULT_WEIGHTS,
    compute_expansion_need_score,
    mask_unscorable_hexes,
    active_weights,
)
from antenna_cell_placement.h3_grid import assign_points_to_h3


def load_sites_utm(sites_csv=CLEANED_PHYSICAL_SITES_CSV, resolution: int = H3_RESOLUTION) -> pd.DataFrame:
    """Load existing physical sites with projected coordinates and their H3 cell."""
    import geopandas as gpd
    from shapely.geometry import Point

    df = pd.read_csv(sites_csv)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(lon, lat) for lon, lat in zip(df["canonical_longitude"], df["canonical_latitude"])],
        crs=CRS_WGS84,
    ).to_crs(CRS_PROJECTED_LIBYA)
    df = df.copy()
    df["utm_x"] = gdf.geometry.x.values
    df["utm_y"] = gdf.geometry.y.values
    df["h3_index"] = assign_points_to_h3(df["canonical_longitude"].values, df["canonical_latitude"].values, resolution)
    return df


def recompute_network_features(df_hex: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    """Recompute the network-gap inputs of each hex from a given set of existing sites."""
    df = df_hex.copy()
    hex_xy = df[["utm_x", "utm_y"]].values
    if sites.empty:
        df["dist_to_nearest_site_m"] = 50000.0
        df["site_density_3km"] = 0
        df["existing_sites_site_count"] = 0
        return df

    tree = cKDTree(sites[["utm_x", "utm_y"]].values)
    dists, _ = tree.query(hex_xy, k=1)
    df["dist_to_nearest_site_m"] = np.round(dists, 1)
    df["site_density_3km"] = [len(n) for n in tree.query_ball_point(hex_xy, 3000.0)]
    counts = sites.groupby("h3_index").size()
    df["existing_sites_site_count"] = df["h3_index"].map(counts).fillna(0).astype(int)
    return df


def _recall_at_fraction(scores: np.ndarray, labels: np.ndarray, fraction: float) -> float:
    k = max(1, int(round(len(scores) * fraction)))
    top_idx = np.argsort(-scores)[:k]
    positives = labels.sum()
    return float(labels[top_idx].sum() / positives) if positives > 0 else float("nan")


def known_site_recovery(
    df_hex: pd.DataFrame,
    sites: pd.DataFrame,
    n_folds: int = 5,
    hide_fraction: float = 0.2,
    random_state: int = 42,
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
) -> Dict[str, object]:
    """
    Repeatedly hide a share of the sites inside the grid and measure how well the
    expansion score (and a population-only baseline) ranks their hexes.
    """
    rng = np.random.default_rng(random_state)
    grid_cells = set(df_hex["h3_index"])
    in_grid = sites[sites["h3_index"].isin(grid_cells)].reset_index(drop=True)
    outside = sites[~sites["h3_index"].isin(grid_cells)]

    folds: List[Dict[str, float]] = []
    for fold in range(n_folds):
        hidden_mask = rng.random(len(in_grid)) < hide_fraction
        hidden = in_grid[hidden_mask]
        remaining = pd.concat([in_grid[~hidden_mask], outside], ignore_index=True)

        df_fold = recompute_network_features(df_hex, remaining)
        df_scored = compute_expansion_need_score(df_fold, weights)

        labels = df_scored["h3_index"].isin(set(hidden["h3_index"])).values.astype(int)
        if labels.sum() == 0 or labels.sum() == len(labels):
            continue

        score = df_scored["expansion_need_score"].values
        baseline = df_scored["demand_population_score"].values

        # Unserved-only view: among hexes with no remaining site, does the score
        # separate the ones that really had a (now hidden) site from the ones that
        # never had one? This removes the bias where hidden sites inside dense,
        # still-served clusters are counted as misses.
        unserved = (df_scored["existing_sites_site_count"].values == 0)
        u_labels, u_score, u_base = labels[unserved], score[unserved], baseline[unserved]
        has_both = 0 < u_labels.sum() < len(u_labels)

        folds.append({
            "fold": fold,
            "hidden_sites": int(len(hidden)),
            "positive_hexes": int(labels.sum()),
            "auc_expansion_score": float(roc_auc_score(labels, score)),
            "auc_population_only": float(roc_auc_score(labels, baseline)),
            "recall_top10pct_expansion_score": _recall_at_fraction(score, labels, 0.10),
            "recall_top10pct_population_only": _recall_at_fraction(baseline, labels, 0.10),
            "recall_top25pct_expansion_score": _recall_at_fraction(score, labels, 0.25),
            "unserved_hexes": int(unserved.sum()),
            "unserved_positive_hexes": int(u_labels.sum()),
            "auc_expansion_score_unserved": float(roc_auc_score(u_labels, u_score)) if has_both else float("nan"),
            "auc_population_only_unserved": float(roc_auc_score(u_labels, u_base)) if has_both else float("nan"),
            "recall_top10pct_expansion_score_unserved": _recall_at_fraction(u_score, u_labels, 0.10) if has_both else float("nan"),
            "recall_top10pct_population_only_unserved": _recall_at_fraction(u_base, u_labels, 0.10) if has_both else float("nan"),
        })

    summary = {
        "n_folds": len(folds),
        "hide_fraction": hide_fraction,
        "sites_in_grid": int(len(in_grid)),
    }
    for key in [
        "auc_expansion_score",
        "auc_population_only",
        "recall_top10pct_expansion_score",
        "recall_top10pct_population_only",
        "recall_top25pct_expansion_score",
        "auc_expansion_score_unserved",
        "auc_population_only_unserved",
        "recall_top10pct_expansion_score_unserved",
        "recall_top10pct_population_only_unserved",
    ]:
        vals = [f[key] for f in folds if np.isfinite(f[key])]
        summary[f"mean_{key}"] = float(np.mean(vals)) if vals else float("nan")
    summary["folds"] = folds
    return summary


def weight_sensitivity(
    df_hex: pd.DataFrame,
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
    factors=(0.5, 1.5),
    top_n: int = 50,
) -> List[Dict[str, float]]:
    """Scale each weight up/down and report rank correlation and top-N overlap vs. default."""
    base = compute_expansion_need_score(df_hex, weights).set_index("h3_index")["expansion_need_score"]
    base_top = set(base.head(top_n).index)

    results = []
    for name in active_weights(df_hex, weights):
        for factor in factors:
            perturbed = dict(weights)
            perturbed[name] = perturbed[name] * factor
            scored = compute_expansion_need_score(df_hex, perturbed).set_index("h3_index")["expansion_need_score"]
            aligned = scored.reindex(base.index)
            rho = spearmanr(base.values, aligned.values).correlation
            overlap = len(base_top & set(scored.head(top_n).index)) / top_n
            results.append({
                "weight": name,
                "factor": factor,
                "spearman_rank_correlation": float(rho),
                f"top{top_n}_overlap": float(overlap),
            })
    return results


def run_validation_pipeline(city: str = DEFAULT_PILOT_CITY) -> Dict[str, object]:
    """Run known-site recovery and weight sensitivity for a city and write a JSON report."""
    table_path = H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city=city)
    print(f"Loading H3 feature table: {table_path}")
    df_hex = pd.read_parquet(table_path)
    df_hex, masked = mask_unscorable_hexes(df_hex)
    print(f"Validating on {len(df_hex)} scorable hexes (masked {masked}).")

    sites = load_sites_utm()

    print("Running known-site recovery test...")
    recovery = known_site_recovery(df_hex, sites)
    print(
        f"  all hexes: AUC expansion={recovery['mean_auc_expansion_score']:.3f} "
        f"vs population-only={recovery['mean_auc_population_only']:.3f}; "
        f"recall@10% expansion={recovery['mean_recall_top10pct_expansion_score']:.3f} "
        f"vs population-only={recovery['mean_recall_top10pct_population_only']:.3f}"
    )
    print(
        f"  unserved hexes only: AUC expansion={recovery['mean_auc_expansion_score_unserved']:.3f} "
        f"vs population-only={recovery['mean_auc_population_only_unserved']:.3f}; "
        f"recall@10% expansion={recovery['mean_recall_top10pct_expansion_score_unserved']:.3f} "
        f"vs population-only={recovery['mean_recall_top10pct_population_only_unserved']:.3f}"
    )

    print("Running weight sensitivity analysis...")
    sensitivity = weight_sensitivity(df_hex)
    min_rho = min(r["spearman_rank_correlation"] for r in sensitivity)
    print(f"  minimum Spearman rank correlation across perturbations: {min_rho:.3f}")

    report = {
        "city": city,
        "scorable_hexes": int(len(df_hex)),
        "masked_hexes": masked,
        "weights": active_weights(df_hex),
        "known_site_recovery": recovery,
        "weight_sensitivity": sensitivity,
    }
    out_path = H3_VALIDATION_JSON_TEMPLATE.format(city=city)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Exported validation report to: {out_path}")
    return report


if __name__ == "__main__":
    run_validation_pipeline(city=DEFAULT_PILOT_CITY)
