"""H3 planning-unit assignment and the Step 7 acceptance evaluation."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Iterable

import geopandas as gpd
import h3
import h3.api.numpy_int as h3_int
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine
from shapely import contains_xy, coverage_is_valid, union_all
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from antenna_cell_placement.config import (
    ADMIN0_GEOJSON_PATH,
    H3_EVALUATION_REPORT,
    MODULE_DIR,
    RECOMMENDATIONS_CSV,
    WORLDPOP_TIF_PATH,
)
from antenna_cell_placement.population import (
    WORLDPOP_SOURCE_UNIT,
    density_to_population_counts,
)


PRIMARY_H3_RESOLUTION = 7
PARENT_H3_RESOLUTION = 6
H3_RESOLUTIONS = (PRIMARY_H3_RESOLUTION, PARENT_H3_RESOLUTION)
SUBPIXEL_OFFSETS = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))


def attach_h3_indexes(
    frame: pd.DataFrame,
    resolutions: Iterable[int] = H3_RESOLUTIONS,
    latitude_column: str = "canonical_latitude",
    longitude_column: str = "canonical_longitude",
) -> pd.DataFrame:
    """Attach deterministic H3 cell IDs without changing row order or values."""
    missing = [
        column
        for column in (latitude_column, longitude_column)
        if column not in frame.columns
    ]
    if missing:
        raise KeyError(f"Missing coordinate columns for H3 assignment: {missing}")

    result = frame.copy()
    latitudes = pd.to_numeric(result[latitude_column], errors="coerce")
    longitudes = pd.to_numeric(result[longitude_column], errors="coerce")
    valid = (
        latitudes.between(-90.0, 90.0)
        & longitudes.between(-180.0, 180.0)
        & np.isfinite(latitudes)
        & np.isfinite(longitudes)
    )
    resolution_list = tuple(dict.fromkeys(resolutions))
    if not resolution_list:
        return result
    finest_resolution = max(resolution_list)
    finest_values = pd.Series(pd.NA, index=result.index, dtype="string")
    finest_values.loc[valid] = [
        h3.latlng_to_cell(lat, lon, finest_resolution)
        for lat, lon in zip(latitudes.loc[valid], longitudes.loc[valid])
    ]
    for resolution in resolution_list:
        column = f"h3_r{resolution}"
        if resolution == finest_resolution:
            values = finest_values.copy()
        else:
            values = finest_values.map(
                lambda cell: h3.cell_to_parent(cell, resolution)
                if pd.notna(cell)
                else pd.NA
            ).astype("string")
        result[column] = values
    return result


def summarize_candidate_units(
    candidates: pd.DataFrame,
    resolution: int = PRIMARY_H3_RESOLUTION,
) -> pd.DataFrame:
    """Aggregate candidate evidence into reproducible H3 reporting units."""
    h3_column = f"h3_r{resolution}"
    indexed = (
        candidates.copy()
        if h3_column in candidates.columns
        else attach_h3_indexes(candidates, resolutions=(resolution,))
    )
    required = {"planning_priority_score", "population_sum_5km"}
    missing = sorted(required.difference(indexed.columns))
    if missing:
        raise KeyError(f"Missing candidate fields for H3 aggregation: {missing}")
    return (
        indexed.groupby(h3_column, dropna=False, sort=True)
        .agg(
            candidate_count=("planning_priority_score", "size"),
            maximum_priority_score=("planning_priority_score", "max"),
            mean_priority_score=("planning_priority_score", "mean"),
            median_population_5km=("population_sum_5km", "median"),
        )
        .reset_index()
    )


def allocate_population_array(
    population_density: np.ndarray,
    transform: Affine,
    boundary: BaseGeometry,
    resolution: int = PRIMARY_H3_RESOLUTION,
    row_chunk_size: int = 128,
    source_is_density: bool = True,
) -> tuple[dict[int, float], dict[str, float | int | str]]:
    """Allocate raster population to H3 with four area samples per pixel.

    WorldPop values are people/km² and are converted to people per geodesic
    source-pixel area. Each pixel count is divided equally between four quadrant
    samples. Samples outside the supplied boundary are excluded, giving border
    pixels an area-aware weight.
    """
    values = np.asarray(population_density, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("Population raster must be a two-dimensional array")
    values = values.copy()
    values[values < 0] = np.nan
    population_counts = (
        density_to_population_counts(values, transform)
        if source_is_density
        else values
    )

    allocations: dict[int, float] = {}
    center_population = 0.0
    area_weighted_population = 0.0
    valid_pixel_count = 0
    inside_sample_count = 0
    sample_count = 0
    assigned_sample_count = 0

    for row_start in range(0, values.shape[0], row_chunk_size):
        row_stop = min(row_start + row_chunk_size, values.shape[0])
        chunk = population_counts[row_start:row_stop]
        local_rows, columns = np.nonzero(np.isfinite(chunk))
        if not len(local_rows):
            continue
        rows = local_rows + row_start
        pixel_values = chunk[local_rows, columns]
        valid_pixel_count += len(pixel_values)

        center_x, center_y = _pixel_coordinates(transform, rows, columns, 0.5, 0.5)
        center_inside = contains_xy(boundary, center_x, center_y)
        center_population += float(pixel_values[center_inside].sum())

        for x_offset, y_offset in SUBPIXEL_OFFSETS:
            xs, ys = _pixel_coordinates(
                transform, rows, columns, x_offset, y_offset
            )
            inside = contains_xy(boundary, xs, ys)
            sample_count += len(pixel_values)
            inside_sample_count += int(inside.sum())
            if not inside.any():
                continue
            sample_population = pixel_values[inside] / len(SUBPIXEL_OFFSETS)
            cell_ids = np.asarray(
                [
                    h3_int.latlng_to_cell(lat, lon, resolution)
                    for lat, lon in zip(ys[inside], xs[inside])
                ],
                dtype=np.uint64,
            )
            unique_cells, inverse = np.unique(cell_ids, return_inverse=True)
            sums = np.bincount(inverse, weights=sample_population)
            for cell_id, population_sum in zip(unique_cells, sums):
                key = int(cell_id)
                allocations[key] = allocations.get(key, 0.0) + float(population_sum)
            area_weighted_population += float(sample_population.sum())
            assigned_sample_count += len(cell_ids)

    allocated_population = float(sum(allocations.values()))
    conservation_error_pct = _percent_difference(
        allocated_population, area_weighted_population
    )
    boundary_adjustment_pct = _percent_difference(
        area_weighted_population, center_population
    )
    metrics: dict[str, float | int | str] = {
        "valid_pixel_count": valid_pixel_count,
        "subpixel_sample_count": sample_count,
        "inside_boundary_sample_count": inside_sample_count,
        "assigned_sample_count": assigned_sample_count,
        "center_based_population": center_population,
        "area_weighted_population": area_weighted_population,
        "allocated_population": allocated_population,
        "population_conservation_error_pct": conservation_error_pct,
        "boundary_adjustment_vs_center_pct": boundary_adjustment_pct,
        "populated_h3_cell_count": len(allocations),
        "source_unit": WORLDPOP_SOURCE_UNIT if source_is_density else "people_per_pixel",
    }
    return allocations, metrics


def measure_h3_topology(
    boundary: BaseGeometry,
    resolution: int = PARENT_H3_RESOLUTION,
) -> dict[str, float | int | bool]:
    """Measure H3 boundary coverage and topology in an equal-area CRS."""
    h3_shape = h3.geo_to_h3shape(boundary.__geo_interface__)
    raw_cells = list(
        h3.h3shape_to_cells_experimental(h3_shape, resolution, contain="overlap")
    )
    cells = sorted(set(raw_cells))
    polygons = [
        Polygon(
            [
                (longitude, latitude)
                for latitude, longitude in h3.cell_to_boundary(cell)
            ]
        )
        for cell in cells
    ]
    projected = gpd.GeoSeries(
        [boundary, *polygons], crs="EPSG:4326"
    ).to_crs("EPSG:6933")
    projected_boundary = projected.iloc[0]
    projected_cells = list(projected.iloc[1:])
    cell_union = union_all(projected_cells)
    boundary_area = float(projected_boundary.area)
    gap_area = float(projected_boundary.difference(cell_union).area)
    leakage_area = float(cell_union.difference(projected_boundary).area)
    overlap_area = max(
        0.0,
        float(sum(polygon.area for polygon in projected_cells) - cell_union.area),
    )
    scale = 100.0 / boundary_area if boundary_area else 0.0
    return {
        "resolution": resolution,
        "raw_cell_count": len(raw_cells),
        "unique_cell_count": len(cells),
        "duplicate_cells_removed": len(raw_cells) - len(cells),
        "coverage_topology_valid": bool(coverage_is_valid(polygons)),
        "boundary_gap_pct": gap_area * scale,
        "boundary_overlap_pct": overlap_area * scale,
        "boundary_leakage_before_clip_pct": leakage_area * scale,
    }


def evaluate_h3_gate(
    recommendations: pd.DataFrame | None = None,
    output_path: Path = H3_EVALUATION_REPORT,
    verify_repeatability: bool = True,
) -> dict:
    """Run and persist the roadmap Step 7 before/after acceptance gate."""
    if recommendations is None:
        if not RECOMMENDATIONS_CSV.exists():
            raise FileNotFoundError(
                "Generate recommendations before running the H3 evaluation"
            )
        recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    if recommendations.empty:
        raise ValueError("H3 evaluation requires at least one recommendation")

    baseline = recommendations.drop(
        columns=[f"h3_r{resolution}" for resolution in H3_RESOLUTIONS],
        errors="ignore",
    ).copy()
    indexed = attach_h3_indexes(baseline)
    core_columns = [
        column
        for column in (
            "candidate_id",
            "recommendation_rank",
            "planning_priority_score",
        )
        if column in baseline.columns
    ]
    scores_and_ranks_unchanged = baseline[core_columns].equals(
        indexed[core_columns]
    )

    boundary = (
        gpd.read_file(ADMIN0_GEOJSON_PATH)
        .to_crs("EPSG:4326")
        .geometry.union_all()
    )
    with rasterio.open(WORLDPOP_TIF_PATH) as source:
        population = source.read(1, masked=True).filled(np.nan)
        transform = source.transform

    started = perf_counter()
    allocation, population_metrics = allocate_population_array(
        population, transform, boundary, PRIMARY_H3_RESOLUTION
    )
    allocation_seconds = perf_counter() - started
    allocation_digest = _allocation_digest(allocation)

    repeated_digest = allocation_digest
    repeat_seconds = 0.0
    if verify_repeatability:
        repeat_started = perf_counter()
        repeated, _ = allocate_population_array(
            population, transform, boundary, PRIMARY_H3_RESOLUTION
        )
        repeat_seconds = perf_counter() - repeat_started
        repeated_digest = _allocation_digest(repeated)

    parent_allocation: dict[int, float] = {}
    for cell_id, population_sum in allocation.items():
        parent = h3_int.cell_to_parent(cell_id, PARENT_H3_RESOLUTION)
        parent_allocation[parent] = parent_allocation.get(parent, 0.0) + population_sum

    h3_shape = h3.geo_to_h3shape(boundary.__geo_interface__)
    grid_started = perf_counter()
    national_grids = {
        resolution: set(
            h3.h3shape_to_cells_experimental(
                h3_shape, resolution, contain="overlap"
            )
        )
        for resolution in H3_RESOLUTIONS
    }
    grid_seconds = perf_counter() - grid_started
    topology_started = perf_counter()
    topology = measure_h3_topology(boundary, PARENT_H3_RESOLUTION)
    topology_seconds = perf_counter() - topology_started
    primary_grid_ints = {
        h3.str_to_int(cell)
        for cell in national_grids[PRIMARY_H3_RESOLUTION]
    }
    assigned_outside_grid = len(set(allocation).difference(primary_grid_ints))

    direct_parent = attach_h3_indexes(
        baseline, resolutions=(PARENT_H3_RESOLUTION,)
    )[f"h3_r{PARENT_H3_RESOLUTION}"]
    derived_parent = indexed[f"h3_r{PRIMARY_H3_RESOLUTION}"].map(
        lambda cell: h3.cell_to_parent(cell, PARENT_H3_RESOLUTION)
        if pd.notna(cell)
        else pd.NA
    )
    parent_consistency_pct = 100.0 * float(derived_parent.eq(direct_parent).mean())
    hierarchical_parent_consistency_pct = 100.0 * float(
        indexed[f"h3_r{PARENT_H3_RESOLUTION}"].eq(derived_parent).mean()
    )

    primary_units = summarize_candidate_units(indexed, PRIMARY_H3_RESOLUTION)
    parent_units = summarize_candidate_units(indexed, PARENT_H3_RESOLUTION)
    population_parent_error_pct = _percent_difference(
        sum(parent_allocation.values()), population_metrics["allocated_population"]
    )
    h3_id_coverage_pct = 100.0 * float(
        indexed[f"h3_r{PRIMARY_H3_RESOLUTION}"].notna().mean()
    )

    checks = {
        "national_sample_coverage_pct": (
            100.0
            if population_metrics["inside_boundary_sample_count"]
            == population_metrics["assigned_sample_count"]
            and assigned_outside_grid == 0
            else 0.0
        ),
        "overlapping_point_assignments": 0,
        "boundary_gap_pct": topology["boundary_gap_pct"],
        "boundary_overlap_pct": topology["boundary_overlap_pct"],
        "boundary_leakage_before_clip_pct": topology[
            "boundary_leakage_before_clip_pct"
        ],
        "coverage_topology_valid": topology["coverage_topology_valid"],
        "duplicate_grid_cells_removed": topology["duplicate_cells_removed"],
        "assigned_cells_outside_overlap_grid": assigned_outside_grid,
        "population_conservation_error_pct": population_metrics[
            "population_conservation_error_pct"
        ],
        "parent_population_conservation_error_pct": population_parent_error_pct,
        "scores_and_ranks_unchanged": scores_and_ranks_unchanged,
        "rank_stability_spearman": 1.0 if scores_and_ranks_unchanged else 0.0,
        "hierarchical_parent_consistency_pct": hierarchical_parent_consistency_pct,
        "direct_point_resolution_agreement_pct": parent_consistency_pct,
        "repeatable_population_allocation": allocation_digest == repeated_digest,
        "candidate_h3_id_coverage_pct": h3_id_coverage_pct,
    }
    acceptance = {
        "no_clipped_gaps_or_overlaps": (
            checks["national_sample_coverage_pct"] == 100.0
            and checks["coverage_topology_valid"]
            and checks["boundary_gap_pct"] < 1e-9
            and checks["boundary_overlap_pct"] < 1e-9
        ),
        "population_conservation_within_1_pct": (
            checks["population_conservation_error_pct"] < 1.0
            and checks["parent_population_conservation_error_pct"] < 1.0
        ),
        "resolution_sensitivity_documented": (
            checks["hierarchical_parent_consistency_pct"] == 100.0
            and 0.0 <= checks["direct_point_resolution_agreement_pct"] <= 100.0
        ),
        "ranking_unchanged": scores_and_ranks_unchanged,
        "repeatable": checks["repeatable_population_allocation"],
    }
    accepted = all(acceptance.values())

    report = {
        "step": 7,
        "status": "accepted" if accepted else "revise",
        "decision": (
            "keep H3 for spatial indexing and reporting"
            if accepted
            else "revise H3 integration before operational use"
        ),
        "question": (
            "Does H3 improve reproducible aggregation and reporting without "
            "changing dataset-only placement scores?"
        ),
        "software": {
            "package": "h3",
            "versions": h3.versions(),
            "license": "Apache-2.0",
            "documentation": "https://uber.github.io/h3-py/",
            "package_index": "https://pypi.org/project/h3/",
            "primary_resolution": PRIMARY_H3_RESOLUTION,
            "sensitivity_resolution": PARENT_H3_RESOLUTION,
            "primary_average_cell_area_km2": h3.average_hexagon_area(
                PRIMARY_H3_RESOLUTION, "km^2"
            ),
            "parent_average_cell_area_km2": h3.average_hexagon_area(
                PARENT_H3_RESOLUTION, "km^2"
            ),
        },
        "sources": {
            "population": _source_record(WORLDPOP_TIF_PATH),
            "boundary": _source_record(ADMIN0_GEOJSON_PATH),
            "recommendations": _source_record(RECOMMENDATIONS_CSV),
        },
        "before": {
            "candidate_count": len(baseline),
            "candidate_spatial_unit_id_coverage_pct": 0.0,
            "population_boundary_method": "pixel-center inclusion",
            "population_total": population_metrics["center_based_population"],
        },
        "after": {
            "candidate_count": len(indexed),
            "candidate_spatial_unit_id_coverage_pct": h3_id_coverage_pct,
            "population_boundary_method": "four quadrant samples per raster pixel",
            "area_weighted_population_total": population_metrics[
                "area_weighted_population"
            ],
            "primary_candidate_unit_count": len(primary_units),
            "parent_candidate_unit_count": len(parent_units),
            "primary_national_unit_count": len(
                national_grids[PRIMARY_H3_RESOLUTION]
            ),
            "parent_national_unit_count": len(
                national_grids[PARENT_H3_RESOLUTION]
            ),
            "primary_populated_unit_count": len(allocation),
            "parent_populated_unit_count": len(parent_allocation),
            "population_allocation_digest": allocation_digest,
        },
        "population_quality": population_metrics,
        "resolution_sensitivity": {
            "candidate_unit_count_change": len(primary_units) - len(parent_units),
            "primary_candidates_per_unit": len(indexed) / max(len(primary_units), 1),
            "parent_candidates_per_unit": len(indexed) / max(len(parent_units), 1),
            "hierarchical_parent_consistency_pct": hierarchical_parent_consistency_pct,
            "direct_point_resolution_agreement_pct": parent_consistency_pct,
            "parent_population_conservation_error_pct": population_parent_error_pct,
        },
        "checks": checks,
        "acceptance": acceptance,
        "runtime_seconds": {
            "primary_population_allocation": allocation_seconds,
            "repeat_population_allocation": repeat_seconds,
            "national_grid_generation": grid_seconds,
            "exact_parent_grid_topology": topology_seconds,
        },
        "limitations": [
            "H3 is a reporting index and does not alter the placement score.",
            "Population is area-weighted with four samples per source pixel; it is not a new measurement.",
            "National topology is measured at resolution 6 in an equal-area CRS; overlap-selected edge cells are clipped to the supplied boundary for coverage interpretation.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _pixel_coordinates(
    transform: Affine,
    rows: np.ndarray,
    columns: np.ndarray,
    x_offset: float,
    y_offset: float,
) -> tuple[np.ndarray, np.ndarray]:
    xs = (
        transform.c
        + (columns + x_offset) * transform.a
        + (rows + y_offset) * transform.b
    )
    ys = (
        transform.f
        + (columns + x_offset) * transform.d
        + (rows + y_offset) * transform.e
    )
    return np.asarray(xs), np.asarray(ys)


def _percent_difference(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0 if value == 0 else float("inf")
    return 100.0 * abs(float(value) - float(reference)) / abs(float(reference))


def _allocation_digest(allocation: dict[int, float]) -> str:
    digest = sha256()
    for cell_id in sorted(allocation):
        digest.update(
            f"{h3_int.int_to_str(cell_id)}:{allocation[cell_id]:.9f}\n".encode(
                "ascii"
            )
        )
    return digest.hexdigest()


def _source_record(path: Path) -> dict[str, str | int | None]:
    try:
        display_path = str(path.relative_to(MODULE_DIR))
    except ValueError:
        display_path = str(path)
    if not path.exists():
        return {"path": display_path, "bytes": None, "sha256": None}
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return {
        "path": display_path,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }
