"""Roadmap Step 11 evaluation and review-only OpenStreetMap context."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree
from shapely import make_valid

from antenna_cell_placement.buildings import verify_manifest
from antenna_cell_placement.config import (
    ADMIN2_GEOJSON_PATH,
    CRS_WGS84,
    OSM_BUILDINGS_GPKG,
    OSM_CONTEXT_EVALUATION_REPORT,
    RECOMMENDATIONS_CSV,
)


EARTH_RADIUS_M = 6_371_008.8

# Every family has its own pre-registered completeness threshold. Port terminals
# are evaluated but intentionally excluded from runtime unless they pass.
FAMILY_SPECS = {
    "hospital": {
        "layers": (("gis_osm_pois_free", ("hospital",)), ("gis_osm_pois_a_free", ("hospital",))),
        "minimum_features": 100,
        "minimum_municipality_coverage_pct": 80.0,
    },
    "higher_education": {
        "layers": (
            ("gis_osm_pois_free", ("university", "college")),
            ("gis_osm_pois_a_free", ("university", "college")),
        ),
        "minimum_features": 100,
        "minimum_municipality_coverage_pct": 80.0,
    },
    "aviation": {
        "layers": (
            ("gis_osm_transport_free", ("airport", "airfield")),
            ("gis_osm_transport_a_free", ("airport", "airfield")),
        ),
        "minimum_features": 20,
        "minimum_municipality_coverage_pct": 50.0,
    },
    "port": {
        "layers": (
            ("gis_osm_transport_free", ("ferry_terminal",)),
            ("gis_osm_transport_a_free", ("ferry_terminal",)),
        ),
        "minimum_features": 10,
        "minimum_municipality_coverage_pct": 25.0,
    },
    "industrial": {
        "layers": (("gis_osm_landuse_a_free", ("industrial",)),),
        "minimum_features": 100,
        "minimum_municipality_coverage_pct": 80.0,
    },
}

ACTIVE_FAMILIES = ("hospital", "higher_education", "aviation", "industrial")
OSM_CONTEXT_COLUMNS = [
    field
    for family in ACTIVE_FAMILIES
    for field in (
        f"osm_{family}_count_h3",
        f"osm_{family}_observed_h3",
        f"osm_{family}_nearest_distance_m",
    )
] + ["osm_selected_context_available"]


def load_selected_osm_features(
    path: Path = OSM_BUILDINGS_GPKG,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Load, validate, and deduplicate only the pre-registered feature families."""
    if not path.exists():
        raise FileNotFoundError(f"OSM GeoPackage is missing: {path}")
    available_layers = {name for name, _ in pyogrio.list_layers(path)}
    parts = []
    input_rows = 0
    for family, spec in FAMILY_SPECS.items():
        for layer, classes in spec["layers"]:
            if layer not in available_layers:
                raise ValueError(f"Expected OSM layer is missing: {layer}")
            quoted = ",".join(f"'{value}'" for value in classes)
            frame = pyogrio.read_dataframe(
                path,
                layer=layer,
                columns=["osm_id", "fclass", "name"],
                where=f"fclass IN ({quoted})",
            )
            input_rows += len(frame)
            if not frame.empty:
                frame["family"] = family
                frame["source_layer"] = layer
                parts.append(frame)
    if not parts:
        empty = gpd.GeoDataFrame(
            columns=["osm_id", "fclass", "name", "family", "source_layer", "geometry"],
            geometry="geometry",
            crs=CRS_WGS84,
        )
        return empty, _quality_metrics(empty, input_rows, 0, 0)
    source = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), geometry="geometry", crs=parts[0].crs
    ).to_crs(CRS_WGS84)
    missing_geometry = int((source.geometry.isna() | source.geometry.is_empty).sum())
    source = source.loc[source.geometry.notna() & ~source.geometry.is_empty].copy()
    invalid_before = int((~source.geometry.is_valid).sum())
    if invalid_before:
        invalid = ~source.geometry.is_valid
        source.loc[invalid, "geometry"] = source.loc[invalid, "geometry"].map(make_valid)
    source = source.explode(index_parts=False, ignore_index=True)
    source = source.loc[source.geometry.notna() & ~source.geometry.is_empty].copy()
    invalid_after = int((~source.geometry.is_valid).sum())
    source["osm_id"] = source["osm_id"].astype("string")
    duplicate_rows = int(source.duplicated(["family", "osm_id"]).sum())
    source = source.drop_duplicates(["family", "osm_id"], keep="first").reset_index(drop=True)
    source["geometry"] = source.geometry.representative_point()
    quality = _quality_metrics(
        source, input_rows, missing_geometry, invalid_before, invalid_after, duplicate_rows
    )
    return source, quality


