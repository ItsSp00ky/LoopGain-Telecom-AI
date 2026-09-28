"""plots.py: Production-grade publication-quality visualizations for the KPI prediction pipeline.
Generates:
1. 01_eda_and_anomalies.png
2. 02_chronological_splits.png
3. 03_model_benchmark_metrics.png
4. 04_actual_vs_predicted_test.png
5. 05_feature_importance.png
6. 06_future_30d_forecast.png
"""

import os
from pathlib import Path
from typing import Any
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# Set global matplotlib typography and aesthetics
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.labelweight": "semibold",
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 15,
    "figure.titleweight": "bold",
    "axes.grid": True,
    "grid.alpha": 0.35,
    "grid.linestyle": "--",
})

_PKG_ROOT = Path(__file__).resolve().parent.parent
LOCAL_PLOTS_DIR = _PKG_ROOT / "plots"


def sync_to_artifacts(fig_path: Path) -> Path:
    """Copies generated plot file to an external directory if ARTIFACT_PLOTS_DIR is set."""
    env_dir = os.environ.get("ARTIFACT_PLOTS_DIR")
    if env_dir:
        dest_dir = Path(env_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / fig_path.name
        shutil.copy2(fig_path, dest)
        return dest
    return fig_path


def plot_eda_and_anomalies(
    clean_csv: str | Path | None = None,
    plots_dir: Path | str | None = None,
) -> Path:
    """Generates historical time series, trend, 7-day rolling mean, and highlighted anomalies."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    if clean_csv is None:
        clean_csv = _PKG_ROOT / "data" / "traffic_kpi_clean.csv"
    else:
        clean_csv = Path(clean_csv)
        if not clean_csv.exists() and (_PKG_ROOT / clean_csv).exists():
            clean_csv = _PKG_ROOT / clean_csv

    df = pd.read_csv(clean_csv)
    df["date"] = pd.to_datetime(df["date"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [2.5, 1.2]}, sharex=False
    )

    # 1. Main Time Series with Rolling Trend
    ax1.plot(
        df["date"],
        df["kpi_volume_gb_raw"] / 1e3,
        color="#94A3B8",
        alpha=0.5,
        linewidth=1.2,
        label="Raw Observed Daily Volume",
    )
    ax1.plot(
        df["date"],
        df["kpi_volume_gb"] / 1e3,
        color="#2563EB",
        linewidth=1.8,
        label="Cleaned KPI Volume (Outage-Adjusted)",
    )

    rolling_7d = (df["kpi_volume_gb"] / 1e3).rolling(7, center=True).mean()
    ax1.plot(
        df["date"],
        rolling_7d,
        color="#D97706",
        linewidth=2.5,
        linestyle="-",
        label="7-Day Rolling Trend Baseline",
    )

    # Highlight Anomalies
    anomalies = df[df["is_anomaly"]]
    if not anomalies.empty:
        ax1.scatter(
            anomalies["date"],
            anomalies["kpi_volume_gb_raw"] / 1e3,
            color="#DC2626",
            s=90,
            zorder=5,
            edgecolors="black",
            linewidth=1.2,
            label=f"Detected Severe Outages/Anomalies (n={len(anomalies)})",
        )
        for _, row in anomalies.iterrows():
            date_label = row["date"].strftime("%b %d")
            ax1.annotate(
                f"{date_label}\n({row['kpi_volume_gb_raw']/1e3:,.0f}k GB)",
                xy=(row["date"], row["kpi_volume_gb_raw"] / 1e3),
                xytext=(0, -32),
                textcoords="offset points",
                ha="center",
                fontsize=8.5,
                weight="bold",
                color="#DC2626",
                arrowprops=dict(arrowstyle="->", color="#DC2626", lw=1),
            )

    ax1.set_title("4G Overall Accumulated Data Volume (Historical Trajectory & Anomaly Detection)")
    ax1.set_ylabel("Traffic Volume ('000 GB)")
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax1.legend(loc="upper left", framealpha=0.9)

    # 2. Day of Week Seasonality Boxplot
    df["DayName"] = df["date"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_data = [df[df["DayName"] == day]["kpi_volume_gb"] / 1e3 for day in order]

    box = ax2.boxplot(
        day_data,
        tick_labels=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        patch_artist=True,
        medianprops=dict(color="#1E293B", linewidth=2),
    )
    colors = ["#E2E8F0", "#E2E8F0", "#E2E8F0", "#E2E8F0", "#BAE6FD", "#BAE6FD", "#E2E8F0"]
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_edgecolor("#64748B")

    ax2.set_title("Weekly Seasonality Profile by Day of Week (Peak traffic on Friday & Saturday)")
    ax2.set_ylabel("Volume ('000 GB)")

    plt.tight_layout()
    out_file = target_plots_dir / "01_eda_and_anomalies.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 1] Saved: {out_file}")
    return out_file


def plot_chronological_splits(datasets: dict, plots_dir: Path | str | None = None) -> Path:
    """Generates visualization of train, validation, and test splits along the timeline."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    train_df = datasets["train"]["df"]
    val_df = datasets["val"]["df"]
    test_df = datasets["test"]["df"]

    fig, ax = plt.subplots(figsize=(14, 5))

    ax.plot(
        train_df["date"],
        train_df["kpi_volume_gb"] / 1e3,
        color="#2563EB",
        linewidth=2,
        label=f"Train Partition (n={len(train_df)} days)",
    )
    ax.plot(
        val_df["date"],
        val_df["kpi_volume_gb"] / 1e3,
        color="#F59E0B",
        linewidth=2,
        label=f"Validation Partition (n={len(val_df)} days)",
    )
    ax.plot(
        test_df["date"],
        test_df["kpi_volume_gb"] / 1e3,
        color="#10B981",
        linewidth=2,
        label=f"Holdout Test Partition (n={len(test_df)} days)",
    )

    # Shaded backgrounds
    ax.axvspan(train_df["date"].min(), train_df["date"].max(), color="#DBEAFE", alpha=0.35)
    ax.axvspan(val_df["date"].min(), val_df["date"].max(), color="#FEF3C7", alpha=0.35)
    ax.axvspan(test_df["date"].min(), test_df["date"].max(), color="#D1FAE5", alpha=0.35)

    # Vertical split boundaries
    ax.axvline(val_df["date"].min(), color="#D97706", linestyle=":", linewidth=2)
    ax.axvline(test_df["date"].min(), color="#059669", linestyle=":", linewidth=2)

    ax.set_title("Chronological Train / Validation / Test Partitions (Strict Zero-Leakage Split)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Traffic Volume ('000 GB)")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", framealpha=0.95)

    plt.tight_layout()
    out_file = target_plots_dir / "02_chronological_splits.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 2] Saved: {out_file}")
    return out_file


