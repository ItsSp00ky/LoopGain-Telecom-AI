import pandas as pd
import numpy as np
import os
from typing import Tuple, List

class CellularDataLoader:
    """
    Production Data Loader for 4G LTE Cell Tower Operational KPIs.
    Handles data validation, chronological sorting, and temporal partitioning.
    """
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Cleaned dataset not found at: {data_path}")
            
    def load_data(self) -> pd.DataFrame:
        """Loads and formats the cleaned dataset."""
        df = pd.read_csv(self.data_path)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values(by=['ERBS Id', 'Date']).reset_index(drop=True)
        return df

    def temporal_train_test_split(
        self, df: pd.DataFrame, train_ratio: float = 0.70
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
        """
        Executes a leak-free chronological 70% Train / 30% Test split.
        """
        unique_dates = sorted(df['Date'].unique())
        train_days = int(len(unique_dates) * train_ratio)
        cutoff_date = unique_dates[train_days]
        
        train_df = df[df['Date'] < cutoff_date].copy()
        test_df = df[df['Date'] >= cutoff_date].copy()
        
        return train_df, test_df, cutoff_date
