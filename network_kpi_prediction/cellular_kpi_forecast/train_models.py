"""
train.py
Stage 2: Model Training, Champion Selection & 365-Day Forecasting Engine.
Network-ML // Enterprise Cellular KPI Forecasting & Telemetry Pipeline.
3GPP Rel-17 NWDAF & O-RAN Near-RT RIC Machine Learning Engine.

Chronologically splits telemetry into Train (70%), Validation (15%), and Test (15%) sets.
Performs validation-based champion model selection across Damped Fourier Ridge,
Hybrid Trend-Seasonal Trees, and Adaptive Seasonal Baseline, then verifies performance
on the holdout test set before retraining on full history to forecast 365 days into the future.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import argparse
import json
import warnings
from datetime import datetime
import numpy as np
import pandas as pd
import joblib

from src.kpi_config import (
    KPI_CONFIG, KPI_KEYS, CARRIER_BANDS, apply_bounds,
    DEFAULT_SPLIT_RATIOS, DEFAULT_FORECAST_HORIZON_DAYS
)
from src.data_cleaning import load_clean_data
from src.temporal_splitting import split_carrier_data, export_splits
from src.feature_engineering import (
    extract_time_features, compute_autoregressive_features,
    get_feature_columns, get_all_feature_columns
)
from src.model_definitions import (
    TargetTransformer, DampedFourierRidgeModel, HybridTrendSeasonalModel,
    AdaptiveSeasonalBaseline, QuantileIntervalEstimator,
    evaluate_predictions, apply_boundary_anchoring
)

warnings.filterwarnings('ignore')

def run_pipeline(
    data_path: str = None,
    output_dir: str = None,
    models_dir: str = None,
    splits_dir: str = None,
    train_ratio: float = None,
    val_ratio: float = None,
    test_ratio: float = None,
    horizon_days: int = None,
    target_carriers: list = None,
    target_kpis: list = None
):
    train_ratio = train_ratio if train_ratio is not None else DEFAULT_SPLIT_RATIOS['train']
    val_ratio = val_ratio if val_ratio is not None else DEFAULT_SPLIT_RATIOS['val']
    test_ratio = test_ratio if test_ratio is not None else DEFAULT_SPLIT_RATIOS['test']
    horizon_days = horizon_days if horizon_days is not None else DEFAULT_FORECAST_HORIZON_DAYS
    active_carriers = target_carriers if target_carriers is not None else CARRIER_BANDS
    active_kpis = target_kpis if target_kpis is not None else KPI_KEYS

    if models_dir is None:
        models_dir = os.path.join(_REPO_ROOT, 'models')
    if splits_dir is None:
        splits_dir = os.path.join(_REPO_ROOT, 'data', 'splits')
    if output_dir is None:
        output_dir = os.path.join(_REPO_ROOT, 'data', 'output')

    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(splits_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 105, flush=True)
    print("NETWORK-ML // S-TIER TELECOM KPI MODEL TRAINING & BENCHMARKING ENGINE", flush=True)
    print("Architecture: 3GPP Rel-17 NWDAF & O-RAN Non-RT RIC SMO (A1 Policy)", flush=True)
    print(f"Validation: Chronological 3-Way Split ({train_ratio*100:.0f}% Train / {val_ratio*100:.0f}% Validation / {test_ratio*100:.0f}% Holdout Test)", flush=True)
    print(f"Forecast Horizon: {horizon_days} Days Forward", flush=True)
    print("=" * 105, flush=True)

    # 1. Ingest Telemetry & Generate Chronological Splits
    print("\n[1/4] Ingesting cleaned carrier telemetry & executing chronological 3-way split...", flush=True)
    if data_path is None:
        candidates = [
            os.path.join(_REPO_ROOT, 'data', 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'data', 'carrier_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'carrier_ran_kpi_clean.csv'),
        ]
        data_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    elif not os.path.isabs(data_path) and not os.path.exists(data_path):
        alt = os.path.join(_REPO_ROOT, data_path)
        if os.path.exists(alt):
            data_path = alt

    if not os.path.exists(data_path):
        print(f"Error: Dataset '{data_path}' not found.", file=sys.stderr)
        sys.exit(1)

    df = load_clean_data(data_path)
    df['date'] = pd.to_datetime(df['date'])

    base_feature_cols = get_feature_columns()
    all_feature_cols = get_all_feature_columns()
    print(f"  Loaded {len(df):,} observations across {len(active_carriers)} carrier bands: {active_carriers}", flush=True)
    print(f"  Engineered {len(base_feature_cols)} base time features + 4 autoregressive features = {len(all_feature_cols)} total features.", flush=True)

    # Execute and persist the 3-way chronological split
    train_df, val_df, test_df, split_manifest = split_carrier_data(
        df, train_ratio=train_ratio, val_ratio=val_ratio, test_ratio=test_ratio
    )
    split_paths = export_splits(train_df, val_df, test_df, split_manifest, output_dir=splits_dir)
    print(f"  Chronological splits exported: Train={len(train_df):,}r ({train_ratio*100:.0f}%), Val={len(val_df):,}r ({val_ratio*100:.0f}%), Test={len(test_df):,}r ({test_ratio*100:.0f}%)", flush=True)

    # 2. Chronological Benchmarking & Validation-Based Selection
    print("\n[2/4] Training on Train Set -> Selecting Champion on Validation Set -> Evaluating on Test Set...", flush=True)
    header = f"{'Carrier':<8} | {'3GPP KPI':<20} | {'Champion':<16} | {'Val-RMSE':<9} | {'Val-MASE':<9} | {'Test-RMSE':<9} | {'Test-MASE':<9} | {'Test-R2':<8}"
    print(header, flush=True)
    print("-" * len(header), flush=True)

    benchmark_records = []
    summary_metrics = {}
    all_forecasts = []

    for carrier in active_carriers:
        sub_df = df[df['carrier_freq'] == carrier].sort_values('date').reset_index(drop=True)
        if sub_df.empty:
            continue

        base_date = sub_df['date'].min()
        summary_metrics[str(carrier)] = {}

        # 3-Way Chronological split
        n_total = len(sub_df)
        n_train = int(np.round(n_total * train_ratio))
        n_val = int(np.round(n_total * val_ratio))
        n_test = n_total - n_train - n_val

        train_raw = sub_df.iloc[:n_train].copy()
        val_raw = sub_df.iloc[n_train:n_train + n_val].copy()
        test_raw = sub_df.iloc[n_train + n_val:].copy()

        train_dow = train_raw['date'].dt.dayofweek.values
        val_dow = val_raw['date'].dt.dayofweek.values
        test_dow = test_raw['date'].dt.dayofweek.values
        full_dow = sub_df['date'].dt.dayofweek.values

        # Extract base features with identical base_date phase origin
        train_feats = extract_time_features(train_raw, base_date=base_date)
        val_feats = extract_time_features(val_raw, base_date=base_date)
        test_feats = extract_time_features(test_raw, base_date=base_date)
        full_feats = extract_time_features(sub_df, base_date=base_date)

        X_train_base = train_feats[base_feature_cols].values
        X_val_base = val_feats[base_feature_cols].values
        X_test_base = test_feats[base_feature_cols].values
        X_full_base = full_feats[base_feature_cols].values

        # Build forward calendar
        last_hist_date = sub_df['date'].max()
        future_dates = pd.date_range(start=last_hist_date + pd.Timedelta(days=1), periods=horizon_days, freq='D')
        future_df = pd.DataFrame({'date': future_dates})
        future_dow = future_df['date'].dt.dayofweek.values
        future_feats = extract_time_features(future_df, base_date=base_date)
        X_future_base = future_feats[base_feature_cols].values

        carrier_forecast = future_df[['date']].copy()
        carrier_forecast['carrier_freq'] = carrier

        for kpi in active_kpis:
            y_train = train_raw[kpi].values
            y_val = val_raw[kpi].values
            y_test = test_raw[kpi].values
            y_full = sub_df[kpi].values
            last_observed_val = float(sub_df[kpi].iloc[-1])

            # Autoregressive lag and rolling 7-day volatility features in transformed space
            trans = TargetTransformer(KPI_CONFIG[kpi].get('transform', 'identity'))
            y_full_t = trans.transform(y_full)
            ar_feats_full = compute_autoregressive_features(y_full_t)

            X_train = np.column_stack([X_train_base, ar_feats_full[:n_train]])
            X_val = np.column_stack([X_val_base, ar_feats_full[n_train:n_train + n_val]])
            X_test = np.column_stack([X_test_base, ar_feats_full[n_train + n_val:]])
            X_full = np.column_stack([X_full_base, ar_feats_full])

            # ==========================================
            # 1. Fit Candidate Models on TRAIN set
            # ==========================================
            # Model 1: Damped Fourier Ridge
            ridge_model = DampedFourierRidgeModel(kpi)
            ridge_model.fit(X_train, y_train)

            # Model 2: Hybrid Trend-Seasonal Ensemble
            hybrid_model = HybridTrendSeasonalModel(kpi)
            hybrid_model.fit(X_train, y_train)

            # Model 3: Adaptive Seasonal Naive Baseline
            base_model = AdaptiveSeasonalBaseline(kpi)
            base_model.fit(X_train, y_train, day_of_week=train_dow)

            # ==========================================
            # 2. Evaluate on VALIDATION set (Tuning / Selection)
            # ==========================================
            pred_ridge_val = apply_boundary_anchoring(ridge_model.predict(X_val), float(y_train[-1]), kpi)
            m_ridge_val = evaluate_predictions(y_val, pred_ridge_val, y_train)

            pred_hybrid_val = apply_boundary_anchoring(hybrid_model.predict(X_val), float(y_train[-1]), kpi)
            m_hybrid_val = evaluate_predictions(y_val, pred_hybrid_val, y_train)

            pred_base_val = apply_boundary_anchoring(base_model.predict(X_val, day_of_week=val_dow), float(y_train[-1]), kpi)
            m_base_val = evaluate_predictions(y_val, pred_base_val, y_train)

            # Champion Selection based strictly on Validation performance
            ml_candidates = []
            if m_hybrid_val['mase'] <= 1.0:
                ml_candidates.append(('HybridEnsemble', m_hybrid_val, hybrid_model))
            if m_ridge_val['mase'] <= 1.0:
                ml_candidates.append(('FourierRidge', m_ridge_val, ridge_model))

            if ml_candidates:
                ml_candidates.sort(key=lambda x: (x[1]['mase'], x[1]['rmse']))
                champion_name, val_metrics, champion_model = ml_candidates[0]
            else:
                champion_name = "AdaptiveBaseline"
                val_metrics = m_base_val
                champion_model = base_model

            # ==========================================
            # 3. Evaluate Champion on HOLDOUT TEST set
            # ==========================================
            pred_ridge_test = apply_boundary_anchoring(ridge_model.predict(X_test), float(y_val[-1]), kpi)
            m_ridge_test = evaluate_predictions(y_test, pred_ridge_test, y_train)

            pred_hybrid_test = apply_boundary_anchoring(hybrid_model.predict(X_test), float(y_val[-1]), kpi)
            m_hybrid_test = evaluate_predictions(y_test, pred_hybrid_test, y_train)

            pred_base_test = apply_boundary_anchoring(base_model.predict(X_test, day_of_week=test_dow), float(y_val[-1]), kpi)
            m_base_test = evaluate_predictions(y_test, pred_base_test, y_train)

            if champion_name == "HybridEnsemble":
                test_metrics = m_hybrid_test
            elif champion_name == "FourierRidge":
                test_metrics = m_ridge_test
            else:
                test_metrics = m_base_test

            # ==========================================
            # 4. Production Training on FULL History
            # ==========================================
            if champion_name == "AdaptiveBaseline":
                best_alpha = 1.0
                prod_model = AdaptiveSeasonalBaseline(kpi)
                prod_model.fit(X_full, y_full, day_of_week=full_dow)
                raw_future_preds = prod_model.predict(X_future_base, day_of_week=future_dow)
                y_full_fitted = prod_model.predict(X_full, day_of_week=full_dow)
            elif champion_name == "HybridEnsemble":
                best_alpha = 1.0
                prod_model = HybridTrendSeasonalModel(kpi)
                prod_model.fit(X_full, y_full)
                # Recursive autoregressive roll-forward across horizon_days
                buffer = list(y_full_t[-14:])
                future_preds_t = []
                for step in range(horizon_days):
                    step_lag1 = buffer[-1]
                    step_lag7 = buffer[-7]
                    step_mean7 = float(np.mean(buffer[-7:]))
                    step_std7 = float(np.std(buffer[-7:]))
                    step_x = np.concatenate([X_future_base[step], [step_lag1, step_lag7, step_mean7, step_std7]]).reshape(1, -1)
                    pred_step_t = float(prod_model.predict_trans(step_x)[0])
                    future_preds_t.append(pred_step_t)
                    buffer.append(pred_step_t)
                raw_future_preds = trans.inverse_transform(np.array(future_preds_t), kpi)
                y_full_fitted = prod_model.predict(X_full)
            else: # FourierRidge
                prod_model = DampedFourierRidgeModel(kpi)
                prod_model.fit(X_full, y_full)
                best_alpha = prod_model.best_alpha
                # Recursive autoregressive roll-forward across horizon_days
                buffer = list(y_full_t[-14:])
                future_preds_t = []
                for step in range(horizon_days):
                    step_lag1 = buffer[-1]
                    step_lag7 = buffer[-7]
                    step_mean7 = float(np.mean(buffer[-7:]))
                    step_std7 = float(np.std(buffer[-7:]))
                    step_x = np.concatenate([X_future_base[step], [step_lag1, step_lag7, step_mean7, step_std7]]).reshape(1, -1)
                    pred_step_t = float(prod_model.predict_trans(step_x)[0])
                    future_preds_t.append(pred_step_t)
                    buffer.append(pred_step_t)
                raw_future_preds = trans.inverse_transform(np.array(future_preds_t), kpi)
                y_full_fitted = prod_model.predict(X_full)

            # Generate 365-day projections with seamless boundary anchoring
            anchored_preds = apply_boundary_anchoring(raw_future_preds, last_observed_val, kpi)
            carrier_forecast[kpi] = anchored_preds

            # Heteroscedastic Quantile Regression Prediction Intervals (p05, p95)
            full_residuals = y_full - y_full_fitted
            residual_std = float(np.std(full_residuals))

            q_est = QuantileIntervalEstimator(kpi)
            q_est.fit(X_full, full_residuals)
            future_ar_feats = compute_autoregressive_features(trans.transform(anchored_preds))
            X_future_kpi = np.column_stack([X_future_base, future_ar_feats])
            lower_preds, upper_preds = q_est.predict_intervals(X_future_kpi, anchored_preds)

            carrier_forecast[f"{kpi}_p05"] = lower_preds
            carrier_forecast[f"{kpi}_p95"] = upper_preds

            # Store metrics
            summary_metrics[str(carrier)][kpi] = {
                "best_model": champion_name,
                "best_alpha": best_alpha,
                "mase": test_metrics['mase'],
                "wape": test_metrics['wape'],
                "val_rmse": val_metrics['rmse'],
                "val_mae": val_metrics['mae'],
                "val_wape": val_metrics['wape'],
                "val_mase": val_metrics['mase'],
                "val_r2_bench": val_metrics['r2_bench'],
                "test_rmse": test_metrics['rmse'],
                "test_mae": test_metrics['mae'],
                "test_wape": test_metrics['wape'],
                "test_mase": test_metrics['mase'],
                "test_r2_bench": test_metrics['r2_bench'],
                "residual_std": round(residual_std, 4),
                "ridge_val_mase": m_ridge_val['mase'],
                "hybrid_val_mase": m_hybrid_val['mase'],
                "base_val_mase": m_base_val['mase'],
                "ridge_test_mase": m_ridge_test['mase'],
                "hybrid_test_mase": m_hybrid_test['mase'],
                "base_test_mase": m_base_test['mase']
            }

            benchmark_records.append({
                "carrier": int(carrier),
                "kpi": kpi,
                "best_model": champion_name,
                "best_alpha": best_alpha,
                "val_rmse": val_metrics['rmse'],
                "val_mase": val_metrics['mase'],
                "test_rmse": test_metrics['rmse'],
                "test_mae": test_metrics['mae'],
                "test_wape_pct": test_metrics['wape'],
                "test_mase": test_metrics['mase'],
                "test_r2_bench": test_metrics['r2_bench']
            })

            # Save serialized production bundle
            bundle = {
                'carrier': int(carrier),
                'kpi': kpi,
                'model_class': champion_name,
                'model': prod_model,
                'quantile_est': q_est,
                'best_alpha': best_alpha,
                'feature_cols': all_feature_cols,
                'base_date': base_date.strftime('%Y-%m-%d'),
                'residual_std': residual_std,
                'metrics': summary_metrics[str(carrier)][kpi]
            }
            joblib.dump(bundle, os.path.join(models_dir, f'{carrier}_{kpi}_bundle.joblib'))

            # Log row
            print(
                f"{carrier:<8} | {kpi:<20} | {champion_name:<16} | "
                f"{val_metrics['rmse']:>9.4f} | {val_metrics['mase']:>9.3f} | "
                f"{test_metrics['rmse']:>9.4f} | {test_metrics['mase']:>9.3f} | "
                f"{test_metrics['r2_bench']:>8.4f}",
                flush=True
            )

        all_forecasts.append(carrier_forecast)

    # 3. Serialize Validation & Test Artifacts
    print(f"\n[3/4] Serializing benchmark artifacts to '{output_dir}'...", flush=True)
    bench_df = pd.DataFrame(benchmark_records)
    metrics_csv_path = os.path.join(output_dir, 'model_metrics.csv')
    bench_df.to_csv(metrics_csv_path, index=False)

    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "standard": "3GPP_NWDAF_REL17_TS28.552",
        "split_ratios": {"train": train_ratio, "val": val_ratio, "test": test_ratio},
        "forecast_horizon_days": horizon_days,
        "total_carriers": len(active_carriers),
        "total_kpis": len(active_kpis),
        "feature_count": len(all_feature_cols),
        "features": all_feature_cols,
        "metrics_summary": summary_metrics,
        "benchmarks": benchmark_records
    }
    metrics_json_path = os.path.join(output_dir, 'model_metrics.json')
    with open(metrics_json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, default=str)

    # 4. Save Multi-Carrier Projections
    print(f"\n[4/4] Assembling full {horizon_days}-day forward multi-carrier projections...", flush=True)
    final_forecast_df = pd.concat(all_forecasts, ignore_index=True)
    final_forecast_df['date'] = final_forecast_df['date'].dt.strftime('%Y-%m-%d')
    cols_order = ['date', 'carrier_freq'] + active_kpis + [f"{k}_p05" for k in active_kpis] + [f"{k}_p95" for k in active_kpis]
    final_forecast_df = final_forecast_df[cols_order]

    output_csv = os.path.join(output_dir, 'carrier_kpi_forecast_2026_2027.csv')
    final_forecast_df.to_csv(output_csv, index=False)
    print(f"  [OK] Exported {len(final_forecast_df):,} forward projections to '{output_csv}'", flush=True)
    print("=" * 105, flush=True)
    print("MODEL TRAINING & FORECAST PIPELINE SUCCESSFULLY COMPLETED [S-TIER]", flush=True)
    print("=" * 105, flush=True)

    return {
        'forecast_csv': output_csv,
        'metrics_json': metrics_json_path,
        'metrics_csv': metrics_csv_path,
        'models_dir': models_dir,
        'splits_dir': splits_dir
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="3GPP Cellular KPI Model Training & Forecasting Engine")
    parser.add_argument("--data-path", type=str, default=None, help="Path to clean telemetry CSV")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for metrics and forecasts")
    parser.add_argument("--models-dir", type=str, default=None, help="Directory to save serialized models")
    parser.add_argument("--splits-dir", type=str, default=None, help="Directory to save dataset splits")
    parser.add_argument("--train-ratio", type=float, default=None, help="Train ratio (default: 0.70)")
    parser.add_argument("--val-ratio", type=float, default=None, help="Val ratio (default: 0.15)")
    parser.add_argument("--test-ratio", type=float, default=None, help="Test ratio (default: 0.15)")
    parser.add_argument("--horizon-days", type=int, default=None, help="Forward forecast horizon in days (default: 365)")
    parser.add_argument("--carrier", type=int, choices=CARRIER_BANDS, default=None, help="Train only for a specific carrier band")
    parser.add_argument("--kpi", type=str, choices=KPI_KEYS, default=None, help="Train only for a specific KPI")

    args = parser.parse_args(argv)
    carriers = [args.carrier] if args.carrier else None
    kpis = [args.kpi] if args.kpi else None

    run_pipeline(
        data_path=args.data_path,
        output_dir=args.output_dir,
        models_dir=args.models_dir,
        splits_dir=args.splits_dir,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        horizon_days=args.horizon_days,
        target_carriers=carriers,
        target_kpis=kpis
    )


if __name__ == '__main__':
    main()
