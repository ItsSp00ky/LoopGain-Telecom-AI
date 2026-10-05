"""
OpenStreetMap (Geofabrik Libya extract) features for the H3 pilot-city planning grid.
Computes road density and POI counts (by category) per hexagon.
"""

from typing import Dict, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd

from antenna_cell_placement.config import OSM_LIBYA_PBF, PILOT_CITY_BBOXES, CRS_WGS84, CRS_PROJECTED_LIBYA

POI_CATEGORY_TAGS = {
    "hospital": {"amenity": ["hospital", "clinic"]},
    "school": {"amenity": ["school"]},
    "university": {"amenity": ["university", "college"]},
    "commercial": {"shop": True, "amenity": ["marketplace"]},
    "industrial": {"landuse": ["industrial"]},
}


def load_osm_pbf(city: str, pbf_path=OSM_LIBYA_PBF):
    """Load the Libya OSM extract scoped to a pilot city's bounding box."""
    import pyrosm

    bbox = PILOT_CITY_BBOXES[city]
    bounding_box = [bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]]
    print(f"Loading OSM extract scoped to {city} bbox...")
    return pyrosm.OSM(str(pbf_path), bounding_box=bounding_box)


def extract_roads_and_pois(osm) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Extract the road network and points of interest from a scoped OSM object."""
    print("Extracting road network...")
    roads = osm.get_network(network_type="driving")

    print("Extracting points of interest...")
    pois = osm.get_pois(custom_filter={"amenity": True, "shop": True, "landuse": ["industrial"]})

    return roads, pois


def _poi_matches_category(row: pd.Series, tags: Dict) -> bool:
    for key, allowed in tags.items():
        value = row.get(key)
        if pd.isna(value):
            continue
        if allowed is True:
            return True
        if value in allowed:
            return True
    return False


def compute_osm_features_per_hex(
    hex_gdf: gpd.GeoDataFrame,
    roads_gdf: Optional[gpd.GeoDataFrame],
    pois_gdf: Optional[gpd.GeoDataFrame],
) -> pd.DataFrame:
    """Compute per-hex road density (km per km^2) and POI counts by category."""
    hex_proj = hex_gdf.to_crs(CRS_PROJECTED_LIBYA).copy()
    hex_proj["hex_area_km2"] = hex_proj.geometry.area / 1_000_000.0

    df = hex_proj[["h3_index", "hex_area_km2"]].copy()

    if roads_gdf is not None and not roads_gdf.empty:
        roads_proj = roads_gdf.to_crs(CRS_PROJECTED_LIBYA)
        road_len = gpd.overlay(
            gpd.GeoDataFrame(geometry=roads_proj.geometry, crs=CRS_PROJECTED_LIBYA),
            hex_proj[["h3_index", "geometry"]],
            how="intersection",
        )
        road_len["length_km"] = road_len.geometry.length / 1000.0
        road_agg = road_len.groupby("h3_index")["length_km"].sum().reset_index(name="osm_road_length_km")
        df = df.merge(road_agg, on="h3_index", how="left")
    else:
        df["osm_road_length_km"] = 0.0

    df["osm_road_length_km"] = df["osm_road_length_km"].fillna(0.0)
    df["osm_road_density_km_per_km2"] = np.round(df["osm_road_length_km"] / df["hex_area_km2"], 3)

    if pois_gdf is not None and not pois_gdf.empty:
        pois_proj = pois_gdf.to_crs(CRS_PROJECTED_LIBYA).copy()
        pois_proj["geometry"] = pois_proj.geometry.centroid
        joined = gpd.sjoin(pois_proj, hex_proj[["h3_index", "geometry"]], how="inner", predicate="within")

        poi_counts = joined.groupby("h3_index").size().reset_index(name="poi_count")
        df = df.merge(poi_counts, on="h3_index", how="left")

        for category, tags in POI_CATEGORY_TAGS.items():
            mask = joined.apply(lambda row: _poi_matches_category(row, tags), axis=1)
            cat_counts = joined[mask].groupby("h3_index").size().reset_index(name=f"poi_count_{category}")
            df = df.merge(cat_counts, on="h3_index", how="left")
    else:
        df["poi_count"] = 0
        for category in POI_CATEGORY_TAGS:
            df[f"poi_count_{category}"] = 0

    count_cols = ["poi_count"] + [f"poi_count_{c}" for c in POI_CATEGORY_TAGS]
    for col in count_cols:
        df[col] = df[col].fillna(0).astype(int)

    return df.drop(columns=["hex_area_km2"])


if __name__ == "__main__":
    from antenna_cell_placement.config import H3_GRID_GEOJSON_TEMPLATE, DEFAULT_PILOT_CITY

    grid = gpd.read_file(H3_GRID_GEOJSON_TEMPLATE.format(city=DEFAULT_PILOT_CITY))
    osm = load_osm_pbf(DEFAULT_PILOT_CITY)
    roads, pois = extract_roads_and_pois(osm)
    result = compute_osm_features_per_hex(grid, roads, pois)
    print(result.sort_values("osm_road_density_km_per_km2", ascending=False).head())