def plot_model_comparison(metrics_df: pd.DataFrame, plots_dir: Path | str | None = None) -> Path:
    """Generates comparison bar charts of error metrics across all candidate models."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    df = metrics_df.copy()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    x = np.arange(len(df))
    width = 0.35

    # 1. WAPE (%) Comparison
    rects1 = ax1.bar(
        x - width / 2, df["Val WAPE (%)"], width, label="Validation WAPE", color="#3B82F6"
    )
    rects2 = ax1.bar(
        x + width / 2, df["Test WAPE (%)"], width, label="Test WAPE", color="#10B981"
    )
    ax1.set_title("Weighted Absolute Percentage Error (WAPE % - Lower is Better)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(df["Model"], rotation=15, ha="right")
    ax1.set_ylabel("WAPE (%)")
    ax1.legend()

    # Add data values on bars
    for rect in rects1:
        h = rect.get_height()
        ax1.annotate(f"{h:.2f}%", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    for rect in rects2:
        h = rect.get_height()
        ax1.annotate(f"{h:.2f}%", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)

    # 2. MAE ('000 GB) Comparison
    rects3 = ax2.bar(
        x - width / 2, df["Val MAE (GB)"] / 1e3, width, label="Validation MAE", color="#6366F1"
    )
    rects4 = ax2.bar(
        x + width / 2, df["Test MAE (GB)"] / 1e3, width, label="Test MAE", color="#EC4899"
    )
    ax2.set_title("Mean Absolute Error (MAE in '000 GB - Lower is Better)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(df["Model"], rotation=15, ha="right")
    ax2.set_ylabel("MAE ('000 GB)")
    ax2.legend()

    for rect in rects3:
        h = rect.get_height()
        ax2.annotate(f"{h:.1f}k", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)
    for rect in rects4:
        h = rect.get_height()
        ax2.annotate(f"{h:.1f}k", xy=(rect.get_x() + rect.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8.5)

    plt.tight_layout()
    out_file = target_plots_dir / "03_model_benchmark_metrics.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 3] Saved: {out_file}")
    return out_file


def plot_actual_vs_predicted(
    datasets: dict, results: dict, champion_name: str, plots_dir: Path | str | None = None
) -> Path:
    """Plots actual vs predicted trajectories on the holdout test set with residual diagnostics."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    test = datasets["test"]
    dates = pd.to_datetime(test["dates"])
    y_true = test["y"] / 1e3

    champ_pred = results[champion_name]["test_pred"] / 1e3
    naive_pred = results["Seasonal Naive (t-7)"]["test_pred"] / 1e3

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [2.2, 1.0]}, sharex=True
    )

    # 1. Actual vs Predicted overlay
    ax1.plot(dates, y_true, color="#0F172A", marker="o", markersize=4.5, linewidth=2.0, label="Actual KPI Volume")
    ax1.plot(dates, champ_pred, color="#2563EB", marker="s", markersize=4.0, linewidth=2.0, linestyle="--",
             label=f"Champion Prediction ({champion_name})")
    ax1.plot(dates, naive_pred, color="#94A3B8", linewidth=1.5, linestyle=":", label="Baseline (Seasonal Naive t-7)")

    ax1.set_title(f"Holdout Test Evaluation: Actual vs Predicted Volume ({dates.min().strftime('%b %d')} - {dates.max().strftime('%b %d, %Y')})")
    ax1.set_ylabel("Volume ('000 GB)")
    ax1.legend(loc="upper left")

    # 2. Residuals (Actual - Predicted)
    residuals = (test["y"] - results[champion_name]["test_pred"]) / 1e3
    ax2.bar(dates, residuals, color=np.where(residuals >= 0, "#3B82F6", "#EF4444"), alpha=0.75, width=0.7)
    ax2.axhline(0, color="#1E293B", linewidth=1.2, linestyle="-")
    ax2.set_title(f"Prediction Residuals [y - y_hat] (Mean error = {np.mean(residuals):.1f}k GB)")
    ax2.set_ylabel("Error ('000 GB)")
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    plt.tight_layout()
    out_file = target_plots_dir / "04_actual_vs_predicted_test.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 4] Saved: {out_file}")
    return out_file


