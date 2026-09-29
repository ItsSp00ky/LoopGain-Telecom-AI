import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from antenna_cell_placement.collected_inventory import group_radio_records, physical_groups, GEOD
from antenna_cell_placement.collected_data import annotate_measurements
from antenna_cell_placement.pilot import _pilot_split
from antenna_cell_placement.source_integrity import sha256
from antenna_cell_placement.service_review import measurement_support


def record(identifier, **changes):
    row=dict(record_id=identifier, mcc='606', mnc='0',rat='LTE',region_id='1',site_id='1',
             latitude=32.8,longitude=13.2,first_seen_ms=1700000000000,last_seen_ms=1780000000000,
             owner_confirmed_almadar=False,source_verified=False,source_file='fixture')
    row.update(changes)
    return row


class InventoryV3Tests(unittest.TestCase):
    def test_network_scope_owner_attribution_and_crosswalk(self):
        frame=pd.DataFrame([record('a'),record('b',mcc=None,mnc=None,owner_confirmed_almadar=True)])
        radios,crosswalk=group_radio_records(frame)
        self.assertEqual(len(radios),2)
        self.assertEqual(crosswalk.set_index('record_id').loc['b','operator'],'Al-Madar')
        self.assertEqual(set(crosswalk.record_id),{'a','b'})
        self.assertTrue(pd.isna(frame.loc[1,'mnc']))  # caller/raw attributes are not rewritten

    def test_far_apart_identity_preserves_alternatives_and_is_order_stable(self):
        frame=pd.DataFrame([record('a'),record('b',longitude=23.0)])
        radios,_=group_radio_records(frame)
        shuffled,_=group_radio_records(frame.iloc[::-1])
        self.assertEqual(set(radios.longitude),{13.2,23.0})
        self.assertTrue(radios.location_conflict.all())
        pd.testing.assert_frame_equal(radios,shuffled)

    def test_50m_chain_never_becomes_80m_mast(self):
        points=[]
        for i in range(3):
            lon,lat,_=GEOD.fwd(13.2,32.8,90,i*40.)
            points.append(record(str(i),site_id=str(i),longitude=lon,latitude=lat))
        radios,_=group_radio_records(pd.DataFrame(points))
        clustered,sites=physical_groups(radios)
        self.assertEqual(len(sites),2)
        self.assertTrue(sites.geodesic_diameter_m.le(50.000001).all())
        self.assertEqual(len(clustered),3)
        self.assertTrue(set(zip(sites.canonical_longitude,sites.canonical_latitude)).issubset(set(zip(radios.longitude,radios.latitude))))

    def test_annotation_weights_blocks_and_preserves_score(self):
        row=dict(mcc=606,mnc=1,net_type='LTE',lat=32.8,lon=13.2,dbm=-100.,
                 device='A',measured_at=pd.Timestamp('2026-09-23T00:00Z'),review_eligible=True)
        measurements=pd.DataFrame([row]*100+[{**row,'device':'B','dbm':-60.}])
        candidates=pd.DataFrame([dict(candidate_id='x',canonical_latitude=32.8,canonical_longitude=13.2,planning_priority_score=77.)])
        result=annotate_measurements(candidates,measurements)
        self.assertEqual(result.measurement_mnc_1_lte_median_dbm_1km.iloc[0],-80.)
        self.assertEqual(result.planning_priority_score.iloc[0],77.)
        self.assertEqual(measurement_support(candidates,measurements)['with_observations_1km'],1)

    def test_missing_collection_is_unavailable_not_zero_measurements(self):
        candidates=pd.DataFrame([dict(canonical_latitude=32.8,canonical_longitude=13.2)])
        result=annotate_measurements(candidates,pd.DataFrame())
        self.assertFalse(result.measurement_context_available.iloc[0])
        self.assertTrue(pd.isna(result.measurement_count_1km.iloc[0]))

    def test_frozen_snapshot_uses_portable_paths_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=root/'data'/'input.csv'
            data.parent.mkdir()
            data.write_bytes(b'original')
            config=root/'snapshot.json'
            config.write_text(json.dumps({'version':2,'pilot_h3_r7':'fixture',
                'training_days':['2026-09-23'],'holdout_days':['2026-09-26'],
                'source_sha256':{'data/input.csv':sha256(data)}}))
            frame=pd.DataFrame({'day':['2026-09-23','2026-09-26']})
            with patch('antenna_cell_placement.pilot.MODULE_DIR',root):
                train,holdout,_=_pilot_split(frame,config,[data])
                self.assertEqual(len(train),1)
                self.assertEqual(len(holdout),1)
                data.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'snapshot changed'):
                    _pilot_split(frame,config,[data])


if __name__=='__main__':
    unittest.main()
