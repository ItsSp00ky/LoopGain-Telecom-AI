"""OpenStreetMap building context and the roadmap Step 9 evaluation gate."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pyogrio
from shapely import make_valid
from shapely.geometry import Polygon

from antenna_cell_placement.config import (
    ADMIN2_GEOJSON_PATH,
    BUILDINGS_EVALUATION_REPORT,
    CRS_WGS84,
    OSM_BUILDINGS_DIR,
    OSM_BUILDINGS_GPKG,
    POP_PLACES_GEOJSON_PATH,
    RECOMMENDATIONS_CSV,
)


SOURCE_URL = "https://download.geofabrik.de/africa/libya-260919-free.gpkg.zip"
SNAPSHOT_DATE = "2026-09-19"
LICENSE = "ODbL-1.0"
LICENSE_URL = "https://www.openstreetmap.org/copyright"
EQUAL_AREA_CRS = "EPSG:6933"
BUILDING_COLUMNS = [
    "osm_building_count_h3",
    "osm_building_footprint_area_m2_h3",
    "osm_building_coverage_ratio_h3",
    "osm_building_density_per_km2_h3",
    "osm_building_observed_h3",
    "osm_building_context_available",
    "osm_building_review_required",
]


def discover_building_layer(path: Path = OSM_BUILDINGS_GPKG) -> str:
    """Return the single Geofabrik building-outline layer in a GeoPackage."""
    layers = [name for name, _ in pyogrio.list_layers(path) if "buildings" in name]
    if len(layers) != 1:
        raise ValueError(f"Expected one building layer in {path}, found {layers}")
    return layers[0]


def prepare_buildings(
    buildings: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, int | float]]:
    """Validate, repair, and deduplicate source building polygons in memory."""
    if buildings.crs is None:
        raise ValueError("Building footprints must declare a CRS")
    source = buildings.copy()
    input_rows = len(source)
    missing_geometry = int(
        (source.geometry.isna() | source.geometry.is_empty).sum()
    )
    source = source.loc[source.geometry.notna() & ~source.geometry.is_empty].copy()
    invalid_before = int((~source.geometry.is_valid).sum())
    if invalid_before:
        invalid = ~source.geometry.is_valid
        source.loc[invalid, "geometry"] = source.loc[invalid, "geometry"].map(
            make_valid
        )
    source = source.explode(index_parts=False, ignore_index=True)
    source = source.loc[
        source.geometry.notna()
        & ~source.geometry.is_empty
        & source.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()
    polygon_parts_after_repair = len(source)
    invalid_after = int((~source.geometry.is_valid).sum())
    geometry_hash = source.geometry.to_wkb(hex=True)
    duplicate_geometry_rows = int(geometry_hash.duplicated().sum())
    source = source.loc[~geometry_hash.duplicated()].copy().reset_index(drop=True)
    source = source.to_crs(EQUAL_AREA_CRS)
    nonpositive_area = int((source.geometry.area <= 0).sum())
    source = source.loc[source.geometry.area > 0].copy().reset_index(drop=True)
    valid_geometry_pct = (
        100.0 * float(source.geometry.is_valid.mean()) if len(source) else 0.0
    )
    return source, {
        "input_rows": input_rows,
        "missing_or_empty_geometry_rows": missing_geometry,
        "invalid_geometry_rows_before_repair": invalid_before,
        "invalid_geometry_rows_after_repair": invalid_after,
        "polygon_parts_after_repair": polygon_parts_after_repair,
        "duplicate_geometry_rows_removed": duplicate_geometry_rows,
        "nonpositive_area_rows_removed": nonpositive_area,
        "retained_polygon_rows": len(source),
        "valid_geometry_pct_after_repair": valid_geometry_pct,
    }


def load_buildings(
    path: Path = OSM_BUILDINGS_GPKG,
    bbox: tuple[float, float, float, float] | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, int | float | str]]:
    """Load and quality-profile the dated OSM building layer."""
    if not path.exists():
        raise FileNotFoundError(f"OSM building source is missing: {path}")
    layer = discover_building_layer(path)
    frame = gpd.read_file(path, layer=layer, columns=[], bbox=bbox)
    prepared, quality = prepare_buildings(frame)
    quality["layer"] = layer
    quality["source_crs"] = str(frame.crs)
    return prepared, quality


class BuildingFootprintExtractor:
    """Attach observed building-footprint summaries to shortlisted H3 units."""

    def __init__(
        self,
        path: Path = OSM_BUILDINGS_GPKG,
        buildings: gpd.GeoDataFrame | None = None,
    ):
        if buildings is None:
            self.buildings, self.quality = load_buildings(path)
        else:
            self.buildings, self.quality = prepare_buildings(buildings)
        self.spatial_index = self.buildings.sindex

    @classmethod
    def for_h3_frame(
        cls,
        frame: pd.DataFrame,
        path: Path = OSM_BUILDINGS_GPKG,
        h3_column: str = "h3_r7",
    ) -> "BuildingFootprintExtractor":
        """Load only source geometries near the requested H3 cells."""
        if h3_column not in frame:
            raise KeyError(f"Missing H3 column for building summary: {h3_column}")
        layer = discover_building_layer(path)
        subsets = []
        for cell in frame[h3_column].dropna().astype(str).unique():
            polygon = Polygon(
                [
                    (longitude, latitude)
                    for latitude, longitude in h3.cell_to_boundary(cell)
                ]
            )
            subset = gpd.read_file(
                path,
                layer=layer,
                columns=[],
                bbox=polygon.bounds,
            )
            if not subset.empty:
                subsets.append(subset)
        if subsets:
            buildings = gpd.GeoDataFrame(
                pd.concat(subsets, ignore_index=True),
                geometry="geometry",
                crs=subsets[0].crs,
            )
        else:
            buildings = gpd.GeoDataFrame(
                geometry=gpd.GeoSeries([], crs=CRS_WGS84)
            )
        return cls(path=path, buildings=buildings)

    def add_h3_context(
        self,
        frame: pd.DataFrame,
        h3_column: str = "h3_r7",
    ) -> pd.DataFrame:
        """Add clipped building count and area statistics without changing rank."""
        if h3_column not in frame:
            raise KeyError(f"Missing H3 column for building summary: {h3_column}")
        result = frame.copy()
        summaries = {
            cell: self._summarize_cell(cell)
            for cell in result[h3_column].dropna().astype(str).unique()
        }
        for column in BUILDING_COLUMNS:
            result[column] = result[h3_column].map(
                lambda cell: summaries.get(str(cell), {}).get(column)
                if pd.notna(cell)
                else None
            )
        built_fraction = result.get(
            "worldcover_h3_built_up_fraction",
            pd.Series(index=result.index, dtype="float64"),
        )
        built_context = (
            pd.to_numeric(built_fraction, errors="coerce").fillna(0.0).gt(0.10)
        )
        point_built = result.get(
            "worldcover_class_code", pd.Series(index=result.index, dtype="float64")
        ).eq(50)
        result["osm_building_review_required"] = (
            (built_context | point_built)
            & ~result["osm_building_observed_h3"].fillna(False).astype(bool)
        )
        return result

    def _summarize_cell(self, cell: str) -> dict[str, int | float | bool]:
        polygon = Polygon(
            [(longitude, latitude) for latitude, longitude in h3.cell_to_boundary(cell)]
        )
        cell_geometry = gpd.GeoSeries([polygon], crs=CRS_WGS84).to_crs(
            EQUAL_AREA_CRS
        ).iloc[0]
        indices = self.spatial_index.query(cell_geometry, predicate="intersects")
        if len(indices):
            intersections = self.buildings.geometry.iloc[indices].intersection(
                cell_geometry
            )
            area_m2 = float(intersections.area.sum())
        else:
            area_m2 = 0.0
        cell_area_m2 = float(cell_geometry.area)
        count = int(len(indices))
        return {
            "osm_building_count_h3": count,
            "osm_building_footprint_area_m2_h3": round(area_m2, 2),
            "osm_building_coverage_ratio_h3": round(
                min(1.0, area_m2 / cell_area_m2), 6
            ),
            "osm_building_density_per_km2_h3": round(
                count / (cell_area_m2 / 1_000_000.0), 4
            ),
            "osm_building_observed_h3": count > 0,
            "osm_building_context_available": True,
            "osm_building_review_required": False,
        }


def add_building_context_if_available(frame: pd.DataFrame) -> pd.DataFrame:
    """Add context when installed and explicit unavailable fields otherwise."""
    if OSM_BUILDINGS_GPKG.exists():
        return BuildingFootprintExtractor.for_h3_frame(frame).add_h3_context(frame)
    result = frame.copy()
    for column in BUILDING_COLUMNS:
        if column in {
            "osm_building_observed_h3",
            "osm_building_context_available",
            "osm_building_review_required",
        }:
            result[column] = False
        else:
            result[column] = np.nan
    return result


def verify_manifest(data_dir: Path = OSM_BUILDINGS_DIR) -> dict[str, object]:
    """Verify Step 9 source metadata and file content hashes."""
    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Building manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    expected = {
        "source_url": SOURCE_URL,
        "snapshot_date": SNAPSHOT_DATE,
        "license": LICENSE,
        "license_url": LICENSE_URL,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            failures.append(f"metadata:{field}")
    for record in manifest.get("files", []):
        path = Path(data_dir) / record["filename"]
        if not path.exists():
            failures.append(f"missing:{record['filename']}")
        elif path.stat().st_size != record["bytes"]:
            failures.append(f"size:{record['filename']}")
        elif _file_sha256(path) != record["sha256"]:
            failures.append(f"sha256:{record['filename']}")
    if len(manifest.get("files", [])) != 2:
        failures.append("manifest:file_count")
    return {"manifest": manifest, "verified": not failures, "failures": failures}


def evaluate_buildings_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = BUILDINGS_EVALUATION_REPORT,
) -> dict[str, object]:
    """Run and persist the roadmap Step 9 before/after evaluation."""
    verification_started = perf_counter()
    provenance = verify_manifest()
    verification_seconds = perf_counter() - verification_started
    if not provenance["verified"]:
        raise ValueError(f"Building source verification failed: {provenance['failures']}")
    if recommendations is None:
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    if recommendations.empty:
        raise ValueError("Building evaluation requires current recommendations")
    baseline = recommendations.drop(columns=BUILDING_COLUMNS, errors="ignore").copy()

    profile_started = perf_counter()
    quality, municipality_metrics, settlement_metrics = _profile_national_source()
    profile_seconds = perf_counter() - profile_started
    load_started = perf_counter()
    extractor = BuildingFootprintExtractor.for_h3_frame(baseline)
    load_seconds = perf_counter() - load_started
    context_started = perf_counter()
    treatment = extractor.add_h3_context(baseline)
    context_seconds = perf_counter() - context_started

    core = ["candidate_id", "recommendation_rank", "planning_priority_score"]
    scores_and_ranks_unchanged = baseline[core].equals(treatment[core])
    observed_count = int(treatment["osm_building_observed_h3"].sum())
    reviewed_missing_count = int(treatment["osm_building_review_required"].sum())
    valid_geometry_pass = quality["valid_geometry_pct_after_repair"] >= 90.0

    checks = {
        "valid_geometry_pct_after_repair": quality[
            "valid_geometry_pct_after_repair"
        ],
        "municipalities_with_observed_buildings_pct": municipality_metrics[
            "municipalities_with_observed_buildings_pct"
        ],
        "populated_place_1km_observation_coverage_pct": settlement_metrics[
            "populated_place_1km_observation_coverage_pct"
        ],
        "shortlist_h3_context_available_pct": 100.0
        * float(treatment["osm_building_context_available"].mean()),
        "shortlist_h3_with_observed_buildings_pct": 100.0
        * observed_count
        / len(treatment),
        "shortlist_review_required_count": reviewed_missing_count,
        "scores_and_ranks_unchanged": scores_and_ranks_unchanged,
        "rank_stability_spearman": 1.0 if scores_and_ranks_unchanged else 0.0,
        "independent_reference_sample_available": False,
        "population_only_classification_improvement_pp": None,
    }
    acceptance = {
        "target_inhabited_area_coverage_at_least_95_pct": False,
        "valid_geometry_after_repair_at_least_90_pct": valid_geometry_pass,
        "independent_built_up_classification_improvement_at_least_5pp": False,
    }
    useful_context = valid_geometry_pass and observed_count > 0
    failed_cases = treatment.loc[
        ~treatment["osm_building_observed_h3"].fillna(False).astype(bool)
    ]
    report = {
        "step": 9,
        "status": "review-only" if useful_context else "revise",
        "decision": (
            "keep dated OSM building footprints as review context only; "
            "mapping completeness and independent accuracy remain unverified"
            if useful_context
            else "remove building footprints from runtime until source quality improves"
        ),
        "question": (
            "Do observed building footprints improve built-up demand and "
            "constructability context?"
        ),
        "source_policy": {
            "selected": "OpenStreetMap contributor-mapped building outlines via Geofabrik",
            "excluded": [
                "Microsoft Global ML Building Footprints",
                "Google Open Buildings",
            ],
            "reason": (
                "Machine-detected footprint products conflict with the project rule "
                "against generated evidence."
            ),
            "absence_semantics": (
                "A zero count means no mapped OSM footprint was observed; it does not "
                "mean that no building exists."
            ),
        },
        "source": provenance["manifest"],
        "quality": quality,
        "municipality_coverage": municipality_metrics,
        "settlement_coverage": settlement_metrics,
        "before": {
            "shortlist_count": len(baseline),
            "building_context_fields": 0,
        },
        "after": {
            "shortlist_count": len(treatment),
            "building_context_fields": len(BUILDING_COLUMNS),
            "shortlist_h3_with_observed_buildings": observed_count,
            "shortlist_review_required_count": reviewed_missing_count,
        },
        "checks": checks,
        "acceptance": acceptance,
        "failed_case_sample": [
            {
                "candidate_id": str(row["candidate_id"]),
                "recommendation_rank": int(row["recommendation_rank"]),
                "municipality_name": str(row["municipality_name"]),
                "worldcover_class_name": str(row["worldcover_class_name"]),
                "mapped_building_count_h3": int(row["osm_building_count_h3"]),
            }
            for _, row in failed_cases.head(10).iterrows()
        ],
        "runtime_seconds": {
            "source_hash_verification": verification_seconds,
            "national_streamed_quality_profile": profile_seconds,
            "shortlist_spatial_index_load": load_seconds,
            "shortlist_h3_context": context_seconds,
        },
        "limitations": [
            "OpenStreetMap building coverage is contributor-dependent and has no complete-coverage mask.",
            "The Geofabrik schema does not prove whether individual outlines were surveyed, traced, or imported.",
            "No independent pre-labeled Libya building sample is supplied, so precision, recall, and the five-point improvement gate are pending.",
            "Building observations do not establish ownership, structural condition, legal access, or constructability.",
            "Building fields remain outside the planning score.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    from antenna_cell_placement.site_optimizer import CellSiteOptimizer

    CellSiteOptimizer._export(treatment)
    return report


def _profile_national_source(
    path: Path = OSM_BUILDINGS_GPKG,
    chunk_size: int = 100_000,
) -> tuple[dict[str, object], dict[str, object], dict[str, int | float]]:
    """Stream the national layer to bound memory during the quality gate."""
    layer = discover_building_layer(path)
    info = pyogrio.read_info(path, layer=layer)
    municipalities = gpd.read_file(ADMIN2_GEOJSON_PATH)[
        ["adm2_name", "geometry"]
    ].to_crs(EQUAL_AREA_CRS)
    settlements = gpd.read_file(POP_PLACES_GEOJSON_PATH).to_crs(EQUAL_AREA_CRS)
    settlement_buffers = settlements.geometry.buffer(1000.0)
    settlement_observed = np.zeros(len(settlements), dtype=bool)
    counts: dict[str, int] = {}
    totals = {
        "input_rows": 0,
        "missing_or_empty_geometry_rows": 0,
        "invalid_geometry_rows_before_repair": 0,
        "invalid_geometry_rows_after_repair": 0,
        "polygon_parts_after_repair": 0,
        "duplicate_geometry_rows_removed": 0,
        "nonpositive_area_rows_removed": 0,
        "retained_polygon_rows": 0,
    }
    seen_geometry_hashes: set[int] = set()
    for offset in range(0, int(info["features"]), chunk_size):
        chunk = gpd.read_file(
            path,
            layer=layer,
            columns=[],
            skip_features=offset,
            max_features=chunk_size,
        )
        prepared, metrics = prepare_buildings(chunk)
        geometry_hashes = pd.util.hash_pandas_object(
            prepared.geometry.to_wkb(), index=False
        ).to_numpy(dtype=np.uint64)
        cross_chunk_duplicate = np.fromiter(
            (int(value) in seen_geometry_hashes for value in geometry_hashes),
            dtype=bool,
            count=len(geometry_hashes),
        )
        seen_geometry_hashes.update(
            int(value) for value in geometry_hashes[~cross_chunk_duplicate]
        )
        cross_chunk_duplicate_count = int(cross_chunk_duplicate.sum())
        if cross_chunk_duplicate_count:
            prepared = prepared.loc[~cross_chunk_duplicate].copy()
            metrics["duplicate_geometry_rows_removed"] += (
                cross_chunk_duplicate_count
            )
            metrics["retained_polygon_rows"] -= cross_chunk_duplicate_count
        for key in totals:
            totals[key] += int(metrics[key])
        points = prepared[["geometry"]].copy()
        points.geometry = points.geometry.representative_point()
        joined = gpd.sjoin(points, municipalities, predicate="within", how="left")
        for name, count in joined["adm2_name"].value_counts().items():
            counts[str(name)] = counts.get(str(name), 0) + int(count)
        index = prepared.sindex
        for position in np.flatnonzero(~settlement_observed):
            if len(index.query(settlement_buffers.iloc[position], predicate="intersects")):
                settlement_observed[position] = True

    retained = totals["retained_polygon_rows"]
    quality: dict[str, object] = {
        **totals,
        "valid_geometry_pct_after_repair": (
            100.0
            * (retained - totals["invalid_geometry_rows_after_repair"])
            / max(retained, 1)
        ),
        "layer": layer,
        "source_crs": str(info["crs"]),
        "processing_chunk_size": chunk_size,
    }
    municipality_count = len(municipalities)
    covered_count = int(municipalities["adm2_name"].isin(counts).sum())
    municipality_metrics = {
        "municipality_count": municipality_count,
        "municipalities_with_observed_buildings": covered_count,
        "municipalities_with_observed_buildings_pct": 100.0
        * covered_count
        / max(municipality_count, 1),
        "building_counts_by_municipality": {
            str(name): int(counts.get(name, 0))
            for name in sorted(municipalities["adm2_name"].dropna().unique())
        },
    }
    observed_count = int(settlement_observed.sum())
    settlement_metrics = {
        "populated_place_count": len(settlements),
        "populated_places_with_building_within_1km": observed_count,
        "populated_place_1km_observation_coverage_pct": 100.0
        * observed_count
        / max(len(settlements), 1),
    }
    return quality, municipality_metrics, settlement_metrics


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
