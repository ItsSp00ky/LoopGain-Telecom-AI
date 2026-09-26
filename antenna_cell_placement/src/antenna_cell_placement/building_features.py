"""
Microsoft Global ML Building Footprints features for the H3 pilot-city planning grid.
Computes building count, density, footprint area, and built-up ratio per hexagon.
"""

import gzip
import json
from typing import List

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape

from antenna_cell_placement.config import MS_BUILDING_FOOTPRINTS_TILES, CRS_WGS84, CRS_PROJECTED_LIBYA


def load_building_footprints(tile_paths: List = MS_BUILDING_FOOTPRINTS_TILES) -> gpd.GeoDataFrame:
    """Load Microsoft Global ML Building Footprints tiles (gzipped GeoJSON-Lines) into a GeoDataFrame."""
    geometries = []
    for path in tile_paths:
        print(f"Loading building footprints: {path}")
        with gzip.open(path, "rt") as f:
            for line in f:
                feature = json.loads(line)
                geometries.append(shape(feature["geometry"]))

    print(f"Loaded {len(geometries)} building footprints.")
    return gpd.GeoDataFrame({"geometry": geometries}, crs=CRS_WGS84)


def compute_building_features_per_hex(hex_gdf: gpd.GeoDataFrame, buildings_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Spatial-join building footprints to hexes and compute per-hex building_count,
    building_density_per_km2, total_building_area_m2, avg_building_area_m2, built_up_ratio.
    """
    hex_proj = hex_gdf.to_crs(CRS_PROJECTED_LIBYA).copy()
    hex_proj["hex_area_m2"] = hex_proj.geometry.area

    buildings_proj = buildings_gdf.to_crs(CRS_PROJECTED_LIBYA).copy()
    buildings_proj["building_area_m2"] = buildings_proj.geometry.area
    buildings_proj["building_centroid"] = buildings_proj.geometry.centroid
    buildings_pts = buildings_proj.set_geometry("building_centroid")[["building_area_m2", "building_centroid"]]
    buildings_pts = buildings_pts.set_geometry("building_centroid")

    print(f"Spatially joining {len(buildings_pts)} buildings to {len(hex_proj)} hexes...")
    joined = gpd.sjoin(buildings_pts, hex_proj[["h3_index", "hex_area_m2", "geometry"]], how="inner", predicate="within")

    agg = joined.groupby("h3_index").agg(
        building_count=("building_area_m2", "count"),
        total_building_area_m2=("building_area_m2", "sum"),
    ).reset_index()

    df = hex_proj[["h3_index", "hex_area_m2"]].merge(agg, on="h3_index", how="left")
    df["building_count"] = df["building_count"].fillna(0).astype(int)
    df["total_building_area_m2"] = df["total_building_area_m2"].fillna(0.0)
    df["building_density_per_km2"] = np.round(df["building_count"] / (df["hex_area_m2"] / 1_000_000.0), 2)
    df["avg_building_area_m2"] = np.round(
        np.where(df["building_count"] > 0, df["total_building_area_m2"] / df["building_count"], 0.0), 2
    )
    df["built_up_ratio"] = np.round(df["total_building_area_m2"] / df["hex_area_m2"], 4)

    return df[["h3_index", "building_count", "building_density_per_km2", "total_building_area_m2", "avg_building_area_m2", "built_up_ratio"]]


if __name__ == "__main__":
    from antenna_cell_placement.config import H3_GRID_GEOJSON_TEMPLATE, DEFAULT_PILOT_CITY

    grid = gpd.read_file(H3_GRID_GEOJSON_TEMPLATE.format(city=DEFAULT_PILOT_CITY))
    buildings = load_building_footprints()
    result = compute_building_features_per_hex(grid, buildings)
    print(result.sort_values("building_count", ascending=False).head())
