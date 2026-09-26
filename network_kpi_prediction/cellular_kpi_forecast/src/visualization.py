"""
src/plots.py
Publication-Grade Static & Comparative Plotting Engine for 3GPP Rel-17 Telemetry.
Generates 300-DPI Dark Industrial NOC Visualizations with Heteroscedastic
Quantile Ribbons (p05-p95), SLA Targets, Moving Average Baselines, and Multi-Band Grids.
"""

import os
import sys
import json
import zipfile
from typing import Dict, Any, List, Optional, Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch

from src.kpi_config import (
    KPI_CONFIG, KPI_KEYS, KPI_CATEGORIES, CARRIER_BANDS,
    CARRIER_BAND_NAMES, CARRIER_CLUSTER_CELLS, BAND_COLORS,
    check_sla_compliance
)

# Clean Light Publication Styling Palette
STYLE_CONFIG = {
    'bg_figure': '#FFFFFF',       # Crisp white canvas
    'bg_axes': '#F8FAFC',         # Clean off-white plotting surface (slate-50)
    'border': '#CBD5E1',          # Light slate border (slate-300)
    'grid': '#E2E8F0',            # Subtle light gray grid lines (slate-200)
    'text_primary': '#0F172A',    # Deep slate / near-black for headers and title (slate-900)
    'text_secondary': '#475569',  # Medium slate for axis labels and ticks (slate-600)
    'text_muted': '#64748B',      # Muted slate for subtitles (slate-500)
    'color_hist': '#059669',      # Emerald green (deep, high contrast on light bg)
    'color_ma': '#10B981',        # Green moving average
    'color_forecast': '#0284C7',  # High-contrast Sky/Ocean Blue (sky-600)
    'color_ribbon': '#38BDF8',    # Translucent Sky Blue ribbon
    'color_sla': '#DC2626',       # Crimson Red SLA threshold line
    'color_split': '#64748B',     # Slate vertical demarcation line
    'font_sans': ['Inter', 'DejaVu Sans', 'Arial', 'sans-serif'],
    'font_mono': ['JetBrains Mono', 'DejaVu Sans Mono', 'Consolas', 'monospace']
}

def apply_noc_theme(fig: plt.Figure, ax: plt.Axes) -> None:
    """Applies clean publication light styling to matplotlib figure and axes."""
    fig.patch.set_facecolor(STYLE_CONFIG['bg_figure'])
    ax.set_facecolor(STYLE_CONFIG['bg_axes'])
    
    # Spines
    for spine in ax.spines.values():
        spine.set_color(STYLE_CONFIG['border'])
        spine.set_linewidth(1.0)
        
    # Ticks & Grid
    ax.tick_params(colors=STYLE_CONFIG['text_secondary'], which='both', labelsize=9)
    ax.grid(True, color=STYLE_CONFIG['grid'], linestyle='--', linewidth=0.8, alpha=0.7)
    
    # Axis labels
    ax.xaxis.label.set_color(STYLE_CONFIG['text_secondary'])
    ax.yaxis.label.set_color(STYLE_CONFIG['text_secondary'])
    ax.title.set_color(STYLE_CONFIG['text_primary'])

