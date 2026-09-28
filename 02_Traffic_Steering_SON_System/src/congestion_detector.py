import numpy as np
import pandas as pd
from typing import Tuple

class CongestionDetector:
    """
    Automated Congestion Detection & Risk Scoring Engine for 4G LTE Cell Towers.
    Combines traffic volume, downlink throughput degradation, and drop rate into a standardized 0-100 score.
    """
    
    def __init__(self, capacity_quantile: float = 0.95, min_capacity: float = 15.0):
        self.capacity_quantile = capacity_quantile
        self.min_capacity = min_capacity
        
    def fit_capacity_ceilings(self, historical_df: pd.DataFrame) -> pd.DataFrame:
        """Computes dynamic physical capacity ceilings per tower based on historical traffic peaks."""
        cap = historical_df.groupby('ERBS Id')['Avg RRC Connected users'].quantile(self.capacity_quantile).reset_index()
        cap.columns = ['ERBS Id', 'Capacity_95th']
        cap['Capacity_95th'] = cap['Capacity_95th'].clip(lower=self.min_capacity)
        return cap

    def calculate_congestion_scores(self, forecast_df: pd.DataFrame, capacity_df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes the Congestion Risk Index (CRI) and assigns severity tiers.
        Formula: 50% Load Factor + 40% Speed Deficit + 10% Session Drop Risk.
        """
        df = forecast_df.merge(capacity_df, on='ERBS Id', how='left')
        
        u_pred = df['Avg RRC Connected users (Predicted)']
        dl_pred = df['E-UTRAN IP Throughput UE DL (Predicted)']
        dr_pred = df['E-RAB Drop Rate (Predicted)']
        cap = df['Capacity_95th']
        
        df['Load_Factor'] = (u_pred / cap).round(3)
        df['Headroom'] = (cap - u_pred).round(2)
        
        # Component Risk Scores (Normalized 0-100)
        load_score = np.clip(df['Load_Factor'] * 100, 0, 100)
        speed_score = np.clip((15.0 - dl_pred) / 15.0 * 100, 0, 100)
        drop_score = np.clip(dr_pred / 2.0 * 100, 0, 100)
        
        df['Congestion_Risk_Score'] = (0.50 * load_score + 0.40 * speed_score + 0.10 * drop_score).round(1)
        
        def assign_tier(row):
            if row['Congestion_Risk_Score'] >= 80.0 and row['E-UTRAN IP Throughput UE DL (Predicted)'] < 5.0:
                return 'CRITICAL'
            elif row['Congestion_Risk_Score'] >= 70.0 and row['E-UTRAN IP Throughput UE DL (Predicted)'] < 8.0:
                return 'HIGH'
            elif row['Congestion_Risk_Score'] >= 60.0:
                return 'MODERATE'
            else:
                return 'NORMAL'
                
        df['Congestion_Category'] = df.apply(assign_tier, axis=1)
        return df
