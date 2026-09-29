"""Command-line interface for dataset validation and placement planning."""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def cmd_clean(_args):
    """Audit source records and build the physical-site inventory in memory."""
    from antenna_cell_placement.data_cleaning import clean_pipeline

    towers, sites = clean_pipeline()
    unknown_operators = int((towers["operator"] == "Unknown").sum())
    console.print(
        Panel(
            f"[bold green]Source inventory validated[/bold green]\n"
            f"{len(towers):,} radio records grouped into {len(sites):,} physical sites.\n"
            f"Unknown operator records preserved: {unknown_operators:,}."
        )
    )


def cmd_opencellid(args):
    """Validate the supplied 14-column OpenCellID export in memory."""
    from antenna_cell_placement.config import OPENCELLID_RAW_PATH
    from antenna_cell_placement.opencellid import import_pipeline

    _, report = import_pipeline(getattr(args, "path", None))
    table = Table(title="OpenCellID source validation")
    table.add_column("Measure")
    table.add_column("Count", justify="right")
    for label, key in [
        ("Input rows", "input_rows"),
        ("Retained identities", "retained_cells"),
        ("Rejected rows", "rejected_rows"),
        ("Duplicate identities", "duplicate_identity_rows"),
        ("Review-eligible observations", "review_eligible_cells"),
    ]:
        table.add_row(label, f"{report[key]:,}")
    console.print(table)


def cmd_features(_args):
    """Audit feature coverage without persisting an intermediate dataset."""
    from antenna_cell_placement.feature_engineering import enrich_physical_sites_pipeline

    enriched = enrich_physical_sites_pipeline()
    population_available = int(enriched["population_data_available"].sum())
    terrain_available = int(enriched["terrain_data_available"].sum())
    console.print(
        Panel(
            f"[bold green]Feature coverage audited[/bold green]\n"
            f"Sites: {len(enriched):,}\n"
            f"Population data: {population_available:,}\n"
            f"Terrain data: {terrain_available:,}"
        )
    )


def cmd_recommend(_args):
    """Generate strictly filtered, dataset-only proposed placements."""
    from antenna_cell_placement.placement import get_top_recommendations

    recommendations = get_top_recommendations()
    table = Table(title="Top Proposed Cell Placements")
    table.add_column("Rank", style="bold yellow")
    table.add_column("Municipality", style="cyan")
    table.add_column("Settlement")
    table.add_column("Priority", justify="right")
    table.add_column("5 km population", justify="right")
    table.add_column("Known-site gap", justify="right")
    table.add_column("Reasons")
    for _, row in recommendations.head(10).iterrows():
        table.add_row(
            str(int(row["recommendation_rank"])),
            str(row["municipality_name"]),
            str(row["nearest_settlement_name"]),
            f"{row['planning_priority_score']:.2f}",
            f"{int(row['population_sum_5km']):,}",
            f"{row['dist_to_nearest_site_m'] / 1000.0:.1f} km",
            str(row["reason_codes"]),
        )
    console.print(table)


def cmd_map(_args):
    """Generate the placement-review map."""
    from antenna_cell_placement.map_visualizer import generate_interactive_map

    path = generate_interactive_map()
    console.print(f"[bold cyan]Placement-review map saved to: {path}[/bold cyan]")


def cmd_h3_evaluate(_args):
    """Run the roadmap Step 7 H3 acceptance gate."""
    from antenna_cell_placement.h3_planning import evaluate_h3_gate

    report = evaluate_h3_gate()
    checks = report["checks"]
    table = Table(title="Step 7: H3 planning-unit gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row(
        "Population conservation error",
        f"{checks['population_conservation_error_pct']:.6f}%",
    )
    table.add_row(
        "National sampled coverage",
        f"{checks['national_sample_coverage_pct']:.2f}%",
    )
    table.add_row(
        "Candidate H3 coverage",
        f"{checks['candidate_h3_id_coverage_pct']:.2f}%",
    )
    table.add_row(
        "Hierarchical parent consistency",
        f"{checks['hierarchical_parent_consistency_pct']:.2f}%",
    )
    table.add_row(
        "Direct resolution agreement",
        f"{checks['direct_point_resolution_agreement_pct']:.2f}%",
    )
    table.add_row("Rank stability", f"{checks['rank_stability_spearman']:.2f}")
    table.add_row(
        "Repeatable population allocation",
        "Yes" if checks["repeatable_population_allocation"] else "No",
    )
    console.print(table)


