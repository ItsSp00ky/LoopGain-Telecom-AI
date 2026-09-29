import tempfile
import unittest
from pathlib import Path

import joblib
import pandas as pd

from antenna_cell_placement.placement_model import (
    SUITABILITY_FEATURE_COLS,
    train_equipment_recommender,
)


class PlacementModelTests(unittest.TestCase):
    def test_equipment_model_uses_the_requested_output_directory(self):
        frame = pd.DataFrame([{column: 0.0 for column in SUITABILITY_FEATURE_COLS}] * 8)
        frame["total_bandwidth_mhz"] = 40.0
        frame["total_carrier_count"] = 3
        frame["primary_tower_type"] = "MACRO"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "custom-models"
            result = train_equipment_recommender(frame, output_dir=output)
            model_path = Path(result["equipment_model_path"])
            self.assertEqual(model_path.parent, output)
            self.assertTrue(model_path.is_file())
            self.assertEqual(joblib.load(model_path).classes_.tolist(), ["Urban_HighCapacity_Macro"])


if __name__ == '__main__':
    unittest.main()
