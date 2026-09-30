import tempfile
import unittest
from pathlib import Path

from antenna_cell_placement.map_visualizer import generate_release_map

RUN = Path(__file__).resolve().parents[1] / "integrated_release_v3"


@unittest.skipUnless((RUN / "manifest.json").exists(), "no integrated_release_v3 run in this checkout")
class ReleaseMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.html = generate_release_map(RUN, Path(cls.tmp.name) / "map.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_layer_is_present_with_the_runs_own_counts(self):
        for layer in [
            "Eligible candidates by planning score (162)",
            "Rejected candidates (2061)",
            "Existing sites: Libyana",
            "Existing sites: Al-Madar",
            "Existing sites: both operators",
            "Building footprints for review",
            "Shortlist: top 20 for engineering review",
        ]:
            self.assertIn(layer, self.html)

    def test_legend_states_the_run_and_that_ranking_is_not_ml(self):
        self.assertIn("integrated_release_v3", self.html)
        self.assertIn("no ML in the ranking", self.html)
        self.assertIn("Rank #1 - Tripoli", self.html)

    def test_refuses_a_run_that_is_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.json").write_text('{"status": "running"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                generate_release_map(Path(tmp), Path(tmp) / "map.html")


if __name__ == "__main__":
    unittest.main()
