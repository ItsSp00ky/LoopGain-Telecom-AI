"""Shared public API for dataset-only placement assessment and ranking."""

from typing import Any

import pandas as pd

from antenna_cell_placement.h3_planning import attach_h3_indexes
from antenna_cell_placement.site_optimizer import CellSiteOptimizer, eligible_candidate_mask


def evaluate_candidate(latitude: float, longitude: float) -> dict[str, Any]:
    """Assess a coordinate with the same source features and score as ranking."""
    optimizer = CellSiteOptimizer()
    indexed = attach_h3_indexes(
        optimizer.evaluate_coordinates([longitude], [latitude])
    )
    from antenna_cell_placement.buildings import add_building_context_if_available
    from antenna_cell_placement.osm_context import add_osm_context_if_available
    row = add_osm_context_if_available(add_building_context_if_available(indexed)).iloc[0]
    required_data_available = bool(
        row["inside_libya"]
        and row["population_data_available"]
        and row["terrain_data_available"]
        and row["worldcover_data_available"]
        and pd.notna(row["dist_to_nearest_site_m"])
        and pd.notna(row["dist_to_nearest_road_m"])
    )
    shortlist_eligible = bool(eligible_candidate_mask(row.to_frame().T).iloc[0])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "planning_data_available": required_data_available,
        "planning_priority_score": (
            float(row["planning_priority_score"]) if required_data_available else None
        ),
        "shortlist_eligible": shortlist_eligible,
        "h3_r7": row["h3_r7"],
        "h3_r6": row["h3_r6"],
        "score_version": row["score_version"],
        "score_components": {
            "demand": _optional_float(row["demand_component"]),
            "known_site_gap": _optional_float(row["known_site_gap_component"]),
            "road_access": _optional_float(row["road_access_component"]),
            "terrain": _optional_float(row["terrain_component"]),
        },
        "municipality": row["municipality_name"],
        "nearest_settlement": row["nearest_settlement_name"],
        "population_density_1km": _optional_float(row["population_density_1km"]),
        "population_sum_5km": _optional_float(row["population_sum_5km"]),
        "distance_to_nearest_known_site_m": _optional_float(row["dist_to_nearest_site_m"]),
        "distance_to_nearest_road_m": _optional_float(row["dist_to_nearest_road_m"]),
        "elevation_m": _optional_float(row["elevation_m"]),
        "terrain_slope_deg": _optional_float(row["terrain_slope_deg"]),
        "worldcover_class_code": (
            int(row["worldcover_class_code"])
            if pd.notna(row["worldcover_class_code"])
            else None
        ),
        "worldcover_class_name": (
            str(row["worldcover_class_name"])
            if pd.notna(row["worldcover_class_name"])
            else None
        ),
        "worldcover_is_water": bool(row["worldcover_is_water"]),
        "osm_building_count_h3": (
            int(row["osm_building_count_h3"])
            if pd.notna(row["osm_building_count_h3"])
            else None
        ),
        "osm_building_footprint_area_m2_h3": _optional_float(
            row["osm_building_footprint_area_m2_h3"]
        ),
        "osm_building_context_available": bool(
            row["osm_building_context_available"]
        ),
        "osm_selected_context_available": bool(
            row["osm_selected_context_available"]
        ),
        "osm_selected_context": {
            family: {
                "count_h3": int(row[f"osm_{family}_count_h3"]),
                "nearest_distance_m": _optional_float(
                    row[f"osm_{family}_nearest_distance_m"]
                ),
            }
            for family in (
                "hospital",
                "higher_education",
                "aviation",
                "industrial",
            )
        },
        "cloudflare_regional_demand_score": _optional_float(
            row["cloudflare_regional_demand_score"]
        ),
        "limitations": (
            "Priority index from supplied planning datasets; it is not a coverage "
            "prediction or deployment-success probability."
        ),
    }


def get_top_recommendations(top_k: int = 50, export: bool = True) -> pd.DataFrame:
    """Return strictly filtered, dataset-only proposed placements."""
    return CellSiteOptimizer().find_priority_placements(top_k=top_k, export=export)


def _optional_float(value: Any) -> float | None:
    return float(value) if pd.notna(value) else None
