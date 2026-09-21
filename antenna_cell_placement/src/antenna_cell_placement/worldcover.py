"""ESA WorldCover sampling and the roadmap Step 8 evaluation gate."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from time import perf_counter

import h3
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as raster_mask
from shapely import union_all
from shapely.geometry import Polygon, box, mapping

from antenna_cell_placement.config import (
    ADMIN0_GEOJSON_PATH,
    WORLDCOVER_DIR,
    WORLDCOVER_EVALUATION_REPORT,
)
from antenna_cell_placement.population import pixel_areas_km2_by_row


WORLDCOVER_VERSION = "ESA WorldCover 10 m 2021 v200"
WORLDCOVER_DOI = "https://doi.org/10.5281/zenodo.7254221"
WORLDCOVER_LICENSE = "CC-BY-4.0"
WORLDCOVER_BASE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
)
WATER_CLASS_CODE = 80
CLASS_LEGEND = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def tile_name(south: int, west: int) -> str:
    """Return the official filename for a three-degree WorldCover tile."""
    latitude = f"{'N' if south >= 0 else 'S'}{abs(south):02d}"
    longitude = f"{'E' if west >= 0 else 'W'}{abs(west):03d}"
    return f"ESA_WorldCover_10m_2021_v200_{latitude}{longitude}_Map.tif"


def tile_name_for_coordinate(latitude: float, longitude: float) -> str:
    """Return the WorldCover tile containing a WGS84 coordinate."""
    south = math.floor(latitude / 3.0) * 3
    west = math.floor(longitude / 3.0) * 3
    return tile_name(south, west)


def tile_names_for_bounds(bounds: tuple[float, float, float, float]) -> list[str]:
    """Return every WorldCover tile touched by geographic bounds."""
    min_lon, min_lat, max_lon, max_lat = bounds
    names = []
    for south in range(
        math.floor(min_lat / 3.0) * 3,
        math.floor(max_lat / 3.0) * 3 + 1,
        3,
    ):
        for west in range(
            math.floor(min_lon / 3.0) * 3,
            math.floor(max_lon / 3.0) * 3 + 1,
            3,
        ):
            names.append(tile_name(south, west))
    return sorted(set(names))


class WorldCoverExtractor:
    """Sample local classes and summarize observed land cover by H3 cell."""

    def __init__(self, data_dir: Path = WORLDCOVER_DIR):
        self.data_dir = Path(data_dir)

    def add_point_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Attach WorldCover class fields while preserving row order."""
        required = {"canonical_latitude", "canonical_longitude"}
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise KeyError(f"Missing coordinate columns for WorldCover: {missing}")

        result = frame.copy()
        class_codes = pd.Series(pd.NA, index=result.index, dtype="Int64")
        groups: dict[str, list[object]] = {}
        for index, row in result.iterrows():
            latitude = pd.to_numeric(row["canonical_latitude"], errors="coerce")
            longitude = pd.to_numeric(row["canonical_longitude"], errors="coerce")
            if not np.isfinite(latitude) or not np.isfinite(longitude):
                continue
            name = tile_name_for_coordinate(float(latitude), float(longitude))
            groups.setdefault(name, []).append(index)

        for name, indices in groups.items():
            path = self.data_dir / name
            if not path.exists():
                continue
            coordinates = [
                (
                    float(result.at[index, "canonical_longitude"]),
                    float(result.at[index, "canonical_latitude"]),
                )
                for index in indices
            ]
            with rasterio.open(path) as source:
                samples = source.sample(coordinates, indexes=1, masked=True)
                for index, sample in zip(indices, samples):
                    value = sample[0]
                    if np.ma.is_masked(value):
                        continue
                    code = int(value)
                    if code in CLASS_LEGEND:
                        class_codes.at[index] = code

        result["worldcover_class_code"] = class_codes
        result["worldcover_class_name"] = class_codes.map(CLASS_LEGEND).astype("string")
        result["worldcover_data_available"] = class_codes.notna()
        result["worldcover_is_water"] = class_codes.eq(WATER_CLASS_CODE).fillna(False)
        return result

    def add_h3_context(self, frame: pd.DataFrame, h3_column: str = "h3_r7") -> pd.DataFrame:
        """Attach area-weighted land-cover proportions for shortlist H3 cells."""
        if h3_column not in frame:
            raise KeyError(f"Missing H3 column for WorldCover summary: {h3_column}")
        result = frame.copy()
        summaries: dict[str, dict[str, object]] = {}
        sources: dict[str, rasterio.io.DatasetReader] = {}
        try:
            for cell in result[h3_column].dropna().astype(str).unique():
                polygon = Polygon(
                    [(longitude, latitude) for latitude, longitude in h3.cell_to_boundary(cell)]
                )
                summaries[cell] = self._summarize_polygon(polygon, cell, sources)
        finally:
            for source in sources.values():
                source.close()

        fields = [
            "worldcover_h3_coverage_pct",
            "worldcover_h3_dominant_class_code",
            "worldcover_h3_dominant_class_name",
            "worldcover_h3_water_fraction",
            "worldcover_h3_built_up_fraction",
            "worldcover_h3_bare_fraction",
            "worldcover_review_required",
        ]
        for field in fields:
            result[field] = result[h3_column].map(
                lambda cell: summaries.get(str(cell), {}).get(field)
                if pd.notna(cell)
                else None
            )
        result["worldcover_h3_dominant_class_code"] = pd.array(
            result["worldcover_h3_dominant_class_code"], dtype="Int64"
        )
        result["worldcover_review_required"] = (
            result["worldcover_review_required"].fillna(True).astype(bool)
        )
        return result

    def _summarize_polygon(
        self,
        polygon: Polygon,
        cell: str,
        sources: dict[str, rasterio.io.DatasetReader],
    ) -> dict[str, object]:
        class_areas: dict[int, float] = {}
        for name in tile_names_for_bounds(polygon.bounds):
            path = self.data_dir / name
            if not path.exists():
                continue
            source = sources.get(name)
            if source is None:
                source = rasterio.open(path)
                sources[name] = source
            try:
                masked, transform = raster_mask(
                    source, [mapping(polygon)], crop=True, filled=False, indexes=1
                )
            except ValueError:
                continue
            values = np.asarray(masked.data)
            valid = ~np.ma.getmaskarray(masked) & np.isin(values, tuple(CLASS_LEGEND))
            if not valid.any():
                continue
            row_areas = pixel_areas_km2_by_row(transform, values.shape[0])
            weights = np.broadcast_to(row_areas[:, None], values.shape)
            for code in np.unique(values[valid]):
                code_int = int(code)
                class_areas[code_int] = class_areas.get(code_int, 0.0) + float(
                    weights[valid & (values == code)].sum()
                )

        classified_area = float(sum(class_areas.values()))
        cell_area = float(h3.cell_area(cell, unit="km^2"))
        coverage = min(100.0, 100.0 * classified_area / cell_area) if cell_area else 0.0
        dominant = max(class_areas, key=class_areas.get) if class_areas else None

        def fraction(code: int) -> float | None:
            if not classified_area:
                return None
            return class_areas.get(code, 0.0) / classified_area

        water_fraction = fraction(WATER_CLASS_CODE)
        return {
            "worldcover_h3_coverage_pct": round(coverage, 4),
            "worldcover_h3_dominant_class_code": dominant,
            "worldcover_h3_dominant_class_name": CLASS_LEGEND.get(dominant),
            "worldcover_h3_water_fraction": _round_optional(water_fraction),
            "worldcover_h3_built_up_fraction": _round_optional(fraction(50)),
            "worldcover_h3_bare_fraction": _round_optional(fraction(60)),
            "worldcover_review_required": coverage < 98.0
            or water_fraction is None
            or water_fraction > 0.20,
        }


