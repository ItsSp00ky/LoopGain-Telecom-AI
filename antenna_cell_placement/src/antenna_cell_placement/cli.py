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
)

console = Console()


def cmd_clean(args):
    """Run data cleaning and physical site consolidation."""
    from antenna_cell_placement.data_cleaning import clean_pipeline
    console.print(Panel("[bold green]Running Data Cleaning & Mast Consolidation Pipeline[/bold green]"))
    df_towers, df_sites = clean_pipeline()
    console.print(f"[bold cyan]✓ Processed {len(df_towers)} radio antennas into {len(df_sites)} physical mast sites.[/bold cyan]")


def cmd_features(args):
    """Run geospatial feature engineering with WorldPop, SRTM DEM, and OCHA roads."""
    from antenna_cell_placement.feature_engineering import enrich_physical_sites_pipeline
    console.print(Panel("[bold green]Running Geospatial Feature Engineering Pipeline[/bold green]"))
    df_enriched = enrich_physical_sites_pipeline()
    console.print(f"[bold cyan]✓ Enriched {len(df_enriched)} sites with 52 multi-layer geospatial features.[/bold cyan]")


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

    console.print(table)


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
    subparsers.add_parser("features", help="Engineer geospatial, demographic, and topography features")
    subparsers.add_parser("train", help="Train placement suitability and equipment recommendation models")
    subparsers.add_parser("recommend", help="Find coverage gaps and output prioritized new site recommendations")
    subparsers.add_parser("map", help="Generate interactive Leaflet coverage and recommendation maps")
    subparsers.add_parser("all", help="Run full end-to-end pipeline")

    pred_parser = subparsers.add_parser("predict", help="Predict suitability for custom (lat, lon) coordinates")
    pred_parser.add_argument("--lat", type=float, required=True, help="Latitude (WGS84)")
    pred_parser.add_argument("--lon", type=float, required=True, help="Longitude (WGS84)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "clean": cmd_clean,
        "features": cmd_features,
        "train": cmd_train,
        "recommend": cmd_recommend,
        "map": cmd_map,
        "all": cmd_all,
        "predict": cmd_predict,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
