"""Roadmap Step 10 audit for explicit OpenStreetMap building heights."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from time import perf_counter

import geopandas as gpd
import h3
import pandas as pd
import pyogrio

from antenna_cell_placement.buildings import LICENSE, LICENSE_URL, SNAPSHOT_DATE
from antenna_cell_placement.config import (
    ADMIN2_GEOJSON_PATH,
    BUILDING_HEIGHT_EVALUATION_REPORT,
    OSM_HEIGHT_MANIFEST,
    OSM_HEIGHT_PBF,
    RECOMMENDATIONS_CSV,
)


HEIGHT_SOURCE_URL = "https://download.geofabrik.de/africa/libya-260919.osm.pbf"
OSM_LAYER = "multipolygons"
MIN_PLAUSIBLE_HEIGHT_M = 1.0
MAX_PLAUSIBLE_HEIGHT_M = 500.0
MIN_NATIONAL_HEIGHT_COVERAGE_PCT = 50.0
MIN_MUNICIPALITY_COVERAGE_PCT = 95.0
MAX_INDEPENDENT_MEDIAN_ERROR_M = 3.0

_TAG_VALUE = r'"((?:\\.|[^"\\])*)"'
_METRES = re.compile(
    r"^([0-9]+(?:\.[0-9]+)?)\s*(?:m|metre|metres|meter|meters)?$",
    re.IGNORECASE,
)
_FEET = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*(?:ft|feet|foot)$", re.IGNORECASE)
_FEET_INCHES = re.compile(r"^([0-9]+)'\s*([0-9]+(?:\.[0-9]+)?)?\s*(?:\"|in)?$")


def extract_osm_tag(other_tags: object, key: str) -> str | None:
    """Extract one value from GDAL's OSM hstore-like other_tags field."""
    if not isinstance(other_tags, str):
        return None
    match = re.search(r'(?:^|,)"' + re.escape(key) + r'"=>' + _TAG_VALUE, other_tags)
    if match is None:
        return None
    return match.group(1).replace(r'\"', '"').replace("\\\\", "\\")


def parse_height_m(value: object) -> tuple[float | None, str]:
    """Parse explicit OSM height units without deriving height from floor count."""
    if not isinstance(value, str) or not value.strip():
        return None, "missing"
    normalized = value.strip()
    match = _METRES.fullmatch(normalized)
    if match:
        height = float(match.group(1))
        unit = "metres"
    else:
        match = _FEET.fullmatch(normalized)
        if match:
            height = float(match.group(1)) * 0.3048
            unit = "feet"
        else:
            match = _FEET_INCHES.fullmatch(normalized)
            if not match:
                return None, "invalid_format"
            feet = float(match.group(1))
            inches = float(match.group(2) or 0.0)
            if inches >= 12:
                return None, "invalid_format"
            height = feet * 0.3048 + inches * 0.0254
            unit = "feet_inches"
    if not math.isfinite(height) or not (
        MIN_PLAUSIBLE_HEIGHT_M <= height <= MAX_PLAUSIBLE_HEIGHT_M
    ):
        return None, "outside_plausible_range"
    return height, unit


def prepare_height_tags(frame: pd.DataFrame) -> pd.DataFrame:
    """Parse explicit height metadata while retaining all source values."""
    result = frame.copy()
    result["height_raw"] = result["other_tags"].map(
        lambda tags: extract_osm_tag(tags, "height")
    )
    parsed = result["height_raw"].map(parse_height_m)
    result["height_m"] = parsed.map(lambda item: item[0])
    result["height_parse_status"] = parsed.map(lambda item: item[1])
    result["height_source_raw"] = result["other_tags"].map(
        lambda tags: extract_osm_tag(tags, "source:height")
    )
    result["height_accuracy_raw"] = result["other_tags"].map(
        lambda tags: extract_osm_tag(tags, "height:accuracy")
    )
    return result


