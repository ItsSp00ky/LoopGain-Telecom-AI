"""models.py: Multi-model training, benchmarking, evaluation, and future forecasting for KPI prediction.
Includes:
- Seasonal Naive (t-7 baseline)
- Ridge Regression (linear baseline)
- Random Forest Regressor
- XGBoost Regressor (tuned)
Also provides recursive multi-step future forecasting with prediction intervals.
"""

from typing import Any
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Computes standard time-series evaluation metrics: MAE, RMSE, WAPE, MAPE, R2."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    wape = float(np.sum(np.abs(y_true - y_pred)) / (np.sum(np.abs(y_true)) + 1e-8)) * 100.0
    mape = float(np.mean(np.abs((y_true - y_pred) / (y_true + 1e-8)))) * 100.0
    r2 = float(r2_score(y_true, y_pred))

    return {
        "MAE": mae,
        "RMSE": rmse,
        "WAPE (%)": wape,
        "MAPE (%)": mape,
        "R2": r2,
    }


class SeasonalNaiveModel:
    """Predicts observation at t using the observation at t-7 (same day last week)."""

    def __init__(self, lag: int = 7):
        self.lag = lag

    def fit(self, X: Any, y: Any) -> "SeasonalNaiveModel":
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if f"lag_{self.lag}" in df.columns:
            return df[f"lag_{self.lag}"].values
        raise ValueError(f"Feature lag_{self.lag} required for SeasonalNaiveModel")


def train_and_benchmark(datasets: dict, feature_cols: list[str]) -> tuple[dict, pd.DataFrame, str]:
    """Trains multiple candidate models, evaluates them on Validation and Test sets,

    and logs comprehensive performance comparisons.
    """
    print("=" * 60)
    print("STEP 3: MULTI-MODEL BENCHMARKING & TRAINING")
    print("=" * 60)

    train = datasets["train"]
    val = datasets["val"]
    test = datasets["test"]

    # Candidate models definition
    models: dict[str, Any] = {
        "Seasonal Naive (t-7)": SeasonalNaiveModel(lag=7),
        "Ridge Regression": Ridge(alpha=10.0),
        "Random Forest": RandomForestRegressor(
            n_estimators=150, max_depth=6, min_samples_split=4, random_state=42
        ),
        "XGBoost Regressor": XGBRegressor(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.5,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=2,
        ),
    }

    results = {}
    metric_rows = []

    for name, model in models.items():
        print(f"--> Training {name}...")

        if name == "Seasonal Naive (t-7)":
            val_pred = model.predict(val["df"])
            test_pred = model.predict(test["df"])
            train_pred = model.predict(train["df"])
        elif name == "Ridge Regression":
            model.fit(train["X_scaled"], train["y"])
            train_pred = model.predict(train["X_scaled"])
            val_pred = model.predict(val["X_scaled"])
            test_pred = model.predict(test["X_scaled"])
        else:
            model.fit(train["X"], train["y"])
            train_pred = model.predict(train["X"])
            val_pred = model.predict(val["X"])
            test_pred = model.predict(test["X"])

        val_metrics = calculate_metrics(val["y"], val_pred)
        test_metrics = calculate_metrics(test["y"], test_pred)

        results[name] = {
            "model": model,
            "train_pred": train_pred,
            "val_pred": val_pred,
            "test_pred": test_pred,
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
        }

        metric_rows.append({
            "Model": name,
            "Val MAE (GB)": val_metrics["MAE"],
            "Val RMSE (GB)": val_metrics["RMSE"],
            "Val WAPE (%)": val_metrics["WAPE (%)"],
            "Val R2": val_metrics["R2"],
            "Test MAE (GB)": test_metrics["MAE"],
            "Test RMSE (GB)": test_metrics["RMSE"],
            "Test WAPE (%)": test_metrics["WAPE (%)"],
            "Test R2": test_metrics["R2"],
        })

    metrics_df = pd.DataFrame(metric_rows).sort_values("Val WAPE (%)").reset_index(drop=True)
    print("\n--- MODEL BENCHMARK LEADERBOARD ---")
    print(metrics_df.to_string(index=False))

    # Select champion model based on lowest Val WAPE
    champion_name = str(metrics_df.iloc[0]["Model"])
    print(f"\n[Selection] Champion model selected: '{champion_name}' based on best validation performance.")

    return results, metrics_df, champion_name


