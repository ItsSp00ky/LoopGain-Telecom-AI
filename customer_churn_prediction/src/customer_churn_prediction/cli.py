import argparse
import sys
import json
import joblib
import warnings
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from customer_churn_prediction.config import MODEL_DIR, REPORTS_DIR, DEFAULT_DATASET_PATH
from customer_churn_prediction.data_loader import load_and_clean_data
from customer_churn_prediction.feature_engineering import TelecomFeatureEngineer
from customer_churn_prediction.model_trainer import train_and_benchmark, detect_cuda
from customer_churn_prediction.evaluate import run_comprehensive_evaluation
from customer_churn_prediction.discount_engine import TelecomDiscountEngine

console = Console()

def cmd_train(args):
    console.print(Panel.fit("[bold green]Maven Telecom Customer Churn Model Training & Benchmark[/bold green]"))
    use_cuda = not args.cpu
    res = train_and_benchmark(data_path=DEFAULT_DATASET_PATH, use_cuda=use_cuda)
    
    table = Table(title="Model Benchmark Results (Maven Telecom)")
    table.add_column("Model", style="cyan")
    table.add_column("CV ROC-AUC", style="magenta")
    table.add_column("Test ROC-AUC", style="green")
    table.add_column("Test PR-AUC", style="yellow")
    table.add_column("Recall", style="blue")
    table.add_column("F1 Score", style="red")

    for model_name, m in res["results"].items():
        is_champ = (model_name == res["champion_name"])
        prefix = "★ " if is_champ else "  "
        table.add_row(
            f"{prefix}{model_name}",
            f"{m['cv_roc_auc_mean']:.4f} (±{m['cv_roc_auc_std']:.4f})",
            f"{m['test_roc_auc']:.4f}",
            f"{m['test_pr_auc']:.4f}",
            f"{m['test_recall']:.4f}",
            f"{m['test_f1']:.4f}"
        )
    console.print(table)
    console.print(f"[bold green]Champion model saved to:[/bold green] {res['model_path']}")

def cmd_evaluate(args):
    console.print(Panel.fit("[bold blue]Generating Comprehensive Model Evaluation & Plots[/bold blue]"))
    metrics = run_comprehensive_evaluation()
    console.print(f"Optimal Threshold: [bold]{metrics['best_threshold']:.2f}[/bold]")
    console.print(f"ROC-AUC: [bold]{metrics['roc_auc']:.4f}[/bold]")
    console.print(f"PR-AUC: [bold]{metrics['pr_auc']:.4f}[/bold]")
    console.print(f"Best F1 Score: [bold]{metrics['best_f1']:.4f}[/bold]")
    console.print(f"[green]All charts saved to:[/green] {REPORTS_DIR}")