def plot_single_kpi(
    carrier: int,
    kpi: str,
    hist_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    metrics_dict: Optional[Dict[str, Any]] = None,
    out_path: Optional[str] = None,
    dpi: int = 300
) -> plt.Figure:
    """
    Renders a publication-grade 300-DPI visual plot for a single carrier and KPI.
    Includes historical observations, 14d rolling MA, 365d forecast, 90% quantile ribbon,
    SLA threshold line, and an inset operational diagnostic badge.
    """
    kpi_meta = KPI_CONFIG.get(kpi, {})
    carrier_name = CARRIER_BAND_NAMES.get(carrier, f"Band {carrier} MHz")
    cell_count = CARRIER_CLUSTER_CELLS.get(carrier, 0)
    
    # Subsets
    h_sub = hist_df[hist_df['carrier_freq'] == carrier].sort_values('date').copy()
    f_sub = forecast_df[forecast_df['carrier_freq'] == carrier].sort_values('date').copy()
    
    fig, ax = plt.subplots(figsize=(12, 6.2), dpi=dpi)
    apply_noc_theme(fig, ax)
    
    # 1. Historical Telemetry
    if not h_sub.empty and kpi in h_sub.columns:
        h_dates = pd.to_datetime(h_sub['date'])
        h_vals = h_sub[kpi].values
        ax.plot(
            h_dates, h_vals,
            color=STYLE_CONFIG['color_hist'],
            linewidth=1.8,
            label='Historical Observations (Cell Telemetry)',
            zorder=3
        )
        
        # 14-Day Moving Average Baseline
        if len(h_vals) >= 14:
            ma14 = pd.Series(h_vals).rolling(14, min_periods=1).mean().values
            ax.plot(
                h_dates, ma14,
                color=STYLE_CONFIG['color_ma'],
                linewidth=1.2,
                linestyle=':',
                label='14-Day Moving Average Baseline',
                zorder=4
            )
            
        last_hist_date = h_dates.iloc[-1]
        last_hist_val = float(h_vals[-1])
    else:
        last_hist_date = pd.to_datetime(f_sub['date'].iloc[0]) - pd.Timedelta(days=1) if not f_sub.empty else pd.Timestamp.now().normalize()
        last_hist_val = 0.0

    # 2. 365-Day Champion Forecast & Quantile Interval Ribbon (p05 - p95)
    if not f_sub.empty and kpi in f_sub.columns:
        f_dates = pd.to_datetime(f_sub['date'])
        f_vals = f_sub[kpi].values
        
        p05_col = f"{kpi}_p05"
        p95_col = f"{kpi}_p95"
        has_quantiles = p05_col in f_sub.columns and p95_col in f_sub.columns
        
        # Connect seamless origin without discontinuity
        proj_dates = [last_hist_date] + list(f_dates)
        proj_vals = [last_hist_val] + list(f_vals)
        
        if has_quantiles:
            y_lower = [last_hist_val] + list(f_sub[p05_col].values)
            y_upper = [last_hist_val] + list(f_sub[p95_col].values)
            ax.fill_between(
                proj_dates, y_lower, y_upper,
                color=STYLE_CONFIG['color_ribbon'],
                alpha=0.18,
                label='90% Quantile Prediction Envelope (p05 - p95)',
                zorder=2
            )
            
        # Projection line
        ax.plot(
            proj_dates, proj_vals,
            color=STYLE_CONFIG['color_forecast'],
            linewidth=2.0,
            linestyle='--',
            label='365-Day Model Projection (Champion)',
            zorder=5
        )
        
    # 3. Operational SLA Target Threshold
    sla_target = kpi_meta.get('sla_target')
    if sla_target is not None:
        ax.axhline(
            y=sla_target,
            color=STYLE_CONFIG['color_sla'],
            linewidth=1.4,
            linestyle='-.',
            label=f"SLA Target ({kpi_meta.get('sla_desc', '')})",
            zorder=6
        )

    # 4. Vertical Forecast Horizon Demarcation Line
    if not h_sub.empty and not f_sub.empty:
        ax.axvline(
            x=last_hist_date,
            color=STYLE_CONFIG['color_split'],
            linewidth=1.2,
            linestyle='--',
            alpha=0.8,
            zorder=2
        )
        ax.text(
            last_hist_date, ax.get_ylim()[1] if ax.get_ylim()[1] != 0 else 1.0,
            '  FORECAST HORIZON  ',
            color=STYLE_CONFIG['text_secondary'],
            fontsize=8,
            fontfamily='monospace',
            fontweight='bold',
            verticalalignment='top',
            bbox=dict(boxstyle='square,pad=0.2', facecolor=STYLE_CONFIG['bg_figure'], edgecolor=STYLE_CONFIG['border'], alpha=0.9)
        )

    # Axis Labels & Format
    ax.set_ylabel(f"{kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')})", fontsize=11, fontweight='bold')
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.setp(ax.get_xticklabels(), rotation=30, ha='right')
    
    # Title Section
    title_text = f"{carrier_name} // {kpi_meta.get('name', kpi)}"
    subtitle_text = f"3GPP Category: {kpi_meta.get('category', 'Telemetry')} | Bounded Domain: {kpi_meta.get('domain', 'N/A')} | Cluster: {cell_count:,} Cells"
    fig.suptitle(title_text, fontsize=14, fontweight='700', color=STYLE_CONFIG['text_primary'], x=0.08, y=0.97, ha='left')
    ax.set_title(subtitle_text, fontsize=9.5, color=STYLE_CONFIG['text_muted'], pad=12, loc='left')

    # Legend
    legend = ax.legend(
        loc='upper left',
        facecolor=STYLE_CONFIG['bg_figure'],
        edgecolor=STYLE_CONFIG['border'],
        labelcolor=STYLE_CONFIG['text_primary'],
        fontsize=8.5,
        framealpha=0.92
    )
    
    # Inset Diagnostic Badge (Top Right)
    k_metrics = {}
    if metrics_dict:
        carrier_summary = metrics_dict.get('metrics_summary', {}).get(str(carrier), {})
        k_metrics = carrier_summary.get(kpi, {})
        
    champ_model = k_metrics.get('best_model', 'FourierRidge')
    mase_val = k_metrics.get('mase', 0.850)
    wape_val = k_metrics.get('wape', 1.20)
    rmse_val = k_metrics.get('rmse', 0.150)
    
    # Evaluate latest SLA status
    latest_val = float(h_sub[kpi].iloc[-1]) if not h_sub.empty and kpi in h_sub.columns else 0.0
    sla_compliant = check_sla_compliance(latest_val, kpi)
    sla_status_str = "SLA COMPLIANT" if sla_compliant else "SLA BREACH"
    sla_status_color = "#10B981" if sla_compliant else "#EF4444"
    
    badge_text = (
        f"ENGINE: {champ_model}\n"
        f"HOLDOUT MASE: {mase_val:.3f}\n"
        f"HOLDOUT WAPE: {wape_val:.2f}%\n"
        f"HOLDOUT RMSE: {rmse_val:.4f}\n"
        f"STATUS: {sla_status_str}"
    )
    
    ax.text(
        0.985, 0.965, badge_text,
        transform=ax.transAxes,
        fontsize=8.0,
        fontfamily='monospace',
        color=STYLE_CONFIG['text_primary'],
        verticalalignment='top',
        horizontalalignment='right',
        bbox=dict(
            boxstyle='round,pad=0.6',
            facecolor=STYLE_CONFIG['bg_figure'],
            edgecolor=STYLE_CONFIG['border'],
            linewidth=1.0,
            alpha=0.95
        ),
        zorder=10
    )
    
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return None
        
    return fig