def verify_manifest(data_dir: Path = WORLDCOVER_DIR) -> dict[str, object]:
    """Verify that every manifest tile is present and content-addressed."""
    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"WorldCover manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    expected_metadata = {
        "dataset": WORLDCOVER_VERSION,
        "doi": WORLDCOVER_DOI,
        "license": WORLDCOVER_LICENSE,
        "source_base_url": WORLDCOVER_BASE_URL,
    }
    for field, expected in expected_metadata.items():
        if manifest.get(field) != expected:
            failures.append(f"metadata:{field}")
    records = manifest.get("tiles", [])
    if manifest.get("tile_count") != len(records):
        failures.append("manifest:tile_count")
    if manifest.get("total_bytes") != sum(
        int(record.get("bytes", 0)) for record in records
    ):
        failures.append("manifest:total_bytes")
    for record in records:
        path = Path(data_dir) / record["filename"]
        if not path.exists():
            failures.append(f"missing:{record['filename']}")
            continue
        if path.stat().st_size != record["bytes"]:
            failures.append(f"size:{record['filename']}")
            continue
        if _file_sha256(path) != record["sha256"]:
            failures.append(f"sha256:{record['filename']}")
    return {
        "manifest": manifest,
        "verified": not failures,
        "failures": failures,
    }


