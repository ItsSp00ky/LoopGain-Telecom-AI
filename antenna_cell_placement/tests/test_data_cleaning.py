import unittest

import pandas as pd

from antenna_cell_placement.data_cleaning import (
    attribute_source_operators,
    consolidate_physical_sites,
    deduplicate_radio_towers,
)


class DataCleaningTests(unittest.TestCase):
    def raw_row(self, **changes):
        row = {
            "record_id": 1,
            "mcc": None,
            "mnc": None,
            "operator": None,
            "rat": "LTE",
            "rat_subtype": "LTE",
            "site_id": "site-1",
            "region_id": "region-1",
            "latitude": 32.88,
            "longitude": 13.18,
            "visible": pd.NA,
            "first_seen_ms": pd.NA,
            "last_seen_ms": pd.NA,
            "channels": [],
            "bands": [],
            "bandwidths": [],
            "tower_type": None,
            "has_timing_advance": 0,
            "has_signal_strength": 0,
        }
        row.update(changes)
        return row

    def test_missing_source_values_remain_unknown(self):
        towers = deduplicate_radio_towers(pd.DataFrame([self.raw_row()]))
        towers = attribute_source_operators(towers)

        self.assertTrue(pd.isna(towers.loc[0, "total_bandwidth_mhz"]))
        self.assertTrue(pd.isna(towers.loc[0, "primary_band"]))
        self.assertTrue(pd.isna(towers.loc[0, "active_days"]))
        self.assertFalse(towers.loc[0, "bandwidth_data_available"])
        self.assertFalse(towers.loc[0, "tower_type_data_available"])
        self.assertEqual(towers.loc[0, "operator"], "Unknown")
        self.assertTrue(pd.isna(towers.loc[0, "mnc"]))

        _, sites = consolidate_physical_sites(towers)
        self.assertTrue(pd.isna(sites.loc[0, "total_bandwidth_mhz"]))
        self.assertEqual(sites.loc[0, "primary_tower_type"], "Unknown")
        self.assertEqual(sites.loc[0, "operators"], "Unknown")

    def test_only_explicit_operator_evidence_is_mapped(self):
        raw = pd.DataFrame(
            [
                self.raw_row(site_id="zero", mnc="00"),
                self.raw_row(site_id="one", mnc="01", longitude=13.2),
                self.raw_row(site_id="other", mnc="9", longitude=13.3),
            ]
        )
        towers = attribute_source_operators(deduplicate_radio_towers(raw))
        by_site = towers.set_index("site_id")
        self.assertEqual(by_site.loc["zero", "operator"], "Libyana")
        self.assertEqual(by_site.loc["one", "operator"], "Al-Madar")
        self.assertEqual(by_site.loc["other", "operator"], "Unknown")
        self.assertEqual(by_site.loc["other", "mnc"], "9")


if __name__ == "__main__":
    unittest.main()
