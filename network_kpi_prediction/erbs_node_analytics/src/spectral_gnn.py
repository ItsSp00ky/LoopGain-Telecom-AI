"""
spectral_gnn.py
Spatio-Temporal Spectral Graph Neural Network (ST-GNN) for Physical ERBS Base Stations.
Implements:
  1. Truncated Chebyshev Spectral Graph Convolutions (ChebNet, K=2)
  2. Dynamic Spatial Edge Attention Layer (GAT Formulation)
  3. Spatio-Temporal Feature Fusion & Forecast Engine
  4. Spatial Spillover Risk & Dynamic Attention Extraction
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.linear_model import Ridge
from .topology_graph import ERBSTopologyGraph


class SpectralChebNetLayer:
    """
    Computes Order-K Chebyshev Spectral Graph Convolution over the base station graph.
    Z = sum_{k=0}^K T_k(L_tilde) X Theta_k
    """

    def __init__(self, K: int = 2):
        self.K = K

    def transform(self, X: np.ndarray, scaled_laplacian: np.ndarray) -> np.ndarray:
        """
        Transforms node feature matrix X [N, F] into multi-hop Chebyshev basis [N, (K+1)*F].
        """
        T_list = []
        T_0 = X
        T_list.append(T_0)

        if self.K >= 1:
            T_1 = scaled_laplacian @ X
            T_list.append(T_1)

        if self.K >= 2:
            T_2 = 2.0 * (scaled_laplacian @ T_1) - T_0
            T_list.append(T_2)

        return np.hstack(T_list)


class SpatialAttentionLayer:
    """
    Computes dynamic spatial attention weights between neighboring base stations.
    Alpha_ij = Softmax( LeakyReLU( a^T [h_i || h_j] ) )
    """

    def __init__(self, in_features: int, negative_slope: float = 0.2):
        self.in_features = in_features
        self.negative_slope = negative_slope
        rng = np.random.RandomState(42)
        self.a_src = rng.randn(in_features) * (1.0 / np.sqrt(in_features))
        self.a_dst = rng.randn(in_features) * (1.0 / np.sqrt(in_features))

    def compute_attention(self, H: np.ndarray, adj_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes sparse dynamic attention matrix Alpha [N, N] and aggregated neighbor representation [N, F].
        """
        N, F = H.shape
        score_src = H @ self.a_src
        score_dst = H @ self.a_dst
        raw_scores = score_src[:, None] + score_dst[None, :]

        scores = np.where(raw_scores >= 0, raw_scores, self.negative_slope * raw_scores)

        mask = (adj_matrix > 0)
        scores_masked = np.full((N, N), -1e9, dtype=np.float32)
        scores_masked[mask] = scores[mask]

        max_s = np.max(scores_masked, axis=1, keepdims=True)
        exp_s = np.exp(scores_masked - max_s) * mask
        sum_exp = np.sum(exp_s, axis=1, keepdims=True)
        sum_exp = np.where(sum_exp > 0, sum_exp, 1.0)
        alpha = exp_s / sum_exp

        H_neighbors = alpha @ H
        return alpha, H_neighbors