def _quality_metrics(
    source: gpd.GeoDataFrame,
    input_rows: int,
    missing_geometry: int,
    invalid_before: int,
    invalid_after: int = 0,
    duplicate_rows: int = 0,
) -> dict[str, object]:
    retained = len(source)
    return {
        "input_rows": int(input_rows),
        "missing_or_empty_geometry_rows": int(missing_geometry),
        "invalid_geometry_rows_before_repair": int(invalid_before),
        "invalid_geometry_rows_after_repair": int(invalid_after),
        "duplicate_family_object_rows_removed": int(duplicate_rows),
        "retained_features": int(retained),
        "valid_geometry_pct_after_repair": (
            100.0 * (retained - invalid_after) / max(retained, 1)
        ),
    }


class OSMContextExtractor:
    """Attach selected OSM observations without changing score or eligibility."""

    def __init__(self, features: gpd.GeoDataFrame | None = None):
        if features is None:
            self.features, self.quality = load_selected_osm_features()
        else:
            prepared = features.copy()
            if prepared.crs is None:
                raise ValueError("OSM context features must declare a CRS")
            prepared = prepared.to_crs(CRS_WGS84)
            prepared = prepared.loc[
                prepared.geometry.notna() & ~prepared.geometry.is_empty
            ].copy()
            prepared["geometry"] = prepared.geometry.map(
                lambda geometry: geometry.representative_point()
            )
            self.features = prepared.reset_index(drop=True)
            self.quality = _quality_metrics(self.features, len(features), 0, 0)

    def add_context(self, candidates: pd.DataFrame) -> pd.DataFrame:
        """Return candidates with H3 counts and geodesic nearest distances."""
        required = {"h3_r7", "canonical_latitude", "canonical_longitude"}
        missing = sorted(required - set(candidates.columns))
        if missing:
            raise KeyError(f"Candidates are missing OSM context fields: {missing}")
        result = candidates.copy()
        candidate_xyz = _unit_sphere_xyz(
            result["canonical_latitude"].to_numpy(dtype=float),
            result["canonical_longitude"].to_numpy(dtype=float),
        )
        for family in ACTIVE_FAMILIES:
            family_features = self.features.loc[self.features["family"] == family]
            counts = pd.Series(dtype="int64")
            if not family_features.empty:
                cells = family_features.geometry.map(
                    lambda point: h3.latlng_to_cell(point.y, point.x, 7)
                )
                counts = cells.value_counts()
                feature_xyz = _unit_sphere_xyz(
                    family_features.geometry.y.to_numpy(),
                    family_features.geometry.x.to_numpy(),
                )
                chord, _ = cKDTree(feature_xyz).query(candidate_xyz, k=1)
                distance = 2.0 * EARTH_RADIUS_M * np.arcsin(np.clip(chord / 2.0, 0.0, 1.0))
                result[f"osm_{family}_nearest_distance_m"] = np.round(distance, 1)
            else:
                result[f"osm_{family}_nearest_distance_m"] = pd.NA
            result[f"osm_{family}_count_h3"] = (
                result["h3_r7"].astype(str).map(counts).fillna(0).astype(int)
            )
            result[f"osm_{family}_observed_h3"] = result[
                f"osm_{family}_count_h3"
            ].gt(0)
        result["osm_selected_context_available"] = True
        return result


def add_osm_context_if_available(frame: pd.DataFrame) -> pd.DataFrame:
    """Add review context, preserving explicit unavailable values if absent."""
    try:
        return OSMContextExtractor().add_context(frame)
    except (FileNotFoundError, OSError):
        result = frame.copy()
        for column in OSM_CONTEXT_COLUMNS:
            result[column] = False if column == "osm_selected_context_available" else pd.NA
        return result



def _unit_sphere_xyz(latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    lat = np.radians(latitudes)
    lon = np.radians(longitudes)
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))