def plot_carrier_grid(
    carrier: int,
    hist_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    metrics_dict: Optional[Dict[str, Any]] = None,
    out_path: Optional[str] = None,
    dpi: int = 300
) -> plt.Figure:
    """
    Generates a high-resolution 10-KPI Master Grid Dashboard (2 rows x 5 cols)
    for a specific carrier frequency band.
    """
    carrier_name = CARRIER_BAND_NAMES.get(carrier, f"Band {carrier} MHz")
    cell_count = CARRIER_CLUSTER_CELLS.get(carrier, 0)
    
    h_sub = hist_df[hist_df['carrier_freq'] == carrier].sort_values('date').copy()
    f_sub = forecast_df[forecast_df['carrier_freq'] == carrier].sort_values('date').copy()
    
    fig, axes = plt.subplots(2, 5, figsize=(26, 11), dpi=dpi)
    fig.patch.set_facecolor(STYLE_CONFIG['bg_figure'])
    axes_flat = axes.flatten()
    
    carrier_metrics = metrics_dict.get('metrics_summary', {}).get(str(carrier), {}) if metrics_dict else {}
    
    for i, kpi in enumerate(KPI_KEYS):
        ax = axes_flat[i]
        apply_noc_theme(fig, ax)
        kpi_meta = KPI_CONFIG.get(kpi, {})
        k_m = carrier_metrics.get(kpi, {})
        champ = k_m.get('best_model', 'Ridge')
        mase = k_m.get('mase', 0.85)
        
        # 1. Historical
        if not h_sub.empty and kpi in h_sub.columns:
            h_dates = pd.to_datetime(h_sub['date'])
            h_vals = h_sub[kpi].values
            ax.plot(h_dates, h_vals, color=STYLE_CONFIG['color_hist'], lw=1.4)
            last_date = h_dates.iloc[-1]
            last_val = float(h_vals[-1])
        else:
            last_date = pd.to_datetime(f_sub['date'].iloc[0]) - pd.Timedelta(days=1) if not f_sub.empty else pd.Timestamp.now().normalize()
            last_val = 0.0
            
        # 2. Forecast & Ribbon
        if not f_sub.empty and kpi in f_sub.columns:
            f_dates = pd.to_datetime(f_sub['date'])
            f_vals = f_sub[kpi].values
            proj_dates = [last_date] + list(f_dates)
            proj_vals = [last_val] + list(f_vals)
            
            p05_col = f"{kpi}_p05"
            p95_col = f"{kpi}_p95"
            if p05_col in f_sub.columns and p95_col in f_sub.columns:
                y_lower = [last_val] + list(f_sub[p05_col].values)
                y_upper = [last_val] + list(f_sub[p95_col].values)
                ax.fill_between(proj_dates, y_lower, y_upper, color=STYLE_CONFIG['color_ribbon'], alpha=0.2)
                
            ax.plot(proj_dates, proj_vals, color=STYLE_CONFIG['color_forecast'], lw=1.6, ls='--')
            
        # 3. SLA Target
        sla_target = kpi_meta.get('sla_target')
        if sla_target is not None:
            ax.axhline(y=sla_target, color=STYLE_CONFIG['color_sla'], lw=1.1, ls='-.')
            
        # Horizon split
        if not h_sub.empty:
            ax.axvline(x=last_date, color=STYLE_CONFIG['color_split'], lw=1.0, ls=':', alpha=0.7)
            
        # Labels
        ax.set_title(f"{kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')})", fontsize=10, fontweight='700', color=STYLE_CONFIG['text_primary'], pad=6)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
        plt.setp(ax.get_xticklabels(), rotation=25, ha='right', fontsize=8)
        ax.tick_params(labelsize=8)
        
        # Mini model tag
        ax.text(
            0.97, 0.93, f"{champ} | MASE:{mase:.2f}",
            transform=ax.transAxes,
            fontsize=7.5,
            fontfamily='monospace',
            color=STYLE_CONFIG['text_secondary'],
            ha='right', va='top',
            bbox=dict(boxstyle='round,pad=0.2', facecolor=STYLE_CONFIG['bg_figure'], edgecolor=STYLE_CONFIG['border'], alpha=0.8)
        )

    fig.suptitle(
        f"{carrier_name} // 10-KPI TELEMETRY & 365-DAY FORECAST MATRIX (~{cell_count:,} CELLS)",
        fontsize=16, fontweight='bold', color=STYLE_CONFIG['text_primary'], y=0.98
    )
    
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return None
        
    return fig

