"""Ahmed's fixed heuristic, ported onto Mahalm GIS v2. No model inference."""
from hashlib import sha256
import numpy as np
import pandas as pd

SCORE_COMPONENT_COLUMNS = [
    "demand_component",
    "known_site_gap_component",
    "road_access_component",
    "terrain_component",
]
SCORE_VERSION = "explainable-gis-v2-20260923"

REQUIRED_CANDIDATE_FIELDS = [
    "population_sum_5km",
    "dist_to_nearest_site_m",
    "dist_to_nearest_road_m",
    "elevation_m",
    "elevation_prominence_3km",
    "terrain_slope_deg",
]


def eligible_candidate_mask(
    candidates: pd.DataFrame,
    min_gap_distance_m: float = 3000.0,
    min_population_5km: float = 300.0,
    max_road_distance_m: float = 4000.0,
    require_worldcover: bool = True,
) -> pd.Series:
    """Return the strict, auditable eligibility mask used for recommendations."""
    required = [
        "inside_libya",
        "population_data_available",
        "terrain_data_available",
        *REQUIRED_CANDIDATE_FIELDS,
    ]
    missing = [column for column in required if column not in candidates]
    if require_worldcover:
        missing.extend(
            column
            for column in ("worldcover_data_available", "worldcover_is_water")
            if column not in candidates
        )
    if missing:
        raise KeyError(f"Candidate features are missing required columns: {missing}")
    complete = np.isfinite(candidates[REQUIRED_CANDIDATE_FIELDS].to_numpy(dtype=float)).all(axis=1)
    eligible = (
        candidates["inside_libya"].fillna(False).astype(bool)
        & complete
        & candidates["population_data_available"].fillna(False).astype(bool)
        & candidates["terrain_data_available"].fillna(False).astype(bool)
        & candidates["dist_to_nearest_site_m"].ge(min_gap_distance_m)
        & candidates["population_sum_5km"].ge(min_population_5km)
        & candidates["dist_to_nearest_road_m"].le(max_road_distance_m)
    )
    if require_worldcover:
        eligible &= candidates["worldcover_data_available"].fillna(False).astype(bool)
        eligible &= ~candidates["worldcover_is_water"].fillna(False).astype(bool)
    return eligible


def score_candidate_features(candidates: pd.DataFrame) -> pd.DataFrame:
    """Calculate a fixed, explainable priority index from supplied datasets.

    The transformations and weights are planning assumptions, not learned model
    parameters. The result is an ordering aid and must not be read as a
    probability of coverage, demand, or deployment success.
    """
    missing = [column for column in REQUIRED_CANDIDATE_FIELDS if column not in candidates]
    if missing:
        raise KeyError(f"Candidate features are missing required columns: {missing}")
    result = candidates.copy()

    result["demand_component"] = np.clip(
        np.log1p(result["population_sum_5km"]) / np.log1p(100_000.0), 0.0, 1.0
    )
    result["known_site_gap_component"] = np.clip(
        (result["dist_to_nearest_site_m"] - 3000.0) / 17_000.0, 0.0, 1.0
    )
    result["road_access_component"] = 1.0 - np.clip(
        result["dist_to_nearest_road_m"] / 4000.0, 0.0, 1.0
    )
    slope_component = 1.0 - np.clip(result["terrain_slope_deg"] / 15.0, 0.0, 1.0)
    prominence_component = np.clip(
        (result["elevation_prominence_3km"] + 50.0) / 100.0, 0.0, 1.0
    )
    result["terrain_component"] = 0.5 * slope_component + 0.5 * prominence_component

    result["planning_priority_score"] = 100.0 * (
        0.40 * result["demand_component"]
        + 0.30 * result["known_site_gap_component"]
        + 0.20 * result["road_access_component"]
        + 0.10 * result["terrain_component"]
    )
    for column in [*SCORE_COMPONENT_COLUMNS, "planning_priority_score"]:
        result[column] = result[column].round(4)
    result["score_version"] = SCORE_VERSION
    return result


def candidate_id(row: pd.Series) -> str:
    """Return a stable ID for a generated coordinate and its generation source."""
    key = (
        f"{float(row['canonical_latitude']):.6f}|"
        f"{float(row['canonical_longitude']):.6f}|{row['candidate_source']}"
    )
    return f"candidate-{sha256(key.encode('ascii')).hexdigest()[:12]}"


def add_reason_codes(candidates: pd.DataFrame) -> pd.DataFrame:
    """Attach compact source-based explanations to each proposed placement."""
    result = candidates.copy()
    if result.empty:
        result["reason_codes"] = pd.Series(index=result.index, dtype="string")
        return result

    def reasons(row: pd.Series) -> str:
        if 'eligible' in row and not bool(row['eligible']):
            return 'ineligible;' + str(row.get('rejection_reasons', 'evidence_or_constraint_check_failed'))
        codes = []
        if row["population_sum_5km"] >= 10_000:
            codes.append("high_population_catchment")
        if row["dist_to_nearest_site_m"] >= 10_000:
            codes.append("large_known_site_gap")
        if row["dist_to_nearest_road_m"] <= 1000:
            codes.append("good_road_access")
        if row["elevation_prominence_3km"] >= 20 and row["terrain_slope_deg"] <= 10:
            codes.append("terrain_advantage")
        if (pd.notna(row.get("opencellid_review_required")) and bool(row.get("opencellid_review_required", False))):
            codes.append("near_recent_opencellid_observation")
        if (pd.notna(row.get("worldcover_review_required")) and bool(row.get("worldcover_review_required", False))):
            codes.append("mixed_or_coastal_landcover_review")
        if (pd.notna(row.get("osm_building_review_required")) and bool(row.get("osm_building_review_required", False))):
            codes.append("mapped_building_context_missing_review")
        return ";".join(codes or ["meets_minimum_planning_constraints"])

    result["reason_codes"] = result.apply(reasons, axis=1)
    return result
