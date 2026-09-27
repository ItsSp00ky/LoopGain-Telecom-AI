"""
gnn_visualizer.py
Publication-Grade Visualizer (300 DPI, Light Theme) for ERBS Spatial-Temporal Graph Neural Networks.
Generates:
  1. 05_erbs_topology_adjacency_heatmap.png
  2. 06_erbs_spatial_spillover_distribution.png
  3. 07_erbs_dynamic_attention_subgraph.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from typing import Dict, List, Tuple


def set_publication_style():
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
        'font.size': 11,
        'axes.titlesize': 13,
        'axes.titleweight': 'bold',
        'axes.labelsize': 11,
        'axes.labelweight': 'bold',
        'axes.edgecolor': '#2C3E50',
        'axes.linewidth': 1.2,
        'grid.color': '#BDC3C7',
        'grid.linestyle': '--',
        'grid.alpha': 0.5,
        'figure.facecolor': '#FFFFFF',
        'axes.facecolor': '#FFFFFF',
        'savefig.dpi': 300,
        'savefig.bbox': 'tight'
    })


def plot_topology_heatmap(adj_matrix: np.ndarray, out_path: str, dpi: int = 300):
    """Plots the base station spatial topology adjacency matrix."""
    set_publication_style()
    fig, ax = plt.subplots(figsize=(10, 8), dpi=dpi)

    N = adj_matrix.shape[0]
    sub_n = min(150, N)  # Zoom in on first 150 nodes for visual clarity
    sub_adj = adj_matrix[:sub_n, :sub_n]

    im = ax.imshow(sub_adj, cmap='YlGnBu', aspect='auto', interpolation='nearest')
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Topological Coupling Weight (A_ij)", weight='bold')

    ax.set_title(f"ERBS Base Station Topology Adjacency Matrix (Sub-Graph: {sub_n} x {sub_n})", pad=12)
    ax.set_xlabel("Physical Base Station Node Index (j)", labelpad=8)
    ax.set_ylabel("Physical Base Station Node Index (i)", labelpad=8)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[+] Saved Topology Adjacency Heatmap: {out_path}")


def plot_spillover_distribution(spillover_scores: np.ndarray, out_path: str, dpi: int = 300):
    """Plots histogram and cumulative distribution of spatial spillover risk."""
    set_publication_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), dpi=dpi)

    # Histogram
    n, bins, patches = ax1.hist(spillover_scores, bins=35, color='#2980B9', edgecolor='#1A5276', alpha=0.85)
    for p, b in zip(patches, bins):
        if b >= 0.80:
            p.set_facecolor('#E74C3C')  # Critical spillover
        elif b >= 0.50:
            p.set_facecolor('#F39C12')  # Elevated spillover

    ax1.axvline(0.50, color='#F39C12', linestyle='--', linewidth=1.5, label='Elevated Threshold (0.50)')
    ax1.axvline(0.80, color='#E74C3C', linestyle='--', linewidth=1.5, label='Critical Spillover (0.80)')
    ax1.set_title("ERBS Spatial Spillover Risk Distribution")
    ax1.set_xlabel("Spatial Spillover Score (||Z_neighbor|| / ||Z_self||)")
    ax1.set_ylabel("Number of Base Stations (N=1,067)")
    ax1.legend(loc='upper right', framealpha=0.9)
    ax1.grid(True)

    # CDF
    sorted_scores = np.sort(spillover_scores)
    cdf = np.arange(1, len(sorted_scores) + 1) / len(sorted_scores)
    ax2.plot(sorted_scores, cdf * 100.0, color='#8E44AD', linewidth=2.5, label='Empirical Cumulative Distribution')
    ax2.axvline(0.80, color='#E74C3C', linestyle=':', linewidth=1.5)
    ax2.set_title("Cumulative Network Load Exposure")
    ax2.set_xlabel("Spatial Spillover Score")
    ax2.set_ylabel("Cumulative Percentage of Nodes (%)")
    ax2.grid(True)
    ax2.legend(loc='lower right', framealpha=0.9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[+] Saved Spillover Distribution Plot: {out_path}")


def plot_attention_subgraph(top_nodes: List[str], neighbor_data: Dict[str, List[Tuple[str, float]]], out_path: str, dpi: int = 300):
    """Plots top coupled nodes and attention weights."""
    set_publication_style()
    fig, ax = plt.subplots(figsize=(10, 6), dpi=dpi)

    y_pos = []
    labels = []
    weights = []
    colors = []

    pos = 0
    for node in top_nodes[:6]:
        nbrs = neighbor_data.get(node, [])[:3]
        for nbr, w in nbrs:
            labels.append(f"{node} -> {nbr}")
            weights.append(w)
            y_pos.append(pos)
            colors.append('#16A085' if w > 0.40 else '#3498DB')
            pos += 1
        pos += 0.5

    y_arr = np.array(y_pos)
    ax.barh(y_arr, weights, color=colors, height=0.7, edgecolor='#2C3E50', alpha=0.85)
    ax.set_yticks(y_arr)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_title("Top Spatial Attention & Coupling Flows Across High-Load Hubs", pad=12)
    ax.set_xlabel("Dynamic Spatial Attention Weight (Alpha_ij)", labelpad=8)
    ax.set_xlim(0, max(weights) * 1.15 if weights else 1.0)
    ax.grid(True, axis='x')

    for y, w in zip(y_arr, weights):
        ax.text(w + 0.01, y, f"{w:.3f}", va='center', fontsize=9, fontweight='bold', color='#2C3E50')

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[+] Saved Attention Subgraph Plot: {out_path}")


def generate_all_gnn_plots(adj_matrix: np.ndarray, spillover_scores: np.ndarray, top_nodes: List[str], neighbor_data: Dict[str, List[Tuple[str, float]]], output_dir: str, dpi: int = 300):
    """Generates all 3 publication GNN figures."""
    p1 = os.path.join(output_dir, "05_erbs_topology_adjacency_heatmap.png")
    p2 = os.path.join(output_dir, "06_erbs_spatial_spillover_distribution.png")
    p3 = os.path.join(output_dir, "07_erbs_dynamic_attention_subgraph.png")

    plot_topology_heatmap(adj_matrix, p1, dpi=dpi)
    plot_spillover_distribution(spillover_scores, p2, dpi=dpi)
    plot_attention_subgraph(top_nodes, neighbor_data, p3, dpi=dpi)
