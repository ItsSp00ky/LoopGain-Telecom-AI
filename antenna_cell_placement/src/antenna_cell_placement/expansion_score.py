"""
Expansion Need Score for the H3 pilot-city planning grid.
Combines per-hex population demand, building/urban demand, network-distance
deficiency, and land-use demand into one normalized 0-100 score used to rank
which areas of a pilot city most need a new cell site, then modulates it with
the trained site-suitability model so Stage 1 (area) feeds Stage 2 (point).
"""

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from antenna_cell_placement.config import (
    DEFAULT_PILOT_CITY,
    H3_FEATURE_TABLE_PARQUET_TEMPLATE,
    H3_EXPANSION_SCORE_CSV_TEMPLATE,
    H3_EXPANSION_SCORE_GEOJSON_TEMPLATE,
    H3_GRID_GEOJSON_TEMPLATE,
    H3_WATER_MASK_PCT,
    H3_UNINHABITED_MAX_ROAD_DIST_M,
    SUITABILITY_MODEL_PATH,
    CRS_WGS84,
)

DEFAULT_WEIGHTS = {
    "population_demand": 0.35,
    "building_urban_demand": 0.25,
    "network_gap": 0.25,
    "landuse_demand": 0.15,
}

NO_SITE_BONUS = 0.15
NORMALIZE_CLIP_PERCENTILES = (2.0, 98.0)

# Phase-2 columns each sub-score depends on. If none of a sub-score's source
# columns carry data, that weight is dropped and the remaining weights are
# renormalized, so scoring works right after Phase 1 and improves once Phase 2
# (buildings/land-cover/OSM) columns are joined in.
_SUBSCORE_SOURCE_COLS = {
    "building_urban_demand": ["building_density_per_km2", "built_up_ratio", "poi_count"],
    "landuse_demand": ["landcover_builtup_pct", "landcover_bare_pct", "landcover_water_pct"],
}

_SUBSCORE_COLUMN = {
    "population_demand": "demand_population_score",
    "building_urban_demand": "demand_building_score",
    "network_gap": "network_gap_score",
    "landuse_demand": "landuse_demand_score",
}


def _has_data(df: pd.DataFrame, cols) -> bool:
    present = [c for c in cols if c in df.columns]
    return bool(present) and bool(df[present].notna().any().any())


def _minmax_normalize(series: pd.Series, clip_percentiles: Tuple[float, float] = NORMALIZE_CLIP_PERCENTILES) -> pd.Series:
    """
    Percentile-clipped min-max normalization to [0, 1]. Clipping keeps a handful
    of extreme hexes (e.g. offshore or far-desert) from compressing everyone else.
    Constant or empty columns return a neutral 0.5.
    """
    values = series.astype(float).replace([np.inf, -np.inf], np.nan)
    finite = values[np.isfinite(values)]
    if finite.empty:
        return pd.Series(0.5, index=values.index)
    lo, hi = np.percentile(finite, clip_percentiles)
    if hi - lo == 0:
        return pd.Series(0.5, index=values.index)
    return ((values.clip(lo, hi) - lo) / (hi - lo)).fillna(0.5)


