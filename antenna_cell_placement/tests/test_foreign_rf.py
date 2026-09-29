"""The external RF fixture contains measured rows and stays isolated."""

import json
from pathlib import Path
import tempfile
import unittest

from antenna_cell_placement.foreign_rf import SOURCE_DIR, _holdout, evaluate_foreign_rf_benchmark


class ForeignRfTests(unittest.TestCase):
    def test_real_source_joins_and_geographic_holdout(self):
        report = evaluate_foreign_rf_benchmark(output_path=None)
        quality, evaluation = report['source_quality'], report['evaluation']
        self.assertEqual(report['dataset_country'], 'China')
        self.assertEqual(quality['raw_rows'], 81419)
        self.assertEqual(quality['rows_with_exact_nci_eci_match_and_valid_distance'], 79795)
        self.assertEqual(evaluation['training_areas'] + evaluation['holdout_areas'], 29)
        self.assertEqual(evaluation['training_blocks'] + evaluation['holdout_blocks'], quality['measured_blocks'])
        self.assertLessEqual(evaluation['scored_holdout_blocks'], evaluation['holdout_blocks'])
        self.assertGreater(evaluation['distance_model']['mae_db'], evaluation['baseline']['mae_db'])
        self.assertEqual(report['distance_model_decision'], 'do_not_use')
        self.assertEqual(_holdout('883002c285fffff'), _holdout('883002c285fffff'))

    def test_raw_measurement_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = json.loads((SOURCE_DIR / 'manifest.json').read_text())
            (root / 'manifest.json').write_text(json.dumps(manifest))
            for name in manifest['files']:
                if name == 'raw_datas.csv':
                    (root / name).write_bytes(b'not real measurements')
                else:
                    (root / name).write_bytes((SOURCE_DIR / name).read_bytes())
            with self.assertRaisesRegex(ValueError, 'source hash or size mismatch'):
                evaluate_foreign_rf_benchmark(directory=root, output_path=None)


if __name__ == '__main__':
    unittest.main()
