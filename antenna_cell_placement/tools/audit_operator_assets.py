"""Audit a supplied authorized export; keep the aggregate report in its private folder."""
import argparse
from pathlib import Path
from antenna_cell_placement.operator_assets import evaluate_operator_assets

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = evaluate_operator_assets(args.directory, output_path=args.directory/'audit.json', observed_path=None)
    print('Aggregate review written to', args.directory/'audit.json')
    print('Status:', report['status'])
