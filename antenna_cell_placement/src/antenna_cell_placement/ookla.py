"""Roadmap Step 12 gate for Ookla mobile-performance review evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely import make_valid
from shapely.geometry import Point

from antenna_cell_placement.config import (
    ADMIN2_GEOJSON_PATH,
    OOKLA_DIR,
    OOKLA_EVALUATION_REPORT,
    OOKLA_MANIFEST,
    OOKLA_TILES_GPKG,
    RECOMMENDATIONS_CSV,
)


MIN_TESTS_PER_TILE_QUARTER = 5
MIN_DEVICES_PER_TILE_QUARTER = 3
MIN_SUPPORTED_QUARTERS = 2
MIN_MUNICIPALITY_COVERAGE_PCT = 50.0
MIN_SHORTLIST_COVERAGE_PCT = 25.0
EXPECTED_PERIODS = ("2025Q2", "2025Q3", "2025Q4", "2026Q1")
OOKLA_COLUMNS = [
    "ookla_download_mbps",
    "ookla_upload_mbps",
    "ookla_latency_ms",
    "ookla_test_count",
    "ookla_supporting_tile_quarters",
    "ookla_supported_quarters",
    "ookla_data_available",
    "ookla_review_required",
]
REQUIRED_SOURCE_COLUMNS = {
    "avg_d_kbps",
    "avg_u_kbps",
    "avg_lat_ms",
    "tests",
    "devices",
    "quadkey",
    "quarter",
    "geometry",
}


def prepare_ookla_tiles(
    frame: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Validate source rows and apply the declared tile-quarter support filter."""
    missing = sorted(REQUIRED_SOURCE_COLUMNS - set(frame.columns))
    if missing:
        raise KeyError(f"Ookla source is missing required columns: {missing}")
    if frame.crs is None:
        raise ValueError("Ookla tiles must declare a CRS")
    result = frame.copy().to_crs("EPSG:4326")
    input_rows = len(result)
    missing_geometry = result.geometry.isna() | result.geometry.is_empty
    result = result.loc[~missing_geometry].copy()
    invalid_before = int((~result.geometry.is_valid).sum())
    if invalid_before:
        invalid = ~result.geometry.is_valid
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].map(
            make_valid
        )
    invalid_after = int((~result.geometry.is_valid).sum())
    result = result.loc[result.geometry.is_valid].copy()
    for column in ("avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    duplicate_rows = int(result.duplicated(["quarter", "quadkey"]).sum())
    result = result.drop_duplicates(["quarter", "quadkey"], keep="first")
    valid_metrics = (
        result[["avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"]]
        .notna()
        .all(axis=1)
        & result["avg_d_kbps"].gt(0)
        & result["avg_u_kbps"].gt(0)
        & result["avg_lat_ms"].gt(0)
        & result["tests"].gt(0)
        & result["devices"].gt(0)
    )
    supported = (
        valid_metrics
        & result["tests"].ge(MIN_TESTS_PER_TILE_QUARTER)
        & result["devices"].ge(MIN_DEVICES_PER_TILE_QUARTER)
    )
    result["support_eligible"] = supported
    points = result.to_crs("EPSG:3857").geometry.centroid.to_crs("EPSG:4326")
    result["h3_r7"] = [
        h3.latlng_to_cell(point.y, point.x, 7) for point in points
    ]
    quality = {
        "input_tile_quarter_rows": int(input_rows),
        "missing_or_empty_geometry_rows": int(missing_geometry.sum()),
        "invalid_geometry_rows_before_repair": invalid_before,
        "invalid_geometry_rows_after_repair": invalid_after,
        "duplicate_quarter_quadkey_rows_removed": duplicate_rows,
        "valid_metric_rows": int(valid_metrics.sum()),
        "supported_tile_quarter_rows": int(supported.sum()),
        "below_support_threshold_rows": int((valid_metrics & ~supported).sum()),
        "invalid_metric_rows": int((~valid_metrics).sum()),
        "valid_geometry_pct_after_repair": 100.0
        * float(result.geometry.is_valid.mean())
        if len(result)
        else 0.0,
    }
    return result.reset_index(drop=True), quality


def aggregate_supported_h3(tiles: gpd.GeoDataFrame) -> pd.DataFrame:
    """Aggregate supported tile-quarter observations without summing devices."""
    supported = tiles.loc[tiles["support_eligible"]].copy()
    if supported.empty:
        return pd.DataFrame(
            columns=[
                "h3_r7",
                "ookla_download_mbps",
                "ookla_upload_mbps",
                "ookla_latency_ms",
                "ookla_test_count",
                "ookla_supporting_tile_quarters",
                "ookla_supported_quarters",
            ]
        )
    rows = []
    for cell, group in supported.groupby("h3_r7", sort=True):
        weights = group["tests"].to_numpy(dtype=float)
        rows.append(
            {
                "h3_r7": str(cell),
                "ookla_download_mbps": float(
                    np.average(group["avg_d_kbps"], weights=weights) / 1000.0
                ),
                "ookla_upload_mbps": float(
                    np.average(group["avg_u_kbps"], weights=weights) / 1000.0
                ),
                "ookla_latency_ms": float(
                    np.average(group["avg_lat_ms"], weights=weights)
                ),
                "ookla_test_count": int(group["tests"].sum()),
                "ookla_supporting_tile_quarters": int(len(group)),
                "ookla_supported_quarters": int(group["quarter"].nunique()),
            }
        )
    return pd.DataFrame(rows)


class OoklaPerformanceExtractor:
    """Attach observed mobile performance to matching H3 planning units."""

    def __init__(self, tiles: gpd.GeoDataFrame | None = None):
        if tiles is None:
            if not OOKLA_TILES_GPKG.exists():
                raise FileNotFoundError(f"Ookla Libya subset is missing: {OOKLA_TILES_GPKG}")
            tiles = gpd.read_file(OOKLA_TILES_GPKG, layer="mobile_performance")
        self.tiles, self.quality = prepare_ookla_tiles(tiles)
        self.summary = aggregate_supported_h3(self.tiles)

    def add_context(self, candidates: pd.DataFrame) -> pd.DataFrame:
        if "h3_r7" not in candidates:
            raise KeyError("Candidates are missing Ookla join field: h3_r7")
        result = candidates.copy()
        existing = [column for column in OOKLA_COLUMNS if column in result]
        if existing:
            result = result.drop(columns=existing)
        result = result.merge(self.summary, on="h3_r7", how="left", validate="many_to_one")
        result["ookla_data_available"] = (
            result["ookla_supported_quarters"].ge(MIN_SUPPORTED_QUARTERS).fillna(False)
        )
        measurement_columns = [
            "ookla_download_mbps",
            "ookla_upload_mbps",
            "ookla_latency_ms",
            "ookla_test_count",
            "ookla_supporting_tile_quarters",
            "ookla_supported_quarters",
        ]
        result.loc[~result["ookla_data_available"], measurement_columns] = pd.NA
        result["ookla_review_required"] = result["ookla_data_available"] & result[
            "ookla_supported_quarters"
        ].lt(len(EXPECTED_PERIODS))
        return result


def add_ookla_context_if_available(frame: pd.DataFrame) -> pd.DataFrame:
    try:
        return OoklaPerformanceExtractor().add_context(frame)
    except (FileNotFoundError, OSError):
        result = frame.copy()
        for column in OOKLA_COLUMNS:
            result[column] = (
                False
                if column in {"ookla_data_available", "ookla_review_required"}
                else pd.NA
            )
        return result


def verify_ookla_manifest(
    manifest_path: Path = OOKLA_MANIFEST,
    data_dir: Path = OOKLA_DIR,
) -> dict[str, object]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Ookla manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    if manifest.get("license") != "CC-BY-NC-SA-4.0":
        failures.append("metadata:license")
    if tuple(manifest.get("periods", [])) != EXPECTED_PERIODS:
        failures.append("metadata:periods")
    records = [*manifest.get("source_files", []), manifest.get("libya_subset", {})]
    for record in records:
        path = data_dir / str(record.get("filename", ""))
        if not path.exists():
            failures.append(f"missing:{path.name}")
        elif path.stat().st_size != record.get("bytes"):
            failures.append(f"size:{path.name}")
        elif _file_sha256(path) != record.get("sha256"):
            failures.append(f"sha256:{path.name}")
    return {"manifest": manifest, "verified": not failures, "failures": failures}


def evaluate_ookla_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = OOKLA_EVALUATION_REPORT,
) -> dict[str, object]:
    """Run and persist the Step 12 before/after evidence gate."""
    verification_started = perf_counter()
    provenance = verify_ookla_manifest()
    verification_seconds = perf_counter() - verification_started
    if not provenance["verified"]:
        raise ValueError(f"Ookla source verification failed: {provenance['failures']}")
    if recommendations is None:
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    if recommendations.empty:
        raise ValueError("Ookla evaluation requires current recommendations")
    baseline = recommendations.drop(columns=OOKLA_COLUMNS, errors="ignore").copy()
    load_started = perf_counter()
    extractor = OoklaPerformanceExtractor()
    treatment = extractor.add_context(baseline)
    load_seconds = perf_counter() - load_started

    municipalities = gpd.read_file(ADMIN2_GEOJSON_PATH)[["adm2_name", "geometry"]]
    supported_tiles = extractor.tiles.loc[extractor.tiles["support_eligible"]].copy()
    supported_tiles.geometry = (
        supported_tiles.to_crs("EPSG:3857")
        .geometry.centroid.to_crs(supported_tiles.crs)
    )
    accepted_units = extractor.summary.loc[
        extractor.summary["ookla_supported_quarters"].ge(MIN_SUPPORTED_QUARTERS)
    ].copy()
    accepted_units = gpd.GeoDataFrame(
        accepted_units,
        geometry=[
            Point(longitude, latitude)
            for latitude, longitude in accepted_units["h3_r7"].map(h3.cell_to_latlng)
        ],
        crs="EPSG:4326",
    )
    municipality_units = gpd.sjoin(
        accepted_units,
        municipalities.to_crs(accepted_units.crs),
        predicate="within",
        how="left",
    )
    covered_municipalities = int(municipality_units["adm2_name"].nunique())
    municipality_coverage_pct = 100.0 * covered_municipalities / max(len(municipalities), 1)
    shortlist_available = int(treatment["ookla_data_available"].sum())
    shortlist_coverage_pct = 100.0 * shortlist_available / len(treatment)
    temporal_tiles = gpd.sjoin(
        supported_tiles,
        municipalities.to_crs(supported_tiles.crs),
        predicate="within",
        how="left",
    )
    temporal_stability = _quarterly_municipality_stability(temporal_tiles)
    core = ["candidate_id", "recommendation_rank", "planning_priority_score"]
    unchanged = baseline[core].equals(treatment[core])
    coverage_pass = (
        municipality_coverage_pct >= MIN_MUNICIPALITY_COVERAGE_PCT
        and shortlist_coverage_pct >= MIN_SHORTLIST_COVERAGE_PCT
    )
    status = "review-only" if coverage_pass else "remove"
    report = {
        "step": 12,
        "status": status,
        "decision": (
            "retain supported Ookla mobile observations as review context only; "
            "independent drive-test or operator KPI labels are unavailable"
            if coverage_pass
            else "exclude Ookla observations from runtime because geographic coverage failed"
        ),
        "question": (
            "Can supported mobile speed, latency, and test density add independent "
            "service-quality context?"
        ),
        "source": provenance["manifest"],
        "thresholds": {
            "minimum_tests_per_tile_quarter": MIN_TESTS_PER_TILE_QUARTER,
            "minimum_devices_per_tile_quarter": MIN_DEVICES_PER_TILE_QUARTER,
            "minimum_supported_quarters_per_h3": MIN_SUPPORTED_QUARTERS,
            "minimum_municipality_coverage_pct": MIN_MUNICIPALITY_COVERAGE_PCT,
            "minimum_shortlist_coverage_pct": MIN_SHORTLIST_COVERAGE_PCT,
        },
        "quality": extractor.quality,
        "coverage": {
            "municipality_count": int(len(municipalities)),
            "municipalities_with_supported_observation": covered_municipalities,
            "municipality_coverage_pct": municipality_coverage_pct,
            "shortlist_count": len(treatment),
            "shortlist_with_supported_observation": shortlist_available,
            "shortlist_coverage_pct": shortlist_coverage_pct,
            "supported_h3_units_any_quarter": int(len(extractor.summary)),
            "accepted_h3_units_at_least_two_quarters": int(len(accepted_units)),
        },
        "temporal_stability": temporal_stability,
        "before": {"shortlist_count": len(baseline), "ookla_fields": 0},
        "after": {
            "shortlist_count": len(treatment),
            "ookla_fields": len(OOKLA_COLUMNS),
        },
        "checks": {
            "scores_and_ranks_unchanged": bool(unchanged),
            "rank_stability_spearman": 1.0 if unchanged else 0.0,
            "municipality_coverage_pass": municipality_coverage_pct
            >= MIN_MUNICIPALITY_COVERAGE_PCT,
            "shortlist_coverage_pass": shortlist_coverage_pct
            >= MIN_SHORTLIST_COVERAGE_PCT,
            "independent_drive_test_or_kpi_labels_available": False,
            "predictive_improvement": None,
        },
        "runtime_seconds": {
            "source_hash_verification": verification_seconds,
            "load_validate_aggregate_and_join": load_seconds,
        },
        "limitations": [
            "Speedtest observations are self-selected and are not a random sample of users or geography.",
            "Device counts are unique only within one tile-quarter and are never summed as unique people.",
            "Missing or unsupported tiles remain missing and do not prove poor service or no coverage.",
            "Tile averages do not identify operator, radio technology, spectrum, congestion cause, or indoor conditions.",
            "No independent drive-test or operator KPI labels are available for geographic holdout validation.",
            "The license restricts use to non-commercial terms and requires attribution and share-alike distribution.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if status == "review-only":
        from antenna_cell_placement.site_optimizer import CellSiteOptimizer

        CellSiteOptimizer._export(treatment)
    return report


def _quarterly_municipality_stability(joined: gpd.GeoDataFrame) -> dict[str, object]:
    if joined.empty:
        return {"adjacent_quarter_download_spearman": {}, "median_spearman": None}
    grouped = (
        joined.groupby(["quarter", "adm2_name"], dropna=True)["avg_d_kbps"]
        .median()
        .unstack("quarter")
        .reindex(columns=EXPECTED_PERIODS)
    )
    correlations = {}
    for left, right in zip(EXPECTED_PERIODS, EXPECTED_PERIODS[1:]):
        value = grouped[left].corr(grouped[right], method="spearman")
        correlations[f"{left}_to_{right}"] = float(value) if pd.notna(value) else None
    valid = [value for value in correlations.values() if value is not None]
    return {
        "adjacent_quarter_download_spearman": correlations,
        "median_spearman": float(np.median(valid)) if valid else None,
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
