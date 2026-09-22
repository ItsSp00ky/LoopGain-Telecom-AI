import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, LineString, Polygon, box, mapping
from shapely.ops import transform

from antenna_cell_placement.gis_v2 import GeographicRaster, GEOD, EQUAL_AREA, FEATURE_VERSION, geodesic_circle, network_features, regional_line_distances
from antenna_cell_placement.inventory_audit_v2 import scoped_radio_inventory, audit_inventory, network_identity
from antenna_cell_placement.rooftop_candidates import roof_record, shortlist_buildings
from antenna_cell_placement.phase2_pipeline import VersionedSuitabilityModel, sha256
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS


class RasterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def raster(self, values, units='density', crs=4326):
        path = Path(self.temp.name)/'test.tif'
        values=np.asarray(values,dtype='float32')
        with rasterio.open(path,'w',driver='GTiff',height=values.shape[0],width=values.shape[1],count=1,
                           dtype='float32',crs=crs,transform=from_origin(13,33,.01,.01),nodata=-9999) as dst:
            dst.write(values,1)
        return GeographicRaster(path,units)

    def test_floor_pixel_index_and_bounds(self):
        r=self.raster([[1,2],[3,4]])
        self.assertEqual(r.sample(13.009,32.991),1)
        self.assertTrue(np.isnan(r.sample(12.999,32.995)))
        self.assertTrue(np.isnan(r.sample(13.03,32.995)))

    def test_density_to_people(self):
        r=self.raster([[100,100],[100,100]])
        p=box(13,32.98,13.02,33)
        expected=100*transform(EQUAL_AREA.transform,p).area/1e6
        self.assertAlmostEqual(r.zonal_population(p)['population'],expected,places=6)

    def test_population_conservation_across_partition(self):
        r=self.raster([[10,20],[30,40]])
        full=r.zonal_population(box(13,32.98,13.02,33))['population']
        parts=sum(r.zonal_population(box(a,32.98,b,33))['population'] for a,b in [(13,13.007),(13.007,13.02)])
        self.assertAlmostEqual(parts,full,places=6)

    def test_count_units_conserve_counts(self):
        r=self.raster([[10,20],[30,40]],'count')
        self.assertAlmostEqual(r.zonal_population(box(13,32.98,13.02,33))['population'],100,places=6)

    def test_nodata_is_unknown_not_zero(self):
        r=self.raster([[100,-9999],[100,-9999]])
        stats=r.zonal_population(box(13,32.98,13.02,33))
        self.assertTrue(np.isnan(stats['population']))
        self.assertGreater(stats['observed_population'],0)
        self.assertAlmostEqual(stats['valid_fraction'],.5,places=6)

    def test_outside_extent_counts_as_missing(self):
        r=self.raster([[100,100],[100,100]])
        stats=r.zonal_population(box(12.99,32.98,13.02,33))
        self.assertTrue(np.isnan(stats['population']))
        self.assertLess(stats['valid_fraction'],.7)
        self.assertTrue(np.isnan(r.zonal_population(box(10,20,11,21))['observed_population']))

    def test_uniform_circle_population(self):
        r=self.raster(np.full((20,20),100))
        actual=r.zonal_population(geodesic_circle(13.1,32.9,3000))['population']
        self.assertAlmostEqual(actual/(100*np.pi*9),1,delta=.002)

    def test_negative_elevation_is_retained(self):
        r=self.raster(np.full((20,20),-50),'elevation')
        elevation,prominence,slope=r.terrain(13.1,32.9)
        self.assertEqual(elevation,-50)
        self.assertAlmostEqual(prominence,0)
        self.assertAlmostEqual(slope,0)

    def test_slope_uses_actual_horizontal_distance(self):
        r=self.raster(np.tile(np.arange(20)*100,(20,1)),'elevation')
        _,_,slope=r.terrain(13.105,32.895)
        row,col=r.index(13.105,32.895)
        cx,cy=r.transform*(col+.5,row+.5)
        dx=GEOD.inv(cx-.01,cy,cx+.01,cy)[2]
        self.assertAlmostEqual(slope,np.degrees(np.arctan(200/dx)))

    def test_unsupported_crs_rejected(self):
        with self.assertRaisesRegex(ValueError,'EPSG:4326'):
            self.raster([[1]],crs=3857)


class DistanceTests(unittest.TestCase):
    def sites(self, coordinates):
        return pd.DataFrame({'physical_site_id':range(len(coordinates)),
            'canonical_longitude':[p[0] for p in coordinates],'canonical_latitude':[p[1] for p in coordinates],
            'has_libyana':True,'has_almadar':False})

    def test_known_distances_west_and_east(self):
        for lon in (10,24):
            x,y,_=GEOD.fwd(lon,32,90,5000)
            f=network_features(lon,32,self.sites([(x,y)]))
            self.assertAlmostEqual(f['dist_to_nearest_site_m'],5000,places=5)
            self.assertTrue(np.isnan(f['dist_to_almadar_site_m']))

    def test_identity_self_exclusion_keeps_colocated_other_site(self):
        f=network_features(13,32,self.sites([(13,32),(13,32)]),exclude_site_id=0)
        self.assertEqual(f['dist_to_nearest_site_m'],0)
        self.assertEqual(f['site_density_1km'],1)

    def test_road_distance_uses_line_interior(self):
        roads=gpd.GeoDataFrame(geometry=[LineString([(13,32),(13,32.1)])],crs=4326)
        points=gpd.GeoDataFrame(geometry=[Point(13,32.05)],crs=4326)
        self.assertLess(regional_line_distances(points,roads).iloc[0],2)


