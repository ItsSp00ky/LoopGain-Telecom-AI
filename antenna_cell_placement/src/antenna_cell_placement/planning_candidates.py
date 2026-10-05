"""Tripoli H3 centres, or geodesic settlement rings and actual road samples."""
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import box, Point

from antenna_cell_placement.config import PILOT_CITY_BBOXES
from antenna_cell_placement.gis_v2 import GEOD
from antenna_cell_placement.planning_score import candidate_id


def generate_candidates(extractor, scope='Tripoli', resolution=8):
    rows = {}
    def add(lon, lat, source):
        lon, lat = round(float(lon), 7), round(float(lat), 7)
        if extractor.boundary.covers(Point(lon, lat)):
            rows.setdefault((lon, lat), set()).add(source)

    if scope == 'national':
        for point in extractor.gis.places.geometry:
            for radius in (2500., 4500., 7000., 10000.):
                for bearing in range(0, 360, 45):
                    lon, lat, _ = GEOD.fwd(point.x, point.y, bearing, radius)
                    add(lon, lat, 'settlement_ring_geodesic')
        # Interpolate actual lines in their local zones. Distances for ranking
        # and shortlist separation are computed independently by the v2 GIS.
        roads = extractor.gis.roads.explode(index_parts=False).reset_index(drop=True)
        for line in roads.geometry:
            if line.geom_type != 'LineString':
                continue
            zone = int((line.centroid.x + 180) // 6) + 1
            projected = gpd.GeoSeries([line], crs=4326).to_crs(32600 + zone).iloc[0]
            distances = np.linspace(0, projected.length, max(2, int(np.ceil(projected.length / 4000)) + 1))
            points = gpd.GeoSeries([projected.interpolate(d) for d in distances], crs=32600 + zone).to_crs(4326)
            for point in points:
                add(point.x, point.y, 'road_line_sample')
    else:
        if scope not in PILOT_CITY_BBOXES:
            raise ValueError(f'Unknown pilot {scope}')
        bounds = PILOT_CITY_BBOXES[scope]
        polygon = box(bounds['min_lon'], bounds['min_lat'], bounds['max_lon'], bounds['max_lat'])
        cells = sorted(h3.geo_to_cells(polygon.__geo_interface__, resolution))
        for cell in cells:
            lat, lon = h3.cell_to_latlng(cell)
            add(lon, lat, f'h3_r{resolution}_centre')
    result = pd.DataFrame([
        {'canonical_longitude': lon, 'canonical_latitude': lat, 'candidate_source': ';'.join(sorted(sources))}
        for (lon, lat), sources in sorted(rows.items())
    ], columns=['canonical_longitude', 'canonical_latitude', 'candidate_source'])
    result['candidate_id'] = result.apply(candidate_id, axis=1) if len(result) else pd.Series(dtype=str)
    return result
