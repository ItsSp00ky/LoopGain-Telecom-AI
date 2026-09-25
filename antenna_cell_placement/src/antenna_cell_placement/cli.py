"""Public planning commands and an explicit experimental research namespace."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'experimental':
        if len(argv) > 1 and argv[1] == 'compare':
            return experimental_compare(argv[2:])
        from antenna_cell_placement.legacy_cli import main as research_main
        return research_main(argv[1:])
    parser = argparse.ArgumentParser(description='Integrated antenna planning priorities for engineering review')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Verify required input hashes and optional source availability')
    for command in ('recommend', 'all'):
        plan = sub.add_parser(command, help='Run corrected GIS, explainable ranking, comparisons and offline maps')
        plan.add_argument('--output-dir', type=Path)
        plan.add_argument('--scope', choices=['Tripoli', 'national'], default='Tripoli')
        plan.add_argument('--operator', choices=['all', 'almadar', 'libyana'], default='all')
        plan.add_argument('--resolution', type=int, choices=range(6, 10), default=8)
        plan.add_argument('--top-k', type=int, default=20)
        plan.add_argument('--min-gap-m', type=float, default=3000.)
        plan.add_argument('--min-population', type=float, default=300.)
        plan.add_argument('--max-road-m', type=float, default=4000.)
        plan.add_argument('--separation-m', type=float, default=2500.)
        plan.add_argument('--no-rooftops', action='store_true')
    for command in ('assess', 'predict'):
        assess = sub.add_parser(command, help='Assess a coordinate with the same corrected GIS and strict rules')
        assess.add_argument('--lat', required=True, type=float)
        assess.add_argument('--lon', required=True, type=float)
        assess.add_argument('--operator', choices=['all', 'almadar', 'libyana'], default='all')
    maps = sub.add_parser('map', help='Report the verified offline map for an existing completed run')
    maps.add_argument('--run-dir', required=True, type=Path)
    sub.add_parser('experimental', help='Historical ML/H3 research commands; compare --run-dir DIR --model FILE')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        from antenna_cell_placement.source_integrity import verify_sources
        report = verify_sources()
        print(json.dumps(report, indent=2))
        return 0 if report['required_ready'] else 1
    if args.command in ('assess', 'predict'):
        from antenna_cell_placement.placement import assess_coordinate
        print(json.dumps(assess_coordinate(args.lat, args.lon, args.operator), indent=2, allow_nan=False))
    elif args.command == 'map':
        from antenna_cell_placement.source_integrity import sha256
        manifest = json.loads((args.run_dir / 'manifest.json').read_text(encoding='utf-8'))
        path = args.run_dir / 'planning_map.html'
        if manifest.get('status') != 'completed' or sha256(path) != manifest['artifacts']['planning_map.html']:
            raise ValueError('Run incomplete or map changed')
        print(path.resolve())
    else:
        from antenna_cell_placement.integrated_optimizer import PlanningConstraints
        from antenna_cell_placement.planning_pipeline import run_planning
        constraints = PlanningConstraints(args.min_gap_m, args.min_population, args.max_road_m, args.separation_m, args.top_k)
        run_planning(args.output_dir, args.scope, args.operator, args.resolution, constraints, not args.no_rooftops)
    return 0


def experimental_compare(argv):
    parser = argparse.ArgumentParser(description='Optional ML comparison; never changes the primary shortlist')
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path, help='Trusted local GIS-v2 research model')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    import pandas as pd
    from antenna_cell_placement.source_integrity import sha256
    from antenna_cell_placement.integrated_optimizer import PlanningConstraints
    from antenna_cell_placement.planning_comparison import compare_rankings
    from antenna_cell_placement.planning_pipeline import write_json
    manifest = json.loads((args.run_dir / 'manifest.json').read_text(encoding='utf-8'))
    path = args.run_dir / 'comparison_candidates.parquet'
    if manifest.get('status') != 'completed' or sha256(path) != manifest['artifacts'][path.name]:
        raise ValueError('Comparison requires an unchanged, completed planning run')
    pool, report = compare_rankings(pd.read_parquet(path), PlanningConstraints(**manifest['constraints']), args.model)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    pool.to_csv(args.output_dir / 'matched_candidates.csv', index=False)
    report.update(model_sha256=sha256(args.model), candidate_file_sha256=sha256(path), primary_rank_unchanged=True)
    write_json(args.output_dir / 'comparison.json', report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
