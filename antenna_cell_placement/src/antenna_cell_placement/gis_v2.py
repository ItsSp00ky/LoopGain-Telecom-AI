"""Versioned GIS measurements. Never overwrites legacy features or models."""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Geod, Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform as transform_geometry

from antenna_cell_placement.config import (
    WORLDPOP_TIF_PATH, DEM_RASTER_PATH, ROADS_SHP_PATH,
    POP_PLACES_GEOJSON_PATH, ADMIN2_GEOJSON_PATH,
)

FEATURE_VERSION = 'gis_v2_density_circles_geodesic_20260922'
GEOD = Geod(ellps='WGS84')
EQUAL_AREA = Transformer.from_crs(4326, 6933, always_xy=True)
MIN_VALID_FRACTION = 0.99


def geodesic_circle(lon, lat, radius_m, vertices=96):
    if radius_m <= 0:
        raise ValueError('radius_m must be positive')
    bearings = np.linspace(0, 360, vertices, endpoint=False)
    x, y, _ = GEOD.fwd(np.full(vertices, lon), np.full(vertices, lat), bearings, np.full(vertices, radius_m))
    return Polygon(zip(x, y))


class GeographicRaster:
    """North-up WGS84 raster with floor indexing and explicit missing values.

    EPSG:6933 gives equal-area cell/intersection weights. A density value times
    the area in km² gives people; a count value is allocated by overlap fraction.
    Uniform density within a source pixel is an explicit approximation.
    """
    def __init__(self, path, units='density'):
        if units not in ('density', 'count', 'elevation'):
            raise ValueError('units must be density, count or elevation')
        with rasterio.open(path) as src:
            if src.crs != rasterio.crs.CRS.from_epsg(4326):
                raise ValueError('Expected EPSG:4326; explicitly reproject other rasters first')
            t = src.transform
            if t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0:
                raise ValueError('Expected north-up, unrotated geographic raster')
            self.values = src.read(1, masked=True).astype('float64').filled(np.nan)
            self.metadata = {'path': str(path), 'crs': str(src.crs), 'shape': list(src.shape),
                             'transform': list(t), 'nodata': src.nodata, 'tags': src.tags(),
                             'band_tags': src.tags(1), 'declared_units': units}
        self.units, self.transform = units, t
        self.height, self.width = self.values.shape
        if units != 'elevation':
            self.values[self.values < 0] = np.nan
        self.values[~np.isfinite(self.values)] = np.nan
        self.lon_edges = t.c + np.arange(self.width + 1) * t.a
        self.lat_edges = t.f + np.arange(self.height + 1) * t.e
        self.x_edges = EQUAL_AREA.transform(self.lon_edges, np.zeros(self.width + 1))[0]
        self.y_edges = EQUAL_AREA.transform(np.zeros(self.height + 1), self.lat_edges)[1]

    def index(self, lon, lat):
        col, row = (~self.transform) * (lon, lat)
        return int(np.floor(row)), int(np.floor(col))

    def sample(self, lon, lat):
        row, col = self.index(lon, lat)
        return float(self.values[row, col]) if 0 <= row < self.height and 0 <= col < self.width else np.nan

    def _window(self, bounds):
        west, south, east, north = bounds
        r0, c0 = self.index(west, north)
        r1, c1 = self.index(east, south)
        r0, r1 = max(0, r0), min(self.height, r1 + 1)
        c0, c1 = max(0, c0), min(self.width, c1 + 1)
        if r1 <= r0 or c1 <= c0:
            return None
        return r0, r1, c0, c1

    def zonal_population(self, polygon):
        """Return observed population, strict total and fraction of valid area."""
        if self.units == 'elevation':
            raise ValueError('Population units required')
        projected = transform_geometry(EQUAL_AREA.transform, polygon)
        if projected.area <= 0:
            raise ValueError('Polygon must have positive area')
        window = self._window(polygon.bounds)
        if window is None:
            return {'observed_population': np.nan, 'population': np.nan, 'valid_fraction': 0.0}
        r0, r1, c0, c1 = window
        rr, cc = np.meshgrid(np.arange(r0, r1), np.arange(c0, c1), indexing='ij')
        cells = shapely.box(self.x_edges[cc], self.y_edges[rr+1], self.x_edges[cc+1], self.y_edges[rr])
        areas = shapely.area(shapely.intersection(cells, projected))
        values = self.values[r0:r1, c0:c1]
        valid = np.isfinite(values) & (areas > 0)
        fraction = min(1.0, float(areas[valid].sum() / projected.area))
        if not valid.any():
            return {'observed_population': np.nan, 'population': np.nan, 'valid_fraction': fraction}
        weights = areas / 1e6 if self.units == 'density' else areas / shapely.area(cells)
        observed = float(np.sum(values[valid] * weights[valid]))
        return {'observed_population': observed,
                'population': observed if fraction >= MIN_VALID_FRACTION else np.nan,
                'valid_fraction': fraction}

    def density_at(self, lon, lat):
        value = self.sample(lon, lat)
        if self.units == 'density' or not np.isfinite(value):
            return value
        row, col = self.index(lon, lat)
        area = (self.x_edges[col+1]-self.x_edges[col])*(self.y_edges[row]-self.y_edges[row+1])
        return value / (area / 1e6)

    def terrain(self, lon, lat):
        """DEM elevation, area-weighted center-sampled 3km prominence and slope."""
        elevation = self.sample(lon, lat)
        row, col = self.index(lon, lat)
        slope = prominence = np.nan
        if not np.isfinite(elevation):
            return elevation, prominence, slope
        if 0 < row < self.height-1 and 0 < col < self.width-1:
            left, right = self.values[row, col-1], self.values[row, col+1]
            up, down = self.values[row-1, col], self.values[row+1, col]
            cx, cy = self.transform * (col+0.5, row+0.5)
            dx = GEOD.inv(cx-self.transform.a, cy, cx+self.transform.a, cy)[2]
            dy = GEOD.inv(cx, cy+self.transform.e, cx, cy-self.transform.e)[2]
            if np.isfinite([left,right,up,down]).all():
                slope = float(np.degrees(np.arctan(np.hypot((right-left)/dx, (up-down)/dy))))
        circle = geodesic_circle(lon, lat, 3000)
        window = self._window(circle.bounds)
        if window:
            r0,r1,c0,c1 = window
            rr,cc = np.meshgrid(np.arange(r0,r1), np.arange(c0,c1), indexing='ij')
            xs = self.transform.c + (cc+0.5)*self.transform.a
            ys = self.transform.f + (rr+0.5)*self.transform.e
            distances = GEOD.inv(np.full(xs.size,lon),np.full(xs.size,lat),xs.ravel(),ys.ravel())[2].reshape(xs.shape)
            inside = distances <= 3000
            vals = self.values[r0:r1,c0:c1]
            valid = inside & np.isfinite(vals)
            # Border truncation must not masquerade as full terrain coverage.
            full_extent = (circle.bounds[0] >= self.lon_edges[0] and circle.bounds[2] <= self.lon_edges[-1]
                           and circle.bounds[1] >= self.lat_edges[-1] and circle.bounds[3] <= self.lat_edges[0])
            if full_extent and inside.any() and valid.sum()/inside.sum() >= MIN_VALID_FRACTION:
                weights = (self.x_edges[cc+1]-self.x_edges[cc])*(self.y_edges[rr]-self.y_edges[rr+1])
                prominence = float(elevation - np.average(vals[valid],weights=weights[valid]))
        return elevation,prominence,slope


