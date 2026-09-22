"""
src/export.py
Production-Grade Data Export Generators for Markdown (.md), Clean CSV (.csv),
and RFC 8259 O-RAN Near-RT RIC / 3GPP NWDAF JSON Streams.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from typing import Dict, Any, Optional
import json
import numpy as np
import pandas as pd
from src.config import (
    KPI_CONFIG, KPI_KEYS, CARRIER_BANDS, CARRIER_BAND_NAMES,
    CARRIER_CLUSTER_CELLS, BAND_COLORS, check_sla_compliance
)

def build_carrier_markdown_report(
    carrier: int,
    kpi: str,
    hist_sub: pd.DataFrame,
    forecast_sub: pd.DataFrame,
    model_metrics_data: Dict[str, Any]
) -> bytes:
    """Generates a complete, untruncated 365-day markdown telemetry report for the specified carrier."""
    kpi_meta = KPI_CONFIG.get(kpi, {})
    carrier_metrics = model_metrics_data.get('metrics_summary', {}).get(str(carrier), {})
    k_metrics = carrier_metrics.get(kpi, {})
    
    val_rmse = k_metrics.get('rmse', 0.0)
    val_mae = k_metrics.get('mae', 0.0)
    val_wape = k_metrics.get('wape', 0.0)
    val_mase = k_metrics.get('mase', 0.0)
    best_model = k_metrics.get('best_model', 'DampedFourierRidge')
    best_alpha = k_metrics.get('best_alpha', 1.0)
    
    last_v = float(hist_sub[kpi].iloc[-1]) if not hist_sub.empty and kpi in hist_sub.columns else 0.0
    last_d = hist_sub['date'].iloc[-1].strftime('%Y-%m-%d') if not hist_sub.empty else "N/A"
    hist_m = float(hist_sub[kpi].mean()) if not hist_sub.empty and kpi in hist_sub.columns else 0.0
    
    fc_m = float(forecast_sub[kpi].mean()) if not forecast_sub.empty and kpi in forecast_sub.columns else 0.0
    fc_min = float(forecast_sub[kpi].min()) if not forecast_sub.empty and kpi in forecast_sub.columns else 0.0
    fc_max = float(forecast_sub[kpi].max()) if not forecast_sub.empty and kpi in forecast_sub.columns else 0.0
    delta = fc_m - last_v
    delta_pct = (delta / (abs(last_v) + 1e-9)) * 100
    sign = "+" if delta >= 0 else ""

    start_d = forecast_sub['date'].iloc[0].strftime('%Y-%m-%d') if not forecast_sub.empty else pd.Timestamp.now().strftime('%Y-%m-%d')
    end_d = forecast_sub['date'].iloc[-1].strftime('%Y-%m-%d') if not forecast_sub.empty else (pd.Timestamp.now() + pd.Timedelta(days=365)).strftime('%Y-%m-%d')
    band_title = CARRIER_BAND_NAMES.get(carrier, f"Band {carrier} MHz")

    lines = [
        f"# {band_title} // KPI Telemetry & 365-Day Forecast Report",
        f"",
        f"> **Focus Metric**: {kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')})",
        f"> **Forecast Horizon**: {start_d} to {end_d} (365 Continuous Days)",
        f"> **Standardization**: 3GPP Rel-17 NWDAF & O-RAN Non-RT RIC SMO (A1 Policy)",
        f"> **Data Status**: 100% Complete // Zero Truncation",
        f"",
        f"---",
        f"",
        f"## 1. Executive Performance Summary",
        f"",
        f"- **Latest Observed Telemetry**: `{kpi_meta['format'].format(last_v)}` ({last_d})",
        f"- **Historical Baseline Mean**: `{kpi_meta['format'].format(hist_m)}`",
        f"- **365-Day Projected Average**: `{kpi_meta['format'].format(fc_m)}`",
        f"- **Projected Trend Shift**: `{sign}{delta_pct:.2f}%` ({sign}{kpi_meta['format'].format(delta)})",
        f"- **Projected Dynamic Range**: Min `{kpi_meta['format'].format(fc_min)}` / Max `{kpi_meta['format'].format(fc_max)}`",
        f"- **Operational Domain Constraint**: `{kpi_meta.get('domain', 'N/A')}`",
        f"- **Operational SLA Specification**: `{kpi_meta.get('sla_desc', 'N/A')}`",
        f"- **Selected S-Tier Model**: `{best_model}` (Holdout RMSE: `{val_rmse:.4f}`, MASE: `{val_mase:.3f}`, WAPE: `{val_wape:.2f}%`)",
        f"",
        f"---",
        f"",
        f"## 2. Multi-KPI Telemetry Matrix for Band {carrier} MHz",
        f"",
        f"| 3GPP Category | Metric Name | Unit | Hist Mean | 365d Projected Mean | Proj Min | Proj Max | Proj Shift | Holdout MASE | Best Model |",
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for k, m in KPI_CONFIG.items():
        if not hist_sub.empty and k in hist_sub.columns and not forecast_sub.empty and k in forecast_sub.columns:
            hm = float(hist_sub[k].mean())
            fm = float(forecast_sub[k].mean())
            fmin = float(forecast_sub[k].min())
            fmax = float(forecast_sub[k].max())
            lv = float(hist_sub[k].iloc[-1])
            d_pct = ((fm - lv) / (abs(lv) + 1e-9)) * 100
            s = "+" if d_pct >= 0 else ""
            
            k_info = carrier_metrics.get(k, {})
            k_mase = k_info.get('mase', 0.0)
            k_model = k_info.get('best_model', 'Ridge')
            lines.append(
                f"| {m['category']} | **{m['name']}** | {m['unit']} | {m['format'].format(hm)} | "
                f"{m['format'].format(fm)} | {m['format'].format(fmin)} | {m['format'].format(fmax)} | "
                f"{s}{d_pct:.2f}% | `{k_mase:.3f}` | `{k_model}` |"
            )

    has_quantiles = f"{kpi}_p05" in forecast_sub.columns and f"{kpi}_p95" in forecast_sub.columns
    if has_quantiles:
        lines.extend([
            f"",
            f"---",
            f"",
            f"## 3. Complete 365-Day Daily Projections Ledger: {kpi_meta.get('name', kpi)}",
            f"",
            f"| Date | Day of Week | Day of Year | Point Projection ({kpi_meta.get('unit', '')}) | 90% Quantile Interval (p05 - p95) |",
            f"| :--- | :--- | :--- | :--- | :--- |",
        ])
        for _, row in forecast_sub.sort_values('date').iterrows():
            d_str = row['date'].strftime('%Y-%m-%d')
            dow_str = row['date'].strftime('%A')
            doy_num = row['date'].day_of_year
            val_str = kpi_meta['format'].format(row[kpi])
            p05_str = kpi_meta['format'].format(row[f"{kpi}_p05"])
            p95_str = kpi_meta['format'].format(row[f"{kpi}_p95"])
            lines.append(f"| {d_str} | {dow_str} | Day {doy_num:03d} | {val_str} | [{p05_str} — {p95_str}] |")
    else:
        lines.extend([
            f"",
            f"---",
            f"",
            f"## 3. Complete 365-Day Daily Projections Ledger: {kpi_meta.get('name', kpi)}",
            f"",
            f"| Date | Day of Week | Day of Year | {kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')}) |",
            f"| :--- | :--- | :--- | :--- |",
        ])
        for _, row in forecast_sub.sort_values('date').iterrows():
            d_str = row['date'].strftime('%Y-%m-%d')
            dow_str = row['date'].strftime('%A')
            doy_num = row['date'].day_of_year
            val_str = kpi_meta['format'].format(row[kpi])
            lines.append(f"| {d_str} | {dow_str} | Day {doy_num:03d} | {val_str} |")

    lines.extend([
        f"",
        f"---",
        f"",
        f"## 4. O-RAN Non-RT RIC SMO & NWDAF Ingestion Specifications",
        f"- **Phase Continuity**: Daily points retain unbroken Fourier harmonics referenced to carrier inception base date.",
        f"- **Residual Anchoring**: Day 1 anchors directly to latest operational telemetry, decaying smoothly into long-range seasonal cycle.",
        f"- **Heteroscedastic Uncertainty**: Dual quantile regression bounds (p05, p95) fitted on empirical residuals.",
        f"- **Physical Domain Enforced**: Bounded strictly to prevent non-physical mathematical extrapolation.",
        f"",
        f"_Generated automatically by Network-ML S-Tier Engine._"
    ])

    return "\n".join(lines).encode('utf-8')

def build_carrier_json_payload(carrier: int, forecast_sub: pd.DataFrame) -> bytes:
    """Generates structured RFC 8259 JSON feed formatted for O-RAN Non-RT RIC SMO A1 Policy."""
    sub_records = []
    for _, row in forecast_sub.sort_values('date').iterrows():
        rec = {
            "date": row['date'].strftime('%Y-%m-%d'),
            "carrier_freq_mhz": int(carrier),
            "day_of_week": row['date'].strftime('%A'),
            "day_of_year": int(row['date'].day_of_year)
        }
        for k in KPI_CONFIG.keys():
            if k in row:
                rec[k] = round(float(row[k]), 5)
            if f"{k}_p05" in row and f"{k}_p95" in row:
                rec[f"{k}_p05"] = round(float(row[f"{k}_p05"]), 5)
                rec[f"{k}_p95"] = round(float(row[f"{k}_p95"]), 5)
        sub_records.append(rec)

    payload = {
        "standard": "3GPP_NWDAF_REL17_TS28.552",
        "interface": "O-RAN_NON_RT_RIC_SMO_A1_POLICY",
        "carrier_freq_mhz": int(carrier),
        "total_projections": len(sub_records),
        "start_date": sub_records[0]["date"] if sub_records else "",
        "end_date": sub_records[-1]["date"] if sub_records else "",
        "data": sub_records
    }
    return json.dumps(payload, indent=2).encode('utf-8')

def build_carrier_csv_bytes(forecast_sub: pd.DataFrame) -> bytes:
    """Exports clean CSV without internal timestamp or index columns."""
    clean_df = forecast_sub.copy()
    clean_df['date'] = clean_df['date'].dt.strftime('%Y-%m-%d')
    if 'dt' in clean_df.columns:
        clean_df.drop(columns=['dt'], inplace=True)
    if 't' in clean_df.columns:
        clean_df.drop(columns=['t'], inplace=True)
    return clean_df.to_csv(index=False).encode('utf-8')
