"""Roadmap Step 13 gate for VIIRS night-light demand evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from antenna_cell_placement.config import (
    RECOMMENDATIONS_CSV,
    VIIRS_DIR,
    VIIRS_EVALUATION_REPORT,
    VIIRS_FLARES_CSV,
    VIIRS_MANIFEST,
)


EXPECTED_MONTHS = ("202401", "202404", "202407", "202410")
MIN_CLOUD_FREE_OBSERVATIONS = 3
MIN_VALID_MONTHS = 3
MIN_SHORTLIST_COVERAGE_PCT = 95.0
MIN_TEMPORAL_SPEARMAN = 0.75
FLARE_EXCLUSION_RADIUS_KM = 5.0
MAX_ARTIFACT_PROMOTION_PCT = 5.0
HYPOTHETICAL_NIGHTLIGHT_WEIGHT = 0.10
NIGHTLIGHT_COLUMNS = [
    *(f"viirs_{month}_radiance" for month in EXPECTED_MONTHS),
    "viirs_median_radiance",
    "viirs_valid_months",
    "viirs_data_available",
    "viirs_nearest_flare_km",
    "viirs_flare_exclusion",
]


class NightLightsExtractor:
    """Sample monthly radiance while preserving darkness versus missing data."""

    def __init__(
        self,
        raster_pairs: dict[str, tuple[Path, Path]] | None = None,
        flare_sites: pd.DataFrame | None = None,
    ):
        self.raster_pairs = raster_pairs or _pairs_from_manifest()
        if tuple(self.raster_pairs) != EXPECTED_MONTHS:
            raise ValueError(f"Expected VIIRS months {EXPECTED_MONTHS}")
        if flare_sites is None:
            flare_sites = pd.read_csv(VIIRS_FLARES_CSV)
        required = {"latitude", "longitude"}
        if not required.issubset(flare_sites.columns):
            raise KeyError(f"Flare sites require columns: {sorted(required)}")
        self.flare_sites = flare_sites.copy()

    def add_context(self, candidates: pd.DataFrame) -> pd.DataFrame:
        required = {"canonical_latitude", "canonical_longitude"}
        missing = sorted(required - set(candidates.columns))
        if missing:
            raise KeyError(f"Candidates are missing VIIRS fields: {missing}")
        result = candidates.drop(columns=NIGHTLIGHT_COLUMNS, errors="ignore").copy()
        coordinates = list(
            zip(result["canonical_longitude"], result["canonical_latitude"])
        )
        valid_arrays = []
        for month, (radiance_path, coverage_path) in self.raster_pairs.items():
            radiance = _sample_raster(radiance_path, coordinates)
            coverage = _sample_raster(coverage_path, coordinates)
            valid = (
                np.isfinite(radiance)
                & np.isfinite(coverage)
                & (radiance >= 0)
                & (coverage >= MIN_CLOUD_FREE_OBSERVATIONS)
            )
            values = np.where(valid, radiance, np.nan)
            result[f"viirs_{month}_radiance"] = values
            valid_arrays.append(valid)
        matrix = result[
            [f"viirs_{month}_radiance" for month in EXPECTED_MONTHS]
        ].to_numpy(dtype=float)
        result["viirs_valid_months"] = np.sum(np.isfinite(matrix), axis=1)
        result["viirs_median_radiance"] = pd.DataFrame(matrix).median(
            axis=1, skipna=True
        ).to_numpy()
        water = result.get("worldcover_is_water", pd.Series(False, index=result.index))
        result["viirs_data_available"] = (
            result["viirs_valid_months"].ge(MIN_VALID_MONTHS) & ~water.fillna(False)
        )
        result.loc[~result["viirs_data_available"], "viirs_median_radiance"] = np.nan
        result["viirs_nearest_flare_km"] = _nearest_distance_km(
            result["canonical_latitude"].to_numpy(dtype=float),
            result["canonical_longitude"].to_numpy(dtype=float),
            self.flare_sites,
        )
        result["viirs_flare_exclusion"] = result["viirs_nearest_flare_km"].le(
            FLARE_EXCLUSION_RADIUS_KM
        )
        return result


def verify_viirs_manifest(
    manifest_path: Path = VIIRS_MANIFEST, data_dir: Path = VIIRS_DIR
) -> dict[str, object]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"VIIRS manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    if manifest.get("license") != "ODbL-1.0":
        failures.append("metadata:license")
    if tuple(manifest.get("periods", [])) != EXPECTED_MONTHS:
        failures.append("metadata:periods")
    records = []
    for product in manifest.get("products", []):
        records.extend([product.get("radiance", {}), product.get("cloudfree_count", {})])
    flare = manifest.get("gas_flare_catalog", {})
    records.extend([flare.get("source_record", {}), flare.get("libya_subset", {})])
    for record in records:
        path = data_dir / str(record.get("filename", ""))
        if not path.exists():
            failures.append(f"missing:{path.name}")
        elif path.stat().st_size != record.get("bytes"):
            failures.append(f"size:{path.name}")
        elif _file_sha256(path) != record.get("sha256"):
            failures.append(f"sha256:{path.name}")
    return {"manifest": manifest, "verified": not failures, "failures": failures}


def evaluate_viirs_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = VIIRS_EVALUATION_REPORT,
) -> dict[str, object]:
    """Evaluate VIIRS as an incremental proxy without changing production ranks."""
    provenance = verify_viirs_manifest()
    if not provenance["verified"]:
        raise ValueError(f"VIIRS source verification failed: {provenance['failures']}")
    if recommendations is None:
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    baseline = recommendations.drop(columns=NIGHTLIGHT_COLUMNS, errors="ignore").copy()
    if baseline.empty:
        raise ValueError("VIIRS evaluation requires current recommendations")
    treatment = NightLightsExtractor().add_context(baseline)
    available = treatment["viirs_data_available"] & ~treatment["viirs_flare_exclusion"]
    coverage_pct = 100.0 * float(available.mean())

    month_columns = [f"viirs_{month}_radiance" for month in EXPECTED_MONTHS]
    correlations = {}
    for left, right in zip(month_columns, month_columns[1:]):
        valid = treatment[left].notna() & treatment[right].notna()
        value = treatment.loc[valid, left].corr(treatment.loc[valid, right], method="spearman")
        correlations[f"{left[6:12]}_to_{right[6:12]}"] = (
            float(value) if pd.notna(value) else None
        )
    valid_stability = [value for value in correlations.values() if value is not None]
    median_stability = float(np.median(valid_stability)) if valid_stability else None

    analysis = treatment.loc[available].copy()
    population_correlation = _spearman_log(
        analysis["viirs_median_radiance"], analysis.get("population_sum_5km")
    )
    building_correlation = _spearman_log(
        analysis["viirs_median_radiance"], analysis.get("osm_building_density_per_km2_h3")
    )
    promotions, artifact_promotions = _hypothetical_promotions(treatment)
    artifact_promotion_pct = (
        100.0 * artifact_promotions / promotions if promotions else 0.0
    )
    coverage_pass = coverage_pct >= MIN_SHORTLIST_COVERAGE_PCT
    stability_pass = median_stability is not None and median_stability >= MIN_TEMPORAL_SPEARMAN
    artifact_pass = artifact_promotion_pct <= MAX_ARTIFACT_PROMOTION_PCT
    status = "remove"
    report = {
        "step": 13,
        "status": status,
        "decision": (
            "exclude VIIRS from runtime scoring and outputs: independent activity/KPI "
            "labels are unavailable, so incremental holdout improvement cannot be shown"
        ),
        "question": "Does night activity identify demand missed by population and buildings?",
        "source": provenance["manifest"],
        "thresholds": {
            "minimum_cloud_free_observations_per_month": MIN_CLOUD_FREE_OBSERVATIONS,
            "minimum_valid_months": MIN_VALID_MONTHS,
            "minimum_shortlist_coverage_pct": MIN_SHORTLIST_COVERAGE_PCT,
            "minimum_temporal_spearman": MIN_TEMPORAL_SPEARMAN,
            "gas_flare_exclusion_radius_km": FLARE_EXCLUSION_RADIUS_KM,
            "maximum_artifact_promotion_pct": MAX_ARTIFACT_PROMOTION_PCT,
            "hypothetical_nightlight_weight": HYPOTHETICAL_NIGHTLIGHT_WEIGHT,
        },
        "coverage": {
            "shortlist_count": int(len(treatment)),
            "valid_before_flare_exclusion": int(treatment["viirs_data_available"].sum()),
            "within_known_flare_exclusion": int(treatment["viirs_flare_exclusion"].sum()),
            "valid_after_flare_exclusion": int(available.sum()),
            "shortlist_coverage_pct": coverage_pct,
            "water_candidates_excluded": int(
                treatment.get("worldcover_is_water", pd.Series(False, index=treatment.index))
                .fillna(False).sum()
            ),
        },
        "temporal_stability": {
            "selected_month_spearman": correlations,
            "median_spearman": median_stability,
        },
        "redundancy": {
            "spearman_log_radiance_vs_log_population_5km": population_correlation,
            "spearman_log_radiance_vs_log_building_density": building_correlation,
        },
        "artifact_test": {
            "hypothetical_top10_promotions": promotions,
            "promotions_within_5km_known_gas_flare": artifact_promotions,
            "artifact_promotion_pct": artifact_promotion_pct,
        },
        "before": {"shortlist_count": int(len(baseline)), "viirs_fields": 0},
        "after_experiment": {
            "shortlist_count": int(len(treatment)),
            "viirs_fields": len(NIGHTLIGHT_COLUMNS),
            "production_export_changed": False,
        },
        "checks": {
            "shortlist_coverage_pass": coverage_pass,
            "temporal_stability_pass": stability_pass,
            "artifact_false_promotion_pass": artifact_pass,
            "independent_activity_or_kpi_labels_available": False,
            "geographic_holdout_improvement": None,
            "production_scores_and_ranks_unchanged": True,
        },
        "limitations": [
            "Night lights are a demand proxy, not observed mobile traffic, coverage, or service quality.",
            "The four-month median reduces transient influence but is not an active-fire mask.",
            "The official 2024 gas-flare catalog supports a 5 km exclusion but cannot identify every industrial light source.",
            "Monthly zero radiance is used only when cloud-free coverage meets the declared threshold; unsupported pixels remain missing.",
            "No independent activity, operator KPI, or reviewed planning labels exist for holdout validation.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _pairs_from_manifest() -> dict[str, tuple[Path, Path]]:
    manifest = json.loads(VIIRS_MANIFEST.read_text(encoding="utf-8"))
    return {
        product["month"]: (
            VIIRS_DIR / product["radiance"]["filename"],
            VIIRS_DIR / product["cloudfree_count"]["filename"],
        )
        for product in manifest["products"]
    }


def _sample_raster(path: Path, coordinates: list[tuple[float, float]]) -> np.ndarray:
    with rasterio.open(path) as source:
        values = np.array([sample[0] for sample in source.sample(coordinates)], dtype=float)
        if source.nodata is not None:
            values[np.isclose(values, source.nodata)] = np.nan
    return values


def _nearest_distance_km(
    latitude: np.ndarray, longitude: np.ndarray, flare_sites: pd.DataFrame
) -> np.ndarray:
    if flare_sites.empty:
        return np.full(len(latitude), np.inf)
    lat1 = np.radians(latitude)[:, None]
    lon1 = np.radians(longitude)[:, None]
    lat2 = np.radians(flare_sites["latitude"].to_numpy(dtype=float))[None, :]
    lon2 = np.radians(flare_sites["longitude"].to_numpy(dtype=float))[None, :]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(value, 0, 1))).min(axis=1)


def _spearman_log(left: pd.Series, right: pd.Series | None) -> float | None:
    if right is None:
        return None
    valid = left.notna() & right.notna()
    value = np.log1p(left[valid]).corr(np.log1p(right[valid]), method="spearman")
    return float(value) if pd.notna(value) else None


def _hypothetical_promotions(frame: pd.DataFrame) -> tuple[int, int]:
    eligible = frame["viirs_data_available"]
    percentile = pd.Series(np.nan, index=frame.index)
    percentile.loc[eligible] = frame.loc[eligible, "viirs_median_radiance"].rank(pct=True) * 100
    score = (
        (1 - HYPOTHETICAL_NIGHTLIGHT_WEIGHT) * frame["planning_priority_score"]
        + HYPOTHETICAL_NIGHTLIGHT_WEIGHT * percentile.fillna(0)
    )
    baseline_top = set(frame.nsmallest(10, "recommendation_rank").index)
    treatment_top = set(score.nlargest(min(10, len(score))).index)
    promoted = treatment_top - baseline_top
    artifacts = int(frame.loc[list(promoted), "viirs_flare_exclusion"].sum()) if promoted else 0
    return len(promoted), artifacts


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