class InventoryTests(unittest.TestCase):
    def raw(self):
        return pd.DataFrame([dict(rat='LTE',region_id='1',site_id='2',mcc='606',mnc=mnc,
            owner_confirmed_almadar=False,record_id=i,last_seen_ms=i,latitude=32,longitude=13,bandwidths=[20])
            for i,mnc in enumerate(['0','0','1'],1)])

    def test_network_scope_and_snapshot_bandwidth(self):
        result=scoped_radio_inventory(self.raw())
        self.assertEqual(len(result),2)
        libyana=result[result.network_identity=='606:0'].iloc[0]
        self.assertEqual(libyana.bandwidth_latest_observed_mhz,20)
        self.assertEqual(libyana.bandwidth_naive_all_observations_mhz,40)

    def test_owner_confirmed_identity(self):
        self.assertEqual(network_identity({'owner_confirmed_almadar':True}), '606:1')

    def test_chain_cluster_audit_flags_endpoints(self):
        coords=[GEOD.fwd(13,32,90,d)[:2] for d in (0,40,80)]
        towers=pd.DataFrame({'physical_site_id':[1]*3,'longitude':[p[0] for p in coords],'latitude':[p[1] for p in coords]})
        _,clusters,audit=audit_inventory(self.raw(),towers,pd.DataFrame({'physical_site_id':[1]}))
        self.assertTrue(clusters.chain_exceeds_50m.iloc[0])
        self.assertAlmostEqual(audit['max_cluster_diameter_m'],80,places=5)
        self.assertEqual(audit['cross_network_legacy_key_collisions'],1)


class RoofAndModelTests(unittest.TestCase):
    def test_directory_raster_hash_tracks_components(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'grid.adf'
            p.write_bytes(b'one')
            before=sha256(folder)
            self.assertEqual(before,sha256(folder))
            p.write_bytes(b'two')
            self.assertNotEqual(before,sha256(folder))

    def test_footprint_does_not_invent_height(self):
        p=box(13,32,13.001,32.001)
        r=roof_record(p,{'height':-1},'fixture',1)
        self.assertTrue(np.isnan(r['building_height_m']))
        self.assertFalse(r['building_height_known'])
        self.assertTrue(r['structural_survey_required'])
        self.assertTrue(np.isnan(r['roof_usable_area_m2']))

    def test_candidate_point_inside_concave_building(self):
        p=Polygon([(13,32),(13.003,32),(13.003,32.003),(13.002,32.003),(13.002,32.001),(13,32.001)])
        r=roof_record(p,{},'fixture',1)
        self.assertTrue(p.contains(Point(r['canonical_longitude'],r['canonical_latitude'])))

    def test_tiny_footprint_rejected(self):
        self.assertIsNone(roof_record(box(13,32,13.00001,32.00001),{},'fixture',1))

    def test_shortlist_deduplicates_and_selects_footprint_area(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'buildings.gz'
            small=box(13,32,13.001,32.001)
            large=box(13.002,32,13.004,32.002)
            with gzip.open(path,'wt',encoding='utf-8') as stream:
                for geom in (small,large,large):
                    stream.write(json.dumps({'type':'Feature','properties':{'height':-1},'geometry':mapping(geom)})+'\n')
            areas=gpd.GeoDataFrame({'h3_index':['a'],'expansion_rank':[1]},geometry=[box(12.99,31.99,13.01,32.01)],crs=4326)
            result,audit=shortlist_buildings(areas,per_hex=1,tile_paths=[path])
            self.assertEqual(len(result),1)
            self.assertTrue(result.geometry.iloc[0].equals(large))
            self.assertEqual(audit['missing_height_records'],3)

    def test_model_rejects_silent_feature_version_change(self):
        pipeline=Mock()
        model=VersionedSuitabilityModel(pipeline)
        df=pd.DataFrame({c:[1.] for c in SUITABILITY_FEATURE_COLS})
        with self.assertRaisesRegex(ValueError,'feature_version'):
            model.predict_proba(df)
        df['feature_version']='legacy'
        with self.assertRaises(ValueError):
            model.predict_proba(df)
        pipeline.predict_proba.assert_not_called()
        df['feature_version']=FEATURE_VERSION
        model.predict_proba(df)
        pipeline.predict_proba.assert_called_once()


if __name__=='__main__':
    unittest.main()
