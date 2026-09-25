"""One public feature contract using corrected GIS and verified context."""
import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from antenna_cell_placement.config import CLEANED_PHYSICAL_SITES_CSV, ADMIN0_GEOJSON_PATH
from antenna_cell_placement.gis_v2 import FeatureExtractorV2, FEATURE_VERSION, MIN_VALID_FRACTION
from antenna_cell_placement.source_integrity import verify_sources, require_sources, group_ready


class PlanningFeatureExtractor:
    def __init__(self, operator='all', verification=None):
        if operator not in ('all', 'almadar', 'libyana'):
            raise ValueError('operator must be all, almadar or libyana')
        self.verification = verification or verify_sources()
        require_sources(self.verification)
        sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
        if operator != 'all':
            sites = sites.loc[sites[f'has_{operator}'].eq(True)].copy()
        self.operator = operator
        self.gis = FeatureExtractorV2(sites)
        self.boundary = gpd.read_file(ADMIN0_GEOJSON_PATH).to_crs(4326).geometry.union_all()

    def extract(self, lons, lats):
        result = self.gis.extract(lons, lats)
        result['inside_libya'] = [self.boundary.covers(p) for p in gpd.points_from_xy(lons, lats)]
        result['population_data_available'] = (
            result.population_valid_fraction_5km.ge(MIN_VALID_FRACTION)
            & np.isfinite(result.population_sum_5km)
        )
        terrain = ['elevation_m', 'elevation_prominence_3km', 'terrain_slope_deg']
        result['terrain_data_available'] = np.isfinite(result[terrain]).all(axis=1)
        result['population_units'] = 'people'
        result['population_radius_m'] = 5000
        result['population_source_units'] = 'people_per_km2'
        result['operator_scope'] = self.operator
        result['source_lock_sha256'] = self.verification['source_lock_sha256']
        result['h3_r7'] = [h3.latlng_to_cell(lat, lon, 7) for lon, lat in zip(lons, lats)]
        result['h3_r6'] = result.h3_r7.map(lambda cell: h3.cell_to_parent(cell, 6))
        result['h3_index'] = [h3.latlng_to_cell(lat, lon, 8) for lon, lat in zip(lons, lats)]
        result['h3_resolution'] = 8
        result['building_height_m'] = np.nan
        result['building_height_status'] = 'Unavailable'
        if group_ready(self.verification, 'worldcover'):
            from antenna_cell_placement.worldcover import WorldCoverExtractor
            result = WorldCoverExtractor().add_point_features(result)
        else:
            result['worldcover_data_available'] = False
            result['worldcover_is_water'] = pd.NA
            result['worldcover_class_name'] = pd.NA
        return result

    def add_context(self, frame):
        """Context cannot alter score, eligibility or ranking."""
        from antenna_cell_placement.buildings import BUILDING_COLUMNS, BuildingFootprintExtractor
        from antenna_cell_placement.osm_context import OSM_CONTEXT_COLUMNS, OSMContextExtractor
        result = frame.copy()
        if not result.empty and group_ready(self.verification, 'worldcover'):
            from antenna_cell_placement.worldcover import WorldCoverExtractor
            result = WorldCoverExtractor().add_h3_context(result)
        if not result.empty and group_ready(self.verification, 'osm'):
            result = BuildingFootprintExtractor.for_h3_frame(result).add_h3_context(result)
            result = OSMContextExtractor().add_context(result)
        else:
            for col in BUILDING_COLUMNS + OSM_CONTEXT_COLUMNS:
                result[col] = False if col.endswith(('available', 'observed_h3')) else pd.NA
            result['osm_building_review_required'] = True
        return result
