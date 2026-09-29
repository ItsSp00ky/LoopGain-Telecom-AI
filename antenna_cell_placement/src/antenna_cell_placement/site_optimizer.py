"""Dataset-only candidate generation and explainable placement prioritization."""

from hashlib import sha256
from typing import List

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from antenna_cell_placement.config import (
    CRS_PROJECTED_LIBYA,
    CRS_WGS84,
    RECOMMENDATIONS_CSV,
    RECOMMENDATIONS_GEOJSON,
)
from antenna_cell_placement.data_cleaning import clean_pipeline
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.h3_planning import attach_h3_indexes


SCORE_COMPONENT_COLUMNS = [
    "demand_component",
    "known_site_gap_component",
    "road_access_component",
    "terrain_component",
]
SCORE_VERSION = "dataset-priority-v2-metric-terrain"

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
    complete = candidates[REQUIRED_CANDIDATE_FIELDS].notna().all(axis=1)
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
        codes = []
        if row["population_sum_5km"] >= 10_000:
            codes.append("high_population_catchment")
        if row["dist_to_nearest_site_m"] >= 10_000:
            codes.append("large_known_site_gap")
        if row["dist_to_nearest_road_m"] <= 1000:
            codes.append("good_road_access")
        if row["elevation_prominence_3km"] >= 20 and row["terrain_slope_deg"] <= 10:
            codes.append("terrain_advantage")
        if bool(row.get("opencellid_review_required", False)):
            codes.append("near_recent_opencellid_observation")
        if bool(row.get("worldcover_review_required", False)):
            codes.append("mixed_or_coastal_landcover_review")
        if bool(row.get("osm_building_review_required", False)):
            codes.append("mapped_building_context_missing_review")
        return ";".join(codes or ["meets_minimum_planning_constraints"])

    result["reason_codes"] = result.apply(reasons, axis=1)
    return result