def evaluate_worldcover_gate(
    output_path: Path = WORLDCOVER_EVALUATION_REPORT,
) -> dict[str, object]:
    """Run and persist the roadmap Step 8 before/after evaluation."""
    from antenna_cell_placement.site_optimizer import (
        CellSiteOptimizer,
        eligible_candidate_mask,
    )

    verification_started = perf_counter()
    provenance = verify_manifest()
    verification_seconds = perf_counter() - verification_started
    if not provenance["verified"]:
        raise ValueError(f"WorldCover source verification failed: {provenance['failures']}")

    optimizer = CellSiteOptimizer()
    grid = optimizer.generate_candidate_grid()
    baseline_started = perf_counter()
    baseline_pool = optimizer.evaluate_coordinates(
        grid["canonical_longitude"].tolist(),
        grid["canonical_latitude"].tolist(),
        include_worldcover=False,
    )
    baseline_pool["candidate_source"] = grid["candidate_source"].values
    baseline_feature_seconds = perf_counter() - baseline_started

    landcover_started = perf_counter()
    treatment_pool = WorldCoverExtractor().add_point_features(baseline_pool)
    landcover_point_seconds = perf_counter() - landcover_started

    baseline_selection_started = perf_counter()
    baseline = optimizer.find_priority_placements(
        candidates=baseline_pool,
        require_worldcover=False,
        add_worldcover_context=False,
        add_building_context=False,
        export=False,
    )
    baseline_selection_seconds = perf_counter() - baseline_selection_started

    treatment_selection_started = perf_counter()
    treatment = optimizer.find_priority_placements(
        candidates=treatment_pool,
        require_worldcover=True,
        add_worldcover_context=True,
        add_building_context=False,
        export=True,
    )
    treatment_selection_seconds = perf_counter() - treatment_selection_started

    baseline_eligible = eligible_candidate_mask(
        baseline_pool, require_worldcover=False
    )
    treatment_eligible = eligible_candidate_mask(
        treatment_pool, require_worldcover=True
    )
    eligible_count = int(baseline_eligible.sum())
    coverage_count = int(
        treatment_pool.loc[baseline_eligible, "worldcover_data_available"].sum()
    )
    eligible_coverage_pct = 100.0 * coverage_count / max(eligible_count, 1)
    water_before = int(
        (
            baseline_eligible
            & treatment_pool["worldcover_is_water"].fillna(False).astype(bool)
        ).sum()
    )
    water_after = int(
        treatment_pool.loc[treatment_eligible, "worldcover_is_water"].sum()
    )
    baseline_ids = baseline["candidate_id"].tolist()
    treatment_ids = treatment["candidate_id"].tolist()
    common = set(baseline_ids).intersection(treatment_ids)
    top_k_overlap_pct = 100.0 * len(common) / max(len(baseline_ids), 1)
    rank_displacements = [
        abs(baseline_ids.index(candidate) - treatment_ids.index(candidate))
        for candidate in common
    ]
    score_unchanged = all(
        float(
            baseline.loc[baseline["candidate_id"] == candidate, "planning_priority_score"].iloc[0]
        )
        == float(
            treatment.loc[
                treatment["candidate_id"] == candidate, "planning_priority_score"
            ].iloc[0]
        )
        for candidate in common
    )
    h3_coverage = pd.to_numeric(
        treatment.get("worldcover_h3_coverage_pct"), errors="coerce"
    )
    minimum_h3_coverage = float(h3_coverage.min()) if h3_coverage.notna().any() else 0.0

    checks = {
        "eligible_candidate_point_coverage_pct": eligible_coverage_pct,
        "shortlist_h3_minimum_coverage_pct": minimum_h3_coverage,
        "water_candidates_before_screening": water_before,
        "water_candidates_after_screening": water_after,
        "top_k_overlap_pct": top_k_overlap_pct,
        "mean_rank_displacement_for_common_candidates": (
            float(np.mean(rank_displacements)) if rank_displacements else None
        ),
        "priority_scores_unchanged_for_common_candidates": score_unchanged,
        "independent_reference_sample_available": False,
        "independent_reference_agreement_pct": None,
        "rf_truth_available": False,
        "rf_validation_improvement": None,
    }
    acceptance = {
        "eligible_area_coverage_at_least_98_pct": eligible_coverage_pct >= 98.0,
        "independent_reference_agreement_at_least_90_pct": False,
        "zero_water_candidates_after_screening": water_after == 0,
        "rf_validation_improved_for_clutter_use": False,
    }
    manifest = provenance["manifest"]
    tile_footprint_coverage_pct = _tile_footprint_coverage_pct(manifest)
    checks["national_tile_footprint_coverage_pct"] = tile_footprint_coverage_pct
    acceptance["eligible_area_coverage_at_least_98_pct"] = (
        tile_footprint_coverage_pct >= 98.0 and eligible_coverage_pct >= 98.0
    )
    screening_ready = (
        acceptance["eligible_area_coverage_at_least_98_pct"]
        and acceptance["zero_water_candidates_after_screening"]
    )
    report = {
        "step": 8,
        "status": "review-only" if screening_ready else "revise",
        "decision": (
            "keep WorldCover for deterministic water screening and review context; "
            "independent class validation remains pending"
            if screening_ready
            else "revise WorldCover integration before using it for screening"
        ),
        "question": "Does land cover improve clutter and buildability screening?",
        "software_and_dataset": {
            "dataset": manifest.get("dataset", WORLDCOVER_VERSION),
            "doi": manifest.get("doi", WORLDCOVER_DOI),
            "license": manifest.get("license", WORLDCOVER_LICENSE),
            "source_base_url": manifest.get("source_base_url", WORLDCOVER_BASE_URL),
            "tile_count": manifest.get("tile_count"),
            "total_bytes": manifest.get("total_bytes"),
            "manifest_verified": provenance["verified"],
        },
        "before": {
            "generated_candidate_count": len(baseline_pool),
            "eligible_candidate_count": eligible_count,
            "shortlist_count": len(baseline),
            "water_candidates_not_screened": water_before,
        },
        "after": {
            "generated_candidate_count": len(treatment_pool),
            "eligible_candidate_count": int(treatment_eligible.sum()),
            "shortlist_count": len(treatment),
            "water_candidates_remaining": water_after,
            "shortlist_review_required_count": int(
                treatment["worldcover_review_required"].sum()
            ),
        },
        "checks": checks,
        "acceptance": acceptance,
        "runtime_seconds": {
            "source_hash_verification": verification_seconds,
            "baseline_feature_extraction": baseline_feature_seconds,
            "worldcover_point_extraction_incremental": landcover_point_seconds,
            "baseline_selection": baseline_selection_seconds,
            "worldcover_selection_and_h3_context": treatment_selection_seconds,
        },
        "limitations": [
            "WorldCover screens observed 2021 surface class; it does not establish buildability.",
            "No independent pre-labeled Libya reference sample is supplied, so the 90% agreement gate is pending.",
            "No RF truth is supplied, so WorldCover is excluded from the priority score and RF clutter model.",
            "Mixed or coastal H3 cells are flagged for review rather than automatically rejected.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _round_optional(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tile_footprint_coverage_pct(manifest: dict) -> float:
    boundary = (
        gpd.read_file(ADMIN0_GEOJSON_PATH)
        .to_crs("EPSG:4326")
        .geometry.union_all()
    )
    footprints = []
    for record in manifest.get("tiles", []):
        with rasterio.open(WORLDCOVER_DIR / record["filename"]) as source:
            footprints.append(box(*source.bounds))
    if not footprints:
        return 0.0
    covered = boundary.intersection(union_all(footprints))
    projected = gpd.GeoSeries([boundary, covered], crs="EPSG:4326").to_crs(
        "EPSG:6933"
    )
    return min(100.0, 100.0 * float(projected.iloc[1].area / projected.iloc[0].area))
