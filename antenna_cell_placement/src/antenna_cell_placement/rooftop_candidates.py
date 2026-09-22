"""Preliminary footprint shortlist. Height and engineering feasibility are unknown."""
import gzip
import hashlib
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import shape, mapping
from antenna_cell_placement.config import MS_BUILDING_FOOTPRINTS_TILES


def roof_record(geometry, properties, source, line_number, min_area_m2=150):
    """Geometry area is a footprint proxy, not measured usable flat roof area."""
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ('Polygon','MultiPolygon'):
        return None
    from antenna_cell_placement.gis_v2 import EQUAL_AREA
    from shapely.ops import transform
    area=float(transform(EQUAL_AREA.transform,geometry).area)
    if area < min_area_m2:
        return None
    height=properties.get('height')
    known=isinstance(height,(int,float)) and np.isfinite(height) and height>0
    point=geometry.representative_point()
    return {'building_id':hashlib.sha256(geometry.wkb).hexdigest()[:20],
            'source_tile':str(source),'source_line':line_number,
            'footprint_area_m2':area,'building_height_m':float(height) if known else np.nan,
            'building_height_known':bool(known),'height_source':'source_property' if known else 'unavailable',
            'canonical_longitude':point.x,'canonical_latitude':point.y,
            'structural_survey_required':True,'owner_permission_verified':False,
            'power_verified':False,'backhaul_verified':False,'roof_usable_area_m2':np.nan,
            'candidate_status':'preliminary_footprint_review','geometry':geometry}


def shortlist_buildings(top_hexes, min_area_m2=150, per_hex=5, tile_paths=None):
    """Scan footprints once; return the largest per reviewed area, with unknowns."""
    if per_hex<1 or min_area_m2<=0 or top_hexes.empty:
        raise ValueError('Need areas, positive per_hex and positive area threshold')
    tiles=MS_BUILDING_FOOTPRINTS_TILES if tile_paths is None else tile_paths
    polygons=list(top_hexes.geometry)
    tree=shapely.STRtree(polygons)
    buckets={i:[] for i in range(len(polygons))}
    audit={'scanned_buildings':0,'usable_height_records':0,'missing_height_records':0,
           'min_footprint_area_m2':min_area_m2,'per_hex':per_hex,'invalid_geometries':0}
    seen=set()
    for path in tiles:
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line_number,line in enumerate(stream,1):
                feature=json.loads(line)
                audit['scanned_buildings']+=1
                height=feature.get('properties',{}).get('height')
                known=isinstance(height,(int,float)) and np.isfinite(height) and height>0
                audit['usable_height_records' if known else 'missing_height_records']+=1
                geometry=shape(feature['geometry'])
                if not geometry.is_valid or geometry.is_empty:
                    audit['invalid_geometries']+=1
                    continue
                # Point is guaranteed inside the footprint, unlike some centroids.
                hits=tree.query(geometry.representative_point(),predicate='intersects')
                if not len(hits):
                    continue
                record=roof_record(geometry,feature.get('properties',{}),path.name,line_number,min_area_m2)
                if record is None or record['building_id'] in seen:
                    continue
                seen.add(record['building_id'])
                idx=min(map(int,hits))
                record['h3_index']=str(top_hexes.iloc[idx].h3_index)
                record['area_priority_rank']=int(top_hexes.iloc[idx].expansion_rank)
                buckets[idx].append(record)
                buckets[idx]=sorted(buckets[idx],key=lambda r:(-r['footprint_area_m2'],r['building_id']))[:per_hex]
        print(f'Building scan: {audit["scanned_buildings"]} records',flush=True)
    records=[r for rows in buckets.values() for r in rows]
    if not records:
        return gpd.GeoDataFrame(columns=['building_id','geometry'],geometry='geometry',crs=4326),audit
    gdf=gpd.GeoDataFrame(records,geometry='geometry',crs=4326)
    audit['shortlisted_buildings']=len(gdf)
    audit['ranking_policy']='Existing H3 area rank, then footprint area. No tallest-building or RF-suitability claim.'
    return gdf,audit


def export_rooftops(gdf, output_dir):
    from pathlib import Path
    import folium
    output_dir=Path(output_dir)
    # JSON conversion also supports an empty shortlist.
    (output_dir/'rooftop_candidates.geojson').write_text(gdf.to_json(),encoding='utf-8')
    gdf.drop(columns='geometry').to_csv(output_dir/'rooftop_candidates.csv',index=False)
    m=folium.Map(location=[32.85,13.25],zoom_start=11,tiles=None)
    from antenna_cell_placement.map_visualizer import add_local_basemap
    add_local_basemap(m)
    if len(gdf):
        folium.GeoJson(gdf.to_json(),name='Footprints for review',
            style_function=lambda _: {'color':'#ef6c00','fillOpacity':0.4},
            tooltip=folium.GeoJsonTooltip(fields=['building_id','footprint_area_m2','building_height_known','candidate_status'])).add_to(m)
        for _,row in gdf.iterrows():
            folium.CircleMarker([row.canonical_latitude,row.canonical_longitude],radius=3,
                tooltip=f'Area rank {row.area_priority_rank}; footprint {row.footprint_area_m2:.0f} m²; height unknown; survey required').add_to(m)
    folium.LayerControl().add_to(m)
    m.get_root().html.add_child(folium.Element('<div style="position:fixed;bottom:20px;left:20px;z-index:9999;background:white;padding:12px;max-width:330px">Preliminary building footprints for survey. Height, usable roof area, structural capacity, permission, power and backhaul are unverified.</div>'))
    m.save(str(output_dir/'rooftop_candidates_map.html'))