def cmd_worldcover_evaluate(_args):
    """Run the roadmap Step 8 WorldCover evaluation gate."""
    from antenna_cell_placement.worldcover import evaluate_worldcover_gate

    report = evaluate_worldcover_gate()
    checks = report["checks"]
    table = Table(title="Step 8: ESA WorldCover screening gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row(
        "Eligible-candidate coverage",
        f"{checks['eligible_candidate_point_coverage_pct']:.2f}%",
    )
    table.add_row(
        "Minimum shortlist H3 coverage",
        f"{checks['shortlist_h3_minimum_coverage_pct']:.2f}%",
    )
    table.add_row(
        "Water candidates before / after",
        f"{checks['water_candidates_before_screening']} / "
        f"{checks['water_candidates_after_screening']}",
    )
    table.add_row("Top-k overlap", f"{checks['top_k_overlap_pct']:.2f}%")
    table.add_row("Independent reference agreement", "Pending")
    console.print(table)


def cmd_buildings_evaluate(_args):
    """Run the roadmap Step 9 mapped-building evaluation gate."""
    from antenna_cell_placement.buildings import evaluate_buildings_gate

    report = evaluate_buildings_gate()
    checks = report["checks"]
    table = Table(title="Step 9: mapped-building context gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row(
        "Valid geometry after repair",
        f"{checks['valid_geometry_pct_after_repair']:.2f}%",
    )
    table.add_row(
        "Municipalities with mapped buildings",
        f"{checks['municipalities_with_observed_buildings_pct']:.2f}%",
    )
    table.add_row(
        "Populated places with mapping within 1 km",
        f"{checks['populated_place_1km_observation_coverage_pct']:.2f}%",
    )
    table.add_row(
        "Shortlist H3 units with mapped buildings",
        f"{checks['shortlist_h3_with_observed_buildings_pct']:.2f}%",
    )
    table.add_row("Independent accuracy improvement", "Pending")
    console.print(table)