class CellSiteOptimizer:
    """Generate and rank proposed placements from supplied geospatial datasets."""

    def __init__(
        self,
        df_sites: pd.DataFrame | None = None,
        extractor: GeospatialFeatureExtractor | None = None,
    ):
        if df_sites is None:
            _, df_sites = clean_pipeline()
        df_sites = df_sites.reset_index(drop=True)
        self.extractor = extractor or GeospatialFeatureExtractor()
        self.extractor.load_layers()
        self.extractor.set_existing_sites(df_sites)

    def generate_candidate_grid(self, step_km: float = 4.0) -> pd.DataFrame:
        """Generate proposed points and retain the supplied geometry source."""
        candidate_sources: dict[tuple[float, float], set[str]] = {}

        def add_candidate(x: float, y: float, source: str) -> None:
            key = (round(float(x), 1), round(float(y), 1))
            candidate_sources.setdefault(key, set()).add(source)

        for point in self.extractor.places_df.geometry:
            for radius_m in [2500.0, 4500.0, 7000.0, 10_000.0]:
                for theta in np.linspace(0, 2 * np.pi, 8, endpoint=False):
                    add_candidate(
                        point.x + radius_m * np.cos(theta),
                        point.y + radius_m * np.sin(theta),
                        "settlement_ring",
                    )

        road_points = self.extractor.road_tree.data
        step_points = max(1, int((step_km * 1000.0) // 500.0))
        for x, y in road_points[::step_points]:
            add_candidate(x, y, "road_sample")

        unique_xy = list(candidate_sources)
        projected = gpd.GeoDataFrame(
            geometry=[Point(x, y) for x, y in unique_xy], crs=CRS_PROJECTED_LIBYA
        )
        inside = projected.geometry.apply(self.extractor.libya_boundary.covers)
        projected = projected.loc[inside].copy()
        projected["candidate_source"] = [
            ";".join(sorted(candidate_sources[unique_xy[index]])) for index in projected.index
        ]
        geographic = projected.to_crs(CRS_WGS84)
        return pd.DataFrame(
            {
                "canonical_longitude": geographic.geometry.x,
                "canonical_latitude": geographic.geometry.y,
                "candidate_source": geographic["candidate_source"].values,
            }
        ).reset_index(drop=True)

    def evaluate_coordinates(
        self,
        lons: List[float],
        lats: List[float],
        include_worldcover: bool = True,
    ) -> pd.DataFrame:
        """Return source features and priority components for arbitrary coordinates."""
        features = self.extractor.extract_features(
            lons,
            lats,
            is_existing_site=False,
            include_worldcover=include_worldcover,
        )
        return score_candidate_features(features)

    def build_candidate_pool(self, include_worldcover: bool = True) -> pd.DataFrame:
        """Generate and evaluate each proposal once for repeatable comparisons."""
        grid = self.generate_candidate_grid()
        candidates = self.evaluate_coordinates(
            grid["canonical_longitude"].tolist(),
            grid["canonical_latitude"].tolist(),
            include_worldcover=include_worldcover,
        )
        candidates["candidate_source"] = grid["candidate_source"].values
        return candidates

    def find_priority_placements(
        self,
        min_gap_distance_m: float = 3000.0,
        min_population_5km: float = 300.0,
        max_road_distance_m: float = 4000.0,
        min_candidate_separation_m: float = 2500.0,
        top_k: int = 50,
        export: bool = True,
        candidates: pd.DataFrame | None = None,
        require_worldcover: bool = True,
        add_worldcover_context: bool = True,
        add_building_context: bool = True,
        add_osm_context: bool = True,
        add_ookla_context: bool = False,
    ) -> pd.DataFrame:
        """Apply strict constraints and rank proposed placements."""
        candidates = (
            self.build_candidate_pool(include_worldcover=require_worldcover)
            if candidates is None
            else candidates.copy()
        )
        mask = eligible_candidate_mask(
            candidates,
            min_gap_distance_m=min_gap_distance_m,
            min_population_5km=min_population_5km,
            max_road_distance_m=max_road_distance_m,
            require_worldcover=require_worldcover,
        )
        eligible = candidates.loc[mask].copy()
        print(
            f"Candidate audit: {len(candidates):,} generated proposals; "
            f"{len(eligible):,} passed all strict source-data constraints."
        )
        if eligible.empty:
            result = add_reason_codes(eligible)
            if export:
                self._export(result)
            return result

        eligible = eligible.sort_values(
            ["planning_priority_score", "canonical_latitude", "canonical_longitude"],
            ascending=[False, True, True],
            kind="stable",
        )

        selected_indices = []
        selected_xy = []
        for index, row in eligible.iterrows():
            coordinate = np.array([row["utm_x"], row["utm_y"]])
            if all(np.linalg.norm(coordinate - prior) >= min_candidate_separation_m for prior in selected_xy):
                selected_indices.append(index)
                selected_xy.append(coordinate)
            if len(selected_indices) >= top_k:
                break

        result = eligible.loc[selected_indices].reset_index(drop=True)
        result.insert(0, "recommendation_rank", range(1, len(result) + 1))
        result.insert(1, "candidate_id", result.apply(candidate_id, axis=1))
        result = attach_h3_indexes(result)

        if add_worldcover_context:
            from antenna_cell_placement.worldcover import WorldCoverExtractor

            result = WorldCoverExtractor().add_h3_context(result)

        if add_building_context:
            from antenna_cell_placement.buildings import (
                add_building_context_if_available,
            )

            result = add_building_context_if_available(result)

        if add_osm_context:
            from antenna_cell_placement.osm_context import (
                add_osm_context_if_available,
            )

            result = add_osm_context_if_available(result)

        if add_ookla_context:
            from antenna_cell_placement.ookla import add_ookla_context_if_available

            result = add_ookla_context_if_available(result)

        from antenna_cell_placement.opencellid import annotate_candidates

        result = annotate_candidates(result)
        from antenna_cell_placement.collected_data import annotate_measurements
        result = annotate_measurements(result)
        result = add_reason_codes(result)
        output_columns = [
            "recommendation_rank",
            "candidate_id",
            "h3_r7",
            "h3_r6",
            "canonical_latitude",
            "canonical_longitude",
            "municipality_name",
            "nearest_settlement_name",
            "candidate_source",
            "planning_priority_score",
            "score_version",
            *SCORE_COMPONENT_COLUMNS,
            "reason_codes",
            "population_density_1km",
            "population_sum_5km",
            "dist_to_nearest_site_m",
            "dist_to_nearest_road_m",
            "elevation_m",
            "elevation_prominence_3km",
            "terrain_slope_deg",
            "worldcover_class_code",
            "worldcover_class_name",
            "worldcover_data_available",
            "worldcover_is_water",
            "worldcover_h3_coverage_pct",
            "worldcover_h3_dominant_class_code",
            "worldcover_h3_dominant_class_name",
            "worldcover_h3_water_fraction",
            "worldcover_h3_built_up_fraction",
            "worldcover_h3_bare_fraction",
            "worldcover_review_required",
            "osm_building_count_h3",
            "osm_building_footprint_area_m2_h3",
            "osm_building_coverage_ratio_h3",
            "osm_building_density_per_km2_h3",
            "osm_building_observed_h3",
            "osm_building_context_available",
            "osm_building_review_required",
            "osm_hospital_count_h3",
            "osm_hospital_observed_h3",
            "osm_hospital_nearest_distance_m",
            "osm_higher_education_count_h3",
            "osm_higher_education_observed_h3",
            "osm_higher_education_nearest_distance_m",
            "osm_aviation_count_h3",
            "osm_aviation_observed_h3",
            "osm_aviation_nearest_distance_m",
            "osm_industrial_count_h3",
            "osm_industrial_observed_h3",
            "osm_industrial_nearest_distance_m",
            "osm_selected_context_available",
            "ookla_download_mbps",
            "ookla_upload_mbps",
            "ookla_latency_ms",
            "ookla_test_count",
            "ookla_supporting_tile_quarters",
            "ookla_supported_quarters",
            "ookla_data_available",
            "ookla_review_required",
            "cloudflare_http_requests_share_52w_pct",
            "cloudflare_regional_demand_score",
            "cloudflare_data_available",
            "measurement_nearest_distance_m",
            "measurement_count_1km",
            *[column for column in result if column.startswith("measurement_mnc_")],
            "opencellid_any_distance_m",
            "opencellid_recent_distance_m",
            "opencellid_libyana_distance_m",
            "opencellid_almadar_distance_m",
            "opencellid_review_required",
        ]
        result = result[[column for column in output_columns if column in result]]
        if export:
            self._export(result)
        return result

    @staticmethod
    def _export(recommendations: pd.DataFrame) -> None:
        RECOMMENDATIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
        recommendations.to_csv(RECOMMENDATIONS_CSV, index=False)
        if recommendations.empty:
            RECOMMENDATIONS_GEOJSON.write_text(
                '{"type":"FeatureCollection","features":[]}\n', encoding="utf-8"
            )
            return
        geodata = gpd.GeoDataFrame(
            recommendations,
            geometry=[
                Point(lon, lat)
                for lon, lat in zip(
                    recommendations["canonical_longitude"],
                    recommendations["canonical_latitude"],
                )
            ],
            crs=CRS_WGS84,
        )
        geodata.to_file(RECOMMENDATIONS_GEOJSON, driver="GeoJSON")


def run_optimizer_pipeline() -> pd.DataFrame:
    """Generate and export the top dataset-only proposed placements."""
    recommendations = CellSiteOptimizer().find_priority_placements()
    print(f"Generated {len(recommendations)} proposed placements: {RECOMMENDATIONS_CSV}")
    return recommendations


if __name__ == "__main__":
    run_optimizer_pipeline()
