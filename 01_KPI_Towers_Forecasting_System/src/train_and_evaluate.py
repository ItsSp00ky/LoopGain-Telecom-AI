import os
import json
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from data_loader import CellularDataLoader
from feature_engineering import TimeSeriesFeatureEngineer

# Configure directories
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DATA_PATH = os.path.join(PROJECT_DIR, "data", "Data_Cleaned.csv")
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
FORECASTS_DIR = os.path.join(PROJECT_DIR, "forecasts")

TARGET_CONFIGS = [
    {'target': 'Avg RRC Connected users', 'prefix': 'connected_users', 'unit': 'users', 'agg': 'sum'},
    {'target': 'E-UTRAN IP Throughput UE DL', 'prefix': 'dl_throughput', 'unit': 'Mbps', 'agg': 'mean'},
    {'target': '4G Cell Av. (%)', 'prefix': 'cell_availability', 'unit': '%', 'agg': 'mean'},
    {'target': 'E-RAB Drop Rate', 'prefix': 'drop_rate', 'unit': '%', 'agg': 'mean'}
]

def run_pipeline():
    print("=" * 70)
    print("4G LTE KPI Forecasting Pipeline – Training & Evaluation")
    print("=" * 70)
    
    loader = CellularDataLoader(DATA_PATH)
    df = loader.load_data()
    _, _, cutoff_date = loader.temporal_train_test_split(df, train_ratio=0.70)
    
    df, base_calendar_feats = TimeSeriesFeatureEngineer.add_calendar_features(df)
    
    metrics_summary = {}
    master_preds = df[df['Date'] >= cutoff_date][['Date', 'ERBS Id']].copy().reset_index(drop=True)
    all_importances = []
    
    for cfg in TARGET_CONFIGS:
        target = cfg['target']
        prefix = cfg['prefix']
        unit = cfg['unit']
        agg_func = cfg['agg']
        
        print(f"\n>>> Training Model for KPI: {target} ({unit})")
        df, kpi_feats = TimeSeriesFeatureEngineer.add_temporal_kpi_features(df, target, prefix, cutoff_date)
        model_features = base_calendar_feats + kpi_feats
        
        # Prepare Train / Test Splits (warmup excluded via lag_28 notna)
        train_mask = (df['Date'] < cutoff_date) & (df[f"{prefix}_lag_28"].notna())
        test_mask = (df['Date'] >= cutoff_date)
        
        X_train, y_train = df.loc[train_mask, model_features], df.loc[train_mask, target]
        X_test, y_test = df.loc[test_mask, model_features], df.loc[test_mask, target]
        
        # Train XGBoost
        model = xgb.XGBRegressor(
            n_estimators=350,
            max_depth=6,
            learning_rate=0.07,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method='hist',
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)
        
        # Predict & post-process
        preds = model.predict(X_test)
        if '%' in unit:
            preds = np.clip(preds, 0.0, 100.0)
        else:
            preds = np.clip(preds, 0.0, None)
        preds = np.round(preds, 3)
        
        # Site-level metrics
        site_rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        site_mae = float(mean_absolute_error(y_test, preds))
        site_r2 = float(r2_score(y_test, preds))
        
        # Network-level aggregation
        eval_df = df.loc[test_mask, ['Date', target]].copy()
        eval_df['pred'] = preds
        net_agg = eval_df.groupby('Date')[[target, 'pred']].agg(agg_func)
        net_rmse = float(np.sqrt(mean_squared_error(net_agg[target], net_agg['pred'])))
        net_mae = float(mean_absolute_error(net_agg[target], net_agg['pred']))
        net_r2 = float(r2_score(net_agg[target], net_agg['pred']))
        net_mape = float(np.mean(np.abs((net_agg[target] - net_agg['pred']) / net_agg[target])) * 100)
        
        print(f"  [Site-Level]    R²: {site_r2:.4f} | MAE: {site_mae:.3f} {unit} | RMSE: {site_rmse:.3f} {unit}")
        print(f"  [Network-Level] R²: {net_r2:.4f} | MAPE: {net_mape:.2f}% | MAE: {net_mae:.3f} {unit}")
        
        # Save checkpoints
        model.save_model(os.path.join(MODELS_DIR, f"xgb_{prefix}.json"))
        joblib.dump(model, os.path.join(MODELS_DIR, f"xgb_{prefix}.joblib"))
        
        # Feature importances
        for feat, imp in zip(model_features, model.feature_importances_):
            all_importances.append({'kpi': prefix, 'feature': feat, 'importance': imp})
            
        master_preds[f"{target} (Actual)"] = y_test.values
        master_preds[f"{target} (Predicted)"] = preds
        
        metrics_summary[prefix] = {
            'target': target,
            'unit': unit,
            'site_metrics': {'r2': site_r2, 'mae': site_mae, 'rmse': site_rmse},
            'network_metrics': {'r2': net_r2, 'mape': net_mape, 'mae': net_mae, 'rmse': net_rmse}
        }
        
    # Save artifacts
    pd.DataFrame(all_importances).to_csv(os.path.join(MODELS_DIR, "feature_importance.csv"), index=False)
    master_preds.to_csv(os.path.join(FORECASTS_DIR, "tower_level_forecast_predictions.csv"), index=False)
    with open(os.path.join(FORECASTS_DIR, "model_evaluation_metrics.json"), 'w') as f:
        json.dump(metrics_summary, f, indent=4)
        
    print("\n>>> Pipeline Execution Complete. All models and artifacts saved successfully.")

if __name__ == '__main__':
    run_pipeline()