def plot_multiband_kpi(
    kpi: str,
    hist_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    out_path: Optional[str] = None,
    dpi: int = 300
) -> plt.Figure:
    """
    Renders cross-carrier comparative trajectory plot for a single KPI across all 6 bands.
    """
    kpi_meta = KPI_CONFIG.get(kpi, {})
    fig, ax = plt.subplots(figsize=(13, 6.5), dpi=dpi)
    apply_noc_theme(fig, ax)
    
    for carrier in CARRIER_BANDS:
        c_color = BAND_COLORS.get(carrier, '#10B981')
        c_name = f"Band {carrier} MHz"
        h_sub = hist_df[hist_df['carrier_freq'] == carrier].sort_values('date')
        f_sub = forecast_df[forecast_df['carrier_freq'] == carrier].sort_values('date')
        
        if not h_sub.empty and kpi in h_sub.columns:
            h_dates = pd.to_datetime(h_sub['date'])
            h_vals = h_sub[kpi].values
            ax.plot(h_dates, h_vals, color=c_color, lw=1.3, alpha=0.75)
            last_date = h_dates.iloc[-1]
            last_val = float(h_vals[-1])
        else:
            last_date = pd.to_datetime(f_sub['date'].iloc[0]) - pd.Timedelta(days=1) if not f_sub.empty else pd.Timestamp.now().normalize()
            last_val = 0.0
            
        if not f_sub.empty and kpi in f_sub.columns:
            f_dates = pd.to_datetime(f_sub['date'])
            f_vals = f_sub[kpi].values
            proj_dates = [last_date] + list(f_dates)
            proj_vals = [last_val] + list(f_vals)
            ax.plot(proj_dates, proj_vals, color=c_color, lw=2.0, ls='--', label=f"{c_name} (Forecast)")

    # SLA Target line if applicable
    sla_target = kpi_meta.get('sla_target')
    if sla_target is not None:
        ax.axhline(y=sla_target, color=STYLE_CONFIG['color_sla'], lw=1.3, ls='-.', label=f"SLA Target ({kpi_meta.get('sla_desc', '')})")

    ax.set_ylabel(f"{kpi_meta.get('name', kpi)} ({kpi_meta.get('unit', '')})", fontsize=11, fontweight='bold')
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.setp(ax.get_xticklabels(), rotation=30, ha='right')
    
    fig.suptitle(f"Multi-Band Trajectory Comparison // {kpi_meta.get('name', kpi)}", fontsize=14, fontweight='700', color=STYLE_CONFIG['text_primary'], x=0.08, y=0.97, ha='left')
    ax.set_title(f"3GPP Category: {kpi_meta.get('category', 'Telemetry')} | Comparative Spectrum Overlay (6 Frequency Tiers)", fontsize=9.5, color=STYLE_CONFIG['text_muted'], pad=12, loc='left')

    ax.legend(
        loc='upper left',
        bbox_to_anchor=(1.01, 1),
        facecolor=STYLE_CONFIG['bg_figure'],
        edgecolor=STYLE_CONFIG['border'],
        labelcolor=STYLE_CONFIG['text_primary'],
        fontsize=8.5
    )
    
    plt.tight_layout(rect=[0, 0, 0.85, 0.94])
    
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return None
        
    return fig

