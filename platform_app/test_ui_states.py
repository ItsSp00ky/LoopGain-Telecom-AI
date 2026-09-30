"""UI recovery tests. Mocked responses stay inside AppTest, never a running server."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))
import _shared

class UIStates(unittest.TestCase):
    def tearDown(self):
        _shared.get_json.clear()

    def test_offline_pages_have_retry_and_no_raw_exceptions(self):
        for page in ['1_GIS_Planning', '2_Network_KPI', '3_Congestion_Steering', '4_Customer_Churn', '5_Assistants']:
            with self.subTest(page=page), patch('requests.get', side_effect=requests.ConnectionError('INTERNAL_HOST_SENTINEL')):
                _shared.get_json.clear()
                at = AppTest.from_file(str(APP / 'views' / f'{page}.py')).run(timeout=30)
                self.assertFalse(at.exception)
                retry = [button for button in at.button if button.label == 'Try again']
                self.assertTrue(retry)
                self.assertNotIn('INTERNAL_HOST_SENTINEL', str([x.value for x in at.markdown]))
                retry[0].click().run(timeout=30)
                self.assertFalse(at.exception)

    def test_empty_shortlist_has_explanation(self):
        with patch.object(_shared, 'load_json', side_effect=[({'status':'ok'}, None), ({'features':[]}, None)]):
            at = AppTest.from_file(str(APP / 'views/1_GIS_Planning.py')).run()
        self.assertFalse(at.exception)
        self.assertIn('no shortlisted sites', at.info[0].value)

    def test_empty_network_sections_do_not_hide_other_tabs(self):
        responses = {
            '/health': {'status':'ok'},
            '/kpis/catalog': {'kpis':[{'key':'test','name':'Test KPI'}], 'bands':[{'band':900,'name':'900 MHz'}]},
            '/kpis/status': {'status':[]},
            '/kpis/scorecard': {'scorecard':[]},
        }
        def response(base, path, **kwargs):
            return responses.get(path, {'forecast':[], 'history':[]}), None
        with patch.object(_shared, 'load_json', side_effect=response):
            at = AppTest.from_file(str(APP / 'views/2_Network_KPI.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs), 4)
        self.assertEqual(len(at.info), 4)

    def test_empty_cluster_and_tower_data_are_explained(self):
        responses = {
            '/steering/summary': {'window_start':'2026-09-01','window_end':'2026-09-02', 'latest_day':{'alerts_by_category':{},'recommendations':0}, 'towers_with_alerts':0, 'recommendations_by_priority':{}},
            '/steering/recommendations?limit=200': {'count':0,'total':0,'date':'2026-09-02','recommendations':[]},
            '/steering/clusters': {'clusters':[]},
            '/towers/TWR_0029/forecast': {'series':{}},
        }
        with patch.object(_shared, 'load_json', side_effect=lambda base,path,**kw:(responses[path],None)):
            at = AppTest.from_file(str(APP / 'views/3_Congestion_Steering.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs), 3)
        self.assertTrue(any('No cluster' in x.value for x in at.info))
        self.assertTrue(any('No forecast' in x.value for x in at.info))

if __name__ == '__main__':
    unittest.main(verbosity=2)
