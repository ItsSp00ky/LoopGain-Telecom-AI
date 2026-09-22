"""
H3 hexagonal planning grid for pilot-city cell-site expansion analysis.
Aggregates existing enriched site features into per-hexagon rows for
area-level demand/gap scoring (Phase 1 of the GIS/RF roadmap).
"""

from pathlib import Path
from typing import Dict, List

import h3
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from numbers import Integral

from antenna_cell_placement.config import (
    PILOT_CITY_BBOXES,
    DEFAULT_PILOT_CITY,
    H3_RESOLUTION,
    H3_OUTPUT_DIR,
    H3_GRID_GEOJSON_TEMPLATE,
    H3_FEATURE_TABLE_PARQUET_TEMPLATE,
    CLEANED_PHYSICAL_SITES_CSV,
    CRS_WGS84,
)
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor


def generate_h3_cells_for_bbox(bbox: Dict[str, float], resolution: int = H3_RESOLUTION) -> List[str]:
    """Generate H3 cell IDs covering a lat/lon bounding box at the given resolution."""
    outer_ring = [
        (bbox["min_lat"], bbox["min_lon"]),
        (bbox["min_lat"], bbox["max_lon"]),
        (bbox["max_lat"], bbox["max_lon"]),
        (bbox["max_lat"], bbox["min_lon"]),
    ]
    poly = h3.LatLngPoly(outer_ring)
    return list(h3.polygon_to_cells(poly, resolution))


def h3_cells_to_gdf(cell_ids: List[str]) -> gpd.GeoDataFrame:
    """Convert H3 cell IDs into a GeoDataFrame of hexagon polygons (WGS84)."""
    polygons = []
    for cell_id in cell_ids:
        boundary = h3.cell_to_boundary(cell_id)  # list of (lat, lon)
        polygons.append(Polygon([(lon, lat) for lat, lon in boundary]))

    centroids = [h3.cell_to_latlng(cell_id) for cell_id in cell_ids]

    return gpd.GeoDataFrame(
        {
            "h3_index": cell_ids,
            "centroid_lat": [c[0] for c in centroids],
            "centroid_lon": [c[1] for c in centroids],
        },
        geometry=polygons,
        crs=CRS_WGS84,
    )


def assign_points_to_h3(lons: np.ndarray, lats: np.ndarray, resolution: int = H3_RESOLUTION) -> np.ndarray:
    """Vectorized assignment of (lon, lat) points to their containing H3 cell id."""
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    return np.array([h3.latlng_to_cell(lat, lon, resolution) for lat, lon in zip(lats, lons)])


def aggregate_existing_sites_per_hex(df_sites_enriched: pd.DataFrame, resolution: int = H3_RESOLUTION) -> pd.DataFrame:
    """
    Aggregate per-site enriched features into one row per H3 hex: site_count,
    mean population/terrain/road-distance/site-density, and operator mix.
    """
    df = df_sites_enriched.copy()
    df["h3_index"] = assign_points_to_h3(
        df["canonical_longitude"].values, df["canonical_latitude"].values, resolution
    )

    agg_spec = {
        "physical_site_id": "count",
        "population_density_1km": "mean",
        "population_sum_5km": "mean",
        "elevation_m": "mean",
        "terrain_slope_deg": "mean",
        "dist_to_nearest_road_m": "mean",
        "dist_to_nearest_site_m": "mean",
        "site_density_3km": "mean",
        "has_libyana": "sum",
        "has_almadar": "sum",
    }
    agg_spec = {k: v for k, v in agg_spec.items() if k in df.columns}

    df_agg = df.groupby("h3_index").agg(agg_spec).rename(columns={"physical_site_id": "site_count"})
    return df_agg.reset_index()


PHASE2_COLUMN_PREFIXES = (
    "building_", "total_building_area_m2", "avg_building_area_m2", "built_up_ratio",
    "landcover_", "osm_", "poi_count",
)


