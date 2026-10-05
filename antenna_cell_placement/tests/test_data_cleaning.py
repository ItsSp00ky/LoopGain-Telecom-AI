import unittest

import pandas as pd

from antenna_cell_placement.data_cleaning import consolidate_physical_sites


class DataCleaningTests(unittest.TestCase):
    def towers(self):
        return pd.DataFrame({
            "longitude": [13.0, 13.0002, 14.0],
            "latitude": [32.0, 32.0, 32.0],
            "rat": ["LTE"] * 3, "rat_subtype": ["LTE"] * 3,
            "operator": ["Libyana"] * 3, "bands_str": ["3"] * 3,
            "tower_type": ["MACRO"] * 3, "has_timing_advance": [1] * 3,
            "has_signal_strength": [1] * 3, "total_bandwidth_mhz": [20.0] * 3,
            "channel_count": [1] * 3, "visible": [1] * 3,
            "first_seen_ms": [100] * 3, "last_seen_ms": [200] * 3,
        })

    def test_filtered_indices_keep_the_same_clusters(self):
        source = self.towers()
        expected, expected_sites = consolidate_physical_sites(source)
        source.index = [8, 20, 41]
        actual, actual_sites = consolidate_physical_sites(source)
        self.assertEqual(actual.index.tolist(), [8, 20, 41])
        pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected)
        pd.testing.assert_frame_equal(actual_sites, expected_sites)

    def test_collocation_distances_are_measured_from_the_centroid(self):
        towers, sites = consolidate_physical_sites(self.towers())
        self.assertEqual(sites.radio_tower_count.tolist(), [2, 1])
        self.assertGreater(towers.loc[0, "collocated_distance_m"], 0)
        self.assertAlmostEqual(towers.loc[0, "collocated_distance_m"],
                               towers.loc[1, "collocated_distance_m"], places=2)
        self.assertEqual(towers.loc[2, "collocated_distance_m"], 0)


if __name__ == "__main__":
    unittest.main()