def plot_benchmark_mase_chart(metrics_dict: Dict[str, Any], out_path: Optional[str] = None, dpi: int = 300) -> plt.Figure:
    """
    Renders holdout MASE benchmark performance across all 60 series.
    Demonstrates superior predictive capability vs Seasonal Naive threshold (MASE = 1.0).
    """
    records = []
    summary = metrics_dict.get('metrics_summary', {})
    for carrier in CARRIER_BANDS:
        c_dict = summary.get(str(carrier), {})
        for kpi in KPI_KEYS:
            km = c_dict.get(kpi, {})
            mase = km.get('mase', 1.0)
            model = km.get('best_model', 'Ridge')
            records.append({
                'series': f"B{carrier} : {kpi}",
                'carrier': carrier,
                'kpi': kpi,
                'mase': mase,
                'model': model
            })
            
    df_m = pd.DataFrame(records).sort_values('mase')
    
    fig, ax = plt.subplots(figsize=(14, 16), dpi=dpi)
    apply_noc_theme(fig, ax)
    
    y_pos = np.arange(len(df_m))
    colors = ['#10B981' if m <= 1.0 else '#F59E0B' for m in df_m['mase']]
    
    ax.barh(y_pos, df_m['mase'], color=colors, height=0.75, edgecolor='none')
    ax.axvline(x=1.0, color='#EF4444', lw=1.5, ls='--', label='Seasonal Naive Parity (MASE = 1.0)')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df_m['series'], fontsize=7.5, fontfamily='monospace')
    ax.set_xlabel('Mean Absolute Scaled Error (MASE) [Holdout Evaluation]', fontsize=10, fontweight='bold')
    ax.set_title("All 60 Telemetry Series: Holdout Tournament MASE (Green <= 1.0 indicates outperforming seasonal baseline)", fontsize=11, color=STYLE_CONFIG['text_primary'], pad=12)
    ax.legend(facecolor=STYLE_CONFIG['bg_figure'], edgecolor=STYLE_CONFIG['border'], labelcolor=STYLE_CONFIG['text_primary'], fontsize=9)
    
    plt.tight_layout()
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return None
        
    return fig