def replace_feature_columns(base: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Replace a feature block by unique H3 identity, preserving missing values."""
    for name, table in (("base", base), ("features", features)):
        if table["h3_index"].isna().any() or table["h3_index"].duplicated().any():
            raise ValueError(f"{name} must have unique, non-null h3_index values")
    columns = [c for c in features.columns if c != "h3_index"]
    stale = [c for c in base.columns if c in columns or
             any(c == f"{feature}{suffix}" for feature in columns for suffix in ("_x", "_y"))]
    return base.drop(columns=stale).merge(
        features, on="h3_index", how="left", validate="one_to_one"
    )


def _carry_over_phase2_columns(df_hex: pd.DataFrame, table_path: str) -> pd.DataFrame:
    """Keep previously computed Phase-2 columns when the Phase-1 table is rebuilt."""
    path = Path(table_path)
    if not path.exists():
        return df_hex
    previous = pd.read_parquet(path)
    phase2_cols = [c for c in previous.columns if c.startswith(PHASE2_COLUMN_PREFIXES)]
    if not phase2_cols:
        return df_hex
    merged = replace_feature_columns(df_hex, previous[["h3_index"] + phase2_cols])
    missing = int(merged[phase2_cols[0]].isna().sum())
    note = f"; {missing} hexes lack Phase-2 values, re-run enrich-h3" if missing else ""
    print(f"Carried over {len(phase2_cols)} Phase-2 columns from the previous table{note}.")
    return merged


def build_h3_grid(city: str = DEFAULT_PILOT_CITY, resolution: int = H3_RESOLUTION) -> gpd.GeoDataFrame:
    """Build and export the H3 hex grid GeoJSON covering a pilot city's bbox."""
    bbox = PILOT_CITY_BBOXES[city]
    print(f"Generating H3 resolution-{resolution} grid for {city}...")
    cell_ids = generate_h3_cells_for_bbox(bbox, resolution)
    grid_gdf = h3_cells_to_gdf(cell_ids)
    print(f"Generated {len(grid_gdf)} hexagons covering {city}.")

    H3_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    grid_path = H3_GRID_GEOJSON_TEMPLATE.format(city=city)
    grid_gdf.to_file(grid_path, driver="GeoJSON")
    print(f"Exported H3 grid to: {grid_path}")

    return grid_gdf


def build_h3_feature_table(city: str = DEFAULT_PILOT_CITY, resolution: int = H3_RESOLUTION) -> pd.DataFrame:
    """
    Phase 1 pipeline: generate the hex grid for a pilot city's bbox, sample hex
    centroids through the existing GeospatialFeatureExtractor (population, terrain,
    roads, site density), join with aggregated existing-site stats for hexes that
    actually contain sites, and write the H3 feature table.
    """
    grid_gdf = build_h3_grid(city, resolution)

    print("Loading cleaned physical sites for feature extraction context...")
    df_sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)

    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    extractor.set_existing_sites(df_sites)

    print(f"Extracting geospatial features for {len(grid_gdf)} hex centroids...")
    centroid_features = extractor.extract_features(
        lons=grid_gdf["centroid_lon"].values,
        lats=grid_gdf["centroid_lat"].values,
        is_existing_site=False,
    )
    centroid_features["h3_index"] = grid_gdf["h3_index"].values

    print("Aggregating existing sites per hex...")
    df_sites_enriched = extractor.extract_features(
        lons=df_sites["canonical_longitude"].values,
        lats=df_sites["canonical_latitude"].values,
        is_existing_site=True,
    )
    df_sites_enriched = pd.concat(
        [df_sites[["physical_site_id", "has_libyana", "has_almadar"]].reset_index(drop=True), df_sites_enriched],
        axis=1,
    )
    site_agg = aggregate_existing_sites_per_hex(df_sites_enriched, resolution)
    site_agg = site_agg.add_prefix("existing_sites_")
    site_agg = site_agg.rename(columns={"existing_sites_h3_index": "h3_index"})

    df_hex = centroid_features.merge(site_agg, on="h3_index", how="left")
    df_hex["existing_sites_site_count"] = df_hex["existing_sites_site_count"].fillna(0).astype(int)

    H3_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    table_path = H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city=city)
    df_hex = _carry_over_phase2_columns(df_hex, table_path)
    df_hex.to_parquet(table_path, index=False)
    print(f"Exported H3 feature table ({len(df_hex)} hexes) to: {table_path}")

    return df_hex


def enrich_h3_feature_table(city: str = DEFAULT_PILOT_CITY) -> pd.DataFrame:
    """
    Phase 2 pipeline: join building, land-cover, and OSM features onto the
    Phase-1 H3 feature table for a pilot city and re-save it in place.
    """
    from antenna_cell_placement.building_features import load_building_footprints, compute_building_features_per_hex
    from antenna_cell_placement.landcover_features import compute_landcover_pct_per_hex
    from antenna_cell_placement.osm_features import load_osm_pbf, extract_roads_and_pois, compute_osm_features_per_hex

    table_path = H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city=city)
    grid_path = H3_GRID_GEOJSON_TEMPLATE.format(city=city)

    print(f"Loading Phase-1 H3 feature table: {table_path}")
    df_hex = pd.read_parquet(table_path)
    grid_gdf = gpd.read_file(grid_path)

    print("Computing building footprint features...")
    buildings_gdf = load_building_footprints()
    building_feats = compute_building_features_per_hex(grid_gdf, buildings_gdf)

    print("Computing land-cover features...")
    landcover_feats = compute_landcover_pct_per_hex(grid_gdf)

    print("Computing OSM road/POI features...")
    osm = load_osm_pbf(city)
    roads_gdf, pois_gdf = extract_roads_and_pois(osm)
    osm_feats = compute_osm_features_per_hex(grid_gdf, roads_gdf, pois_gdf)

    df_enriched = df_hex
    for features in (building_feats, landcover_feats, osm_feats):
        df_enriched = replace_feature_columns(df_enriched, features)

    df_enriched.to_parquet(table_path, index=False)
    print(f"Exported Phase-2 enriched H3 feature table ({len(df_enriched)} hexes) to: {table_path}")

    return df_enriched


if __name__ == "__main__":
    build_h3_feature_table(city=DEFAULT_PILOT_CITY)
