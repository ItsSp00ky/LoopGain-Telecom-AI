"""
Prepares optimized JSON data for the interactive visual web dashboard.
Generates network aggregations and pre-computes site-level time-series
for representative towers.
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DATA_PATH = os.path.join(PROJECT_DIR, "forecasts", "tower_level_forecast_predictions.csv")
DASHBOARD_DIR = os.path.join(PROJECT_DIR, "dashboard")
DATA_OUT_DIR = os.path.join(DASHBOARD_DIR, "data")
os.makedirs(DATA_OUT_DIR, exist_ok=True)

KPI_MAP = {
    'connected_users': {
        'actual': 'Avg RRC Connected users (Actual)',
        'pred': 'Avg RRC Connected users (Predicted)',
        'unit': 'users',
        'agg': 'sum'
    },
    'dl_throughput': {
        'actual': 'E-UTRAN IP Throughput UE DL (Actual)',
        'pred': 'E-UTRAN IP Throughput UE DL (Predicted)',
        'unit': 'Mbps',
        'agg': 'mean'
    },
    'cell_availability': {
        'actual': '4G Cell Av. (%) (Actual)',
        'pred': '4G Cell Av. (%) (Predicted)',
        'unit': '%',
        'agg': 'mean'
    },
    'drop_rate': {
        'actual': 'E-RAB Drop Rate (Actual)',
        'pred': 'E-RAB Drop Rate (Predicted)',
        'unit': '%',
        'agg': 'mean'
    }
}

def calculate_metrics(y_true, y_pred, is_pct=False):
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = float(r2_score(y_true, y_pred))
    
    # Avoid zero division in MAPE
    denom = np.where(np.abs(y_true) < 1e-4, np.nan, y_true)
    mape = float(np.nanmean(np.abs((y_true - y_pred) / denom)) * 100) if not np.all(np.isnan(denom)) else 0.0
    return {
        'mae': round(mae, 4),
        'rmse': round(rmse, 4),
        'r2': round(r2, 4),
        'mape': round(mape, 2)
    }

def build_dashboard_data():
    print(f"Reading predictions from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    
    dates = sorted(df['Date'].unique().tolist())
    all_towers = sorted(df['ERBS Id'].unique().tolist())
    print(f"Total Towers: {len(all_towers)}, Total Dates: {len(dates)}")
    
    # 1. Network Aggregations
    print("Computing network-wide aggregates...")
    network_data = {}
    for kpi_key, cfg in KPI_MAP.items():
        act_col = cfg['actual']
        prd_col = cfg['pred']
        agg_func = cfg['agg']
        
        net_agg = df.groupby('Date')[[act_col, prd_col]].agg(agg_func).reset_index()
        net_agg = net_agg.sort_values('Date')
        
        y_act = net_agg[act_col].round(3).values
        y_prd = net_agg[prd_col].round(3).values
        
        metrics = calculate_metrics(y_act, y_prd, is_pct='%' in cfg['unit'])
        network_data[kpi_key] = {
            'actual': y_act.tolist(),
            'pred': y_prd.tolist(),
            'metrics': metrics,
            'unit': cfg['unit']
        }
        
    # 2. Select Representative Towers + Top Volume Towers
    tower_user_avg = df.groupby('ERBS Id')['Avg RRC Connected users (Actual)'].mean().to_dict()
    # Sort towers by volume
    sorted_by_vol = sorted(tower_user_avg.items(), key=lambda x: x[1], reverse=True)
    top_volume_towers = [t[0] for t in sorted_by_vol[:30]]
    
    # Representative sample
    preset_towers = ['TWR_0001', 'TWR_0002', 'TWR_0003', 'TWR_0004', 'TWR_0005', 
                     'TWR_0007', 'TWR_0008', 'TWR_0009', 'TWR_0010', 'TWR_0015',
                     'TWR_0020', 'TWR_0033', 'TWR_0050', 'TWR_0100', 'TWR_0250', 
                     'TWR_0500', 'TWR_0750', 'TWR_1000']
                     
    selected_towers = sorted(list(set(preset_towers + top_volume_towers)))
    selected_towers = [t for t in selected_towers if t in all_towers]
    
    print(f"Pre-packaging {len(selected_towers)} featured towers into bundle...")
    towers_data = {}
    for tid in selected_towers:
        t_df = df[df['ERBS Id'] == tid].sort_values('Date').copy()
        t_entry = {'kpis': {}, 'avg_users': round(float(tower_user_avg.get(tid, 0)), 2)}
        for kpi_key, cfg in KPI_MAP.items():
            act_col = cfg['actual']
            prd_col = cfg['pred']
            y_act = t_df[act_col].round(3).values
            y_prd = t_df[prd_col].round(3).values
            metrics = calculate_metrics(y_act, y_prd, is_pct='%' in cfg['unit'])
            t_entry['kpis'][kpi_key] = {
                'actual': y_act.tolist(),
                'pred': y_prd.tolist(),
                'metrics': metrics
            }
        towers_data[tid] = t_entry
        
    tower_metadata = [
        {'id': tid, 'avg_users': round(float(tower_user_avg.get(tid, 0)), 2), 'is_featured': tid in towers_data}
        for tid in all_towers
    ]
    
    output_payload = {
        'dates': dates,
        'network': network_data,
        'featured_towers': towers_data,
        'all_towers': tower_metadata,
        'summary': {
            'total_towers': len(all_towers),
            'total_days': len(dates),
            'start_date': dates[0],
            'end_date': dates[-1]
        }
    }
    
    out_file = os.path.join(DATA_OUT_DIR, "forecast_dashboard_data.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, separators=(',', ':'))
        
    file_size_kb = os.path.getsize(out_file) / 1024
    print(f"Saved optimized dashboard payload to {out_file} ({file_size_kb:.1f} KB)")
    
    # Also write a JS file with data variable for instant zero-CORS browser viewing
    js_out_file = os.path.join(DATA_OUT_DIR, "forecast_data.js")
    with open(js_out_file, 'w', encoding='utf-8') as f:
        f.write("window.FORECAST_DASHBOARD_DATA = ")
        json.dump(output_payload, f, separators=(',', ':'))
        f.write(";\n")
    print(f"Saved zero-CORS JS bundle to {js_out_file}")

if __name__ == '__main__':
    build_dashboard_data()
