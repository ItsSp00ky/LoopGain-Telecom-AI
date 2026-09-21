"""Derive auditable planning features from the supplied Libya GIS layers."""

from typing import List, Union

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
    ADMIN0_GEOJSON_PATH,
    ADMIN2_GEOJSON_PATH,
    POP_PLACES_GEOJSON_PATH,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
)
from antenna_cell_placement.population import (
    circular_population_sum,
    density_to_population_counts,
)


class GeospatialFeatureExtractor:
    """
    Centralized extractor for geospatial, environmental, and infrastructure features
    across Libya. Caches rasters and KD-trees in memory for sub-second vector extraction.
    """

    def __init__(self):
        self._loaded = False
        self.pop_arr = None
        self.pop_count_arr = None
        self.pop_transform = None
        self.inv_pop = None
        self.pop_shape = None

        self.dem_arr = None
        self.inv_dem = None
        self.dem_shape = None

        self.road_tree = None
        self.place_tree = None
        self.places_df = None
        self.admin2_gdf = None
        self.libya_boundary = None

        self.site_tree_all = None

    def load_layers(self):
        """Loads and precomputes geospatial raster and vector indices into memory."""
        if self._loaded:
            return

        print("Loading WorldPop 2020 1km raster...")
        with rasterio.open(WORLDPOP_TIF_PATH) as src:
            arr = src.read(1, masked=True).astype(np.float32)
            self.pop_arr = arr.filled(np.nan)
            self.pop_arr[self.pop_arr < 0] = np.nan
            self.pop_count_arr = density_to_population_counts(
                self.pop_arr, src.transform
            )
            self.pop_transform = src.transform
            self.inv_pop = ~src.transform
            self.pop_shape = self.pop_arr.shape

        print("Loading SRTM DEM 250m raster...")
        with rasterio.open(DEM_RASTER_PATH) as src:
            arr = src.read(1, masked=True).astype(np.float32)
            self.dem_arr = arr.filled(np.nan)
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
        self.libya_boundary = (
            gpd.read_file(ADMIN0_GEOJSON_PATH)
            .to_crs(CRS_PROJECTED_LIBYA)
            .geometry.union_all()
        )

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

    def extract_features(
        self,
        lons: Union[List[float], np.ndarray],
        lats: Union[List[float], np.ndarray],
        is_existing_site: bool = False,
        include_worldcover: bool = True,
    ) -> pd.DataFrame:
        """
        Vectorized feature extraction for an array of (lon, lat) coordinates.
        Supports both existing cell sites and arbitrary candidate points.
        """
        self.load_layers()

        lons = np.asarray(lons, dtype=np.float64)
        lats = np.asarray(lats, dtype=np.float64)
        n = len(lons)

        # 1. Project to UTM Zone 33N (meters) for accurate Euclidean measurements
        gdf_pts = gpd.GeoDataFrame(
            geometry=[Point(x, y) for x, y in zip(lons, lats)],
            crs=CRS_WGS84
        ).to_crs(CRS_PROJECTED_LIBYA)
        utm_coords = np.array([(pt.x, pt.y) for pt in gdf_pts.geometry])

        # 2. Extract Population Features (WorldPop)
        pop_dens_1km = np.full(n, np.nan, dtype=np.float32)
        pop_sum_5km = np.full(n, np.nan, dtype=np.float32)

        for i in range(n):
            col, row = self.inv_pop * (lons[i], lats[i])
            c, r = int(np.floor(col)), int(np.floor(row))
            if 0 <= r < self.pop_shape[0] and 0 <= c < self.pop_shape[1]:
                pop_dens_1km[i] = self.pop_arr[r, c]
                pop_sum_5km[i] = circular_population_sum(
                    self.pop_count_arr,
                    self.pop_transform,
                    lons[i],
                    lats[i],
                    r,
                    c,
                )

        # 3. Extract Topography & Elevation (SRTM DEM)
        elevation_m = np.full(n, np.nan, dtype=np.float32)
        prominence_3km = np.full(n, np.nan, dtype=np.float32)
        terrain_slope_deg = np.full(n, np.nan, dtype=np.float32)

        for i in range(n):
            col, row = self.inv_dem * (lons[i], lats[i])
            c, r = int(np.floor(col)), int(np.floor(row))
            if 0 <= r < self.dem_shape[0] and 0 <= c < self.dem_shape[1]:
                elev = float(self.dem_arr[r, c])
                elevation_m[i] = elev

                # 3km window (~12 pixels radius at 250m)
                r0, r1 = max(0, r - 12), min(self.dem_shape[0], r + 13)
                c0, c1 = max(0, c - 12), min(self.dem_shape[1], c + 13)
                window = self.dem_arr[r0:r1, c0:c1]
                if np.isfinite(elev) and np.isfinite(window).any():
                    prominence_3km[i] = elev - float(np.nanmean(window))

                # Local slope gradient
                if 0 < r < self.dem_shape[0] - 1 and 0 < c < self.dem_shape[1] - 1:
                    neighbors = self.dem_arr[[r, r, r + 1, r - 1], [c + 1, c - 1, c, c]]
                    if np.isfinite(neighbors).all():
                        dz_dx = (float(neighbors[0]) - float(neighbors[1])) / 500.0
                        dz_dy = (float(neighbors[2]) - float(neighbors[3])) / 500.0
                        terrain_slope_deg[i] = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))

        # 4. Extract Transportation & Infrastructure (UN OCHA Roads)
        dist_to_road_m, _ = self.road_tree.query(utm_coords)

        # 5. Extract Settlement Proximity & Administrative Names
        _, place_idxs = self.place_tree.query(utm_coords)
        nearest_settlement_names = self.places_df.iloc[place_idxs]["featurename_en"].values

        # Spatial join with Admin2 municipalities (with fallback to nearest geometry)
        joined_admin2 = gpd.sjoin_nearest(
            gdf_pts[["geometry"]],
            self.admin2_gdf[["adm2_name", "geometry"]],
            how="left"
        )
        # Deduplicate if point is equidistant to two polygons
        joined_admin2 = joined_admin2[~joined_admin2.index.duplicated(keep="first")]
        municipalities = joined_admin2["adm2_name"].values
        inside_libya = gdf_pts.geometry.apply(self.libya_boundary.covers).to_numpy(dtype=bool)
        municipalities = np.where(inside_libya, municipalities, None)

        # 6. Extract Spatial Network Topology Features
        dist_to_nearest_site_m = np.full(n, np.nan, dtype=np.float32)
        if self.site_tree_all is not None:
            if is_existing_site:
                # k=2 because k=1 is self
                dists, _ = self.site_tree_all.query(utm_coords, k=2)
                dist_to_nearest_site_m = dists[:, 1].astype(np.float32)
            else:
                dists, _ = self.site_tree_all.query(utm_coords, k=1)
                dist_to_nearest_site_m = dists.astype(np.float32)

        # Build feature DataFrame
        df_features = pd.DataFrame({
            "canonical_latitude": lats,
            "canonical_longitude": lons,
            "utm_x": utm_coords[:, 0],
            "utm_y": utm_coords[:, 1],
            # Population features
            "population_density_1km": np.round(pop_dens_1km, 1),
            "population_sum_5km": np.round(pop_sum_5km, 0),
            "population_data_available": np.isfinite(pop_dens_1km) & np.isfinite(pop_sum_5km),
            # Topography features
            "elevation_m": np.round(elevation_m, 1),
            "elevation_prominence_3km": np.round(prominence_3km, 1),
            "terrain_slope_deg": np.round(terrain_slope_deg, 2),
            "terrain_data_available": (
                np.isfinite(elevation_m) & np.isfinite(prominence_3km)
                & np.isfinite(terrain_slope_deg)
            ),
            # Transportation features
            "dist_to_nearest_road_m": np.round(dist_to_road_m, 1),
            # Settlement & Admin
            "nearest_settlement_name": nearest_settlement_names,
            "municipality_name": municipalities,
            "inside_libya": inside_libya,
            # Spatial Network Topology
            "dist_to_nearest_site_m": np.round(dist_to_nearest_site_m, 1),
        })

        if include_worldcover:
            from antenna_cell_placement.worldcover import WorldCoverExtractor

            df_features = WorldCoverExtractor().add_point_features(df_features)

        # Add optional regional Internet-demand context without affecting rank.
        from antenna_cell_placement.cloudflare_radar import add_regional_features

        return add_regional_features(df_features)


def enrich_physical_sites_pipeline(df_sites: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build an enriched physical-site table in memory from supplied inputs."""
    if df_sites is None:
        from antenna_cell_placement.data_cleaning import clean_pipeline

        _, df_sites = clean_pipeline()
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

    return df_combined


if __name__ == "__main__":
    enrich_physical_sites_pipeline()
