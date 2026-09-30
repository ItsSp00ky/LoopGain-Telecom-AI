"""
Plotting and Visualization Utility for 4G LTE Cell Tower KPI Forecasts.
Generates publication-quality comparison plots (Actual vs Predicted)
for both countrywide aggregates and individual base stations.
"""

import os
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DATA_PATH = os.path.join(PROJECT_DIR, "forecasts", "tower_level_forecast_predictions.csv")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")

KPI_CONFIG = {
    'connected_users': {
        'name': 'Avg RRC Connected users',
        'unit': 'users',
        'color_actual': '#00bcd4',  # Cyan
        'color_pred': '#ff5722',    # Orange/Coral
        'title': 'Connected Users (Traffic Load & Capacity)',
    },
    'dl_throughput': {
        'name': 'E-UTRAN IP Throughput UE DL',
        'unit': 'Mbps',
        'color_actual': '#4caf50',  # Green
        'color_pred': '#e91e63',    # Pink/Magenta
        'title': 'Downlink Throughput (Speed & QoE)',
    },
    'cell_availability': {
        'name': '4G Cell Av. (%)',
        'unit': '%',
        'color_actual': '#2196f3',  # Blue
        'color_pred': '#ff9800',    # Amber
        'title': 'Cell Availability (Uptime & Hardware Health)',
    },
    'drop_rate': {
        'name': 'E-RAB Drop Rate',
        'unit': '%',
        'color_actual': '#9c27b0',  # Purple
        'color_pred': '#f44336',    # Red
        'title': 'E-RAB Drop Rate (Session Retention)',
    }
}

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['figure.autolayout'] = True


def load_forecast_data() -> pd.DataFrame:
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Predictions file not found at: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    df['Date'] = pd.to_datetime(df['Date'])
    return df