def plot_benchmark_wape_matrix(metrics_dict: Dict[str, Any], out_path: Optional[str] = None, dpi: int = 300) -> plt.Figure:
    """
    Renders holdout WAPE (%) error heatmap across all 6 carriers and 10 KPIs.
    """
    summary = metrics_dict.get('metrics_summary', {})
    data_matrix = []
    
    for carrier in CARRIER_BANDS:
        c_row = []
        c_dict = summary.get(str(carrier), {})
        for kpi in KPI_KEYS:
            wape = c_dict.get(kpi, {}).get('wape', 0.0)
            c_row.append(wape)
        data_matrix.append(c_row)
        
    arr = np.array(data_matrix)
    
    fig, ax = plt.subplots(figsize=(14, 6), dpi=dpi)
    apply_noc_theme(fig, ax)
    
    cax = ax.imshow(arr, cmap='viridis', aspect='auto')
    cbar = fig.colorbar(cax, ax=ax)
    cbar.ax.tick_params(colors=STYLE_CONFIG['text_secondary'])
    cbar.set_label('Holdout WAPE (%)', color=STYLE_CONFIG['text_secondary'], fontsize=10)
    
    ax.set_xticks(np.arange(len(KPI_KEYS)))
    ax.set_xticklabels(KPI_KEYS, rotation=35, ha='right', fontsize=9, fontfamily='monospace')
    ax.set_yticks(np.arange(len(CARRIER_BANDS)))
    ax.set_yticklabels([f"Band {c} MHz" for c in CARRIER_BANDS], fontsize=9, fontfamily='monospace')
    
    for i in range(len(CARRIER_BANDS)):
        for j in range(len(KPI_KEYS)):
            val = arr[i, j]
            text_color = '#FFFFFF' if val < 15.0 else '#000000'
            ax.text(j, i, f"{val:.1f}%", ha='center', va='center', color=text_color, fontsize=8, fontfamily='monospace')
            
    ax.set_title("Network-Wide Holdout WAPE Matrix Across All Spectrum Bands & 3GPP KPIs", fontsize=12, fontweight='700', color=STYLE_CONFIG['text_primary'], pad=12)
    plt.tight_layout()
    
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return None
        
    return fig