def plot_feature_importance(
    champion_model: Any, feature_cols: list[str], champion_name: str, plots_dir: Path | str | None = None
) -> Path:
    """Plots top predictive feature importances for tree-based champion models."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 7))

    if hasattr(champion_model, "feature_importances_"):
        importances = champion_model.feature_importances_
    elif hasattr(champion_model, "coef_"):
        importances = np.abs(champion_model.coef_)
    else:
        # Fallback uniform
        importances = np.ones(len(feature_cols))

    feat_df = pd.DataFrame({"Feature": feature_cols, "Importance": importances})
    feat_df = feat_df.sort_values("Importance", ascending=True).tail(15)

    bars = ax.barh(feat_df["Feature"], feat_df["Importance"], color="#3B82F6", edgecolor="#1D4ED8")
    ax.set_title(f"Top 15 Predictive Features ({champion_name})")
    ax.set_xlabel("Relative Feature Importance")

    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.3f}", xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=8.5)

    plt.tight_layout()
    out_file = target_plots_dir / "05_feature_importance.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 5] Saved: {out_file}")
    return out_file


def plot_future_forecast(
    clean_csv: str | Path | None = None,
    forecast_csv: str | Path | None = None,
    capacity_threshold: float = 1200000.0,
    plots_dir: Path | str | None = None,
) -> Path:
    """Generates next 30-day forecast projection with 80% and 95% uncertainty cones and capacity lines."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    if clean_csv is None:
        clean_csv = _PKG_ROOT / "data" / "traffic_kpi_clean.csv"
    else:
        clean_csv = Path(clean_csv)
        if not clean_csv.exists() and (_PKG_ROOT / clean_csv).exists():
            clean_csv = _PKG_ROOT / clean_csv

    if forecast_csv is None:
        forecast_csv = _PKG_ROOT / "data" / "future_30d_forecast.csv"
    else:
        forecast_csv = Path(forecast_csv)
        if not forecast_csv.exists() and (_PKG_ROOT / forecast_csv).exists():
            forecast_csv = _PKG_ROOT / forecast_csv

    history = pd.read_csv(clean_csv)
    history["date"] = pd.to_datetime(history["date"])
    forecast = pd.read_csv(forecast_csv)
    forecast["date"] = pd.to_datetime(forecast["date"])

    # Recent history window (last 60 days)
    recent_history = history.tail(60).copy()

    fig, ax = plt.subplots(figsize=(15, 6))

    # Recent actuals
    ax.plot(
        recent_history["date"],
        recent_history["kpi_volume_gb"] / 1e3,
        color="#1E293B",
        linewidth=2.2,
        label="Recent Observed Volume (Historical)",
    )

    # Future forecast
    ax.plot(
        forecast["date"],
        forecast["predicted_kpi_volume_gb"] / 1e3,
        color="#2563EB",
        linewidth=2.5,
        linestyle="--",
        marker="o",
        markersize=3.5,
        label="Future 30-Day Forecast Projection",
    )

    # Uncertainty bands
    ax.fill_between(
        forecast["date"],
        forecast["lower_80"] / 1e3,
        forecast["upper_80"] / 1e3,
        color="#93C5FD",
        alpha=0.45,
        label="80% Confidence Prediction Interval",
    )
    ax.fill_between(
        forecast["date"],
        forecast["lower_95"] / 1e3,
        forecast["upper_95"] / 1e3,
        color="#BFDBFE",
        alpha=0.25,
        label="95% Confidence Prediction Interval",
    )

    # Capacity threshold line (1.2 Million GB)
    ax.axhline(
        capacity_threshold / 1e3,
        color="#DC2626",
        linestyle="-.",
        linewidth=1.8,
        label=f"Carrier Capacity Threshold Alert ({capacity_threshold/1e6:.1f}M GB)",
    )

    # Vertical demarcation
    split_date = history["date"].max()
    ax.axvline(split_date, color="#64748B", linestyle=":", linewidth=1.5)
    ax.annotate(
        f"Forecast Origin\n({split_date.strftime('%b %d, %Y')})",
        xy=(split_date, (recent_history["kpi_volume_gb"].min() / 1e3)),
        xytext=(-30, 20),
        textcoords="offset points",
        fontsize=9,
        weight="bold",
        color="#475569",
    )

    end_month_str = forecast["date"].max().strftime("%B %Y") if not forecast.empty else "Horizon"
    ax.set_title(f"30-Day Network Traffic Forecast Cone (Projected Through {end_month_str})")
    ax.set_xlabel("Timeline")
    ax.set_ylabel("Traffic Volume ('000 GB)")
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.legend(loc="upper left", framealpha=0.95)

    plt.tight_layout()
    out_file = target_plots_dir / "06_future_30d_forecast.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 6] Saved: {out_file}")
    return out_file