def plot_tower_kpi(df: pd.DataFrame, tower_id: str, kpi_key: str, output_path: str = None) -> str:
    """Plot Actual vs Predicted for a specific tower and specific KPI."""
    cfg = KPI_CONFIG[kpi_key]
    kpi_name = cfg['name']
    unit = cfg['unit']
    
    tower_df = df[df['ERBS Id'] == tower_id].sort_values('Date').copy()
    if tower_df.empty:
        raise ValueError(f"Tower '{tower_id}' not found in predictions dataset.")
        
    actual_col = f"{kpi_name} (Actual)"
    pred_col = f"{kpi_name} (Predicted)"
    
    y_true = tower_df[actual_col].values
    y_pred = tower_df[pred_col].values
    dates = tower_df['Date'].values
    
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    
    fig, (ax_main, ax_err) = plt.subplots(2, 1, figsize=(13, 7), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    fig.patch.set_facecolor('#0d1117')
    for ax in [ax_main, ax_err]:
        ax.set_facecolor('#161b22')
        ax.tick_params(colors='#c9d1d9')
        ax.grid(True, color='#30363d', linestyle='--', alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color('#30363d')
            
    # Main plot
    ax_main.plot(dates, y_true, label=f'Actual Ground Truth', color=cfg['color_actual'], linewidth=2.0, alpha=0.9)
    ax_main.plot(dates, y_pred, label=f'XGBoost Forecast', color=cfg['color_pred'], linewidth=2.0, linestyle='--', alpha=0.95)
    ax_main.fill_between(dates, y_true, y_pred, color=cfg['color_pred'], alpha=0.15, label='Residual Variance')
    
    ax_main.set_title(f"Cell Tower [{tower_id}] – {cfg['title']}\n"
                      f"Test Horizon: 109 Days | R²: {r2:.4f} | MAE: {mae:.3f} {unit} | RMSE: {rmse:.3f} {unit}",
                      fontsize=13, fontweight='bold', color='#f0f6fc', pad=12)
    ax_main.set_ylabel(f"{kpi_name} ({unit})", color='#f0f6fc', fontsize=11)
    ax_main.legend(facecolor='#21262d', edgecolor='#30363d', labelcolor='#f0f6fc', loc='upper right', framealpha=0.9)
    
    # Error / Residual Subplot
    residual = y_true - y_pred
    ax_err.bar(dates, residual, color='#f85149', alpha=0.6, width=0.8, label='Error (Actual - Predicted)')
    ax_err.axhline(0, color='#8b949e', linestyle='-', linewidth=1.0)
    ax_err.set_ylabel(f"Delta ({unit})", color='#f0f6fc', fontsize=9)
    ax_err.set_xlabel("Out-of-Time Chronological Test Date", color='#f0f6fc', fontsize=11, labelpad=8)
    ax_err.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax_err.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=20)
    
    if output_path is None:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        output_path = os.path.join(ASSETS_DIR, f"forecast_{tower_id}_{kpi_key}.png")
        
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    return output_path


def plot_tower_all_kpis(df: pd.DataFrame, tower_id: str, output_path: str = None) -> str:
    """Generates a 4-panel dashboard plot showing all 4 KPIs for a selected tower."""
    tower_df = df[df['ERBS Id'] == tower_id].sort_values('Date').copy()
    if tower_df.empty:
        raise ValueError(f"Tower '{tower_id}' not found.")
        
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.patch.set_facecolor('#0d1117')
    fig.suptitle(f"4G LTE Multi-KPI Performance Forecast: Tower [{tower_id}]\n109-Day Chronological Out-of-Time Horizon",
                 fontsize=15, fontweight='bold', color='#f0f6fc', y=0.98)
                 
    kpi_keys = ['connected_users', 'dl_throughput', 'cell_availability', 'drop_rate']
    dates = tower_df['Date'].values
    
    for ax, kpi_key in zip(axes.flatten(), kpi_keys):
        cfg = KPI_CONFIG[kpi_key]
        kpi_name = cfg['name']
        unit = cfg['unit']
        
        ax.set_facecolor('#161b22')
        ax.tick_params(colors='#c9d1d9')
        ax.grid(True, color='#30363d', linestyle='--', alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color('#30363d')
            
        y_true = tower_df[f"{kpi_name} (Actual)"].values
        y_pred = tower_df[f"{kpi_name} (Predicted)"].values
        
        mae = mean_absolute_error(y_true, y_pred)
        r2 = r2_score(y_true, y_pred)
        
        ax.plot(dates, y_true, label='Actual', color=cfg['color_actual'], linewidth=2.0, alpha=0.9)
        ax.plot(dates, y_pred, label='Forecast', color=cfg['color_pred'], linewidth=2.0, linestyle='--', alpha=0.95)
        ax.fill_between(dates, y_true, y_pred, color=cfg['color_pred'], alpha=0.15)
        
        ax.set_title(f"{cfg['title']}\nR² = {r2:.4f} | MAE = {mae:.3f} {unit}", fontsize=11, fontweight='bold', color='#f0f6fc', pad=8)
        ax.set_ylabel(unit, color='#c9d1d9', fontsize=10)
        ax.legend(facecolor='#21262d', edgecolor='#30363d', labelcolor='#f0f6fc', loc='upper right', fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
        plt.setp(ax.get_xticklabels(), rotation=20, ha='right')

    plt.tight_layout(rect=[0, 0.03, 1, 0.94])
    
    if output_path is None:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        output_path = os.path.join(ASSETS_DIR, f"multi_kpi_forecast_{tower_id}.png")
        
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate Visual Forecast Graphs for Cell Towers")
    parser.add_argument("--tower", type=str, default="TWR_0001", help="Target Tower ID (e.g. TWR_0001)")
    parser.add_argument("--kpi", type=str, default="all", choices=['all', 'connected_users', 'dl_throughput', 'cell_availability', 'drop_rate'])
    parser.add_argument("--output", type=str, default=None, help="Custom output image path")
    args = parser.parse_args()
    
    print(f"Loading predictions data from {DATA_PATH}...")
    df = load_forecast_data()
    
    if args.kpi == 'all':
        print(f"Generating 4-panel multi-KPI plot for tower: {args.tower}...")
        out = plot_tower_all_kpis(df, args.tower, args.output)
        print(f"Successfully saved plot to: {out}")
    else:
        print(f"Generating {args.kpi} plot for tower: {args.tower}...")
        out = plot_tower_kpi(df, args.tower, args.kpi, args.output)
        print(f"Successfully saved plot to: {out}")


if __name__ == '__main__':
    main()
