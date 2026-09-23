"""
Main interface and pipeline entry point for Antenna Cell Placement AI.
"""

from typing import Dict, Any, List, Optional
import pandas as pd

from antenna_cell_placement.site_optimizer import CellSiteOptimizer
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
import joblib
from antenna_cell_placement.config import SUITABILITY_MODEL_PATH, CLEANED_SITES_PARQUET


def predict_site_suitability(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Return experimental existing-site pattern similarity and observed GIS context.
    This is not a coverage prediction or installation approval.
    """
    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()

    df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)
    extractor.set_existing_sites(df_sites)

    features = extractor.extract_features([longitude], [latitude], is_existing_site=False)

    suit_model = joblib.load(SUITABILITY_MODEL_PATH)

    score = float(suit_model.predict_proba(features[SUITABILITY_FEATURE_COLS])[0, 1])

    return {
        "latitude": latitude,
        "longitude": longitude,
        "experimental_site_pattern_score": round(score, 4),
        "interpretation": "Existing-site pattern recognition; not RF coverage or deployment success.",
        "building_height_m": None,
        "building_height_status": "Unavailable",
        "municipality": features["municipality_name"].iloc[0],
        "nearest_settlement": features["nearest_settlement_name"].iloc[0],
        "distance_to_nearest_settlement_km": round(features["dist_to_nearest_settlement_m"].iloc[0] / 1000.0, 2),
        "population_density_1km": float(features["population_density_1km"].iloc[0]),
        "population_sum_5km": int(features["population_sum_5km"].iloc[0]),
        "distance_to_nearest_cell_km": round(features["dist_to_nearest_site_m"].iloc[0] / 1000.0, 2),
        "distance_to_nearest_road_m": round(features["dist_to_nearest_road_m"].iloc[0], 1),
        "elevation_m": float(features["elevation_m"].iloc[0]),
        "cloudflare_http_requests_share_52w_pct": float(
            features["cloudflare_http_requests_share_52w_pct"].iloc[0]
        ),
        "cloudflare_regional_demand_score": float(
            features["cloudflare_regional_demand_score"].iloc[0]
        ),
        "cloudflare_data_available": bool(
            features["cloudflare_data_available"].iloc[0]
        ),
    }


def get_top_recommendations(top_k: int = 50) -> pd.DataFrame:
    """Returns top ranked cell site placement recommendations for Libya."""
    optimizer = CellSiteOptimizer()
    return optimizer.find_optimal_placements(top_k=top_k)
