"""Checks that public official tables remain genuine and geographically honest."""

import json
from pathlib import Path
import tempfile
import unittest

from antenna_cell_placement.public_evidence import SOURCE_DIR, evaluate_public_evidence


class PublicEvidenceTests(unittest.TestCase):
    def test_real_official_tables_keep_unmatched_regions_visible(self):
        report = evaluate_public_evidence(output_path=None)
        comparison = report['population_comparison']
        self.assertEqual(comparison['official_regions'], 22)
        self.assertEqual(comparison['matched_municipalities'], 19)
        self.assertEqual(len(comparison['unmatched_official_regions_ar']), 3)
        self.assertEqual(len({row['adm2_pcode'] for row in comparison['rows']}), 19)
        self.assertEqual(report['mobile_technology']['rows'][-1]['reported_lte_4g'], 8177187)
        self.assertEqual(report['status'], 'review_only')

    def test_changed_source_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_bytes((SOURCE_DIR / 'manifest.json').read_bytes())
            manifest = json.loads((root / 'manifest.json').read_text())
            for name in manifest['sources']:
                (root / name).write_bytes((SOURCE_DIR / name).read_bytes())
            with (root / 'population_by_region_2022.csv').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                evaluate_public_evidence(directory=root, output_path=None)


if __name__ == '__main__':
    unittest.main()
