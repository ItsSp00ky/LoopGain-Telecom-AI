"""Build the full planning map (all candidates, existing sites, shortlist) for a completed run.

    uv run python tools/build_full_map.py
    uv run python tools/build_full_map.py --run-dir integrated_release_v3 --output eval_reports/tripoli_full_map_v3.html

The completed run directory is only read, never written: its files are fingerprinted
in its manifest.
"""

import argparse
from pathlib import Path

from antenna_cell_placement.map_visualizer import generate_release_map

MODULE = Path(__file__).resolve().parents[1]
DEFAULT_RUN = MODULE / "integrated_release_v3"
DEFAULT_OUTPUT = MODULE / "eval_reports" / "tripoli_full_map_v3.html"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    path = generate_release_map(args.run_dir, args.output)
    print(f"Saved full planning map to: {path}")


if __name__ == "__main__":
    main()
