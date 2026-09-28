"""node_clustering.py
ERBS Base Station Behavioral Clustering & Operational Persona Classification.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Performs behavioral clustering across 1,067 physical base stations.
Follows ml-best-practices:
- Feature standardization via StandardScaler
- Silhouette score evaluation over k in [3, 6] to determine optimal clusters
- 2D dimensionality reduction via Principal Component Analysis (PCA)
- Operational persona tagging (Commercial, Residential, Transit, Rural)
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score


CLUSTER_PERSONA_MAP = {
    0: "Commercial & Business Hub (Peak Day Load)",
    1: "Residential Streaming Zone (Evening & Weekend Heavy)",
    2: "High-Mobility Transit Corridor (Heavy Handover)",
    3: "Rural & Low-Density Edge (Coverage Focus)",
    4: "Industrial & Backhaul Sensitive Node",
    5: "High-Density Congested Microcell",
}


def build_clustering_features(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Extracts aggregate behavioral, temporal, and load distribution features per ERBS node."""
    df = df_raw.copy()
    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

    # 1. Base statistics per node
    base_agg = df.groupby("erbs_id").agg(
        mean_users=("connected_users", "mean"),
        p95_users=("connected_users", lambda s: s.quantile(0.95)),
        std_users=("connected_users", "std"),
        mean_dl_tp=("dl_throughput_mbps", "mean"),
        p95_dl_tp=("dl_throughput_mbps", lambda s: s.quantile(0.95)),
        mean_ul_tp=("ul_throughput_mbps", "mean"),
        mean_drop_rate=("erab_drop_rate", "mean"),
        mean_handover_sr=("handover_sr", "mean"),
        mean_availability=("cell_availability_pct", "mean"),
        total_days=("date", "nunique")
    ).reset_index()

    # 2. Weekday vs Weekend Traffic Dynamics (Sign of Commercial vs Residential)
    wknd_agg = df.groupby(["erbs_id", "is_weekend"])["connected_users"].mean().unstack(fill_value=1.0)
    wknd_agg.columns = ["weekday_users", "weekend_users"]
    wknd_agg["weekend_to_weekday_ratio"] = (
        (wknd_agg["weekend_users"] + 1e-4) / (wknd_agg["weekday_users"] + 1e-4)
    ).clip(0.1, 5.0)
    wknd_agg = wknd_agg.reset_index()

    feat_df = pd.merge(base_agg, wknd_agg[["erbs_id", "weekend_to_weekday_ratio"]], on="erbs_id")
    feat_df["user_burstiness"] = (feat_df["p95_users"] / (feat_df["mean_users"] + 1e-4)).clip(1.0, 10.0)
    feat_df["throughput_burstiness"] = (feat_df["p95_dl_tp"] / (feat_df["mean_dl_tp"] + 1e-4)).clip(1.0, 10.0)

    return feat_df.fillna(0)


def perform_erbs_clustering(
    feat_df: pd.DataFrame,
    k_range: range = range(3, 7),
    random_state: int = 42
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Evaluates multiple cluster sizes using Silhouette Score,
    selects the best k, applies PCA, and assigns operational personas.
    """
    feature_cols = [
        "mean_users", "mean_dl_tp", "mean_ul_tp", "mean_drop_rate",
        "mean_handover_sr", "mean_availability", "weekend_to_weekday_ratio",
        "user_burstiness", "throughput_burstiness"
    ]

    X = feat_df[feature_cols].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Evaluate silhouette scores across candidate k values
    silhouette_scores = {}
    models = {}
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X_scaled)
        score = silhouette_score(X_scaled, labels)
        silhouette_scores[k] = float(score)
        models[k] = (km, labels)

    # Optimal k selection
    optimal_k = max(silhouette_scores, key=silhouette_scores.get)
    best_model, best_labels = models[optimal_k]

    # Dimensionality Reduction via PCA for 2D visualization
    pca = PCA(n_components=2, random_state=random_state)
    pca_coords = pca.fit_transform(X_scaled)

    result_df = feat_df.copy()
    result_df["cluster_id"] = best_labels
    result_df["pca_dim1"] = pca_coords[:, 0].round(4)
    result_df["pca_dim2"] = pca_coords[:, 1].round(4)

    # Dynamically assign operational persona based on cluster centroid characteristics
    cluster_profiles = {}
    for c_id in range(optimal_k):
        c_sub = result_df[result_df["cluster_id"] == c_id]
        avg_users = c_sub["mean_users"].mean()
        avg_tp = c_sub["mean_dl_tp"].mean()
        avg_ratio = c_sub["weekend_to_weekday_ratio"].mean()
        avg_ho = c_sub["mean_handover_sr"].mean()

        # Operational heuristic based on real telecom load profiles
        if avg_users > 20 and avg_tp < 7.0:
            persona = "High-Density Congested Microcell"
        elif avg_ratio < 0.90 and avg_users > 12.0:
            persona = "Commercial & Business Hub (Peak Day Load)"
        elif avg_ratio >= 1.05:
            persona = "Residential Streaming Zone (Evening & Weekend Heavy)"
        elif avg_ho < 97.0 or c_sub["throughput_burstiness"].mean() > 2.5:
            persona = "High-Mobility Transit Corridor (Heavy Handover)"
        elif avg_users < 8.0:
            persona = "Rural & Low-Density Edge (Coverage Focus)"
        else:
            persona = CLUSTER_PERSONA_MAP.get(c_id, f"Operational Cluster {c_id}")

        cluster_profiles[c_id] = {
            "persona": persona,
            "node_count": int(len(c_sub)),
            "pct_of_network": round(len(c_sub) / len(result_df) * 100, 2),
            "mean_users": round(float(avg_users), 2),
            "mean_dl_throughput_mbps": round(float(avg_tp), 2),
            "weekend_to_weekday_ratio": round(float(avg_ratio), 3),
            "mean_handover_sr": round(float(avg_ho), 2),
        }

    result_df["operational_persona"] = result_df["cluster_id"].map(
        lambda c: cluster_profiles[c]["persona"]
    )

    cluster_metadata = {
        "tested_k_scores": silhouette_scores,
        "optimal_k": optimal_k,
        "optimal_silhouette_score": silhouette_scores[optimal_k],
        "pca_variance_explained": [round(float(v), 4) for v in pca.explained_variance_ratio_],
        "total_pca_variance_explained": round(float(np.sum(pca.explained_variance_ratio_)), 4),
        "cluster_profiles": cluster_profiles
    }

    return result_df, cluster_metadata
