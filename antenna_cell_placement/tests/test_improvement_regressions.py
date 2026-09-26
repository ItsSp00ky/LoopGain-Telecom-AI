import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from antenna_cell_placement.data_cleaning import load_raw_records_from_sqlite, deduplicate_radio_towers, impute_operators
from antenna_cell_placement.h3_grid import replace_feature_columns
from antenna_cell_placement.expansion_score import _minmax_normalize, mask_unscorable_hexes, compute_landuse_demand
from antenna_cell_placement.evaluation import generate_hard_negatives
from antenna_cell_placement.feature_engineering import nearest_operator_distance
from antenna_cell_placement.training_experiment import assign_splits
from antenna_cell_placement.placement_model import generate_synthetic_negative_samples


class ImprovementRegressions(unittest.TestCase):
    def make_import(self, path, fingerprint, count=645):
        with sqlite3.connect(path) as conn:
            conn.executescript('''
                CREATE TABLE imports(import_id INTEGER, source_name TEXT, source_sha256 TEXT);
                CREATE TABLE source_responses(response_id INTEGER, import_id INTEGER);
                CREATE TABLE source_records(source_record_id INTEGER, response_id INTEGER, mcc TEXT, mnc TEXT, rat TEXT, raw_json TEXT);
            ''')
            conn.execute('INSERT INTO imports VALUES(1,?,?)',('cells.json',fingerprint))
            conn.execute('INSERT INTO source_responses VALUES(1,1)')
            for i in range(count):
                raw={'siteID':str(i),'regionID':'99','latitude':32.8,'longitude':13.1}
                conn.execute('INSERT INTO source_records VALUES(?,1,NULL,NULL,?,?)',(i,'LTE',json.dumps(raw)))
        conn.close()

    def test_confirmed_import_is_scoped_and_raw_operator_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cells.db'
            self.make_import(path,'a099aa826f11a80e7f4dc23405f70dff7bac9327fb82e129acb61fef0d1c2b2a')
            raw=load_raw_records_from_sqlite(path)
            self.assertEqual(int(raw.owner_confirmed_almadar.sum()),645)
            towers=impute_operators(deduplicate_radio_towers(raw))
            self.assertTrue(towers.operator.eq('Al-Madar').all())
            self.assertTrue(towers.raw_operator.isna().all())
            self.assertTrue(towers.operator_attribution_method.str.startswith('owner_confirmed').all())
            with sqlite3.connect(path) as conn:
                conn.execute("UPDATE imports SET source_sha256='another_import'")
            conn.close()
            self.assertFalse(load_raw_records_from_sqlite(path).owner_confirmed_almadar.any())

    def test_changed_historical_cohort_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cells.db'
            self.make_import(path,'a099aa826f11a80e7f4dc23405f70dff7bac9327fb82e129acb61fef0d1c2b2a',644)
            with self.assertRaisesRegex(ValueError,'645'):
                load_raw_records_from_sqlite(path)

    def test_feature_join_is_idempotent_and_missing_is_not_zero(self):
        base=pd.DataFrame({'h3_index':['a','b'],'building_count':[9,9],'building_count_x':[8,8]})
        features=pd.DataFrame({'h3_index':['a'],'building_count':[2]})
        first=replace_feature_columns(base,features)
        pd.testing.assert_frame_equal(first,replace_feature_columns(first,features))
        self.assertEqual(first.loc[0,'building_count'],2)
        self.assertTrue(pd.isna(first.loc[1,'building_count']))
        self.assertNotIn('building_count_x',first)
        with self.assertRaisesRegex(ValueError,'unique'):
            replace_feature_columns(base,pd.concat([features,features]))

    def test_missing_features_are_neutral_and_not_masked_as_uninhabited(self):
        values=_minmax_normalize(pd.Series([0.,10.,np.inf,np.nan]))
        self.assertEqual(values.iloc[2],0.5)
        df=pd.DataFrame({'population_sum_5km':[np.nan,0,0],
                         'dist_to_nearest_road_m':[5000,np.nan,5000],
                         'landcover_builtup_pct':[np.nan,20,10]})
        retained,_=mask_unscorable_hexes(df)
        self.assertEqual(retained.index.tolist(),[0,1])
        self.assertEqual(compute_landuse_demand(df).iloc[0],0.5)

    def test_hard_negatives_stay_inside_municipality_and_distance_band(self):
        sites=pd.DataFrame({'canonical_longitude':[13.1],'canonical_latitude':[32.8],'municipality_name':['A']})
        extractor=Mock()
        extractor.extract_features.return_value=pd.DataFrame({
            'dist_to_nearest_site_m':[1000,1000,3001,499],
            'population_sum_5km':[500]*4,'municipality_name':['A','B','A','A']})
        result=generate_hard_negatives(sites,extractor,n=4)
        self.assertEqual(result.index.tolist(),[0])

    def test_operator_neighbor_excludes_self_only_if_present(self):
        tree=cKDTree([[0,0],[100,0]])
        result=nearest_operator_distance(tree,np.array([[0,0],[20,0]]),True)
        np.testing.assert_allclose(result,[100,20])
        self.assertTrue(np.isnan(nearest_operator_distance(None,[[0,0]])[0]))
        self.assertTrue(np.isnan(nearest_operator_distance(cKDTree([[0,0]]),[[0,0]],True)[0]))

    def test_splits_preserve_municipality_membership(self):
        data=pd.DataFrame({'municipality_name':['Tripoli','Tripoli','Sebha','Sebha'],
                           'is_cell_site':[0,1,0,1]})
        result=assign_splits(data)
        self.assertEqual(result.split.tolist(),['development','development','test','test'])
        with self.assertRaisesRegex(ValueError,'both classes'):
            assign_splits(data.iloc[:3])

    def test_road_negative_rejects_nearby_sites_in_meter_coordinates(self):
        import geopandas as gpd
        from pyproj import Transformer
        extractor=Mock()
        extractor.road_tree=cKDTree([[500000.,3600000.],[507000.,3600000.]])
        extractor.site_tree_all=cKDTree([[500000.,3600000.]])
        extractor.places_df=gpd.GeoDataFrame(geometry=[],crs='EPSG:32633')
        extractor.extract_features.side_effect=lambda lons,lats,**kwargs: pd.DataFrame({'lon':lons,'lat':lats})
        result=generate_synthetic_negative_samples(pd.DataFrame(),extractor,n_negatives=5)
        xy=Transformer.from_crs('EPSG:4326','EPSG:32633',always_xy=True).transform(result.lon.iloc[0],result.lat.iloc[0])
        distance=extractor.site_tree_all.query(xy)[0]
        self.assertGreater(distance,5000)
        self.assertLess(distance,8000)


if __name__=='__main__':
    unittest.main()
