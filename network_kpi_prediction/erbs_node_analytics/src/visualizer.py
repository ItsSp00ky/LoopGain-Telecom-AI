"""visualizer.py
High-Resolution Publication Visualizer for ERBS Node Intelligence.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Generates 300-DPI publication figures:
- 01_erbs_cluster_pca.png
- 02_erbs_health_distribution.png
- 03_erbs_sleeping_cells_top20.png
- 04_erbs_summer_stress_benchmark.png
"""

from pathlib import Path
from typing import Dict, Any
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Styling standards
STYLE_CONFIG = {
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 14,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.titlesize": 16,
    "axes.edgecolor": "#CBD5E1",
    "axes.linewidth": 1.2,
    "grid.color": "#E2E8F0",
    "grid.linestyle": "--",
    "grid.alpha": 0.7,
}


def setup_plotting_env():
    plt.rcParams.update(STYLE_CONFIG)
    sns.set_palette(["#2563EB", "#059669", "#D97706", "#DC2626", "#7C3AED", "#DB2777"])


def plot_erbs_clusters(cluster_df: pd.DataFrame, cluster_meta: Dict[str, Any], output_path: Path | str, dpi: int = 300):
    """Plots 2D PCA representation of base station behavioral clusters with operational personas."""
    setup_plotting_env()
    fig, ax = plt.subplots(figsize=(12, 8), dpi=dpi)

    personas = sorted(cluster_df["operational_persona"].unique())
    palette = sns.color_palette("tab10", len(personas))

    for idx, persona in enumerate(personas):
        sub = cluster_df[cluster_df["operational_persona"] == persona]
        ax.scatter(
            sub["pca_dim1"], sub["pca_dim2"],
            label=f"{persona} (n={len(sub):,})",
            color=palette[idx], alpha=0.75, edgecolors="white", linewidth=0.5, s=65
        )

    # Plot Centroids
    centroids = cluster_df.groupby("operational_persona")[["pca_dim1", "pca_dim2"]].mean()
    for persona, row in centroids.iterrows():
        ax.scatter(row["pca_dim1"], row["pca_dim2"], s=180, color="black", marker="X", zorder=5)
        ax.annotate(
            persona.split("(")[0].strip(),
            (row["pca_dim1"], row["pca_dim2"]),
            xytext=(6, 6), textcoords="offset points",
            fontsize=9, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", alpha=0.85)
        )

    var1 = cluster_meta["pca_variance_explained"][0] * 100
    var2 = cluster_meta["pca_variance_explained"][1] * 100
    ax.set_xlabel(f"Principal Component 1 ({var1:.1f}% Variance Explained)", fontweight="bold")
    ax.set_ylabel(f"Principal Component 2 ({var2:.1f}% Variance Explained)", fontweight="bold")
    ax.set_title(
        f"Base Station Behavioral Clustering & Operational Personas (1,067 ERBS Nodes)\n"
        f"Optimal k={cluster_meta['optimal_k']} (Silhouette Score: {cluster_meta['optimal_silhouette_score']:.3f})",
        fontweight="bold", pad=15
    )
    ax.legend(title="Operational Persona", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=True)
    ax.grid(True)
    plt.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_health_distribution(profile_df: pd.DataFrame, stats: Dict[str, Any], output_path: Path | str, dpi: int = 300):
    """Plots distribution of composite Health Index with SLA risk tiers."""
    setup_plotting_env()
    fig, ax = plt.subplots(figsize=(11, 6), dpi=dpi)

    sns.histplot(profile_df["health_index"], bins=35, kde=True, color="#2563EB", ax=ax, alpha=0.6, edgecolor="white")

    # Tier shading
    ax.axvspan(0, 60, color="#EF4444", alpha=0.12, label="Severe Degradation / Chronic Risk (< 60)")
    ax.axvspan(60, 80, color="#F59E0B", alpha=0.12, label="Moderate Performance Risk (60 - 80)")
    ax.axvspan(80, 100, color="#10B981", alpha=0.12, label="Healthy / 3GPP SLA Compliant (80 - 100)")

    mean_h = stats["mean_health_index"]
    ax.axvline(mean_h, color="#B91C1C", linestyle="--", linewidth=2.0, label=f"Network Mean Health: {mean_h:.1f}")

    ax.set_xlabel("Composite 3GPP Health Index (0 - 100)", fontweight="bold")
    ax.set_ylabel("Base Station Frequency Count", fontweight="bold")
    ax.set_title(
        f"Macro Grid Health Index Distribution Across 1,067 Physical ERBS Nodes\n"
        f"Compliant: {stats['healthy_nodes_count']} ({stats['healthy_nodes_count']/stats['total_nodes']*100:.1f}%) | "
        f"Degraded: {stats['severe_degraded_count']} | Sleeping Cells: {stats['sleeping_cells_detected']}",
        fontweight="bold", pad=15
    )
    ax.set_xlim(0, 100)
    ax.legend(loc="upper left", frameon=True)
    ax.grid(True)
    plt.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_sleeping_cells_top20(profile_df: pd.DataFrame, output_path: Path | str, dpi: int = 300):
    """Plots top 20 worst performing / sleeping ERBS base stations."""
    setup_plotting_env()
    top20 = profile_df.head(20).copy()
    top20 = top20.sort_values("health_index", ascending=True)

    fig, ax = plt.subplots(figsize=(12, 8), dpi=dpi)
    y_pos = np.arange(len(top20))

    colors = ["#DC2626" if s else "#EA580C" for s in top20["is_sleeping_cell"]]
    bars = ax.barh(y_pos, top20["health_index"], color=colors, edgecolor="black", height=0.7)

    for bar, (_, row) in zip(bars, top20.iterrows()):
        w = bar.get_width()
        txt = f" Health: {w:.1f} | Drop: {row['erab_drop_rate_mean']:.2f}% | DL: {row['dl_throughput_mbps_mean']:.1f} Mbps | Violations: {row['total_sla_violations']}"
        ax.text(w + 1.0, bar.get_y() + bar.get_height() / 2, txt, va="center", fontsize=8.5, fontweight="medium")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(top20["erbs_id"], fontweight="bold")
    ax.set_xlabel("Composite Health Index (0 to 100; Lower is Worse)", fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_title(
        "Top 20 Chronically Degraded & Sleeping ERBS Towers\n"
        "(Red: Verified Sleeping Cell Anomaly | Orange: Chronic SLA Degradation)",
        fontweight="bold", pad=15
    )
    ax.grid(True, axis="x")
    plt.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_summer_stress(summer_df: pd.DataFrame, stats: Dict[str, Any], output_path: Path | str, dpi: int = 300):
    """Plots summer peak load vs annual baseline degradation scatter."""
    setup_plotting_env()
    fig, ax = plt.subplots(figsize=(11, 7), dpi=dpi)

    throttled = summer_df[summer_df["is_summer_throttled"]]
    normal = summer_df[~summer_df["is_summer_throttled"]]

    ax.scatter(
        normal["delta_connected_users"], normal["delta_dl_throughput_mbps"],
        color="#2563EB", alpha=0.55, edgecolors="white", s=50, label="Standard Operational Behavior"
    )
    ax.scatter(
        throttled["delta_connected_users"], throttled["delta_dl_throughput_mbps"],
        color="#DC2626", alpha=0.9, edgecolors="black", s=80, marker="D",
        label=f"Summer Throttled / Overloaded Nodes (n={len(throttled)})"
    )

    ax.axhline(0, color="gray", linestyle="--", linewidth=1.0)
    ax.axvline(0, color="gray", linestyle="--", linewidth=1.0)

    ax.set_xlabel("Change in Daily Connected Users (Summer - Annual Baseline)", fontweight="bold")
    ax.set_ylabel("Change in Downlink Throughput (Mbps; Negative = Throttling)", fontweight="bold")
    ax.set_title(
        f"Summer Peak Load Stress & Degradation Benchmark (120-Day Peak vs Full Year)\n"
        f"Throttled Nodes: {stats['summer_throttled_nodes']} | Surge Hotspots: {stats['summer_surge_nodes']}",
        fontweight="bold", pad=15
    )
    ax.legend(loc="lower left", frameon=True)
    ax.grid(True)
    plt.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
