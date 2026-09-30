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

    def test_embedded_apps_are_checked_here_but_opened_at_their_public_address(self):
        public = {
            'CHURN_APP_PUBLIC_URL': 'https://churn.example.test',
            'CHATBOT_APP_PUBLIC_URL': 'https://chatbot.example.test',
            'COPILOT_APP_PUBLIC_URL': 'https://copilot.example.test',
        }
        checked = []
        with patch.multiple(_shared, **public), \
                patch.object(_shared, 'app_available', side_effect=lambda url: checked.append(url) or True), \
                patch.object(_shared, 'churn_portfolio', return_value=(None, 'offline')):
            pages = [AppTest.from_file(str(APP / 'views' / f'{page}.py')).run(timeout=30)
                     for page in ['4_Customer_Churn', '5_Assistants']]
        for at in pages:
            self.assertFalse(at.exception)
        self.assertEqual(checked, [_shared.CHURN_APP_URL, _shared.CHATBOT_APP_URL, _shared.COPILOT_APP_URL])
        frames = [frame.proto.src for at in pages for frame in at.get('iframe')]
        self.assertEqual(frames, [f'{url}/?embed=true&embed_options=light_theme' for url in public.values()])
        self.assertEqual([link.proto.url for at in pages for link in at.get('link_button')], list(public.values()))

    def test_full_map_opens_at_the_public_gis_address(self):
        site = {
            'recommendation_rank': 1, 'planning_priority_score': 66.7, 'reason_codes': 'high_population;large_gap',
            'dist_to_nearest_site_m': 3300.0, 'population_sum_5km': 30724.0, 'dist_to_nearest_road_m': 40.0,
            'canonical_latitude': 32.8, 'canonical_longitude': 13.2, 'municipality_name': 'Tripoli Centre',
            'candidate_status': 'recommended',
        }
        responses = {'/health': {'status': 'ok'}, '/shortlist': {'features': [{'properties': site}]}}
        called = []
        def response(base, path, **kwargs):
            called.append(base)
            return responses[path], None
        with patch.object(_shared, 'GIS_PUBLIC_URL', 'https://gis.example.test'), \
                patch.object(_shared, 'load_json', side_effect=response):
            at = AppTest.from_file(str(APP / 'views/1_GIS_Planning.py')).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(set(called), {_shared.GIS_API_URL})
        self.assertEqual([link.proto.url for link in at.get('link_button')], ['https://gis.example.test/full-map'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