def verify_height_manifest(
    manifest_path: Path = OSM_HEIGHT_MANIFEST,
    source_path: Path = OSM_HEIGHT_PBF,
) -> dict[str, object]:
    """Verify Step 10 metadata and the raw PBF content hash."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Building-height manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    expected = {
        "source_url": HEIGHT_SOURCE_URL,
        "snapshot_date": SNAPSHOT_DATE,
        "license": LICENSE,
        "license_url": LICENSE_URL,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            failures.append(f"metadata:{field}")
    record = manifest.get("file", {})
    if record.get("filename") != source_path.name:
        failures.append("metadata:filename")
    if not source_path.exists():
        failures.append(f"missing:{source_path.name}")
    elif source_path.stat().st_size != record.get("bytes"):
        failures.append(f"size:{source_path.name}")
    elif _file_sha256(source_path) != record.get("sha256"):
        failures.append(f"sha256:{source_path.name}")
    return {"manifest": manifest, "verified": not failures, "failures": failures}


def evaluate_building_height_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = BUILDING_HEIGHT_EVALUATION_REPORT,
) -> dict[str, object]:
    """Profile explicit height evidence and persist the Step 10 decision."""
    verification_started = perf_counter()
    provenance = verify_height_manifest()
    verification_seconds = perf_counter() - verification_started
    if not provenance["verified"]:
        raise ValueError(f"Height source verification failed: {provenance['failures']}")

    if recommendations is None:
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    baseline = recommendations.copy(deep=True)

    profile_started = perf_counter()
    raw = pyogrio.read_dataframe(
        OSM_HEIGHT_PBF,
        layer=OSM_LAYER,
        columns=["osm_id", "osm_way_id", "building", "other_tags"],
        where='building IS NOT NULL AND other_tags LIKE \'%"height"=>%\'',
    )
    heights = prepare_height_tags(raw)
    levels = pyogrio.read_dataframe(
        OSM_HEIGHT_PBF,
        layer=OSM_LAYER,
        columns=["osm_id", "osm_way_id", "building", "other_tags"],
        read_geometry=False,
        where='building IS NOT NULL AND other_tags LIKE \'%"building:levels"=>%\'',
    )
    profile_seconds = perf_counter() - profile_started

    heights["osm_object_id"] = _osm_object_ids(heights)
    duplicate_objects = int(heights["osm_object_id"].duplicated().sum())
    heights = heights.drop_duplicates("osm_object_id").copy()
    valid = heights.loc[heights["height_m"].notna()].copy()
    valid_geometry = valid.loc[
        valid.geometry.notna() & ~valid.geometry.is_empty & valid.geometry.is_valid
    ].copy()

    footprint_count = int(provenance["manifest"]["reference_building_feature_count"])
    national_coverage_pct = 100.0 * len(valid) / max(footprint_count, 1)
    municipality_metrics = _municipality_coverage(valid_geometry)
    shortlist_metrics = _shortlist_coverage(valid_geometry, baseline)
    source_declared = valid["height_source_raw"].notna()
    parse_counts = Counter(heights["height_parse_status"].astype(str))

    acceptance = {
        "national_building_height_coverage_at_least_50_pct": (
            national_coverage_pct >= MIN_NATIONAL_HEIGHT_COVERAGE_PCT
        ),
        "municipality_coverage_at_least_95_pct": (
            municipality_metrics["municipalities_with_valid_height_pct"]
            >= MIN_MUNICIPALITY_COVERAGE_PCT
        ),
        "independent_median_absolute_error_at_most_3m": False,
        "rf_or_kpi_improvement_demonstrated": False,
    }
    output_unchanged = baseline.equals(recommendations)
    report = {
        "step": 10,
        "status": "remove",
        "decision": (
            "exclude building height from runtime outputs and scoring; explicit height "
            "coverage is sparse and no independent reference or RF truth is supplied"
        ),
        "question": (
            "Does independently supported vertical form improve planning context "
            "beyond mapped footprints?"
        ),
        "source": provenance["manifest"],
        "source_policy": {
            "accepted_for_audit": "explicit OpenStreetMap height tags only",
            "excluded": [
                "height inferred from building:levels",
                "Microsoft machine-learned building height",
                "other remotely inferred or generated height products",
            ],
            "reason": (
                "The project prohibits generated evidence and has no supplied floor-height "
                "assumption or independent height labels."
            ),
        },
        "quality": {
            "explicit_height_tag_rows": int(len(raw)),
            "duplicate_osm_objects_removed": duplicate_objects,
            "valid_explicit_height_rows": int(len(valid)),
            "valid_geometry_rows": int(len(valid_geometry)),
            "invalid_geometry_rows": int(len(valid) - len(valid_geometry)),
            "building_levels_tag_rows_profiled_only": int(len(levels)),
            "height_parse_status_counts": dict(sorted(parse_counts.items())),
            "height_unit_counts": dict(
                sorted(
                    Counter(
                        heights.loc[heights["height_m"].notna(), "height_parse_status"]
                    ).items()
                )
            ),
            "height_source_declared_rows": int(source_declared.sum()),
            "height_source_missing_rows": int((~source_declared).sum()),
            "height_source_values": {
                str(key): int(value)
                for key, value in valid.loc[source_declared, "height_source_raw"]
                .value_counts()
                .head(20)
                .items()
            },
            "height_m_min": _optional_stat(valid["height_m"], "min"),
            "height_m_median": _optional_stat(valid["height_m"], "median"),
            "height_m_p90": _optional_stat(valid["height_m"], "quantile", 0.9),
            "height_m_max": _optional_stat(valid["height_m"], "max"),
        },
        "coverage": {
            "reference_building_footprint_count": footprint_count,
            "buildings_with_valid_explicit_height": int(len(valid)),
            "national_building_height_coverage_pct": national_coverage_pct,
            **municipality_metrics,
            **shortlist_metrics,
        },
        "before": {
            "shortlist_count": int(len(baseline)),
            "height_fields_in_runtime_output": 0,
        },
        "after": {
            "shortlist_count": int(len(recommendations)),
            "height_fields_in_runtime_output": 0,
            "runtime_integration_rejected": True,
        },
        "checks": {
            "recommendation_output_unchanged": output_unchanged,
            "independent_reference_sample_available": False,
            "independent_median_absolute_error_m": None,
            "rf_or_kpi_truth_available": False,
            "rf_or_kpi_improvement": None,
        },
        "acceptance": acceptance,
        "runtime_seconds": {
            "source_hash_verification": verification_seconds,
            "height_and_levels_profile": profile_seconds,
        },
        "limitations": [
            "Most explicit OSM height tags do not declare how the value was obtained.",
            "OpenStreetMap contributor coverage is uneven and has no completeness mask.",
            "No independent Libya height reference is supplied for error measurement.",
            "No RF or KPI truth is supplied for testing added planning value.",
            "Floor counts are not converted into height because that requires an assumption.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _osm_object_ids(frame: pd.DataFrame) -> pd.Series:
    return frame.apply(
        lambda row: (
            f"r{row['osm_id']}" if pd.notna(row["osm_id"]) else f"w{row['osm_way_id']}"
        ),
        axis=1,
    )


def _municipality_coverage(valid: gpd.GeoDataFrame) -> dict[str, object]:
    municipalities = gpd.read_file(ADMIN2_GEOJSON_PATH)[
        ["adm2_name", "geometry"]
    ].to_crs(valid.crs)
    if valid.empty:
        counts = pd.Series(dtype="int64")
    else:
        points = valid[["geometry"]].copy()
        points.geometry = points.geometry.representative_point()
        joined = gpd.sjoin(points, municipalities, predicate="within", how="left")
        counts = joined["adm2_name"].value_counts()
    covered = int(municipalities["adm2_name"].isin(counts.index).sum())
    return {
        "municipality_count": int(len(municipalities)),
        "municipalities_with_valid_height": covered,
        "municipalities_with_valid_height_pct": 100.0
        * covered
        / max(len(municipalities), 1),
        "valid_height_counts_by_municipality": {
            str(name): int(counts.get(name, 0))
            for name in sorted(municipalities["adm2_name"].dropna().unique())
        },
    }


def _shortlist_coverage(
    valid: gpd.GeoDataFrame, recommendations: pd.DataFrame
) -> dict[str, int | float]:
    shortlist_cells = set(recommendations["h3_r7"].dropna().astype(str))
    if valid.empty:
        observed_cells: set[str] = set()
    else:
        points = valid.geometry.representative_point()
        observed_cells = {
            h3.latlng_to_cell(point.y, point.x, 7)
            for point in points
            if point is not None and not point.is_empty
        }
    covered = len(shortlist_cells & observed_cells)
    return {
        "shortlist_h3_count": len(shortlist_cells),
        "shortlist_h3_with_valid_height": covered,
        "shortlist_h3_with_valid_height_pct": 100.0
        * covered
        / max(len(shortlist_cells), 1),
    }


def _optional_stat(series: pd.Series, method: str, *args: float) -> float | None:
    if series.empty:
        return None
    return float(getattr(series, method)(*args))


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
