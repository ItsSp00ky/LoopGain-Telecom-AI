"""
Main interface and pipeline entry point for Antenna Cell Placement AI.
"""

from typing import Dict, Any, List, Optional
import pandas as pd

from antenna_cell_placement.site_optimizer import CellSiteOptimizer
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
import joblib
from antenna_cell_placement.config import SUITABILITY_MODEL_PATH, EQUIPMENT_MODEL_PATH, CLEANED_SITES_PARQUET


def predict_site_suitability(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Predicts the suitability and recommended equipment configuration
    for an antenna cell site at a given (latitude, longitude) coordinate in Libya.
    """
    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()

    df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)
    extractor.set_existing_sites(df_sites)

    features = extractor.extract_features([longitude], [latitude], is_existing_site=False)

    suit_model = joblib.load(SUITABILITY_MODEL_PATH)
    eq_model = joblib.load(EQUIPMENT_MODEL_PATH)

    score = float(suit_model.predict_proba(features[SUITABILITY_FEATURE_COLS])[0, 1])

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
    tier = str(eq_model.predict(features[eq_features])[0])

    return {
        "latitude": latitude,
        "longitude": longitude,
        "suitability_score": round(score, 4),
        "is_suitable": score >= 0.65,
        "recommended_equipment_tier": tier,
        "municipality": features["municipality_name"].iloc[0],
        "nearest_settlement": features["nearest_settlement_name"].iloc[0],
        "distance_to_nearest_settlement_km": round(features["dist_to_nearest_settlement_m"].iloc[0] / 1000.0, 2),
        "population_density_1km": float(features["population_density_1km"].iloc[0]),
        "population_sum_5km": int(features["population_sum_5km"].iloc[0]),
        "distance_to_nearest_cell_km": round(features["dist_to_nearest_site_m"].iloc[0] / 1000.0, 2),
        "distance_to_nearest_road_m": round(features["dist_to_nearest_road_m"].iloc[0], 1),
        "elevation_m": float(features["elevation_m"].iloc[0]),
    }


def get_top_recommendations(top_k: int = 50) -> pd.DataFrame:
    """Returns top ranked cell site placement recommendations for Libya."""
    optimizer = CellSiteOptimizer()
    return optimizer.find_optimal_placements(top_k=top_k)