def plot_multivariate_vs_univariate_comparison(
    comp_df: pd.DataFrame | None = None,
    plots_dir: Path | str | None = None,
) -> Path:
    """Generates 3-panel comparative performance plot contrasting Univariate vs Multivariate Exogenous models."""
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    if comp_df is None:
        csv_p = _PKG_ROOT / "data" / "multivariate_vs_univariate_comparison.csv"
        if csv_p.exists():
            comp_df = pd.read_csv(csv_p)
        else:
            raise FileNotFoundError(f"Comparison dataframe not found at: {csv_p}")

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=300)
    labels = ["Univariate\nBaseline", "Multivariate\nExogenous"]
    colors = ["#2563EB", "#059669"]

    # 1. WAPE (%)
    wapes = comp_df["Test-WAPE (%)"].values
    bars1 = axes[0].bar(labels, wapes, color=colors, width=0.55, edgecolor="black")
    for bar in bars1:
        y = bar.get_height()
        axes[0].text(bar.get_x() + bar.get_width()/2, y + 0.05, f"{y:.2f}%", ha="center", weight="bold", fontsize=11)
    diff_wape = wapes[1] - wapes[0]
    axes[0].set_title(f"Test WAPE (%)\n({diff_wape:+.2f}% Improvement)", fontweight="bold")
    axes[0].set_ylabel("WAPE (%) — Lower is Better")
    axes[0].set_ylim(0, max(wapes) * 1.25)

    # 2. MAE (GB)
    maes = comp_df["Test-MAE"].values / 1e3
    bars2 = axes[1].bar(labels, maes, color=colors, width=0.55, edgecolor="black")
    for bar in bars2:
        y = bar.get_height()
        axes[1].text(bar.get_x() + bar.get_width()/2, y + 0.5, f"{y:.1f}k GB", ha="center", weight="bold", fontsize=11)
    pct_mae = ((maes[1] - maes[0]) / maes[0]) * 100
    axes[1].set_title(f"Test MAE ('000 GB)\n({pct_mae:.1f}% Error Reduction)", fontweight="bold")
    axes[1].set_ylabel("Mean Absolute Error ('000 GB) — Lower is Better")
    axes[1].set_ylim(0, max(maes) * 1.25)

    # 3. R2 Score
    r2s = comp_df["Test-R2"].values
    bars3 = axes[2].bar(labels, r2s, color=colors, width=0.55, edgecolor="black")
    for bar in bars3:
        y = bar.get_height()
        axes[2].text(bar.get_x() + bar.get_width()/2, y + 0.02, f"{y:.4f}", ha="center", weight="bold", fontsize=11)
    diff_r2 = r2s[1] - r2s[0]
    axes[2].set_title(f"Test R² Score\n({diff_r2:+.4f} Accuracy Lift)", fontweight="bold")
    axes[2].set_ylabel("R² Goodness of Fit — Higher is Better")
    axes[2].set_ylim(0, max(r2s) * 1.25)

    fig.suptitle(
        "Multivariate 4G Traffic Model vs. Univariate Baseline (Holdout Test Performance)\n"
        "Exogenous Radio Indicators: DL/UL Throughput, E-RAB Drop Rate, RRC SR (t-1 Shifted)",
        fontsize=13, fontweight="bold", y=1.03
    )

    plt.tight_layout()
    out_file = target_plots_dir / "07_multivariate_vs_univariate_comparison.png"
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()
    sync_to_artifacts(out_file)
    print(f"[Plot 7] Saved: {out_file}")
    return out_file



