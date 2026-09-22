"""
predict.py
On-Demand Inference CLI for 3GPP Cellular KPI & Traffic Predictions.
Supports querying precomputed forecast tables or executing live dynamic inference
using trained champion model bundles (with 90% quantile ribbons and SLA checks).
"""

import os
import sys
import argparse
import joblib
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.config import CARRIER_BANDS, KPI_KEYS, KPI_CONFIG, check_sla_compliance, apply_bounds
from src.clean import load_clean_data
from src.features import extract_time_features, get_feature_columns, compute_autoregressive_features
from src.models import TargetTransformer, apply_boundary_anchoring


def resolve_file(filename: str) -> str:
    """Resolves data paths checking multiple standard directory locations."""
    candidates = [
        os.path.join(_REPO_ROOT, filename),
        os.path.join(_REPO_ROOT, "data", filename),
        os.path.join(_REPO_ROOT, "data", "output", filename),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def query_predictions_precomputed(carrier: int, kpi: str, days: int = 7) -> bool:
    """Attempts to query predictions from precomputed forecast table."""
    forecast_csv = resolve_file("carrier_kpi_forecast_2026_2027.csv")
    if not os.path.exists(forecast_csv):
        return False

    df = pd.read_csv(forecast_csv)
    if 'carrier_freq' not in df.columns or kpi not in df.columns:
        return False

    df['date'] = pd.to_datetime(df['date'])
    sub = df[df['carrier_freq'] == carrier].sort_values('date').head(days)
    if sub.empty:
        return False

    kpi_meta = KPI_CONFIG.get(kpi, {})
    p05_col = f"{kpi}_p05"
    p95_col = f"{kpi}_p95"

    print("=" * 80)
    print(f"PREDICTION QUERY (TABLE LOOKUP) // Band {carrier} MHz: {kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')})")
    print(f"SLA Specification: {kpi_meta.get('sla_desc', 'N/A')}")
    print("=" * 80)

    for _, row in sub.iterrows():
        val = float(row[kpi])
        p05 = float(row[p05_col]) if p05_col in row else val * 0.95
        p95 = float(row[p95_col]) if p95_col in row else val * 1.05
        fmt = kpi_meta.get('format', '{:.2f}')
        sla_pass = check_sla_compliance(val, kpi)
        sla_flag = "PASS" if sla_pass else "BREACH"
        date_str = row['date'].strftime('%Y-%m-%d')
        print(f"  {date_str} | Forecast: {fmt.format(val):<14} | 90% Ribbon: [{fmt.format(p05)} -> {fmt.format(p95)}] | SLA: {sla_flag}")
    print("=" * 80)
    return True


def query_predictions_live(carrier: int, kpi: str, days: int = 7) -> bool:
    """Executes live on-demand inference using the serialized model bundle and autoregressive roll-forward."""
    bundle_path = os.path.join(_REPO_ROOT, "models", f"{carrier}_{kpi}_bundle.joblib")
    if not os.path.exists(bundle_path):
        return False

    bundle = joblib.load(bundle_path)
    model = bundle['model']
    model_class = bundle.get('model_class', 'Model')
    q_est = bundle.get('quantile_est')
    base_date = pd.to_datetime(bundle.get('base_date', '2025-09-01'))
    kpi_meta = KPI_CONFIG.get(kpi, {})
    trans = TargetTransformer(kpi_meta.get('transform', 'identity'))

    # Load recent telemetry for memory anchoring and autoregressive history
    try:
        clean_df = load_clean_data()
        sub_hist = clean_df[clean_df['carrier_freq'] == carrier].sort_values('date')
        last_hist_val = float(sub_hist[kpi].iloc[-1])
        last_hist_date = pd.to_datetime(sub_hist['date'].iloc[-1])
        recent_vals = sub_hist[kpi].values[-14:]
    except Exception:
        last_hist_val = None
        last_hist_date = pd.Timestamp.now().normalize()
        recent_vals = np.zeros(14)

    start_date = last_hist_date + pd.Timedelta(days=1)
    future_dates = pd.date_range(start=start_date, periods=days, freq='D')
    future_df = pd.DataFrame({'date': future_dates})
    future_dow = future_df['date'].dt.dayofweek.values

    # Feature extraction for time horizon
    feats = extract_time_features(future_df, base_date=base_date)
    base_cols = get_feature_columns()
    X_base = feats[base_cols].values

    if model_class == "AdaptiveBaseline":
        raw_preds = model.predict(X_base, day_of_week=future_dow)
    else:
        # Autoregressive recursive roll-forward
        buffer = list(trans.transform(recent_vals))
        if len(buffer) < 14:
            buffer = [0.0] * (14 - len(buffer)) + buffer
        future_preds_t = []
        for step in range(days):
            step_lag1 = buffer[-1]
            step_lag7 = buffer[-7]
            step_mean7 = float(np.mean(buffer[-7:]))
            step_std7 = float(np.std(buffer[-7:]))
            step_x = np.concatenate([X_base[step], [step_lag1, step_lag7, step_mean7, step_std7]]).reshape(1, -1)
            pred_step_t = float(model.predict_trans(step_x)[0])
            future_preds_t.append(pred_step_t)
            buffer.append(pred_step_t)
        raw_preds = trans.inverse_transform(np.array(future_preds_t), kpi)

    # Apply boundary anchoring to avoid origin step jumps
    if last_hist_val is not None:
        preds = apply_boundary_anchoring(raw_preds, last_hist_val, kpi)
    else:
        preds = apply_bounds(raw_preds, kpi)

    # Predict 90% Quantile Intervals (p05, p95)
    if q_est is not None and hasattr(q_est, 'predict_intervals'):
        future_ar = compute_autoregressive_features(trans.transform(preds))
        X_future_kpi = np.column_stack([X_base, future_ar])
        low, high = q_est.predict_intervals(X_future_kpi, preds)
    else:
        res_std = bundle.get('residual_std', 0.1)
        low = np.maximum(preds - 1.645 * res_std, kpi_meta.get('min_val', 0.0))
        high = preds + 1.645 * res_std
        if kpi_meta.get('max_val') is not None:
            high = np.minimum(high, kpi_meta['max_val'])

    print("=" * 80)
    print(f"PREDICTION QUERY (LIVE INFERENCE: {model_class}) // Band {carrier} MHz")
    print(f"Metric: {kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')}) | SLA: {kpi_meta.get('sla_desc', 'N/A')}")
    print("=" * 80)

    fmt = kpi_meta.get('format', '{:.2f}')
    for i, d in enumerate(future_dates):
        val = float(preds[i])
        p05 = float(low[i])
        p95 = float(high[i])
        sla_pass = check_sla_compliance(val, kpi)
        sla_flag = "PASS" if sla_pass else "BREACH"
        d_str = d.strftime('%Y-%m-%d')
        print(f"  {d_str} | Live Forecast: {fmt.format(val):<14} | 90% Ribbon: [{fmt.format(p05)} -> {fmt.format(p95)}] | SLA: {sla_flag}")
    print("=" * 80)
    return True


def query_predictions(carrier: int, kpi: str, days: int = 7, force_live: bool = False):
    """Unified entry point querying precomputed forecasts or live model inference."""
    if force_live:
        success = query_predictions_live(carrier, kpi, days)
        if not success:
            print(f"[!] Live model bundle not found for Carrier {carrier}, KPI {kpi}. Falling back to precomputed table...", file=sys.stderr)
            if not query_predictions_precomputed(carrier, kpi, days):
                print(f"[!] No predictions available. Run 'python train.py' to train models and generate forecasts.", file=sys.stderr)
                sys.exit(1)
    else:
        if not query_predictions_precomputed(carrier, kpi, days):
            # Fallback to live inference
            if not query_predictions_live(carrier, kpi, days):
                print(f"[!] Neither precomputed forecast nor trained model bundle found. Run 'python train.py' first.", file=sys.stderr)
                sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Query 3GPP Cellular KPI Predictions & Uncertainty Ribbons")
    parser.add_argument("--carrier", type=int, required=True, choices=CARRIER_BANDS, help="Carrier band (e.g. 3500)")
    parser.add_argument("--kpi", type=str, required=True, choices=KPI_KEYS, help="KPI key (e.g. connected_users)")
    parser.add_argument("--days", type=int, default=7, help="Number of forecast days to display (default: 7)")
    parser.add_argument("--live", action="store_true", help="Force real-time live inference from model bundle rather than table lookup")
    args = parser.parse_args()

    query_predictions(carrier=args.carrier, kpi=args.kpi, days=args.days, force_live=args.live)


if __name__ == "__main__":
    main()