def cmd_recommend(args):
    model_path = MODEL_DIR / "best_churn_model.joblib"
    if not model_path.exists():
        console.print("[bold red]Model not trained yet! Run `train` first.[/bold red]")
        sys.exit(1)

    pipeline = joblib.load(model_path)
    X_raw, y, meta = load_and_clean_data()
    engine = TelecomDiscountEngine()

    id_col = "Customer ID" if "Customer ID" in meta.columns else "CustomerID"

    if args.customer_id:
        match_idx = meta.index[meta[id_col] == args.customer_id].tolist()
        if not match_idx:
            console.print(f"[bold red]Customer ID {args.customer_id} not found in dataset.[/bold red]")
            sys.exit(1)
        idx = match_idx[0]
    else:
        # Pick a high-risk customer on Offer E or month-to-month as showcase
        probs = pipeline.predict_proba(X_raw)[:, 1]
        high_risk_indices = np.where((probs >= 0.70) & (meta["Offer"] == "Offer E"))[0]
        if len(high_risk_indices) == 0:
            high_risk_indices = np.where(probs >= 0.65)[0]
        idx = high_risk_indices[0] if len(high_risk_indices) > 0 else 0

    cust_row = X_raw.iloc[[idx]]
    meta_row = meta.iloc[idx]
    churn_prob = float(pipeline.predict_proba(cust_row)[0, 1])

    mc = float(meta_row.get("Monthly Charge", meta_row.get("Monthly Charges", 70.0)))
    rev = float(meta_row.get("Total Revenue", meta_row.get("Total Charges", 2500.0)))
    offer = str(meta_row.get("Offer", "None"))
    contract = str(meta_row.get("Contract", "Month-to-Month"))
    internet = str(meta_row.get("Internet Type", "Fiber Optic"))
    gb = float(meta_row.get("Avg Monthly GB Download", 20.0))
    extra_fees = float(meta_row.get("Total Extra Data Charges", 0.0))
    refunds = float(meta_row.get("Total Refunds", 0.0))
    ts = (cust_row["Premium Tech Support"].values[0] == "Yes") if "Premium Tech Support" in cust_row.columns else False
    sec = (cust_row["Online Security"].values[0] == "Yes") if "Online Security" in cust_row.columns else False
    tenure = int(meta_row.get("Tenure in Months", 12))

    rec = engine.evaluate_customer(
        churn_prob=churn_prob,
        monthly_charge=mc,
        total_revenue=rev,
        current_offer=offer,
        contract=contract,
        internet_type=internet,
        avg_gb_download=gb,
        extra_data_charges=extra_fees,
        refunds=refunds,
        has_tech_support=ts,
        has_security=sec,
        tenure_months=tenure
    )

    console.print(Panel.fit(f"[bold yellow]Retention & Discount Profile for Customer: {meta_row[id_col]}[/bold yellow]"))
    
    t = Table(show_header=False)
    t.add_row("Churn Probability", f"[bold red]{rec['churn_probability']:.1%}[/bold red]")
    t.add_row("Risk Level / Urgency", f"{rec['risk_level']} ({rec['urgency']})")
    t.add_row("Current Marketing Offer", f"[bold]{offer}[/bold]")
    t.add_row("Total Customer Revenue", f"${rev:,.2f}")
    t.add_row("Current Monthly Bill", f"${rec['current_monthly_charge']:.2f}")
    t.add_row("Retention Tier", f"[bold magenta]{rec['retention_tier']}[/bold magenta]")
    t.add_row("Recommended Action", rec["recommended_action"])
    t.add_row("Prescribed Target Offer", f"[bold cyan]{rec['prescribed_offer']}[/bold cyan]")
    t.add_row("Target Discount %", f"[bold green]{rec['discount_percentage']}%[/bold green]")
    t.add_row("New Discounted Monthly Bill", f"[bold green]${rec['new_monthly_charge']:.2f}[/bold green] (Save ${(rec['current_monthly_charge'] - rec['new_monthly_charge']):.2f}/mo)")
    t.add_row("Contract Requirement", rec["contract_recommendation"])
    t.add_row("Package Add-on Offer", rec["package_add_ons"])
    t.add_row("Expected Saved Revenue (12m)", f"${rec['expected_saved_revenue']:.2f}")
    t.add_row("Discount Cost (12m)", f"${rec['expected_annual_discount_cost']:.2f}")
    t.add_row("Net Financial Gain", f"[bold green]${rec['net_retention_gain']:.2f}[/bold green]")
    t.add_row("Projected ROI %", f"[bold cyan]{rec['roi_percentage']:.1f}%[/bold cyan]")
    
    console.print(t)
    if rec["strategic_notes"]:
        console.print("\n[bold yellow]Strategic Telecom Diagnostics & Offer Rationale:[/bold yellow]")
        for note in rec["strategic_notes"]:
            console.print(f" • {note}")

def cmd_batch_recommend(args):
    model_path = MODEL_DIR / "best_churn_model.joblib"
    if not model_path.exists():
        console.print("[bold red]Model not trained yet! Run `train` first.[/bold red]")
        sys.exit(1)

    pipeline = joblib.load(model_path)
    X_raw, y, meta = load_and_clean_data()
    engine = TelecomDiscountEngine()

    console.print("Scoring all customers with Champion Model...")
    probs = pipeline.predict_proba(X_raw)[:, 1]

    eval_df = meta.copy()
    for col in ["Premium Tech Support", "Online Security"]:
        if col in X_raw.columns:
            eval_df[col] = X_raw[col].values

    recs_df = engine.batch_recommend(eval_df, probs)
    output_path = args.output or "maven_retention_campaign.csv"
    recs_df.to_csv(output_path, index=False)

    console.print(f"[bold green]Batch retention campaign saved to:[/bold green] {output_path}")
    console.print("\nRetention Tier Distribution:")
    console.print(recs_df["retention_tier"].value_counts())
    console.print(f"\nTotal Projected Net Saved Revenue: [bold green]${recs_df['net_retention_gain'].sum():,.2f}[/bold green]")

def main():
    parser = argparse.ArgumentParser(description="Maven Telecom Churn Prediction & Discount Optimization CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Train
    train_parser = subparsers.add_parser("train", help="Train and benchmark models on GPU/CPU")
    train_parser.add_argument("--cpu", action="store_true", help="Force CPU training instead of CUDA GPU")

    # Evaluate
    subparsers.add_parser("evaluate", help="Generate evaluation charts and metrics")

    # Recommend
    rec_parser = subparsers.add_parser("recommend", help="Get personalized discount recommendations for a customer")
    rec_parser.add_argument("--customer-id", type=str, help="Specific Customer ID to evaluate")

    # Batch Recommend
    batch_parser = subparsers.add_parser("batch-recommend", help="Run batch discount targeting for all customers")
    batch_parser.add_argument("--output", type=str, default="retention_campaign_targets.csv", help="Output CSV path")

    args = parser.parse_args()

    if args.command == "train":
        cmd_train(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "recommend":
        cmd_recommend(args)
    elif args.command == "batch-recommend":
        cmd_batch_recommend(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