def mask_unscorable_hexes(df_hex: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Drop hexes that are mostly water or have no population and no road access."""
    mask = pd.Series(False, index=df_hex.index)
    counts = {}

    if _has_data(df_hex, ["landcover_water_pct"]):
        water = df_hex["landcover_water_pct"].fillna(0.0) >= H3_WATER_MASK_PCT
        counts["water_hexes"] = int(water.sum())
        mask |= water

    uninhabited = (df_hex["population_sum_5km"] <= 0.0) & (
        df_hex["dist_to_nearest_road_m"] > H3_UNINHABITED_MAX_ROAD_DIST_M
    )
    counts["uninhabited_hexes"] = int((uninhabited & ~mask).sum())
    mask |= uninhabited

    return df_hex[~mask].copy(), counts


def compute_population_demand(df_hex: pd.DataFrame) -> pd.Series:
    """
    Local population demand: mean of normalized 1km density and 3km sum. Within a
    city the 5km sum saturates (every central hex sees the same catchment), so the
    tighter windows are what actually discriminate between neighbouring hexes.
    """
    parts = [
        _minmax_normalize(df_hex[col])
        for col in ("population_density_1km", "population_sum_3km")
        if col in df_hex.columns
    ]
    if not parts:
        return _minmax_normalize(df_hex["population_sum_5km"])
    return pd.concat(parts, axis=1).mean(axis=1)


def compute_building_urban_demand(df_hex: pd.DataFrame) -> pd.Series:
    """Combine normalized building density, built-up ratio, and POI count (Phase 2)."""
    parts = [
        _minmax_normalize(df_hex[col])
        for col in _SUBSCORE_SOURCE_COLS["building_urban_demand"]
        if col in df_hex.columns and df_hex[col].notna().any()
    ]
    if not parts:
        return pd.Series(0.5, index=df_hex.index)
    return pd.concat(parts, axis=1).mean(axis=1)


def compute_network_gap_score(df_hex: pd.DataFrame) -> pd.Series:
    """
    Normalized distance-to-nearest-site combined with inverse site density
    (higher = more underserved). Hexes with zero existing sites get a
    deficiency bonus so genuinely unserved areas rank above merely sparse ones.
    """
    dist_score = _minmax_normalize(df_hex["dist_to_nearest_site_m"])
    if "site_density_3km" in df_hex.columns:
        inv_density_score = 1.0 - _minmax_normalize(df_hex["site_density_3km"])
    else:
        inv_density_score = pd.Series(0.5, index=df_hex.index)

    gap_score = 0.5 * dist_score + 0.5 * inv_density_score

    if "existing_sites_site_count" in df_hex.columns:
        no_site_bonus = (df_hex["existing_sites_site_count"].fillna(0) == 0).astype(float) * NO_SITE_BONUS
        gap_score = np.clip(gap_score + no_site_bonus, 0.0, 1.0)

    return pd.Series(gap_score, index=df_hex.index)


def compute_landuse_demand(df_hex: pd.DataFrame) -> pd.Series:
    """Weight built-up land-cover % positively, water/bare % negatively (Phase 2)."""
    if not _has_data(df_hex, _SUBSCORE_SOURCE_COLS["landuse_demand"]):
        return pd.Series(0.5, index=df_hex.index)

    zeros = pd.Series(0.0, index=df_hex.index)
    builtup = df_hex.get("landcover_builtup_pct", zeros).fillna(0.0) / 100.0
    bare = df_hex.get("landcover_bare_pct", zeros).fillna(0.0) / 100.0
    water = df_hex.get("landcover_water_pct", zeros).fillna(0.0) / 100.0

    score = builtup - 0.5 * bare - 1.0 * water
    present = [c for c in _SUBSCORE_SOURCE_COLS["landuse_demand"] if c in df_hex]
    missing = df_hex[present].isna().all(axis=1)
    return pd.Series(np.clip(score, 0.0, 1.0), index=df_hex.index).mask(missing, 0.5)


def active_weights(df_hex: pd.DataFrame, weights: Dict[str, float] = DEFAULT_WEIGHTS) -> Dict[str, float]:
    """Drop sub-score weights whose source columns carry no data and renormalize."""
    active = dict(weights)
    for name, cols in _SUBSCORE_SOURCE_COLS.items():
        if not _has_data(df_hex, cols):
            active.pop(name, None)

    total = sum(active.values())
    if total <= 0:
        return dict(weights)
    return {k: v / total for k, v in active.items()}


def compute_expansion_need_score(df_hex: pd.DataFrame, weights: Dict[str, float] = DEFAULT_WEIGHTS) -> pd.DataFrame:
    """
    Combine the four normalized sub-scores into `expansion_need_score` (0-100),
    keeping each sub-score column for auditability. Gracefully degrades to a
    Phase-1-only score (population + network gap) when Phase-2 columns are absent.
    """
    df = df_hex.copy()
    df["demand_population_score"] = compute_population_demand(df)
    df["demand_building_score"] = compute_building_urban_demand(df)
    df["network_gap_score"] = compute_network_gap_score(df)
    df["landuse_demand_score"] = compute_landuse_demand(df)

    weights_used = active_weights(df_hex, weights)
    combined = sum(w * df[_SUBSCORE_COLUMN[name]] for name, w in weights_used.items())
    df["expansion_need_score"] = np.round(100.0 * combined, 2)

    return df.sort_values("expansion_need_score", ascending=False).reset_index(drop=True)


def add_suitability_priority(df_scored: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 1 -> Stage 2 hand-off: score each hex centroid with the trained
    site-suitability model and modulate the expansion score by a bounded
    factor in [0.75, 1.25], mirroring how the optimizer bounds external priors.
    """
    df = df_scored.copy()
    try:
        import joblib
        from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
    except ImportError:
        SUITABILITY_FEATURE_COLS = None

    if (
        SUITABILITY_FEATURE_COLS is None
        or not SUITABILITY_MODEL_PATH.exists()
        or any(col not in df.columns for col in SUITABILITY_FEATURE_COLS)
    ):
        df["placement_suitability_score"] = np.nan
        df["combined_priority_score"] = df["expansion_need_score"]
        return df

    model = joblib.load(SUITABILITY_MODEL_PATH)
    probs = model.predict_proba(df[SUITABILITY_FEATURE_COLS])[:, 1]
    df["placement_suitability_score"] = np.round(probs, 4)
    df["combined_priority_score"] = np.round(df["expansion_need_score"] * (0.75 + 0.5 * probs), 2)
    return df.sort_values("combined_priority_score", ascending=False).reset_index(drop=True)


def run_expansion_score_pipeline(city: str = DEFAULT_PILOT_CITY) -> pd.DataFrame:
    """Loads the H3 feature table for a city, computes and exports the expansion need score."""
    table_path = H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city=city)
    print(f"Loading H3 feature table: {table_path}")
    df_hex = pd.read_parquet(table_path)

    df_scorable, masked = mask_unscorable_hexes(df_hex)
    print(f"Masked {sum(masked.values())} unscorable hexes {masked}; scoring {len(df_scorable)} hexes.")

    weights_used = active_weights(df_scorable)
    print("Active weights:", {k: round(v, 3) for k, v in weights_used.items()})

    df_scored = compute_expansion_need_score(df_scorable)
    df_scored = add_suitability_priority(df_scored)
    df_scored["expansion_rank"] = range(1, len(df_scored) + 1)

    csv_path = H3_EXPANSION_SCORE_CSV_TEMPLATE.format(city=city)
    df_scored.to_csv(csv_path, index=False)
    print(f"Exported expansion need scores to: {csv_path}")

    import geopandas as gpd

    grid_path = H3_GRID_GEOJSON_TEMPLATE.format(city=city)
    grid_gdf = gpd.read_file(grid_path)[["h3_index", "geometry"]]
    gdf_scored = grid_gdf.merge(df_scored, on="h3_index", how="inner").set_crs(CRS_WGS84)

    geojson_path = H3_EXPANSION_SCORE_GEOJSON_TEMPLATE.format(city=city)
    gdf_scored.to_file(geojson_path, driver="GeoJSON")
    print(f"Exported expansion need scores GeoJSON to: {geojson_path}")

    return df_scored


if __name__ == "__main__":
    scored = run_expansion_score_pipeline(city=DEFAULT_PILOT_CITY)
    print("\nTop 10 highest priority hexes:")
    print(
        scored[["h3_index", "combined_priority_score", "expansion_need_score", "placement_suitability_score"]]
        .head(10)
        .to_string(index=False)
    )
