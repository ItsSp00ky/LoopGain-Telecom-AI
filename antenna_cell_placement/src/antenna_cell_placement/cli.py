"""
Command-line Interface (CLI) for Antenna Cell Placement AI Module.
Provides modular commands to clean data, engineer features, train AI models,
generate placement recommendations, and predict suitability for custom coordinates.
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from antenna_cell_placement.config import (
    CLEANED_RADIO_TOWERS_CSV,
    CLEANED_PHYSICAL_SITES_CSV,
    CLEANED_SITES_PARQUET,
    SUITABILITY_MODEL_PATH,
    MODEL_METRICS_PATH,
    RECOMMENDATIONS_CSV,
    CLEANED_MAP_HTML,
    DEFAULT_PILOT_CITY,
    H3_RESOLUTION,
)

# Windows consoles with a non-UTF-8 code page (e.g. cp1256) cannot encode the
# check marks in the status lines below and crash rich; force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console()


def cmd_clean(args):
    """Run data cleaning and physical site consolidation."""
    from antenna_cell_placement.data_cleaning import clean_pipeline
    console.print(Panel("[bold green]Running Data Cleaning & Mast Consolidation Pipeline[/bold green]"))
    df_towers, df_sites = clean_pipeline()
    console.print(f"[bold cyan]✓ Processed {len(df_towers)} radio antennas into {len(df_sites)} physical mast sites.[/bold cyan]")


def cmd_opencellid(args):
    """Import and assess supplementary OpenCellID observations."""
    from antenna_cell_placement.opencellid import import_pipeline
    from antenna_cell_placement.config import OPENCELLID_RAW_PATH
    import_pipeline(getattr(args, "path", OPENCELLID_RAW_PATH))


def cmd_features(args):
    """Run geospatial feature engineering with WorldPop, SRTM DEM, and OCHA roads."""
    from antenna_cell_placement.feature_engineering import enrich_physical_sites_pipeline
    console.print(Panel("[bold green]Running Geospatial Feature Engineering Pipeline[/bold green]"))
    df_enriched = enrich_physical_sites_pipeline()
    console.print(
        f"[bold cyan]✓ Enriched {len(df_enriched)} sites with "
        f"{len(df_enriched.columns)} multi-source attributes.[/bold cyan]"
    )


def cmd_train(args):
    """Train placement suitability and equipment recommendation models."""
    from antenna_cell_placement.placement_model import train_all_models_pipeline
    console.print(Panel("[bold green]Training Placement Suitability & Equipment Recommendation AI Models[/bold green]"))
    results = train_all_models_pipeline()
    m = results["suitability"]

    table = Table(title="AI Placement Model Benchmark Performance")
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("LightGBM Score", style="green", justify="right")
    table.add_row("ROC-AUC", f"{m['roc_auc']:.4f}")
    table.add_row("PR-AUC", f"{m['pr_auc']:.4f}")
    table.add_row("Accuracy", f"{m['accuracy']:.4f}")
    table.add_row("F1-Score", f"{m['f1_score']:.4f}")
    table.add_row("Precision", f"{m['precision']:.4f}")
    table.add_row("Recall", f"{m['recall']:.4f}")
    table.add_row("Brier Score", f"{m['brier_score']:.4f}")
    console.print(table)


def cmd_recommend(args):
    """Run coverage gap optimizer and rank top new cell site placements."""
    from antenna_cell_placement.site_optimizer import run_optimizer_pipeline
    console.print(Panel("[bold green]Running Coverage Gap Optimization & Site Placement Ranking[/bold green]"))
    recs = run_optimizer_pipeline()

    table = Table(title="Top 10 AI Recommended Cell Placements for Libya")
    table.add_column("Rank", style="bold yellow")
    table.add_column("Municipality", style="cyan")
    table.add_column("Settlement", style="magenta")
    table.add_column("Suitability", style="green")
    table.add_column("Priority", style="bold green")
    table.add_column("Equipment Tier", style="white")
    table.add_column("5km Pop", style="blue")
    table.add_column("Gap (km)", style="red")

    for _, row in recs.head(10).iterrows():
        table.add_row(
            str(int(row["recommendation_rank"])),
            str(row["municipality_name"]),
            str(row["nearest_settlement_name"]),
            f"{row['placement_suitability_score']:.3f}",
            f"{row['deployment_priority_score']:.2f}",
            str(row["recommended_equipment_tier"]).replace("_Macro", ""),
            f"{int(row['population_sum_5km']):,}",
            f"{row['dist_to_nearest_site_m'] / 1000.0:.1f} km",
        )
    console.print(table)


def cmd_map(args):
    """Generate interactive geospatial maps."""
    from antenna_cell_placement.map_visualizer import generate_interactive_map
    console.print(Panel("[bold green]Generating Interactive Geospatial Coverage & Recommendation Maps[/bold green]"))
    map_path = generate_interactive_map()
    console.print(f"[bold cyan]✓ Interactive map saved to: {map_path}[/bold cyan]")


def cmd_predict(args):
    """Predict placement suitability and recommended equipment for a custom coordinate."""
    import joblib
    from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
    from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
    import pandas as pd

    lat = float(args.lat)
    lon = float(args.lon)

    console.print(Panel(f"[bold green]Evaluating Custom Candidate Site at ({lat:.4f}, {lon:.4f})[/bold green]"))

    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)
    extractor.set_existing_sites(df_sites)

    features = extractor.extract_features([lon], [lat], is_existing_site=False)

    suit_model = joblib.load(SUITABILITY_MODEL_PATH)
    eq_model = joblib.load(SUITABILITY_MODEL_PATH.parent / "equipment_recommendation_model.joblib")

    score = suit_model.predict_proba(features[SUITABILITY_FEATURE_COLS])[0, 1]

    eq_features = [
        "population_density_1km",
        "population_sum_3km",
        "population_sum_5km",
        "elevation_m",
        "elevation_prominence_3km",
        "terrain_slope_deg",
        "dist_to_nearest_road_m",
        "dist_to_nearest_settlement_m",
        "dist_to_nearest_site_m",
        "site_density_3km",
        "site_density_5km",
    ]
    tier = eq_model.predict(features[eq_features])[0]

    table = Table(title=f"AI Placement Assessment: ({lat:.4f}, {lon:.4f})")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Placement Suitability Score", f"{score:.4f} ({'HIGHLY SUITABLE' if score >= 0.75 else ('MODERATE' if score >= 0.50 else 'LOW')})")
    table.add_row("Recommended Equipment Tier", str(tier))
    table.add_row("Municipality", str(features['municipality_name'].iloc[0]))
    table.add_row("Nearest City / Town", f"{features['nearest_settlement_name'].iloc[0]} ({features['dist_to_nearest_settlement_m'].iloc[0] / 1000.0:.1f} km)")
    table.add_row("Population Density (1km²)", f"{features['population_density_1km'].iloc[0]:.1f} people/km²")
    table.add_row("5km Population Catchment", f"{int(features['population_sum_5km'].iloc[0]):,} people")
    table.add_row("Distance to Nearest Cell Tower", f"{features['dist_to_nearest_site_m'].iloc[0] / 1000.0:.2f} km")
    table.add_row("Distance to Nearest Road", f"{features['dist_to_nearest_road_m'].iloc[0]:.1f} meters")
    table.add_row("Ground Elevation", f"{features['elevation_m'].iloc[0]:.1f} m ASL")
    table.add_row("Elevation Prominence (3km)", f"{features['elevation_prominence_3km'].iloc[0]:.1f} m")
    if features["cloudflare_data_available"].iloc[0]:
        table.add_row(
            "Regional HTTP Traffic Share (52w)",
            f"{features['cloudflare_http_requests_share_52w_pct'].iloc[0]:.3f}%",
        )
        table.add_row(
            "Regional Digital Demand Score",
            f"{features['cloudflare_regional_demand_score'].iloc[0]:.3f}",
        )

    console.print(table)


def cmd_h3_grid(args):
    """Build the H3 planning grid and Phase-1 feature table for a pilot city."""
    from antenna_cell_placement.h3_grid import build_h3_feature_table
    console.print(Panel(f"[bold green]Building H3 Grid for {args.city}[/bold green]"))
    df = build_h3_feature_table(city=args.city, resolution=args.resolution)
    console.print(f"[bold cyan]Built {len(df)} H3 hexes at resolution {args.resolution}.[/bold cyan]")


def cmd_enrich_h3(args):
    """Enrich the H3 grid with building, land-cover, and OSM features (Phase 2)."""
    from antenna_cell_placement.h3_grid import enrich_h3_feature_table
    console.print(Panel(f"[bold green]Enriching H3 Grid with Phase-2 Data for {args.city}[/bold green]"))
    df = enrich_h3_feature_table(city=args.city)
    console.print(f"[bold cyan]Enriched {len(df)} H3 hexes with building/land-cover/OSM features.[/bold cyan]")


def cmd_expansion_score(args):
    """Compute the expansion need score per H3 hex and export ranked CSV/GeoJSON."""
    from antenna_cell_placement.expansion_score import run_expansion_score_pipeline
    console.print(Panel(f"[bold green]Computing Expansion Need Score for {args.city}[/bold green]"))
    scored = run_expansion_score_pipeline(city=args.city)

    table = Table(title=f"Top 10 Priority Hexes: {args.city}")
    table.add_column("Rank", style="bold yellow")
    table.add_column("H3 Index", style="cyan")
    table.add_column("Priority", style="bold green")
    table.add_column("Expansion Need", style="green")
    table.add_column("Suitability", style="magenta")
    table.add_column("Pop (5km)", style="blue")
    table.add_column("Sites in hex", style="red")

    for _, row in scored.head(10).iterrows():
        suit = row.get("placement_suitability_score")
        table.add_row(
            str(int(row["expansion_rank"])),
            str(row["h3_index"]),
            f"{row['combined_priority_score']:.2f}",
            f"{row['expansion_need_score']:.2f}",
            "n/a" if suit is None or suit != suit else f"{suit:.3f}",
            f"{int(row['population_sum_5km']):,}",
            str(int(row["existing_sites_site_count"])),
        )
    console.print(table)


def cmd_validate_h3(args):
    """Validate the expansion score via known-site recovery and weight sensitivity."""
    from antenna_cell_placement.validation import run_validation_pipeline
    console.print(Panel(f"[bold green]Validating Expansion Need Score for {args.city}[/bold green]"))
    report = run_validation_pipeline(city=args.city)
    rec = report["known_site_recovery"]

    table = Table(title=f"Known-Site Recovery ({rec['n_folds']} folds, {rec['hide_fraction']:.0%} of sites hidden)")
    table.add_column("Metric", style="cyan")
    table.add_column("Expansion Score", style="bold green", justify="right")
    table.add_column("Population-only baseline", style="blue", justify="right")
    table.add_row("ROC-AUC", f"{rec['mean_auc_expansion_score']:.3f}", f"{rec['mean_auc_population_only']:.3f}")
    table.add_row(
        "Recall @ top 10% hexes",
        f"{rec['mean_recall_top10pct_expansion_score']:.3f}",
        f"{rec['mean_recall_top10pct_population_only']:.3f}",
    )
    table.add_row("Recall @ top 25% hexes", f"{rec['mean_recall_top25pct_expansion_score']:.3f}", "-")
    table.add_row(
        "ROC-AUC (unserved hexes only)",
        f"{rec['mean_auc_expansion_score_unserved']:.3f}",
        f"{rec['mean_auc_population_only_unserved']:.3f}",
    )
    table.add_row(
        "Recall @ top 10% (unserved hexes only)",
        f"{rec['mean_recall_top10pct_expansion_score_unserved']:.3f}",
        f"{rec['mean_recall_top10pct_population_only_unserved']:.3f}",
    )
    console.print(table)

    sens = Table(title="Weight Sensitivity (vs. default weights)")
    sens.add_column("Weight", style="cyan")
    sens.add_column("Factor", justify="right")
    sens.add_column("Spearman rank corr.", justify="right", style="green")
    sens.add_column("Top-50 overlap", justify="right", style="blue")
    for row in report["weight_sensitivity"]:
        sens.add_row(row["weight"], f"x{row['factor']}", f"{row['spearman_rank_correlation']:.3f}", f"{row['top50_overlap']:.0%}")
    console.print(sens)


def cmd_evaluate(args):
    """Municipality-held-out evaluation of the suitability and equipment models."""
    from antenna_cell_placement.evaluation import run_evaluation_pipeline
    console.print(Panel("[bold green]Geographic Hold-out Evaluation of Placement Models[/bold green]"))
    report = run_evaluation_pipeline()
    suit, equip = report["suitability_model"], report["equipment_model"]

    table = Table(title="Suitability model (LightGBM): how the score changes with an honest split")
    table.add_column("Evaluation", style="cyan")
    table.add_column("ROC-AUC", justify="right", style="bold green")
    table.add_column("Avg precision", justify="right")
    table.add_row("Random 5-fold CV (shipped scheme)", f"{suit['random_cv']['roc_auc']:.4f}", f"{suit['random_cv']['average_precision']:.4f}")
    table.add_row("Municipality-grouped 5-fold CV", f"{suit['municipality_grouped_cv']['roc_auc']:.4f}", f"{suit['municipality_grouped_cv']['average_precision']:.4f}")
    held = suit["held_out_test"]
    table.add_row(f"Held-out test ({len(held['municipalities'])} municipalities)", f"{held['roc_auc']:.4f}", f"{held['average_precision']:.4f}")
    table.add_row("  population-only baseline (same test)", f"{held['population_only_baseline_roc_auc']:.4f}", "-")
    stress = suit["hard_negative_stress_test"]
    if stress:
        table.add_row("Hard-negative stress test (real sites vs populated non-sites)", f"{stress['roc_auc']:.4f}", "-")
        table.add_row("  population-only baseline (same test)", f"{stress['population_only_roc_auc']:.4f}", "-")
    console.print(table)

    eq = Table(title="Equipment recommender (Random Forest)")
    eq.add_column("Evaluation", style="cyan")
    eq.add_column("Accuracy", justify="right", style="bold green")
    eq.add_column("Macro-F1", justify="right")
    eq.add_row("In-sample (as shipped)", f"{equip['in_sample_accuracy_as_shipped']:.4f}", "-")
    eq.add_row("Random 5-fold CV", f"{equip['random_cv']['accuracy']:.4f}", f"{equip['random_cv']['macro_f1']:.4f}")
    eq.add_row("Municipality-grouped 5-fold CV", f"{equip['municipality_grouped_cv']['accuracy']:.4f}", f"{equip['municipality_grouped_cv']['macro_f1']:.4f}")
    eq.add_row("Majority-class baseline", f"{equip['majority_class_baseline_accuracy']:.4f}", "-")
    eq.add_row("Feature-side rules only (no model)", f"{equip['feature_side_rules_only_accuracy']:.4f}", "-")
    console.print(eq)


def cmd_h3_map(args):
    """Generate the interactive expansion-priority map for a pilot city."""
    from antenna_cell_placement.map_visualizer import generate_h3_expansion_map
    console.print(Panel(f"[bold green]Generating H3 Expansion Priority Map for {args.city}[/bold green]"))
    path = generate_h3_expansion_map(city=args.city, top_n=args.top_n)
    console.print(f"[bold cyan]Map saved to: {path}[/bold cyan]")


def cmd_h3_all(args):
    """Run the full pilot-city pipeline: grid, Phase-2 enrichment, scoring, validation, map."""
    cmd_h3_grid(args)
    cmd_enrich_h3(args)
    cmd_expansion_score(args)
    cmd_validate_h3(args)
    cmd_h3_map(args)
    console.print(Panel(f"[bold green]Pilot-city H3 pipeline for {args.city} completed.[/bold green]"))


def cmd_train_experiment(args):
    from antenna_cell_placement.training_experiment import run_training_experiment
    run_training_experiment(args.output_dir)


def cmd_phase2(args):
    from antenna_cell_placement.phase2_pipeline import run_phase2
    run_phase2(args.output_dir, args.frozen_dataset)


def cmd_all(args):
    """Run full end-to-end pipeline."""
    cmd_clean(args)
    cmd_features(args)
    cmd_train(args)
    cmd_recommend(args)
    cmd_map(args)
    console.print(Panel("[bold green]✓ Entire AI Antenna Cell Placement Pipeline Completed Successfully![/bold green]"))


def main():
    parser = argparse.ArgumentParser(
        description="AI Antenna Cell Placement Optimization CLI - Team Loop Gain",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("clean", help="Clean raw SQLite/JSON and consolidate physical cell sites")
    from antenna_cell_placement.config import OPENCELLID_RAW_PATH
    oc_parser = subparsers.add_parser("opencellid", help="Import OpenCellID cells and review recommendation proximity")
    oc_parser.add_argument("--path", type=Path, default=OPENCELLID_RAW_PATH)
    subparsers.add_parser("features", help="Engineer geospatial, demographic, and topography features")
    subparsers.add_parser("train", help="Train placement suitability and equipment recommendation models")
    subparsers.add_parser("recommend", help="Find coverage gaps and output prioritized new site recommendations")
    subparsers.add_parser("map", help="Generate interactive Leaflet coverage and recommendation maps")
    subparsers.add_parser("all", help="Run full end-to-end pipeline")

    pred_parser = subparsers.add_parser("predict", help="Predict suitability for custom (lat, lon) coordinates")
    pred_parser.add_argument("--lat", type=float, required=True, help="Latitude (WGS84)")
    pred_parser.add_argument("--lon", type=float, required=True, help="Longitude (WGS84)")

    h3_parser = subparsers.add_parser("h3-grid", help="Build H3 planning grid for a pilot city (Phase 1)")
    h3_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")
    h3_parser.add_argument("--resolution", type=int, default=H3_RESOLUTION, help="H3 resolution")

    enrich_h3_parser = subparsers.add_parser("enrich-h3", help="Add building/land-cover/OSM features to H3 grid (Phase 2)")
    enrich_h3_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")

    score_parser = subparsers.add_parser("expansion-score", help="Compute per-hex expansion need score")
    score_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")

    validate_parser = subparsers.add_parser("validate-h3", help="Known-site recovery and weight sensitivity validation")
    validate_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")

    experiment_parser = subparsers.add_parser("train-experiment", help="Reproducible grouped training experiment; saves a separate artifact")
    experiment_parser.add_argument("--output-dir", type=Path, default=None, help="New directory for data, split manifest, model and metrics")

    phase2_parser = subparsers.add_parser("phase2", help="Versioned GIS migration, controlled training and preliminary rooftop shortlist")
    phase2_parser.add_argument("--output-dir", type=Path, default=None, help="New output directory; existing outputs are never overwritten")
    phase2_parser.add_argument("--frozen-dataset", type=Path, default=None)

    subparsers.add_parser("evaluate", help="Municipality-held-out evaluation of the suitability and equipment models")

    h3_map_parser = subparsers.add_parser("h3-map", help="Generate the interactive expansion-priority map")
    h3_map_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")
    h3_map_parser.add_argument("--top-n", type=int, default=20, help="Number of top hexes to call out")

    h3_all_parser = subparsers.add_parser("h3-all", help="Run grid, enrichment, scoring, validation and map for a pilot city")
    h3_all_parser.add_argument("--city", default=DEFAULT_PILOT_CITY, help="Pilot city name")
    h3_all_parser.add_argument("--resolution", type=int, default=H3_RESOLUTION, help="H3 resolution")
    h3_all_parser.add_argument("--top-n", type=int, default=20, help="Number of top hexes to call out on the map")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "clean": cmd_clean,
        "opencellid": cmd_opencellid,
        "features": cmd_features,
        "train": cmd_train,
        "recommend": cmd_recommend,
        "map": cmd_map,
        "all": cmd_all,
        "predict": cmd_predict,
        "h3-grid": cmd_h3_grid,
        "enrich-h3": cmd_enrich_h3,
        "expansion-score": cmd_expansion_score,
        "validate-h3": cmd_validate_h3,
        "evaluate": cmd_evaluate,
        "train-experiment": cmd_train_experiment,
        "phase2": cmd_phase2,
        "h3-map": cmd_h3_map,
        "h3-all": cmd_h3_all,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