def cmd_building_heights_evaluate(_args):
    """Run the roadmap Step 10 explicit building-height evidence gate."""
    from antenna_cell_placement.building_heights import (
        evaluate_building_height_gate,
    )

    report = evaluate_building_height_gate()
    coverage = report["coverage"]
    quality = report["quality"]
    table = Table(title="Step 10: explicit building-height evidence gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row("Explicit height tags", f"{quality['explicit_height_tag_rows']:,}")
    table.add_row("Valid explicit heights", f"{quality['valid_explicit_height_rows']:,}")
    table.add_row(
        "National footprint coverage",
        f"{coverage['national_building_height_coverage_pct']:.3f}%",
    )
    table.add_row(
        "Municipalities with a valid height",
        f"{coverage['municipalities_with_valid_height_pct']:.2f}%",
    )
    table.add_row(
        "Shortlist H3 units with a valid height",
        f"{coverage['shortlist_h3_with_valid_height_pct']:.2f}%",
    )
    table.add_row("Independent height error", "Pending")
    console.print(table)


def cmd_osm_evaluate(_args):
    """Run the roadmap Step 11 selected OSM-family evidence gate."""
    from antenna_cell_placement.osm_context import evaluate_osm_context_gate

    report = evaluate_osm_context_gate()
    table = Table(title="Step 11: selected OpenStreetMap context gate")
    table.add_column("Family")
    table.add_column("Decision")
    table.add_column("Features", justify="right")
    table.add_column("Municipality coverage", justify="right")
    for family, result in report["family_results"].items():
        table.add_row(
            family.replace("_", " ").title(),
            result["status"].upper(),
            f"{result['feature_count']:,}",
            f"{result['municipality_coverage_pct']:.2f}%",
        )
    console.print(table)


def cmd_ookla_evaluate(_args):
    """Run the roadmap Step 12 Ookla mobile-performance evidence gate."""
    from antenna_cell_placement.ookla import evaluate_ookla_gate

    report = evaluate_ookla_gate()
    coverage = report["coverage"]
    table = Table(title="Step 12: Ookla mobile-performance gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row(
        "Supported tile-quarter rows",
        f"{report['quality']['supported_tile_quarter_rows']:,}",
    )
    table.add_row(
        "Municipality coverage", f"{coverage['municipality_coverage_pct']:.2f}%"
    )
    table.add_row("Shortlist coverage", f"{coverage['shortlist_coverage_pct']:.2f}%")
    table.add_row(
        "Median adjacent-quarter stability",
        str(report["temporal_stability"]["median_spearman"]),
    )
    table.add_row("Independent KPI validation", "Pending")
    console.print(table)


def cmd_viirs_evaluate(_args):
    """Run the roadmap Step 13 VIIRS night-light evidence gate."""
    from antenna_cell_placement.nightlights import evaluate_viirs_gate

    report = evaluate_viirs_gate()
    coverage = report["coverage"]
    table = Table(title="Step 13: VIIRS night-light gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row("Shortlist coverage", f"{coverage['shortlist_coverage_pct']:.2f}%")
    table.add_row(
        "Median selected-month stability",
        str(report["temporal_stability"]["median_spearman"]),
    )
    table.add_row(
        "Known-flare artifact promotions",
        f"{report['artifact_test']['artifact_promotion_pct']:.2f}%",
    )
    table.add_row("Independent activity/KPI validation", "Pending")
    console.print(table)


def cmd_fabdem_evaluate(args):
    """Run the roadmap Step 14 FABDEM terrain comparison."""
    import pandas as pd
    from antenna_cell_placement.config import RECOMMENDATIONS_CSV
    from antenna_cell_placement.fabdem import evaluate_fabdem_gate

    recommendations = pd.read_csv(getattr(args, "recommendations", None) or RECOMMENDATIONS_CSV)
    report = evaluate_fabdem_gate(recommendations)
    table = Table(title="Step 14: FABDEM terrain gate")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    table.add_row("Shortlist coverage", f"{report['coverage']['shortlist_coverage_pct']:.2f}%")
    table.add_row("Shortlist municipality coverage", f"{report['coverage']['shortlist_municipality_coverage_pct']:.2f}%")
    table.add_row("Independent elevation/RF validation", "Unavailable")
    console.print(table)


def cmd_operator_assets_evaluate(args):
    """Audit a locally supplied operator export for roadmap Step 15."""
    from antenna_cell_placement.config import REPORTS_DIR
    from antenna_cell_placement.operator_assets import evaluate_operator_assets

    report = evaluate_operator_assets(args.directory, output_path=args.output or
                                      REPORTS_DIR / "step_15_operator_assets_evaluation.json",
                                      observed_path=None if args.no_observed_match else args.observed)
    table = Table(title="Step 15: operator asset audit")
    table.add_column("Measure")
    table.add_column("Result", justify="right")
    table.add_row("Decision", report["status"].upper())
    for name in ("sites", "sectors"):
        item = report["metrics"][name]
        table.add_row(name.title(), f"{item['valid_rows']}/{item['rows']} valid")
    table.add_row("Engineering fields complete",
                  f"{report['metrics']['sectors']['engineering_complete_pct']:.2f}%")
    table.add_row("Engineer thresholds", "Supplied" if report["thresholds"] else "Pending")
    console.print(table)


def cmd_public_evidence_evaluate(_args):
    """Compare official public population and mobile statistics with planning inputs."""
    from antenna_cell_placement.public_evidence import evaluate_public_evidence

    report = evaluate_public_evidence()
    population = report['population_comparison']
    table = Table(title='Official Libya public-data review')
    table.add_column('Measure')
    table.add_column('Result', justify='right')
    table.add_row('Decision', report['status'].upper())
    table.add_row('Matched population regions', f"{population['matched_municipalities']}/{population['official_regions']}")
    table.add_row('2020 WorldPop / 2022 official, matched areas',
                  f"{population['matched_worldpop_to_official_ratio']:.2%}")
    table.add_row('2025 reported LTE/4G share',
                  f"{report['mobile_technology']['rows'][-1]['lte_4g_share_pct']:.2f}%")
    console.print(table)


def cmd_foreign_rf_benchmark(_args):
    """Exercise RF measurement evaluation with isolated observed foreign data."""
    from antenna_cell_placement.foreign_rf import evaluate_foreign_rf_benchmark

    report = evaluate_foreign_rf_benchmark()
    evaluation = report['evaluation']
    table = Table(title='External RF method benchmark')
    table.add_column('Measure')
    table.add_column('Result', justify='right')
    table.add_row('Distance model decision', report['distance_model_decision'].upper())
    table.add_row('Scored holdout blocks', str(evaluation['scored_holdout_blocks']))
    table.add_row('Measured median MAE',
                  f"{evaluation['baseline']['mae_db']:.3f} dB" if evaluation['baseline'] else 'Unavailable')
    table.add_row('Distance model MAE',
                  f"{evaluation['distance_model']['mae_db']:.3f} dB" if evaluation['distance_model'] else 'Unavailable')
    console.print(table)


def cmd_assess(args):
    """Assess one coordinate through the shared placement API."""
    from antenna_cell_placement.placement import evaluate_candidate

    assessment = evaluate_candidate(float(args.lat), float(args.lon))
    table = Table(title=f"Planning assessment: ({args.lat}, {args.lon})")
    table.add_column("Measure")
    table.add_column("Value")
    priority = assessment["planning_priority_score"]
    table.add_row("Planning priority index", f"{priority:.2f}" if priority is not None else "Unavailable")
    table.add_row("Required planning data", "Available" if assessment["planning_data_available"] else "Missing")
    table.add_row("Shortlist constraints", "Pass" if assessment["shortlist_eligible"] else "Fail")
    table.add_row("H3 resolution 7", str(assessment["h3_r7"]))
    table.add_row("H3 resolution 6 parent", str(assessment["h3_r6"]))
    table.add_row("Municipality", str(assessment["municipality"]))
    table.add_row("Nearest settlement", str(assessment["nearest_settlement"]))
    table.add_row("5 km population", _display_number(assessment["population_sum_5km"], precision=0))
    table.add_row("Known-site distance", _display_number(assessment["distance_to_nearest_known_site_m"], suffix=" m"))
    table.add_row("Road distance", _display_number(assessment["distance_to_nearest_road_m"], suffix=" m"))
    table.add_row("Elevation", _display_number(assessment["elevation_m"], suffix=" m"))
    table.add_row("Point land cover", str(assessment["worldcover_class_name"]))
    table.add_row(
        "Mapped buildings in H3",
        str(assessment["osm_building_count_h3"]),
    )
    table.add_row(
        "Nearest mapped hospital",
        _display_number(
            assessment["osm_selected_context"]["hospital"]["nearest_distance_m"],
            suffix=" m",
        ),
    )
    table.add_row("Interpretation", assessment["limitations"])
    console.print(table)


def _display_number(value, suffix="", precision=1):
    return "Missing" if value is None else f"{value:,.{precision}f}{suffix}"


def cmd_collected_data(_args):
    from antenna_cell_placement.collected_data import audit_collections
    report = audit_collections()
    for source, result in report['sources'].items():
        console.print(f"{source}: {result['retained_rows']:,} retained; {result['rejected_rows']:,} rejected; {result['duplicate_rows']:,} duplicates")


def cmd_pilot_review(args):
    from antenna_cell_placement.pilot import build_pilot_review
    from antenna_cell_placement.config import REPORTS_DIR

    assets = getattr(args, 'assets', None)
    output_dir = REPORTS_DIR / 'private_pilot_review' if assets else REPORTS_DIR
    report = build_pilot_review(output_dir=output_dir, asset_directory=assets)
    console.print(f"Measured service review: {report['eligible_measurements']:,} eligible samples; "
                  f"{report['service_area_operator_radio_groups']} operator/radio/area groups")
    console.print(f"Pilot: {report['pilot']['status']}; RF inputs: {report['rf_readiness']['status']}")
    console.print(f"Reports: {output_dir / 'pilot_review.md'} and {output_dir / 'pilot_review.json'}")


def cmd_all(args):
    cmd_collected_data(args)
    cmd_pilot_review(args)
    cmd_public_evidence_evaluate(args)
    cmd_clean(args)
    cmd_opencellid(args)
    cmd_features(args)
    cmd_recommend(args)
    cmd_h3_evaluate(args)
    cmd_worldcover_evaluate(args)
    cmd_buildings_evaluate(args)
    cmd_building_heights_evaluate(args)
    cmd_osm_evaluate(args)
    cmd_ookla_evaluate(args)
    cmd_viirs_evaluate(args)
    cmd_map(args)


def main():
    parser = argparse.ArgumentParser(
        description="Dataset-only telecom placement planning for Libya",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser("clean", help="Audit source records and physical-site grouping")
    from antenna_cell_placement.config import OPENCELLID_RAW_PATH

    open_cell = subparsers.add_parser("opencellid", help="Validate the OpenCellID source export")
    open_cell.add_argument("--path", type=Path, help="Single export; default merges declared exports")
    subparsers.add_parser("collected-data", help="Validate collected antennas and phone measurements")
    pilot = subparsers.add_parser("pilot-review", help="Reconcile locations, summarize measured service, and validate a pilot")
    pilot.add_argument("--assets", type=Path, help="Explicit private Step 15 operator export to compare with pilot identities")
    subparsers.add_parser("features", help="Audit source feature coverage")
    subparsers.add_parser("recommend", help="Generate dataset-only proposed placements")
    subparsers.add_parser("h3-evaluate", help="Run the Step 7 H3 acceptance gate")
    subparsers.add_parser(
        "worldcover-evaluate", help="Run the Step 8 WorldCover screening gate"
    )
    subparsers.add_parser(
        "buildings-evaluate", help="Run the Step 9 mapped-building context gate"
    )
    subparsers.add_parser(
        "building-heights-evaluate",
        help="Run the Step 10 explicit building-height evidence gate",
    )
    subparsers.add_parser(
        "osm-evaluate", help="Run the Step 11 selected OSM-family evidence gate"
    )
    subparsers.add_parser(
        "ookla-evaluate", help="Run the Step 12 Ookla mobile-performance gate"
    )
    subparsers.add_parser(
        "viirs-evaluate", help="Run the Step 13 VIIRS night-light gate"
    )
    fabdem = subparsers.add_parser("fabdem-evaluate", help="Run the Step 14 FABDEM terrain gate")
    fabdem.add_argument("--recommendations", type=Path, help="Frozen shortlist CSV")
    assets = subparsers.add_parser("operator-assets-evaluate", help="Audit a Step 15 operator asset export")
    assets.add_argument("--directory", type=Path, required=True, help="Authorized asset export directory")
    assets.add_argument("--output", type=Path, help="Aggregate JSON report path")
    assets.add_argument("--observed", type=Path, default=OPENCELLID_RAW_PATH,
                        help="Observed OpenCellID CSV for exact identity matching")
    assets.add_argument("--no-observed-match", action="store_true", help="Skip observed identity matching")
    subparsers.add_parser("public-evidence-evaluate", help="Audit official Libya population and mobile technology statistics")
    subparsers.add_parser("foreign-rf-benchmark", help="Evaluate RF methods on isolated real-world observations")
    subparsers.add_parser("map", help="Generate the placement-review map")
    subparsers.add_parser("all", help="Run validation, placement, and map generation")
    assess = subparsers.add_parser("assess", help="Assess one planning coordinate")
    assess.add_argument("--lat", type=float, required=True)
    assess.add_argument("--lon", type=float, required=True)

    args = parser.parse_args()
    commands = {
        "clean": cmd_clean,
        "collected-data": cmd_collected_data,
        "pilot-review": cmd_pilot_review,
        "opencellid": cmd_opencellid,
        "features": cmd_features,
        "recommend": cmd_recommend,
        "h3-evaluate": cmd_h3_evaluate,
        "worldcover-evaluate": cmd_worldcover_evaluate,
        "buildings-evaluate": cmd_buildings_evaluate,
        "building-heights-evaluate": cmd_building_heights_evaluate,
        "osm-evaluate": cmd_osm_evaluate,
        "ookla-evaluate": cmd_ookla_evaluate,
        "viirs-evaluate": cmd_viirs_evaluate,
        "fabdem-evaluate": cmd_fabdem_evaluate,
        "operator-assets-evaluate": cmd_operator_assets_evaluate,
        "public-evidence-evaluate": cmd_public_evidence_evaluate,
        "foreign-rf-benchmark": cmd_foreign_rf_benchmark,
        "map": cmd_map,
        "all": cmd_all,
        "assess": cmd_assess,
    }
    if not args.command:
        parser.print_help()
        sys.exit(0)
    commands[args.command](args)


if __name__ == "__main__":
    main()
