"""
Experimental planning priorities for engineering review.
Known-site distance and population are proxies; the score does not predict RF
coverage or deployment success. Equipment and spectrum advice are not produced.
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
    CLEANED_SITES_PARQUET,
    RECOMMENDATIONS_CSV,
    REPORTS_DIR,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
    LIBYA_BBOX,
)
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS


class CellSiteOptimizer:
    """
    Evaluates geospatial candidate locations across Libya to recommend
    optimal placements for new cell sites based on population demand,
    known-site gaps, terrain elevation, and road accessibility.
    """

    def __init__(
        self,
        suitability_model_path: Path = SUITABILITY_MODEL_PATH
    ):
        self.suitability_model = joblib.load(suitability_model_path)
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
        Scans candidate grid across Libya, filters for known-site gaps,
        runs experimental site-pattern inference, and returns ranked recommendations.
        """
        if top_k < 1:
            raise ValueError("top_k must be positive")
        print("Generating candidate search grid across Libyan populated regions and highway corridors...")
        cand_lons, cand_lats = self.generate_candidate_grid(step_km=4.0)
        print(f"Generated {len(cand_lons)} candidate evaluation points.")

        print("Extracting multi-layer geospatial features for candidate locations...")
        df_candidates = self.extractor.extract_features(cand_lons, cand_lats, is_existing_site=False)

        print(f"Filtering for known-site gaps (min distance to existing tower >= {min_gap_distance_m}m, min 5km pop >= {min_population_5km})...")
        mask_gap = (
            (df_candidates["dist_to_nearest_site_m"] >= min_gap_distance_m) &
            (df_candidates["population_sum_5km"] >= min_population_5km) &
            (df_candidates["dist_to_nearest_road_m"] <= 4000.0)
        )
        df_gaps = df_candidates[mask_gap].copy()
        print(f"Identified {len(df_gaps)} planning candidates meeting demographic criteria.")

        # Keep the requested constraints, including when no candidate survives.
        if df_gaps.empty:
            print("No eligible planning candidates; constraints were not relaxed.")
            df_gaps["placement_suitability_score"] = pd.Series(dtype=float)
        else:
            probabilities = self.suitability_model.predict_proba(df_gaps[SUITABILITY_FEATURE_COLS])[:, 1]
            df_gaps["placement_suitability_score"] = np.round(probabilities, 4)

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

        df_recommendations = (pd.DataFrame(final_picks) if final_picks else df_gaps.iloc[0:0].copy()).reset_index(drop=True)
        df_recommendations["recommendation_rank"] = range(1, len(df_recommendations) + 1)

        # Reorder columns for presentation
        display_cols = [
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
            "population_density_1km",
            "population_sum_5km",
            "dist_to_nearest_site_m",
            "dist_to_nearest_road_m",
            "elevation_m",
        ]
        df_recommendations = df_recommendations[display_cols]

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
        rec_geojson_path.write_text(gdf_rec.to_json(), encoding="utf-8")
        print(f"Exported Recommendations GeoJSON to: {rec_geojson_path}")

        return df_recommendations


def run_optimizer_pipeline() -> pd.DataFrame:
    """Runs the cell site optimization and coverage gap recommendation pipeline."""
    optimizer = CellSiteOptimizer()
    recs = optimizer.find_optimal_placements(min_gap_distance_m=3000.0, min_population_5km=300.0, top_k=50)
    print("\n" + "="*70)
    print("TOP 10 PLANNING PRIORITIES FOR ENGINEERING REVIEW")
    print("="*70)
    print(recs[[
        "recommendation_rank", "municipality_name", "nearest_settlement_name",
        "deployment_priority_score", "placement_suitability_score",
        "population_sum_5km", "dist_to_nearest_site_m"
    ]].head(10).to_string(index=False))
    return recs


if __name__ == "__main__":
    run_optimizer_pipeline()