def network_features(lon, lat, sites, exclude_site_id=None):
    """Exact WGS84 ellipsoidal distances, with identity-based self exclusion."""
    n = len(sites)
    if n:
        distances = np.asarray(GEOD.inv(np.full(n,lon),np.full(n,lat),
            sites.canonical_longitude.to_numpy(),sites.canonical_latitude.to_numpy())[2])
        keep = np.ones(n,dtype=bool)
        if exclude_site_id is not None:
            keep &= sites.physical_site_id.to_numpy() != exclude_site_id
    else:
        distances,keep = np.array([]),np.array([],dtype=bool)
    result = {'dist_to_nearest_site_m':float(distances[keep].min()) if keep.any() else np.nan}
    for radius in (1,3,5,10):
        result[f'site_density_{radius}km'] = int(np.sum(keep & (distances <= radius*1000)))
    for operator in ('libyana','almadar'):
        selected = keep & sites[f'has_{operator}'].to_numpy().astype(bool) if n else keep
        result[f'dist_to_{operator}_site_m'] = float(distances[selected].min()) if selected.any() else np.nan
    return result


def regional_line_distances(points, lines):
    """Nearest actual road geometry in each query's local UTM zone (Libya)."""
    points = points.to_crs(4326)
    result = pd.Series(np.nan,index=points.index,dtype=float)
    zones = np.floor((points.geometry.x+180)/6).astype(int)+1
    for zone in sorted(zones.unique()):
        group = points[zones == zone].to_crs(32600+int(zone))
        projected_lines = lines.to_crs(group.crs)
        joined = gpd.sjoin_nearest(group[['geometry']],projected_lines[['geometry']],how='left',distance_col='distance')
        result.loc[group.index] = joined.groupby(level=0)['distance'].min().reindex(group.index)
    return result