def run_all_plots(
    datasets: dict,
    results: dict,
    metrics_df: pd.DataFrame,
    champion_name: str,
    champion_model: Any,
    feature_cols: list[str],
    clean_csv: str | Path | None = None,
    forecast_csv: str | Path | None = None,
    plots_dir: Path | str | None = None,
) -> list[Path]:
    """Generates all 6 production charts and syncs them to the artifacts directory."""
    print("=" * 60)
    print("STEP 4: GENERATING PUBLICATION-QUALITY VISUALIZATIONS")
    print("=" * 60)
    target_plots_dir = Path(plots_dir) if plots_dir else LOCAL_PLOTS_DIR
    target_plots_dir.mkdir(parents=True, exist_ok=True)

    generated = [
        plot_eda_and_anomalies(clean_csv=clean_csv, plots_dir=target_plots_dir),
        plot_chronological_splits(datasets, plots_dir=target_plots_dir),
        plot_model_comparison(metrics_df, plots_dir=target_plots_dir),
        plot_actual_vs_predicted(datasets, results, champion_name, plots_dir=target_plots_dir),
        plot_feature_importance(champion_model, feature_cols, champion_name, plots_dir=target_plots_dir),
        plot_future_forecast(clean_csv=clean_csv, forecast_csv=forecast_csv, plots_dir=target_plots_dir),
    ]

    print(f"Successfully generated {len(generated)} visual figures in {target_plots_dir.resolve()}.\n")
    return generated


if __name__ == "__main__":
    from src.feature_engineering import prepare_datasets
    from src.model_definitions import train_and_benchmark, retrain_champion

    datasets, _, feature_cols = prepare_datasets()
    results, metrics_df, champion_name = train_and_benchmark(datasets, feature_cols)
    champion_model, _, _ = retrain_champion(datasets, feature_cols, champion_name)
    run_all_plots(datasets, results, metrics_df, champion_name, champion_model, feature_cols)
