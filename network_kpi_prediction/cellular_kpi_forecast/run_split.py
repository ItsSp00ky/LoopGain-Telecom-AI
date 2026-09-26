"""
split.py
Stage 1: Chronological 3-Way Dataset Splitter (Train: 70%, Val: 15%, Test: 15%).
Enforces strict chronological ordering per carrier band with zero temporal leakage.
"""

import os
import sys
import argparse
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.data_cleaning import load_clean_data
from src.temporal_splitting import split_carrier_data, export_splits


def main():
    parser = argparse.ArgumentParser(
        description="KPI Prediction Pipeline // Stage 1: Chronological Dataset Splitter"
    )
    default_data = os.path.join(_REPO_ROOT, "data", "carrier_ran_kpi_clean.csv")
    if not os.path.exists(default_data) and os.path.exists(os.path.join(_REPO_ROOT, "data", "carrier_kpi_clean.csv")):
        default_data = os.path.join(_REPO_ROOT, "data", "carrier_kpi_clean.csv")

    parser.add_argument(
        "--data-path",
        type=str,
        default=default_data,
        help="Path to clean telemetry CSV (default: data/carrier_ran_kpi_clean.csv)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(_REPO_ROOT, "data", "splits"),
        help="Output directory for split datasets (default: data/splits)"
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
        help="Fraction of data for training (default: 0.70)"
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.15,
        help="Fraction of data for validation (default: 0.15)"
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.15,
        help="Fraction of data for testing (default: 0.15)"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("KPI PREDICTION PIPELINE // STAGE 1: CHRONOLOGICAL DATASET SPLITTER")
    print(f"Input: {args.data_path}")
    print(f"Ratios: Train={args.train_ratio*100:.1f}%, Validation={args.val_ratio*100:.1f}%, Test={args.test_ratio*100:.1f}%")
    print("=" * 80)

    df = load_clean_data(args.data_path)
    print(f"Loaded {len(df):,} sanitized records from '{args.data_path}'.")

    train_df, val_df, test_df, manifest = split_carrier_data(
        df,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio
    )

    paths = export_splits(train_df, val_df, test_df, manifest, output_dir=args.output_dir)

    print("\n--- CHRONOLOGICAL SPLIT SUMMARY BY CARRIER ---")
    header = f"{'Carrier':<8} | {'Total':<6} | {'Train (Dates / Rows)':<32} | {'Val (Dates / Rows)':<32} | {'Test (Dates / Rows)':<32}"
    print(header)
    print("-" * len(header))

    for carrier, meta in manifest['carriers'].items():
        tr = f"{meta['train']['start_date']} -> {meta['train']['end_date']} ({meta['train']['count']}r)"
        va = f"{meta['val']['start_date']} -> {meta['val']['end_date']} ({meta['val']['count']}r)"
        te = f"{meta['test']['start_date']} -> {meta['test']['end_date']} ({meta['test']['count']}r)"
        print(f"{carrier:<8} | {meta['total_rows']:<6} | {tr:<32} | {va:<32} | {te:<32}")

    print("-" * len(header))
    s = manifest['summary']
    print(f"TOTALS   | {s['total_rows']:<6} | {s['train_rows']:<5} ({s['train_pct']}%)                   | {s['val_rows']:<5} ({s['val_pct']}%)                   | {s['test_rows']:<5} ({s['test_pct']}%)")
    print("\nExported Datasets:")
    for name, p in paths.items():
        print(f"  [{name.upper():<8}] -> {p}")
    print("=" * 80)
    print("CHRONOLOGICAL SPLIT COMPLETED SUCCESSFULLY [LEAK-FREE]")
    print("=" * 80)


if __name__ == "__main__":
    main()