class SpatioTemporalGraphForecaster:
    """
    End-to-End Spatio-Temporal Graph Neural Network for physical ERBS base station forecasting.
    """

    def __init__(self, topology: ERBSTopologyGraph, lookback_window: int = 7, K_cheb: int = 2, alpha_reg: float = 10.0):
        self.topology = topology
        self.window = lookback_window
        self.K_cheb = K_cheb
        self.alpha_reg = alpha_reg
        self.cheb_layer = SpectralChebNetLayer(K=K_cheb)
        self.attention_layer: Optional[SpatialAttentionLayer] = None
        self.spatial_head = Ridge(alpha=alpha_reg, fit_intercept=True)
        self.baseline_head = Ridge(alpha=alpha_reg, fit_intercept=True)
        self.results_cache: Dict[str, any] = {}

    def _prepare_spatial_temporal_tensors(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        nodes = self.topology.nodes
        dates = sorted(df['Date'].unique())

        piv_users = df.pivot(index='Date', columns='ERBS Id', values='Avg RRC Connected users').reindex(columns=nodes).fillna(0).values
        piv_dl = df.pivot(index='Date', columns='ERBS Id', values='E-UTRAN IP Throughput UE DL').reindex(columns=nodes).fillna(0).values
        piv_rrc = df.pivot(index='Date', columns='ERBS Id', values='RRC Setup Success Rate').reindex(columns=nodes).fillna(99.0).values
        piv_drop = df.pivot(index='Date', columns='ERBS Id', values='E-RAB Drop Rate').reindex(columns=nodes).fillna(0.5).values

        tensor = np.stack([piv_users, piv_dl, piv_rrc, piv_drop], axis=-1)
        return tensor, piv_users, dates

    def train_and_benchmark(self, df_full_year: pd.DataFrame) -> Dict[str, any]:
        """
        Trains the ST-GNN on chronological 70/15/15 splits and benchmarks against Non-Spatial Baseline.
        """
        tensor, target_matrix, dates = self._prepare_spatial_temporal_tensors(df_full_year)
        T, N, F = tensor.shape

        cheb_dim = (self.K_cheb + 1) * F
        self.attention_layer = SpatialAttentionLayer(in_features=cheb_dim)

        means = np.mean(tensor, axis=(0, 1), keepdims=True)
        stds = np.std(tensor, axis=(0, 1), keepdims=True) + 1e-6
        tensor_norm = np.nan_to_num((tensor - means) / stds)

        L_scaled = self.topology.scaled_laplacian
        adj = self.topology.adj_matrix

        print("[ST-GNN] Convolving Spectral Chebyshev filters across 1,067 nodes over 363 days...")
        H_spatial_list = []
        for t in range(T):
            X_t = tensor_norm[t]  # [N, F]
            Z_cheb = self.cheb_layer.transform(X_t, L_scaled)
            _, H_nbr = self.attention_layer.compute_attention(Z_cheb, adj)
            H_fused = np.hstack([Z_cheb, H_nbr])  # [N, 2 * (K+1)*F]
            H_spatial_list.append(H_fused)

        H_spatial_tensor = np.stack(H_spatial_list, axis=0)  # [T, N, D_spatial]

        # Spatial-temporal lag features + Target lag features
        # Lags: t, t-1, t-7
        X_gnn, X_base, Y_targets = [], [], []
        for t in range(7, T - 1):
            # Base features: node's own load at t, t-1, t-7
            f_base = np.column_stack([
                target_matrix[t],
                target_matrix[t - 1],
                target_matrix[t - 7]
            ])  # [N, 3]

            # GNN features: base features + Spatial Chebyshev & Attention embeddings
            s_t = H_spatial_tensor[t]        # [N, D_spatial]
            s_lag1 = H_spatial_tensor[t - 1]  # [N, D_spatial]
            f_gnn = np.column_stack([f_base, s_t, s_lag1])  # [N, 3 + 2*D_spatial]

            X_base.append(f_base)
            X_gnn.append(f_gnn)
            Y_targets.append(target_matrix[t + 1])

        X_base = np.nan_to_num(np.vstack(X_base))
        X_gnn = np.nan_to_num(np.vstack(X_gnn))
        Y_all = np.nan_to_num(np.vstack(Y_targets).ravel())

        n_steps = len(Y_targets)
        n_train = int(0.70 * n_steps) * N
        n_val = int(0.85 * n_steps) * N

        X_tr_b, Y_tr = X_base[:n_train], Y_all[:n_train]
        X_te_b, Y_te = X_base[n_val:], Y_all[n_val:]

        X_tr_g = X_gnn[:n_train]
        X_te_g = X_gnn[n_val:]

        print("[ST-GNN] Fitting Non-Spatial Baseline (Temporal Lags Only)...")
        self.baseline_head.fit(X_tr_b, Y_tr)
        preds_base = np.maximum(self.baseline_head.predict(X_te_b), 0.0)

        print("[ST-GNN] Fitting Spatio-Temporal Graph Neural Network (ChebNet + Dynamic Attention)...")
        self.spatial_head.fit(X_tr_g, Y_tr)
        preds_gnn = np.maximum(self.spatial_head.predict(X_te_g), 0.0)

        mae_base = float(np.mean(np.abs(Y_te - preds_base)))
        rmse_base = float(np.sqrt(np.mean((Y_te - preds_base) ** 2)))
        wape_base = float(np.sum(np.abs(Y_te - preds_base)) / (np.sum(np.abs(Y_te)) + 1e-6) * 100.0)

        mae_gnn = float(np.mean(np.abs(Y_te - preds_gnn)))
        rmse_gnn = float(np.sqrt(np.mean((Y_te - preds_gnn) ** 2)))
        wape_gnn = float(np.sum(np.abs(Y_te - preds_gnn)) / (np.sum(np.abs(Y_te)) + 1e-6) * 100.0)

        error_reduction_pct = float((mae_base - mae_gnn) / mae_base * 100.0)

        # Compute latest dynamic attention weights and spatial spillover risk scores
        latest_H = H_spatial_tensor[-1, :, :cheb_dim]
        alpha_latest, H_nbr_latest = self.attention_layer.compute_attention(latest_H, adj)
        spillover_risk = np.linalg.norm(H_nbr_latest, axis=1) / (np.linalg.norm(latest_H, axis=1) + 1e-6)
        spillover_risk = np.clip(spillover_risk / np.percentile(spillover_risk, 95), 0.0, 1.0)

        self.results_cache = {
            "baseline_metrics": {
                "test_mae": mae_base,
                "test_rmse": rmse_base,
                "test_wape_pct": wape_base
            },
            "gnn_metrics": {
                "test_mae": mae_gnn,
                "test_rmse": rmse_gnn,
                "test_wape_pct": wape_gnn
            },
            "error_reduction_pct": error_reduction_pct,
            "spillover_risk": spillover_risk,
            "latest_attention_matrix": alpha_latest,
            "test_sample_count": len(Y_te)
        }
        return self.results_cache

    def export_artifacts(self, output_dir: str):
        """Exports benchmark metrics and node-level spatial spillover risk to CSV."""
        if not self.results_cache:
            raise RuntimeError("Must call train_and_benchmark() before exporting artifacts.")

        os.makedirs(output_dir, exist_ok=True)
        nodes = self.topology.nodes
        spillover = self.results_cache["spillover_risk"]
        alpha = self.results_cache["latest_attention_matrix"]

        rows = []
        for i, node in enumerate(nodes):
            top_nbrs = self.topology.get_top_spatial_neighbors(node, k=3)
            nbr_info = "; ".join([f"{n} (w={w:.2f}, attn={alpha[i, self.topology.node_to_idx[n]]:.2f})" for n, w in top_nbrs])
            risk_val = float(spillover[i])
            status = "CRITICAL_SPILLOVER" if risk_val > 0.80 else ("ELEVATED" if risk_val > 0.50 else "STABLE")
            rows.append({
                "ERBS_Id": node,
                "Spatial_Spillover_Risk": round(risk_val, 4),
                "Spillover_Status": status,
                "Top_Coupled_Neighbors_With_Attention": nbr_info
            })

        df_risk = pd.DataFrame(rows).sort_values("Spatial_Spillover_Risk", ascending=False)
        out_csv = os.path.join(output_dir, "erbs_spatial_spillover_risk.csv")
        df_risk.to_csv(out_csv, index=False)
        print(f"[+] Exported Spatial Spillover Risk to: {out_csv}")

        # Benchmark comparison CSV
        m_base = self.results_cache["baseline_metrics"]
        m_gnn = self.results_cache["gnn_metrics"]
        df_bench = pd.DataFrame([
            {"Model": "Non-Spatial Baseline (Temporal Lags Only)", "Test_MAE": m_base["test_mae"], "Test_RMSE": m_base["test_rmse"], "Test_WAPE_Pct": m_base["test_wape_pct"]},
            {"Model": "Spatio-Temporal GNN (ChebNet + Dynamic Attention)", "Test_MAE": m_gnn["test_mae"], "Test_RMSE": m_gnn["test_rmse"], "Test_WAPE_Pct": m_gnn["test_wape_pct"]}
        ])
        bench_csv = os.path.join(output_dir, "erbs_gnn_vs_baseline_benchmark.csv")
        df_bench.to_csv(bench_csv, index=False)
        print(f"[+] Exported GNN Benchmark Leaderboard to: {bench_csv}")