def retrain_champion(
    datasets: dict, feature_cols: list[str], champion_name: str
) -> tuple[Any, np.ndarray, dict]:
    """Retrains the champion model on Train + Validation combined, then evaluates on Test."""
    print(f"\nRetraining champion '{champion_name}' on Train + Validation combined...")

    train = datasets["train"]
    val = datasets["val"]
    test = datasets["test"]

    # Combine Train and Val
    X_train_val = pd.concat([train["X"], val["X"]], axis=0).reset_index(drop=True)
    y_train_val = np.concatenate([train["y"], val["y"]])

    if champion_name == "XGBoost Regressor":
        champion_model = XGBRegressor(
            n_estimators=180,
            max_depth=4,
            learning_rate=0.04,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.5,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=2,
        )
        champion_model.fit(X_train_val, y_train_val)
        test_pred = champion_model.predict(test["X"])
    elif champion_name == "Random Forest":
        champion_model = RandomForestRegressor(
            n_estimators=180, max_depth=6, min_samples_split=4, random_state=42
        )
        champion_model.fit(X_train_val, y_train_val)
        test_pred = champion_model.predict(test["X"])
    elif champion_name == "Ridge Regression":
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_tv_scaled = scaler.fit_transform(X_train_val)
        X_test_scaled = scaler.transform(test["X"])
        champion_model = Ridge(alpha=10.0)
        champion_model.fit(X_tv_scaled, y_train_val)
        test_pred = champion_model.predict(X_test_scaled)
    else:
        champion_model = SeasonalNaiveModel(lag=7)
        test_pred = champion_model.predict(test["df"])

    final_test_metrics = calculate_metrics(test["y"], test_pred)
    print(
        f"Final Champion Test Metrics: WAPE = {final_test_metrics['WAPE (%)']:.2f}%, "
        f"MAE = {final_test_metrics['MAE']:,.1f} GB, RMSE = {final_test_metrics['RMSE']:,.1f} GB, R2 = {final_test_metrics['R2']:.3f}"
    )

    return champion_model, test_pred, final_test_metrics


