"""Segment discovery.  Owner: E3

    K-Means on scaled RFM-LE, k chosen by silhouette + elbow
    Hierarchical clustering with a dendrogram -- structural cross-check: are
        the eight business segments natural, or imposed?
    PCA for 2-D visualisation, and to check how much RFM-LE variance actually
        sits in two components

Hierarchical clustering is the first thing to cut if the week gets tight;
K-Means and PCA carry the screen on their own.
"""

from __future__ import annotations

import pandas as pd


def fit_kmeans(rfm: pd.DataFrame, k_search: tuple[int, ...] = tuple(range(3, 11))):
    """Fit across k, select by silhouette and elbow, return the chosen model."""
    raise NotImplementedError("TODO(E3)")


def fit_hierarchical(rfm: pd.DataFrame):
    raise NotImplementedError("TODO(E3)")


def dendrogram_data(model):
    raise NotImplementedError("TODO(E3)")


def fit_pca(rfm: pd.DataFrame, n_components: int = 2):
    """Also report explained variance -- the interesting number, not the plot."""
    raise NotImplementedError("TODO(E3)")


def compare_rules_vs_clusters(rule_segments: pd.Series, cluster_labels: pd.Series) -> pd.DataFrame:
    """Cross-tab. The cells that disagree are the dashboard insight."""
    raise NotImplementedError("TODO(E3)")
