"""
Cell Site Placement Optimizer & Coverage Gap Analyzer for Libya.
Identifies unserved and underserved populated corridors, evaluates candidate coordinates
using the trained AI suitability model, and generates prioritized deployment recommendations.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from antenna_cell_placement.config import (
    SUITABILITY_MODEL_PATH,
    EQUIPMENT_MODEL_PATH,
    CLEANED_SITES_PARQUET,
    RECOMMENDATIONS_CSV,
    REPORTS_DIR,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
    LIBYA_BBOX,
)
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS


RECOMMENDATION_COLUMNS = [
    "recommendation_rank",
    "canonical_latitude",
    "canonical_longitude",
    "municipality_name",
    "nearest_settlement_name",
    "deployment_priority_score",
    "geospatial_priority_score",
    "placement_suitability_score",
    "cloudflare_regional_demand_score",
    "cloudflare_priority_factor",
    "cloudflare_http_requests_share_52w_pct",
    "cloudflare_annual_traffic_growth_52w_pct",
    "cloudflare_data_available",
    "recommended_equipment_tier",
    "recommended_rf_bands",
    "recommended_bandwidth",
    "recommended_operator_strategy",
    "population_density_1km",
    "population_sum_5km",
    "dist_to_nearest_site_m",
    "dist_to_nearest_road_m",
    "elevation_m",
]


class CellSiteOptimizer:
    """
    Evaluates geospatial candidate locations across Libya to recommend
    optimal placements for new cell sites based on population demand,
    coverage gaps, terrain elevation, and road accessibility.
    """

    def __init__(
        self,
        suitability_model_path: Path = SUITABILITY_MODEL_PATH,
        equipment_model_path: Path = EQUIPMENT_MODEL_PATH
    ):
        self.suitability_model = joblib.load(suitability_model_path)
        self.equipment_model = joblib.load(equipment_model_path)
        self.extractor = GeospatialFeatureExtractor()
        self.extractor.load_layers()

        df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)
        self.extractor.set_existing_sites(df_sites)
        self.df_existing_sites = df_sites

    def generate_candidate_grid(self, step_km: float = 3.0) -> Tuple[List[float], List[float]]:
        """
        Generates candidate locations focusing on populated settlement perimeters
        and major road networks in Libya.
        """
        cand_lons = []
        cand_lats = []

        # 1. Populated places rings (from 2km to 12km in steps)
        for _, place in self.extractor.places_df.iterrows():
            pt_wgs = gpd.GeoDataFrame(geometry=[place.geometry], crs=CRS_PROJECTED_LIBYA).to_crs(CRS_WGS84).geometry.iloc[0]
            for r_km in [2.5, 4.5, 7.0, 10.0]:
                r_deg = r_km / 111.0
                for theta in np.linspace(0, 2 * np.pi, 8, endpoint=False):
                    cx = pt_wgs.x + r_deg * np.cos(theta)
                    cy = pt_wgs.y + r_deg * np.sin(theta)
                    if (LIBYA_BBOX["min_lon"] <= cx <= LIBYA_BBOX["max_lon"] and
                        LIBYA_BBOX["min_lat"] <= cy <= LIBYA_BBOX["max_lat"]):
                        cand_lons.append(cx)
                        cand_lats.append(cy)

        # 2. Highway and road network sampling every 3km
        road_pts = self.extractor.road_tree.data
        step_pts = int((step_km * 1000.0) // 500.0)  # road points sampled at 500m
        selected_road_pts = road_pts[::max(1, step_pts)]

        gdf_roads = gpd.GeoDataFrame(
            geometry=[Point(pt[0], pt[1]) for pt in selected_road_pts],
            crs=CRS_PROJECTED_LIBYA
        ).to_crs(CRS_WGS84)

        for geom in gdf_roads.geometry:
            if (LIBYA_BBOX["min_lon"] <= geom.x <= LIBYA_BBOX["max_lon"] and
                LIBYA_BBOX["min_lat"] <= geom.y <= LIBYA_BBOX["max_lat"]):
                cand_lons.append(geom.x)
                cand_lats.append(geom.y)

        return cand_lons, cand_lats

    def find_optimal_placements(
        self,
        min_gap_distance_m: float = 3000.0,
        min_population_5km: float = 400.0,
        top_k: int = 50
    ) -> pd.DataFrame:
        """
        Scans candidate grid across Libya, filters for coverage gaps,
        runs AI suitability inference, and returns ranked recommendations.
        """
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if (not np.isfinite([min_gap_distance_m, min_population_5km]).all()
                or min_gap_distance_m < 0 or min_population_5km < 0):
            raise ValueError("Minimum distance and population must be finite and non-negative")
        print("Generating candidate search grid across Libyan populated regions and highway corridors...")
        cand_lons, cand_lats = self.generate_candidate_grid(step_km=4.0)
        print(f"Generated {len(cand_lons)} candidate evaluation points.")
        if not cand_lons:
            return export_recommendations(pd.DataFrame(columns=RECOMMENDATION_COLUMNS))

        print("Extracting multi-layer geospatial features for candidate locations...")
        df_candidates = self.extractor.extract_features(cand_lons, cand_lats, is_existing_site=False)

        print(f"Filtering for coverage gaps (min distance to existing tower >= {min_gap_distance_m}m, min 5km pop >= {min_population_5km})...")
        mask_gap = (
            (df_candidates["dist_to_nearest_site_m"] >= min_gap_distance_m) &
            (df_candidates["population_sum_5km"] >= min_population_5km) &
            (df_candidates["dist_to_nearest_road_m"] <= 4000.0)
        )
        df_gaps = df_candidates[mask_gap].copy()
        print(f"Identified {len(df_gaps)} coverage gap candidates meeting demographic criteria.")

        if df_gaps.empty:
            print("No gaps found matching the requested criteria.")
            return export_recommendations(pd.DataFrame(columns=RECOMMENDATION_COLUMNS))

        # Run AI Suitability Predictor
        X_cand = df_gaps[SUITABILITY_FEATURE_COLS]
        suitability_probs = self.suitability_model.predict_proba(X_cand)[:, 1]
        df_gaps["placement_suitability_score"] = np.round(suitability_probs, 4)

        # Run Equipment Recommender
        eq_features = [
            "population_density_1km",
            "population_sum_3km",
            "population_sum_5km",
            "elevation_m",
            "elevation_prominence_3km",
            "terrain_slope_deg",
            "dist_to_nearest_road_m",
            "dist_to_nearest_settlement_m",
            "dist_to_nearest_site_m",
            "site_density_3km",
            "site_density_5km",
        ]
        eq_preds = self.equipment_model.predict(df_gaps[eq_features])
        df_gaps["recommended_equipment_tier"] = eq_preds

        # Recommend Frequency Bands & Deployment Strategy
        rec_bands = []
        rec_bandwidth = []
        rec_operators = []

        for _, row in df_gaps.iterrows():
            tier = row["recommended_equipment_tier"]
            pop_5k = row["population_sum_5km"]
            dist_lib = row["dist_to_libyana_site_m"]
            dist_mad = row["dist_to_almadar_site_m"]

            if tier == "Urban_HighCapacity_Macro":
                rec_bands.append("B3 (1800MHz) + B1 (2100MHz) + B20 (800MHz)")
                rec_bandwidth.append("40 - 60 MHz (Multi-Carrier LTE-A)")
            elif tier == "Suburban_Standard_Macro":
                rec_bands.append("B3 (1800MHz) + B20 (800MHz)")
                rec_bandwidth.append("20 - 30 MHz (Dual-Carrier LTE)")
            else:
                rec_bands.append("B20 (800MHz) + B8 (900MHz)")
                rec_bandwidth.append("10 - 15 MHz (Long-Range Coverage)")

            # Recommend Operator
            if dist_lib > 6000 and dist_mad > 6000:
                rec_operators.append("Shared Infrastructure (Libyana + Al-Madar)")
            elif dist_lib > dist_mad:
                rec_operators.append("Libyana Priority")
            else:
                rec_operators.append("Al-Madar Priority")

        df_gaps["recommended_rf_bands"] = rec_bands
        df_gaps["recommended_bandwidth"] = rec_bandwidth
        df_gaps["recommended_operator_strategy"] = rec_operators

        # Compute the geospatial score first, keeping the model output auditable.
        # Cloudflare Radar is a regional HTTP-demand prior rather than coverage
        # ground truth, so its influence is deliberately bounded to +/- 10%.
        pop_weight = np.log10(np.maximum(10.0, df_gaps["population_sum_5km"]))
        gap_weight = np.clip(df_gaps["dist_to_nearest_site_m"] / 5000.0, 0.5, 2.0)
        df_gaps["geospatial_priority_score"] = np.round(
            df_gaps["placement_suitability_score"] * pop_weight * gap_weight,
            2,
        )
        df_gaps["deployment_priority_score"] = np.round(
            df_gaps["geospatial_priority_score"]
            * df_gaps["cloudflare_priority_factor"],
            2,
        )

        # Sort and deduplicate spatially so recommendations aren't clustered together
        df_sorted = df_gaps.sort_values("deployment_priority_score", ascending=False).reset_index(drop=True)

        # Spatial non-maximum suppression (keep top sites separated by at least 2.5km)
        final_picks = []
        suppressed_coords = []

        for idx, row in df_sorted.iterrows():
            cand_coord = np.array([row["utm_x"], row["utm_y"]])
            too_close = False
            for sc in suppressed_coords:
                if np.linalg.norm(cand_coord - sc) < 2500.0:
                    too_close = True
                    break
            if not too_close:
                final_picks.append(row)
                suppressed_coords.append(cand_coord)
            if len(final_picks) >= top_k:
                break

        df_recommendations = pd.DataFrame(final_picks).reset_index(drop=True)
        df_recommendations["recommendation_rank"] = range(1, len(df_recommendations) + 1)

        # Reorder columns for presentation
        df_recommendations = df_recommendations[RECOMMENDATION_COLUMNS]

        return export_recommendations(df_recommendations)


def export_recommendations(df_recommendations: pd.DataFrame) -> pd.DataFrame:
    """Write the current result, including empty results so old recommendations cannot linger."""
    # Supplementary cell evidence is for review, not confirmed mast coverage.
    from antenna_cell_placement.opencellid import annotate_candidates
    df_recommendations = annotate_candidates(df_recommendations)

    # Export CSV
    RECOMMENDATIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_recommendations.to_csv(RECOMMENDATIONS_CSV, index=False)
    print(f"Exported Top {len(df_recommendations)} Recommendations to: {RECOMMENDATIONS_CSV}")

    # Also export GeoJSON
    rec_geojson_path = REPORTS_DIR / "recommended_cell_placements.geojson"
    gdf_rec = gpd.GeoDataFrame(
        df_recommendations,
        geometry=[Point(lon, lat) for lon, lat in zip(df_recommendations["canonical_longitude"], df_recommendations["canonical_latitude"])],
        crs=CRS_WGS84
    )
    if df_recommendations.empty:
        rec_geojson_path.write_text('{"type": "FeatureCollection", "features": []}\n', encoding="utf-8")
    else:
        gdf_rec.to_file(rec_geojson_path, driver="GeoJSON")
    print(f"Exported Recommendations GeoJSON to: {rec_geojson_path}")

    return df_recommendations


def run_optimizer_pipeline() -> pd.DataFrame:
    """Runs the cell site optimization and coverage gap recommendation pipeline."""
    optimizer = CellSiteOptimizer()
    recs = optimizer.find_optimal_placements(min_gap_distance_m=3000.0, min_population_5km=300.0, top_k=50)
    print("\n" + "="*70)
    print("TOP 10 RECOMMENDED CELL SITE PLACEMENTS FOR LIBYA")
    print("="*70)
    print(recs[[
        "recommendation_rank", "municipality_name", "nearest_settlement_name",
        "deployment_priority_score", "placement_suitability_score",
        "recommended_equipment_tier", "population_sum_5km", "dist_to_nearest_site_m"
    ]].head(10).to_string(index=False))
    return recs


if __name__ == "__main__":
    run_optimizer_pipeline()