class FeatureExtractorV2:
    def __init__(self, sites, population_units='density'):
        if population_units != 'density':
            raise ValueError('This feature version requires density units')
        self.sites = sites.reset_index(drop=True)
        if self.sites.physical_site_id.duplicated().any():
            raise ValueError('physical_site_id must be unique')
        self.population = GeographicRaster(WORLDPOP_TIF_PATH,population_units)
        self.dem = GeographicRaster(DEM_RASTER_PATH,'elevation')
        self.roads = gpd.read_file(ROADS_SHP_PATH).to_crs(4326)
        self.roads = self.roads[self.roads.geometry.notna() & ~self.roads.geometry.is_empty]
        self.places = gpd.read_file(POP_PLACES_GEOJSON_PATH).to_crs(4326)
        self.admin = gpd.read_file(ADMIN2_GEOJSON_PATH).to_crs(4326)

    def extract(self, lons, lats, site_ids=None):
        lons,lats = np.asarray(lons,dtype=float),np.asarray(lats,dtype=float)
        if len(lons)!=len(lats) or not np.isfinite(lons).all() or not np.isfinite(lats).all():
            raise ValueError('Coordinates must be equally sized and finite')
        if np.any((lons<9)|(lons>26)|(lats<19)|(lats>34)):
            raise ValueError('V2 regional extractor supports the Libya planning extent')
        ids = [None]*len(lons) if site_ids is None else list(site_ids)
        if len(ids)!=len(lons):
            raise ValueError('site_ids must match coordinates')
        points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lons,lats),crs=4326)
        road_distances = regional_line_distances(points,self.roads)
        joined = gpd.sjoin(points,self.admin[['adm2_name','geometry']],how='left',predicate='intersects')
        joined = joined[~joined.index.duplicated(keep='first')].reindex(points.index)
        rows=[]
        for i,(lon,lat,site_id) in enumerate(zip(lons,lats,ids)):
            row={'canonical_longitude':lon,'canonical_latitude':lat,'feature_version':FEATURE_VERSION,
                 'population_density_1km':self.population.density_at(lon,lat),
                 'dist_to_nearest_road_m':road_distances.iloc[i],
                 'municipality_name':joined.adm2_name.iloc[i]}
            for radius in (3,5):
                stats=self.population.zonal_population(geodesic_circle(lon,lat,radius*1000))
                row[f'population_sum_{radius}km']=stats['population']
                row[f'population_observed_{radius}km']=stats['observed_population']
                row[f'population_valid_fraction_{radius}km']=stats['valid_fraction']
            row['elevation_m'],row['elevation_prominence_3km'],row['terrain_slope_deg']=self.dem.terrain(lon,lat)
            row.update(network_features(lon,lat,self.sites,site_id))
            n=len(self.places)
            row['dist_to_nearest_settlement_m']=float(np.min(GEOD.inv(np.full(n,lon),np.full(n,lat),
                self.places.geometry.x.to_numpy(),self.places.geometry.y.to_numpy())[2])) if n else np.nan
            rows.append(row)
            if (i+1)%500==0:
                print(f'V2 features: {i+1}/{len(lons)}',flush=True)
        return pd.DataFrame(rows)
