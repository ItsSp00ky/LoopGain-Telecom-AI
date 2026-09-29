"""Roadmap Step 14: controlled FABDEM terrain comparison."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from antenna_cell_placement.config import (
    DEM_RASTER_PATH, FABDEM_DIR, FABDEM_EVALUATION_REPORT, FABDEM_MANIFEST,
    RECOMMENDATIONS_CSV,
)
from antenna_cell_placement.site_optimizer import score_candidate_features
from antenna_cell_placement.terrain import TerrainSampler


TERRAIN_COLUMNS = ("elevation_m", "elevation_prominence_3km", "terrain_slope_deg")
MIN_SHORTLIST_COVERAGE_PCT = 95.0
MIN_MUNICIPALITY_COVERAGE_PCT = 95.0
MIN_CHECKPOINT_ERROR_REDUCTION_PCT = 10.0
MIN_RF_ERROR_REDUCTION_PCT = 5.0


def verify_fabdem_manifest(directory: Path = FABDEM_DIR) -> dict:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"FABDEM manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("dataset") != "FABDEM V1-2" or not manifest.get("tiles"):
        raise ValueError("Unexpected FABDEM source manifest")
    for record in manifest["tiles"]:
        filename = record["filename"]
        if Path(filename).name != filename:
            raise ValueError("FABDEM manifest contains an unsafe filename")
        path = directory / filename
        if not path.exists() or path.stat().st_size != record["bytes"]:
            raise ValueError(f"FABDEM tile size mismatch: {filename}")
        if sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"FABDEM tile checksum mismatch: {filename}")
    return manifest


def _tile_name(lat: float, lon: float) -> str:
    y, x = math.floor(lat), math.floor(lon)
    return f"{'N' if y >= 0 else 'S'}{abs(y):02d}{'E' if x >= 0 else 'W'}{abs(x):03d}_FABDEM_V1-2.tif"


def _summary(values: pd.Series) -> dict:
    valid = pd.to_numeric(values, errors="coerce").dropna()
    if valid.empty:
        return {"count": 0, "median": None, "median_absolute": None, "p90_absolute": None}
    return {"count": int(len(valid)), "median": float(valid.median()),
            "median_absolute": float(valid.abs().median()),
            "p90_absolute": float(valid.abs().quantile(0.9))}


def evaluate_fabdem_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = FABDEM_EVALUATION_REPORT,
    fabdem_dir: Path = FABDEM_DIR,
) -> dict:
    manifest = verify_fabdem_manifest(fabdem_dir)
    if recommendations is None:
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    if recommendations.empty:
        raise ValueError("FABDEM evaluation requires a frozen candidate shortlist")
    baseline = recommendations.copy().reset_index(drop=True)
    baseline["fabdem_tile"] = [_tile_name(lat, lon) for lat, lon in zip(
        baseline.canonical_latitude, baseline.canonical_longitude)]
    available_tiles = {entry["filename"] for entry in manifest["tiles"]}
    treatment = baseline.copy()
    for column in TERRAIN_COLUMNS:
        treatment[column] = np.nan
    treatment["terrain_data_available"] = False
    treatment["fabdem_window_complete"] = False

    srtm = TerrainSampler.from_raster(DEM_RASTER_PATH)
    reference = baseline.copy()
    for row in reference.itertuples():
        sample = srtm.sample(row.canonical_longitude, row.canonical_latitude,
                             require_full_window=True)
        for column in TERRAIN_COLUMNS:
            reference.at[row.Index, column] = sample[column]
        reference.at[row.Index, "terrain_data_available"] = sample["terrain_data_available"]
    tile_quality = []
    for name, indices in baseline.groupby("fabdem_tile").groups.items():
        if name not in available_tiles:
            continue
        with rasterio.open(fabdem_dir / name) as source:
            if source.crs is None or source.count != 1:
                raise ValueError(f"Unexpected FABDEM raster schema: {name}")
            sampler = TerrainSampler.from_raster(fabdem_dir / name)
            tile_quality.append({"filename": name, "crs": str(source.crs),
                                 "resolution_degrees": list(source.res),
                                 "nodata": source.nodata,
                                 "valid_pixel_pct": 100.0 * float(np.isfinite(sampler.array).mean()),
                                 "bounds": list(source.bounds)})
        for index in indices:
            row = baseline.loc[index]
            sample = sampler.sample(row.canonical_longitude, row.canonical_latitude,
                                    require_full_window=True)
            for column in TERRAIN_COLUMNS:
                treatment.at[index, column] = sample[column]
            treatment.at[index, "terrain_data_available"] = sample["terrain_data_available"]
            treatment.at[index, "fabdem_window_complete"] = sample["window_complete"]

    supported = (reference.terrain_data_available.astype(bool) &
                 treatment.terrain_data_available.astype(bool))
    supported_count = int(supported.sum())
    coverage_pct = 100 * supported_count / len(baseline)
    municipalities = baseline.municipality_name.dropna().unique()
    covered_municipalities = treatment.loc[supported, "municipality_name"].dropna().unique()
    municipality_coverage_pct = (100 * len(covered_municipalities) / len(municipalities)
                                 if len(municipalities) else 0.0)
    differences = {column: _summary(treatment.loc[supported, column] -
                                    reference.loc[supported, column])
                   for column in TERRAIN_COLUMNS}

    baseline_score = score_candidate_features(reference.loc[supported]) if supported_count else pd.DataFrame()
    treatment_score = score_candidate_features(treatment.loc[supported]) if supported_count else pd.DataFrame()
    score_change = (_summary(treatment_score.planning_priority_score -
                             baseline_score.planning_priority_score)
                    if supported_count else _summary(pd.Series(dtype=float)))
    rank_spearman = None
    top10_promotions = None
    if supported_count >= 3:
        rank_spearman = float(baseline_score.planning_priority_score.corr(
            treatment_score.planning_priority_score, method="spearman"))
        if supported_count > 10:
            before_top = set(baseline_score.nlargest(10, "planning_priority_score").candidate_id)
            after_top = set(treatment_score.nlargest(10, "planning_priority_score").candidate_id)
            top10_promotions = len(after_top - before_top)

    features = []
    failed_cases = []
    for index, row in baseline.iterrows():
        properties = {"candidate_id": row.candidate_id,
                      "municipality_name": row.municipality_name,
                      "fabdem_available": bool(supported.iloc[index]),
                      "fabdem_tile": row.fabdem_tile}
        if supported.iloc[index]:
            for column in TERRAIN_COLUMNS:
                properties[f"{column}_delta"] = float(treatment.at[index, column] -
                                                       reference.at[index, column])
        elif len(failed_cases) < 8:
            reason = ("tile_not_in_sample" if row.fabdem_tile not in available_tiles
                      else "tile_edge_or_nodata")
            failed_cases.append({"candidate_id": row.candidate_id,
                                 "tile": row.fabdem_tile, "reason": reason})
        features.append({"type": "Feature", "geometry": {"type": "Point",
                        "coordinates": [float(row.canonical_longitude), float(row.canonical_latitude)]},
                        "properties": properties})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    map_path = output_path.with_name("step_14_fabdem_difference.geojson")
    map_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}) + "\n")
    report = {
        "step": 14, "status": "remove",
        "decision": "Do not replace the active SRTM source: independent elevation checkpoints and measured RF references are unavailable, and selected one-degree tiles do not establish national coverage.",
        "question": "Does FABDEM improve terrain accuracy and RF results over the active elevation source?",
        "source": manifest,
        "baseline": {"dem_path": str(DEM_RASTER_PATH),
                     "vertical_datum": "undocumented in supplied raster metadata",
                     "shortlist_count": int(len(baseline)),
                     "candidate_id_sha256": sha256("\n".join(baseline.candidate_id).encode()).hexdigest()},
        "treatment": {"sampled_tiles": len(manifest["tiles"]),
                      "role": "isolated experiment; no production FABDEM fields"},
        "quality": {"sampled_tile_rasters": tile_quality,
                    "national_void_and_seam_audit_complete": False},
        "thresholds": {"minimum_shortlist_coverage_pct": MIN_SHORTLIST_COVERAGE_PCT,
                       "minimum_shortlist_municipality_coverage_pct": MIN_MUNICIPALITY_COVERAGE_PCT,
                       "minimum_independent_checkpoint_error_reduction_pct": MIN_CHECKPOINT_ERROR_REDUCTION_PCT,
                       "minimum_rf_holdout_error_reduction_pct": MIN_RF_ERROR_REDUCTION_PCT},
        "coverage": {"supported_candidates": supported_count,
                     "shortlist_coverage_pct": coverage_pct,
                     "shortlist_municipality_coverage_pct": municipality_coverage_pct,
                     "missing_or_edge_candidates": int(len(baseline) - supported_count)},
        "differences": differences,
        "score_sensitivity": {"within_frozen_shortlist_score_delta": score_change,
                              "within_frozen_shortlist_spearman": rank_spearman,
                              "within_frozen_shortlist_top10_promotions": top10_promotions,
                              "full_candidate_rerank_evaluated": False},
        "checks": {"shortlist_coverage_pass": coverage_pct >= MIN_SHORTLIST_COVERAGE_PCT,
                   "municipality_coverage_pass": municipality_coverage_pct >= MIN_MUNICIPALITY_COVERAGE_PCT,
                   "independent_elevation_checkpoints_available": False,
                   "independent_rf_reference_available": False,
                   "national_void_and_seam_audit_complete": False,
                   "production_fabdem_integration": False},
        "geographic_difference_map": map_path.name,
        "failed_cases": failed_cases,
        "limitations": ["The sample consists of one-degree tiles containing frozen shortlisted candidates; it is not a national completeness audit.",
                        "Within-shortlist rank changes do not measure full-grid candidate promotion.",
                        "Absolute elevation differences are not errors without independent checkpoints.",
                        "The supplied SRTM raster does not declare a vertical datum, so absolute elevation offsets cannot be attributed solely to terrain quality.",
                        "FABDEM's published non-commercial terms limit reuse."],
    }
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
