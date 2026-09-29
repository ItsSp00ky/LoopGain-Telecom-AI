"""
Interactive Dashboard Local Web Server with Dynamic API.
Serves the frontend dashboard and provides live endpoints for all 1,060 towers.
"""

import os
import sys
import json
import webbrowser
from http.server import SimpleHTTPRequestHandler, HTTPServer
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DASHBOARD_DIR = os.path.join(PROJECT_DIR, "dashboard")
DATA_PATH = os.path.join(PROJECT_DIR, "forecasts", "tower_level_forecast_predictions.csv")

PORT = 8050
_PREDICTIONS_DF = None

KPI_CONFIG = {
    'connected_users': ('Avg RRC Connected users (Actual)', 'Avg RRC Connected users (Predicted)'),
    'dl_throughput': ('E-UTRAN IP Throughput UE DL (Actual)', 'E-UTRAN IP Throughput UE DL (Predicted)'),
    'cell_availability': ('4G Cell Av. (%) (Actual)', '4G Cell Av. (%) (Predicted)'),
    'drop_rate': ('E-RAB Drop Rate (Actual)', 'E-RAB Drop Rate (Predicted)')
}

def get_df():
    global _PREDICTIONS_DF
    if _PREDICTIONS_DF is None:
        print("Loading full predictions dataset into memory for sub-millisecond queries...")
        _PREDICTIONS_DF = pd.read_csv(DATA_PATH)
    return _PREDICTIONS_DF

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith('/api/tower/'):
            tower_id = self.path.replace('/api/tower/', '').split('?')[0].strip()
            self.handle_tower_request(tower_id)
        else:
            super().do_GET()

    def handle_tower_request(self, tower_id: str):
        df = get_df()
        t_df = df[df['ERBS Id'] == tower_id].sort_values('Date')
        
        if t_df.empty:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f"Tower {tower_id} not found"}).encode('utf-8'))
            return

        result = {'id': tower_id, 'dates': t_df['Date'].tolist(), 'kpis': {}}
        for kpi_key, (act_col, prd_col) in KPI_CONFIG.items():
            y_act = t_df[act_col].round(3).values
            y_prd = t_df[prd_col].round(3).values
            
            mae = float(mean_absolute_error(y_act, y_prd))
            rmse = float(np.sqrt(mean_squared_error(y_act, y_prd)))
            r2 = float(r2_score(y_act, y_prd))
            denom = np.where(np.abs(y_act) < 1e-4, np.nan, y_act)
            mape = float(np.nanmean(np.abs((y_act - y_prd) / denom)) * 100) if not np.all(np.isnan(denom)) else 0.0

            result['kpis'][kpi_key] = {
                'actual': y_act.tolist(),
                'pred': y_prd.tolist(),
                'metrics': {
                    'mae': round(mae, 4),
                    'rmse': round(rmse, 4),
                    'r2': round(r2, 4),
                    'mape': round(mape, 2)
                }
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode('utf-8'))

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    get_df()  # Pre-warm cache
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, DashboardHandler)
    url = f"http://localhost:{PORT}/index.html"
    print("=" * 65)
    print(f"[OK] 4G LTE Forecasting Interactive Visual Dashboard is LIVE!")
    print(f"--> Local URL: {url}")
    print(f"--> Serving 1,060 Cell Towers with Sub-Millisecond Dynamic Queries")
    print("=" * 65)
    
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        httpd.server_close()

if __name__ == '__main__':
    main()