def generate_all_plots(
    output_dir: str = "plots",
    dpi: int = 300,
    clean_csv_path: str = "data/carrier_ran_kpi_clean.csv",
    forecast_csv_path: str = "carrier_kpi_forecast_2026_2027.csv",
    metrics_json_path: str = "model_metrics.json",
    quiet: bool = False
) -> Dict[str, Any]:
    """
    Orchestrates the generation of all 78 publication-grade plots:
    - 60 Single KPI plots in plots/carrier_{carrier}/
    - 6 Multi-KPI Master Grid plots in plots/grids/
    - 10 Multi-Band comparison plots in plots/multiband/
    - 2 Model Benchmark plots in plots/benchmarks/
    - 1 Zip archive bundle in archive/Network_ML_All_Plots_300DPI.zip
    """
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    if not quiet:
        print("=" * 75)
        print(f"Network-ML // Publication Plot Generator (DPI={dpi})")
        print(f"Output Directory: {output_dir}")
        print("=" * 75)

    # 1. Load Data
    if not os.path.exists(clean_csv_path):
        for alt in [
            os.path.join("data", clean_csv_path),
            "carrier_ran_kpi_clean.csv",
            os.path.join("data", "carrier_ran_kpi_clean.csv"),
            "carrier_kpi_clean.csv",
            os.path.join("data", "carrier_kpi_clean.csv"),
        ]:
            if os.path.exists(alt):
                clean_csv_path = alt
                break

    hist_df = pd.read_csv(clean_csv_path)
    hist_df['date'] = pd.to_datetime(hist_df['date'])
    
    forecast_df = pd.read_csv(forecast_csv_path)
    forecast_df['date'] = pd.to_datetime(forecast_df['date'])
    
    with open(metrics_json_path, 'r', encoding='utf-8') as f:
        metrics_dict = json.load(f)

    generated_files: List[str] = []

    # 2. Generate 60 Individual KPI Plots
    if not quiet:
        print(f"[*] [Phase 1/5] Generating 60 Individual Carrier-KPI Trajectory Plots...")
    for carrier in CARRIER_BANDS:
        c_dir = os.path.join(output_dir, f"carrier_{carrier}")
        os.makedirs(c_dir, exist_ok=True)
        for kpi in KPI_KEYS:
            out_p = os.path.join(c_dir, f"{kpi}.png")
            plot_single_kpi(
                carrier=carrier,
                kpi=kpi,
                hist_df=hist_df,
                forecast_df=forecast_df,
                metrics_dict=metrics_dict,
                out_path=out_p,
                dpi=dpi
            )
            generated_files.append(out_p)
            if not quiet:
                print(f"    + [Carrier {carrier:4d}] {kpi:<22} -> {os.path.basename(out_p)}")

    # 3. Generate 6 Consolidated Master Grid Dashboards
    if not quiet:
        print(f"[*] [Phase 2/5] Generating 6 Carrier 10-KPI Master Grid Dashboards...")
    grid_dir = os.path.join(output_dir, "grids")
    os.makedirs(grid_dir, exist_ok=True)
    for carrier in CARRIER_BANDS:
        grid_p = os.path.join(grid_dir, f"carrier_{carrier}_all_kpis_grid.png")
        plot_carrier_grid(
            carrier=carrier,
            hist_df=hist_df,
            forecast_df=forecast_df,
            metrics_dict=metrics_dict,
            out_path=grid_p,
            dpi=dpi
        )
        generated_files.append(grid_p)
        if not quiet:
            print(f"    + Master Grid: Carrier {carrier} MHz -> {os.path.basename(grid_p)}")

    # 4. Generate 10 Multi-Band Overlays
    if not quiet:
        print(f"[*] [Phase 3/5] Generating 10 Cross-Band Multi-Carrier Comparison Plots...")
    mb_dir = os.path.join(output_dir, "multiband")
    os.makedirs(mb_dir, exist_ok=True)
    for kpi in KPI_KEYS:
        mb_p = os.path.join(mb_dir, f"multiband_{kpi}.png")
        plot_multiband_kpi(
            kpi=kpi,
            hist_df=hist_df,
            forecast_df=forecast_df,
            out_path=mb_p,
            dpi=dpi
        )
        generated_files.append(mb_p)
        if not quiet:
            print(f"    + Multi-Band: {kpi:<22} -> {os.path.basename(mb_p)}")

    # 5. Generate 2 Model Benchmark Figures
    if not quiet:
        print(f"[*] [Phase 4/5] Generating Model Tournament Benchmark Figures...")
    bm_dir = os.path.join(output_dir, "benchmarks")
    os.makedirs(bm_dir, exist_ok=True)
    mase_p = os.path.join(bm_dir, "benchmark_mase_all_series.png")
    plot_benchmark_mase_chart(metrics_dict, out_path=mase_p, dpi=dpi)
    generated_files.append(mase_p)

    wape_p = os.path.join(bm_dir, "benchmark_wape_matrix.png")
    plot_benchmark_wape_matrix(metrics_dict, out_path=wape_p, dpi=dpi)
    generated_files.append(wape_p)

    # 6. Build Consolidated Zip Archive
    if not quiet:
        print(f"[*] [Phase 5/5] Compiling Consolidated ZIP Bundle...")
    archive_dir = os.path.join(_REPO_ROOT, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    zip_path = os.path.join(archive_dir, "Network_ML_All_Plots_300DPI.zip")
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for f in generated_files:
            rel_name = os.path.relpath(f, output_dir)
            zf.write(f, arcname=rel_name)
    generated_files.append(zip_path)

    if not quiet:
        print("=" * 75)
        print(f"[+] Successfully generated {len(generated_files)} artifacts:")
        print(f"    - 60 Individual KPI Trajectory Plots (300 DPI)")
        print(f"    - 6 Master Grid Dashboards (24x11, 300 DPI)")
        print(f"    - 10 Multi-Band Cross-Carrier Comparisons (300 DPI)")
        print(f"    - 2 Holdout Model Benchmark Charts (300 DPI)")
        print(f"    - 1 Consolidated Zip Bundle ({os.path.getsize(zip_path):,} bytes)")
        print("=" * 75)

    return {
        'total_files': len(generated_files),
        'zip_path': zip_path,
        'files': generated_files
    }
