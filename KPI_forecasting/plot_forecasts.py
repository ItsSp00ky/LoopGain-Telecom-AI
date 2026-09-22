"""
=====================================================================
 plot_forecasts.py
 Purpose : Generate visualization charts for the KPI forecasting results.

 Charts generated per KPI:
   1. Actual vs Predicted over time (full test period)
   2. Daily aggregated view (averaged across all bands)
   3. Per-band breakdown

 Usage:
   python plot_forecasts.py
=====================================================================
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

# ----------------------------- CONFIG ------------------------------ #
RESULTS_DIR = "forecast_results"
PLOTS_DIR = "forecast_results/plots"
CLEANED_FILE = "Data2_Cleaned.csv"

KPIS = {
    "E-RAB Drop Rate": {
        "file": "predictions_E-RAB_Drop_Rate.csv",
        "unit": "%",
        "color": "#e74c3c",
        "description": "Session Drop Rate",
    },
    "4G Cell Av. (%)": {
        "file": "predictions_4G_Cell_Av._pct.csv",
        "unit": "%",
        "color": "#2ecc71",
        "description": "Cell Availability",
    },
    "Avg RRC Connected users": {
        "file": "predictions_Avg_RRC_Connected_users.csv",
        "unit": "users",
        "color": "#3498db",
        "description": "Connected Users",
    },
}

BAND_COLORS = {
    350: "#e74c3c",
    400: "#e67e22",
    1556: "#f1c40f",
    1700: "#2ecc71",
    3500: "#3498db",
    6200: "#9b59b6",
}


def setup_style():
    """Set up a clean, professional plot style."""
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "#f8f9fa",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": "#cccccc",
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "legend.fontsize": 9,
        "figure.dpi": 150,
    })


# ------------------------------------------------------------------- #
# CHART 1: Actual vs Predicted (Daily Aggregate)
# ------------------------------------------------------------------- #
def plot_daily_forecast(kpi_name, pred_df, info):
    """
    Plot actual vs predicted, averaged across all bands per day.
    This shows the overall forecast quality over time.
    """
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1])

    # Aggregate by date
    daily = pred_df.groupby("Date").agg(
        Actual=("Actual", "mean"),
        Predicted=("Predicted", "mean"),
    ).reset_index()
    daily["Date"] = pd.to_datetime(daily["Date"])
    daily = daily.sort_values("Date")

    # -- Top: Actual vs Predicted --
    ax = axes[0]
    ax.plot(daily["Date"], daily["Actual"], color=info["color"],
            linewidth=1.5, label="Actual", alpha=0.9)
    ax.plot(daily["Date"], daily["Predicted"], color="#2c3e50",
            linewidth=1.5, linestyle="--", label="Predicted", alpha=0.8)
    ax.fill_between(daily["Date"], daily["Actual"], daily["Predicted"],
                     alpha=0.15, color=info["color"])

    ax.set_title(f"{info['description']} - Actual vs Predicted (Daily Average)", fontweight="bold")
    ax.set_ylabel(f"{kpi_name} ({info['unit']})")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())

    # -- Bottom: Residuals (Error) --
    ax2 = axes[1]
    residuals = daily["Actual"] - daily["Predicted"]
    colors = ["#e74c3c" if r < 0 else "#2ecc71" for r in residuals]
    ax2.bar(daily["Date"], residuals, color=colors, alpha=0.6, width=1)
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.set_title("Prediction Error (Actual - Predicted)", fontsize=11)
    ax2.set_ylabel("Error")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())

    plt.tight_layout()
    fname = os.path.join(PLOTS_DIR, f"forecast_{kpi_name.replace(' ', '_').replace('(%)', 'pct')}_daily.png")
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


# ------------------------------------------------------------------- #
# CHART 2: Per-Band Breakdown
# ------------------------------------------------------------------- #
def plot_per_band(kpi_name, pred_df, info):
    """
    Plot actual vs predicted for each frequency band separately.
    Shows how the model performs across different bands.
    """
    bands = sorted(pred_df["earfcndl"].unique())
    n_bands = len(bands)
    fig, axes = plt.subplots(n_bands, 1, figsize=(14, 3 * n_bands), sharex=True)
    if n_bands == 1:
        axes = [axes]

    for ax, band in zip(axes, bands):
        band_data = pred_df[pred_df["earfcndl"] == band].copy()
        band_data["Date"] = pd.to_datetime(band_data["Date"])
        band_data = band_data.sort_values("Date")

        color = BAND_COLORS.get(band, "#333333")
        ax.plot(band_data["Date"], band_data["Actual"], color=color,
                linewidth=1.2, label="Actual", alpha=0.9)
        ax.plot(band_data["Date"], band_data["Predicted"], color="#2c3e50",
                linewidth=1.2, linestyle="--", label="Predicted", alpha=0.7)
        ax.fill_between(band_data["Date"], band_data["Actual"], band_data["Predicted"],
                         alpha=0.1, color=color)

        # Per-band MAE
        mae = np.mean(np.abs(band_data["Actual"] - band_data["Predicted"]))
        ax.set_ylabel(f"{band} MHz")
        ax.legend([f"Actual", f"Predicted (MAE={mae:.3f})"], loc="upper right", fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.xaxis.set_major_locator(mdates.MonthLocator())

    axes[0].set_title(f"{info['description']} - Per Frequency Band", fontweight="bold")
    axes[-1].set_xlabel("Date")

    plt.tight_layout()
    fname = os.path.join(PLOTS_DIR, f"forecast_{kpi_name.replace(' ', '_').replace('(%)', 'pct')}_bands.png")
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


# ------------------------------------------------------------------- #
# CHART 3: Full Timeline (Train + Test)
# ------------------------------------------------------------------- #
def plot_full_timeline(kpi_name, pred_df, cleaned_df, info):
    """
    Show the full year of data with training period in grey and
    test period with actual vs predicted overlay.
    """
    fig, ax = plt.subplots(figsize=(14, 5))

    # Daily aggregates for full dataset
    full_daily = cleaned_df.groupby("Date")[kpi_name].mean().reset_index()
    full_daily["Date"] = pd.to_datetime(full_daily["Date"])
    full_daily = full_daily.sort_values("Date")

    # Test period aggregates
    test_daily = pred_df.groupby("Date").agg(
        Actual=("Actual", "mean"),
        Predicted=("Predicted", "mean"),
    ).reset_index()
    test_daily["Date"] = pd.to_datetime(test_daily["Date"])
    test_daily = test_daily.sort_values("Date")

    split_date = test_daily["Date"].min()

    # Training period (grey)
    train_data = full_daily[full_daily["Date"] < split_date]
    ax.plot(train_data["Date"], train_data[kpi_name], color="#bdc3c7",
            linewidth=1, label="Training Data (70%)", alpha=0.7)

    # Test period - actual
    ax.plot(test_daily["Date"], test_daily["Actual"], color=info["color"],
            linewidth=1.5, label="Actual (Test 30%)", alpha=0.9)

    # Test period - predicted
    ax.plot(test_daily["Date"], test_daily["Predicted"], color="#2c3e50",
            linewidth=1.5, linestyle="--", label="Predicted", alpha=0.8)

    # Split line
    ax.axvline(x=split_date, color="#e74c3c", linewidth=1, linestyle=":",
               label=f"Train/Test Split ({split_date.strftime('%Y-%m-%d')})")

    ax.set_title(f"{info['description']} - Full Year Timeline (Train + Test)", fontweight="bold")
    ax.set_ylabel(f"{kpi_name} ({info['unit']})")
    ax.set_xlabel("Date")
    ax.legend(loc="best", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=30)

    plt.tight_layout()
    fname = os.path.join(PLOTS_DIR, f"forecast_{kpi_name.replace(' ', '_').replace('(%)', 'pct')}_timeline.png")
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


# ------------------------------------------------------------------- #
# CHART 4: Weekly Aggregated Forecast
# ------------------------------------------------------------------- #
def plot_weekly_forecast(kpi_name, pred_df, info):
    """
    Aggregate predictions by week for a cleaner long-term view.
    """
    fig, ax = plt.subplots(figsize=(14, 5))

    pred_copy = pred_df.copy()
    pred_copy["Date"] = pd.to_datetime(pred_copy["Date"])
    pred_copy["Week"] = pred_copy["Date"].dt.isocalendar().week.astype(int)
    pred_copy["Year"] = pred_copy["Date"].dt.year

    weekly = pred_copy.groupby(["Year", "Week"]).agg(
        Actual=("Actual", "mean"),
        Predicted=("Predicted", "mean"),
        Date=("Date", "min"),
    ).reset_index()
    weekly = weekly.sort_values("Date")

    ax.plot(weekly["Date"], weekly["Actual"], color=info["color"],
            linewidth=2, marker="o", markersize=4, label="Actual (weekly avg)")
    ax.plot(weekly["Date"], weekly["Predicted"], color="#2c3e50",
            linewidth=2, marker="s", markersize=4, linestyle="--", label="Predicted (weekly avg)")
    ax.fill_between(weekly["Date"], weekly["Actual"], weekly["Predicted"],
                     alpha=0.15, color=info["color"])

    ax.set_title(f"{info['description']} - Weekly Forecast View", fontweight="bold")
    ax.set_ylabel(f"{kpi_name} ({info['unit']})")
    ax.set_xlabel("Week Starting")
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=30)

    plt.tight_layout()
    fname = os.path.join(PLOTS_DIR, f"forecast_{kpi_name.replace(' ', '_').replace('(%)', 'pct')}_weekly.png")
    plt.savefig(fname, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {fname}")
    return fname


# ------------------------------------------------------------------- #
# MAIN
# ------------------------------------------------------------------- #
def main():
    print("=" * 60)
    print("  GENERATING FORECAST VISUALIZATIONS")
    print("=" * 60)

    setup_style()
    os.makedirs(PLOTS_DIR, exist_ok=True)

    # Load cleaned data for full timeline
    cleaned_df = pd.read_csv(CLEANED_FILE, parse_dates=["Date"])

    all_plots = {}

    for kpi_name, info in KPIS.items():
        print(f"\n--- {info['description']} ---")

        pred_path = os.path.join(RESULTS_DIR, info["file"])
        if not os.path.exists(pred_path):
            print(f"  SKIPPED: {pred_path} not found")
            continue

        pred_df = pd.read_csv(pred_path)
        plots = {}

        plots["daily"] = plot_daily_forecast(kpi_name, pred_df, info)
        plots["bands"] = plot_per_band(kpi_name, pred_df, info)
        plots["timeline"] = plot_full_timeline(kpi_name, pred_df, cleaned_df, info)
        plots["weekly"] = plot_weekly_forecast(kpi_name, pred_df, info)

        all_plots[kpi_name] = plots

    print(f"\n{'='*60}")
    print(f"  ALL CHARTS SAVED TO: {PLOTS_DIR}/")
    print(f"  Total charts: {sum(len(v) for v in all_plots.values())}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
