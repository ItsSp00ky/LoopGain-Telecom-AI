"""
Geospatial Feature Engineering Pipeline for Libyan Cell Tower Placement AI.
Integrates WorldPop Population Density, SRTM DEM Topography, UN OCHA Road Network,
and UN OCHA Administrative Districts into high-dimensional ML features.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree
import rasterio

from antenna_cell_placement.config import (
    WORLDPOP_TIF_PATH,
    DEM_RASTER_PATH,
    ROADS_SHP_PATH,
    ADMIN1_GEOJSON_PATH,
    ADMIN2_GEOJSON_PATH,
    POP_PLACES_GEOJSON_PATH,
    CLEANED_PHYSICAL_SITES_CSV,
    CLEANED_SITES_PARQUET,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
)


def nearest_operator_distance(tree, coordinates, exclude_self=False):
    """Exclude one colocated query point only if it exists in this operator index."""
    if tree is None:
        return np.full(len(coordinates), np.nan, dtype=np.float32)
    if not exclude_self:
        return tree.query(coordinates, k=1)[0].astype(np.float32)
    distances, _ = tree.query(coordinates, k=2)
    selected = np.where(distances[:, 0] < 1e-6, distances[:, 1], distances[:, 0])
    return np.where(np.isfinite(selected), selected, np.nan).astype(np.float32)


class GeospatialFeatureExtractor:
    """
    Centralized extractor for geospatial, environmental, and infrastructure features
    across Libya. Caches rasters and KD-trees in memory for sub-second vector extraction.
    """

    def __init__(self):
        self._loaded = False
        self.pop_arr = None
        self.pop_trans = None
        self.inv_pop = None
        self.pop_shape = None

        self.dem_arr = None
        self.dem_trans = None
        self.inv_dem = None
        self.dem_shape = None

        self.road_tree = None
        self.place_tree = None
        self.places_df = None
        self.admin2_gdf = None
        self.admin1_gdf = None

        self.site_tree_all = None
        self.site_tree_libyana = None
        self.site_tree_almadar = None
        self.existing_site_coords = None

    def load_layers(self):
        """Loads and precomputes geospatial raster and vector indices into memory."""
        if self._loaded:
            return

        print("Loading WorldPop 2020 1km raster...")
        with rasterio.open(WORLDPOP_TIF_PATH) as src:
            arr = src.read(1)
            self.pop_arr = np.where((arr == src.nodata) | (arr < 0) | np.isnan(arr), 0.0, arr).astype(np.float32)
            self.pop_trans = src.transform
            self.inv_pop = ~src.transform
            self.pop_shape = self.pop_arr.shape

        print("Loading SRTM DEM 250m raster...")
        with rasterio.open(DEM_RASTER_PATH) as src:
            arr = src.read(1)
            self.dem_arr = np.where((arr == src.nodata) | (arr < -100), 0, arr).astype(np.int16)
            self.dem_trans = src.transform
            self.inv_dem = ~src.transform
            self.dem_shape = self.dem_arr.shape

        print("Loading UN OCHA Highway & Road Network...")
        roads_gdf = gpd.read_file(ROADS_SHP_PATH).to_crs(CRS_PROJECTED_LIBYA)
        road_points = []
        for geom in roads_gdf.geometry:
            if geom is not None and not geom.is_empty:
                length = geom.length
                step = 500.0  # 500m sampling along road lines
                num_pts = max(1, int(length // step))
                for dist in np.linspace(0, length, num_pts):
                    pt = geom.interpolate(dist)
                    road_points.append((pt.x, pt.y))
        self.road_tree = cKDTree(np.array(road_points))

        print("Loading UN OCHA Populated Places & Administrative Boundaries...")
        self.places_df = gpd.read_file(POP_PLACES_GEOJSON_PATH).to_crs(CRS_PROJECTED_LIBYA)
        place_coords = np.array([(pt.x, pt.y) for pt in self.places_df.geometry])
        self.place_tree = cKDTree(place_coords)

        self.admin2_gdf = gpd.read_file(ADMIN2_GEOJSON_PATH).to_crs(CRS_PROJECTED_LIBYA)
        self.admin1_gdf = gpd.read_file(ADMIN1_GEOJSON_PATH).to_crs(CRS_PROJECTED_LIBYA)

        self._loaded = True
        print("All geospatial layers successfully initialized in memory.")

    def set_existing_sites(self, df_sites: pd.DataFrame):
        """Build spatial KDTree indices for existing physical cell sites."""
        gdf = gpd.GeoDataFrame(
            df_sites,
            geometry=[Point(lon, lat) for lon, lat in zip(df_sites["canonical_longitude"], df_sites["canonical_latitude"])],
            crs=CRS_WGS84
        ).to_crs(CRS_PROJECTED_LIBYA)

        coords_all = np.array([(pt.x, pt.y) for pt in gdf.geometry])
        self.site_tree_all = cKDTree(coords_all)
        self.existing_site_coords = coords_all

        self.site_tree_libyana = None
        self.site_tree_almadar = None
        lib_idx = df_sites[df_sites["has_libyana"] == 1].index
        mad_idx = df_sites[df_sites["has_almadar"] == 1].index

        if len(lib_idx) > 0:
            coords_lib = np.array([(pt.x, pt.y) for pt in gdf.loc[lib_idx, "geometry"]])
            self.site_tree_libyana = cKDTree(coords_lib)

        if len(mad_idx) > 0:
            coords_mad = np.array([(pt.x, pt.y) for pt in gdf.loc[mad_idx, "geometry"]])
            self.site_tree_almadar = cKDTree(coords_mad)

    def extract_features(
        self,
        lons: Union[List[float], np.ndarray],
        lats: Union[List[float], np.ndarray],
        is_existing_site: bool = False
    ) -> pd.DataFrame:
        """
        Vectorized feature extraction for an array of (lon, lat) coordinates.
        Supports both existing cell sites and arbitrary candidate points.
        """
        lons = np.asarray(lons, dtype=np.float64)
        lats = np.asarray(lats, dtype=np.float64)
        if (lons.ndim != 1 or lats.ndim != 1 or lons.shape != lats.shape
                or not len(lons) or not np.isfinite(lons).all() or not np.isfinite(lats).all()
                or (np.abs(lons) > 180).any() or (np.abs(lats) > 90).any()):
            raise ValueError("Expected non-empty, paired, finite longitude/latitude coordinates.")
        self.load_layers()
        n = len(lons)

        # 1. Project to UTM Zone 33N (meters) for accurate Euclidean measurements
        gdf_pts = gpd.GeoDataFrame(
            geometry=[Point(x, y) for x, y in zip(lons, lats)],
            crs=CRS_WGS84
        ).to_crs(CRS_PROJECTED_LIBYA)
        utm_coords = np.array([(pt.x, pt.y) for pt in gdf_pts.geometry])

        # 2. Extract Population Features (WorldPop)
        pop_dens_1km = np.zeros(n, dtype=np.float32)
        pop_sum_3km = np.zeros(n, dtype=np.float32)
        pop_sum_5km = np.zeros(n, dtype=np.float32)

        for i in range(n):
            col, row = self.inv_pop * (lons[i], lats[i])
            c, r = int(round(col)), int(round(row))
            if 0 <= r < self.pop_shape[0] and 0 <= c < self.pop_shape[1]:
                pop_dens_1km[i] = self.pop_arr[r, c]

                # 3km window (~3 pixels radius)
                r0, r1 = max(0, r - 3), min(self.pop_shape[0], r + 4)
                c0, c1 = max(0, c - 3), min(self.pop_shape[1], c + 4)
                pop_sum_3km[i] = self.pop_arr[r0:r1, c0:c1].sum()

                # 5km window (~5 pixels radius)
                r0, r1 = max(0, r - 5), min(self.pop_shape[0], r + 6)
                c0, c1 = max(0, c - 5), min(self.pop_shape[1], c + 6)
                pop_sum_5km[i] = self.pop_arr[r0:r1, c0:c1].sum()

        # Population classification
        pop_categories = []
        for val in pop_dens_1km:
            if val >= 1000.0:
                pop_categories.append("Urban_High_Density")
            elif val >= 100.0:
                pop_categories.append("Suburban_Medium_Density")
            elif val >= 5.0:
                pop_categories.append("Rural_Low_Density")
            else:
                pop_categories.append("Remote_Desert")

        # 3. Extract Topography & Elevation (SRTM DEM)
        elevation_m = np.zeros(n, dtype=np.float32)
        prominence_3km = np.zeros(n, dtype=np.float32)
        terrain_slope_deg = np.zeros(n, dtype=np.float32)

        for i in range(n):
            col, row = self.inv_dem * (lons[i], lats[i])
            c, r = int(round(col)), int(round(row))
            if 0 <= r < self.dem_shape[0] and 0 <= c < self.dem_shape[1]:
                elev = float(self.dem_arr[r, c])
                elevation_m[i] = elev

                # 3km window (~12 pixels radius at 250m)
                r0, r1 = max(0, r - 12), min(self.dem_shape[0], r + 13)
                c0, c1 = max(0, c - 12), min(self.dem_shape[1], c + 13)
                surr_mean = float(self.dem_arr[r0:r1, c0:c1].mean())
                prominence_3km[i] = elev - surr_mean

                # Local slope gradient
                if 0 < r < self.dem_shape[0] - 1 and 0 < c < self.dem_shape[1] - 1:
                    dz_dx = (float(self.dem_arr[r, c+1]) - float(self.dem_arr[r, c-1])) / 500.0
                    dz_dy = (float(self.dem_arr[r+1, c]) - float(self.dem_arr[r-1, c])) / 500.0
                    terrain_slope_deg[i] = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))

        # 4. Extract Transportation & Infrastructure (UN OCHA Roads)
        dist_to_road_m, _ = self.road_tree.query(utm_coords)

        road_tiers = []
        for d in dist_to_road_m:
            if d <= 250.0:
                road_tiers.append("Highway_Corridor")
            elif d <= 1000.0:
                road_tiers.append("Road_Adjacent")
            elif d <= 5000.0:
                road_tiers.append("Moderate_Access")
            else:
                road_tiers.append("Remote_OffRoad")

        # 5. Extract Settlement Proximity & Administrative Names
        dist_to_place_m, place_idxs = self.place_tree.query(utm_coords)
        nearest_settlement_names = self.places_df.iloc[place_idxs]["featurename_en"].values
        nearest_settlement_classes = self.places_df.iloc[place_idxs]["popplaceclasstitle"].values

        # Spatial join with Admin2 municipalities (with fallback to nearest geometry)
        joined_admin2 = gpd.sjoin_nearest(
            gdf_pts[["geometry"]],
            self.admin2_gdf[["adm2_name", "adm1_name", "geometry"]],
            how="left"
        )
        # Deduplicate if point is equidistant to two polygons
        joined_admin2 = joined_admin2[~joined_admin2.index.duplicated(keep="first")]
        municipalities = joined_admin2["adm2_name"].values
        macro_regions = joined_admin2["adm1_name"].values

        # 6. Extract Spatial Network Topology Features
        dist_to_nearest_site_m = np.zeros(n, dtype=np.float32)
        site_dens_1km = np.zeros(n, dtype=np.int32)
        site_dens_3km = np.zeros(n, dtype=np.int32)
        site_dens_5km = np.zeros(n, dtype=np.int32)
        site_dens_10km = np.zeros(n, dtype=np.int32)
        dist_to_libyana_m = np.zeros(n, dtype=np.float32)
        dist_to_almadar_m = np.zeros(n, dtype=np.float32)

        if self.site_tree_all is not None:
            if is_existing_site:
                # k=2 because k=1 is self
                dists, _ = self.site_tree_all.query(utm_coords, k=2)
                dist_to_nearest_site_m = dists[:, 1].astype(np.float32)
            else:
                dists, _ = self.site_tree_all.query(utm_coords, k=1)
                dist_to_nearest_site_m = dists.astype(np.float32)

            # Count in one batch per radius, without allocating lists of neighbor indices.
            densities = []
            for radius in (1000.0, 3000.0, 5000.0, 10000.0):
                counts = self.site_tree_all.query_ball_point(utm_coords, radius, return_length=True)
                densities.append(np.maximum(0, counts - int(is_existing_site)).astype(np.int32))
            site_dens_1km, site_dens_3km, site_dens_5km, site_dens_10km = densities

            dist_to_libyana_m = nearest_operator_distance(self.site_tree_libyana, utm_coords, is_existing_site)
            dist_to_almadar_m = nearest_operator_distance(self.site_tree_almadar, utm_coords, is_existing_site)

        # Build feature DataFrame
        df_features = pd.DataFrame({
            "canonical_latitude": lats,
            "canonical_longitude": lons,
            "utm_x": utm_coords[:, 0],
            "utm_y": utm_coords[:, 1],
            # Population features
            "population_density_1km": np.round(pop_dens_1km, 1),
            "population_sum_3km": np.round(pop_sum_3km, 0),
            "population_sum_5km": np.round(pop_sum_5km, 0),
            "population_category": pop_categories,
            # Topography features
            "elevation_m": np.round(elevation_m, 1),
            "elevation_prominence_3km": np.round(prominence_3km, 1),
            "terrain_slope_deg": np.round(terrain_slope_deg, 2),
            # Transportation features
            "dist_to_nearest_road_m": np.round(dist_to_road_m, 1),
            "road_access_tier": road_tiers,
            # Settlement & Admin
            "dist_to_nearest_settlement_m": np.round(dist_to_place_m, 1),
            "nearest_settlement_name": nearest_settlement_names,
            "nearest_settlement_class": nearest_settlement_classes,
            "municipality_name": municipalities,
            "macro_region": macro_regions,
            # Spatial Network Topology
            "dist_to_nearest_site_m": np.round(dist_to_nearest_site_m, 1),
            "dist_to_libyana_site_m": np.round(dist_to_libyana_m, 1),
            "dist_to_almadar_site_m": np.round(dist_to_almadar_m, 1),
            "site_density_1km": site_dens_1km,
            "site_density_3km": site_dens_3km,
            "site_density_5km": site_dens_5km,
            "site_density_10km": site_dens_10km,
            "is_coverage_isolated": (dist_to_nearest_site_m > 5000.0).astype(int),
        })

        # Add optional regional Internet-demand context. These columns are not
        # classifier inputs; the optimizer uses a bounded factor for final ranking.
        from antenna_cell_placement.cloudflare_radar import add_regional_features

        return add_regional_features(df_features)


def enrich_physical_sites_pipeline() -> pd.DataFrame:
    """Enriches cleaned physical sites with geospatial, demographic, and topography features."""
    print("Loading cleaned physical sites...")
    df_sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
    print(f"Loaded {len(df_sites)} sites.")

    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    extractor.set_existing_sites(df_sites)

    print("Extracting multi-layer geospatial features for existing cell sites...")
    features = extractor.extract_features(
        lons=df_sites["canonical_longitude"].values,
        lats=df_sites["canonical_latitude"].values,
        is_existing_site=True
    )

    # Combine original site attributes with enriched features
    # Drop duplicate coordinate columns from features
    feature_cols = [c for c in features.columns if c not in ["canonical_latitude", "canonical_longitude"]]
    df_combined = pd.concat([df_sites, features[feature_cols]], axis=1)

    # Calculate capacity efficiency metric (MHz per 1,000 population served within 3km)
    df_combined["bandwidth_per_1k_pop_3km"] = np.round(
        df_combined["total_bandwidth_mhz"] / ((df_combined["population_sum_3km"] / 1000.0) + 1.0), 3
    )

    # Save to Parquet and CSV
    CLEANED_SITES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_combined.to_parquet(CLEANED_SITES_PARQUET, index=False)
    print(f"Exported enriched dataset to Parquet: {CLEANED_SITES_PARQUET}")

    enriched_csv_path = CLEANED_PHYSICAL_SITES_CSV.parent / "cleaned_physical_sites_enriched.csv"
    df_combined.to_csv(enriched_csv_path, index=False)
    print(f"Exported enriched dataset to CSV: {enriched_csv_path}")

    return df_combined


if __name__ == "__main__":
    enrich_physical_sites_pipeline()