def forecast_future(
    model: Any,
    full_df: pd.DataFrame,
    feature_cols: list[str],
    horizon_days: int = 30,
    residual_std: float = 25000.0,
) -> pd.DataFrame:
    """Recursively forecasts the next `horizon_days` (e.g., 30 days) beyond the latest date,

    updating lag and rolling features dynamically at each step.
    """
    print(f"\nForecasting next {horizon_days} days into the future...")
    history_df = full_df.copy().sort_values("date").reset_index(drop=True)
    start_date = history_df["date"].min()
    last_date = history_df["date"].max()

    forecast_records = []

    # Current working series of historical target values
    values_history = list(history_df["kpi_volume_gb"].values)
    dates_history = list(history_df["date"].values)

    for step in range(1, horizon_days + 1):
        next_date = pd.to_datetime(last_date) + pd.Timedelta(days=step)
        dow = next_date.dayofweek
        doy = next_date.dayofyear
        month = next_date.month
        dom = next_date.day
        is_weekend = 1 if dow in [5, 6] else 0
        trend_step = (next_date - pd.to_datetime(start_date)).days

        sin_dow = np.sin(2 * np.pi * dow / 7.0)
        cos_dow = np.cos(2 * np.pi * dow / 7.0)
        sin_doy = np.sin(2 * np.pi * doy / 365.25)
        cos_doy = np.cos(2 * np.pi * doy / 365.25)

        # Lags from values_history (where index -1 is yesterday)
        lag_1 = values_history[-1]
        lag_2 = values_history[-2]
        lag_3 = values_history[-3]
        lag_7 = values_history[-7]
        lag_14 = values_history[-14]
        lag_21 = values_history[-21]
        lag_28 = values_history[-28]

        # Rolling stats
        last_7 = values_history[-7:]
        last_14 = values_history[-14:]
        last_28 = values_history[-28:]

        rolling_mean_7 = float(np.mean(last_7))
        rolling_std_7 = float(np.std(last_7))
        rolling_min_7 = float(np.min(last_7))
        rolling_max_7 = float(np.max(last_7))

        rolling_mean_14 = float(np.mean(last_14))
        rolling_std_14 = float(np.std(last_14))
        rolling_mean_28 = float(np.mean(last_28))

        diff_1 = lag_1 - lag_2
        diff_7 = lag_1 - values_history[-8]
        ratio_7_28 = rolling_mean_7 / (rolling_mean_28 + 1e-6)

        feat_dict = {
            "day_of_week": dow,
            "is_weekend": is_weekend,
            "month": month,
            "day_of_month": dom,
            "day_of_year": doy,
            "week_of_year": int(next_date.isocalendar().week),
            "sin_dow": sin_dow,
            "cos_dow": cos_dow,
            "sin_doy": sin_doy,
            "cos_doy": cos_doy,
            "trend_step": trend_step,
            "lag_1": lag_1,
            "lag_2": lag_2,
            "lag_3": lag_3,
            "lag_7": lag_7,
            "lag_14": lag_14,
            "lag_21": lag_21,
            "lag_28": lag_28,
            "rolling_mean_7": rolling_mean_7,
            "rolling_std_7": rolling_std_7,
            "rolling_min_7": rolling_min_7,
            "rolling_max_7": rolling_max_7,
            "rolling_mean_14": rolling_mean_14,
            "rolling_std_14": rolling_std_14,
            "rolling_mean_28": rolling_mean_28,
            "diff_1": diff_1,
            "diff_7": diff_7,
            "ratio_7_28": ratio_7_28,
        }

        X_step = pd.DataFrame([feat_dict])[feature_cols]
        pred_val = float(model.predict(X_step)[0])

        # Expanding uncertainty with horizon
        horizon_factor = np.sqrt(step / 7.0) + 1.0
        ci_80 = 1.28 * residual_std * horizon_factor
        ci_95 = 1.96 * residual_std * horizon_factor

        forecast_records.append({
            "date": next_date,
            "predicted_kpi_volume_gb": pred_val,
            "lower_80": pred_val - ci_80,
            "upper_80": pred_val + ci_80,
            "lower_95": pred_val - ci_95,
            "upper_95": pred_val + ci_95,
        })

        # Append to history to feed next step lags
        values_history.append(pred_val)
        dates_history.append(next_date)

    forecast_df = pd.DataFrame(forecast_records)
    print(f"Future forecast generated from {forecast_df['date'].min().strftime('%Y-%m-%d')} to {forecast_df['date'].max().strftime('%Y-%m-%d')}")
    return forecast_df


def run_training_pipeline() -> tuple[dict, pd.DataFrame, pd.DataFrame, Any]:
    """Executes feature preparation, benchmarking, champion retraining, and future forecasting."""
    from src.feature_engineering import prepare_datasets

    datasets, scaler, feature_cols = prepare_datasets()
    results, metrics_df, champion_name = train_and_benchmark(datasets, feature_cols)

    champion_model, test_pred, final_metrics = retrain_champion(datasets, feature_cols, champion_name)

    # Compute empirical residual standard deviation for prediction intervals
    test_y = datasets["test"]["y"]
    res_std = float(np.std(test_y - test_pred))

    forecast_df = forecast_future(
        champion_model, datasets["full_df"], feature_cols, horizon_days=30, residual_std=res_std
    )

    # Save future forecast to csv
    forecast_df.to_csv("data/future_30d_forecast.csv", index=False)
    print("Saved future forecast to: data/future_30d_forecast.csv")

    return results, metrics_df, forecast_df, champion_model


if __name__ == "__main__":
    run_training_pipeline()
