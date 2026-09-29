"""
topology_graph.py
Physical ERBS Base Station Topology Graph Construction Engine (Zero-GPS).
Builds a multi-relational Adjacency Matrix and Graph Laplacian across all 1,067 nodes
using historical telemetry co-movement, handover coupling, and toponymic sector clustering.
"""

import os
import re
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional


class ERBSTopologyGraph:
    """
    Constructs and manages the spatial/topological adjacency graph for the 1,067 physical base stations.
    """

    def __init__(self, top_k_neighbors: int = 8, sigma: float = 1.0):
        self.top_k = top_k_neighbors
        self.sigma = sigma
        self.nodes: List[str] = []
        self.node_to_idx: Dict[str, int] = {}
        self.idx_to_node: Dict[int, str] = {}
        self.adj_matrix: Optional[np.ndarray] = None
        self.laplacian_norm: Optional[np.ndarray] = None
        self.scaled_laplacian: Optional[np.ndarray] = None
        self.neighbor_cache: Dict[str, List[Tuple[str, float]]] = {}

    def fit(self, df_full_year: pd.DataFrame, alpha_cov: float = 0.60, alpha_ho: float = 0.25, alpha_topo: float = 0.15) -> "ERBSTopologyGraph":
        """
        Builds the composite multi-relational adjacency matrix from historical ERBS telemetry.
        """
        # 1. Index unique base stations
        self.nodes = sorted(df_full_year['ERBS Id'].dropna().unique().tolist())
        self.node_to_idx = {node: i for i, node in enumerate(self.nodes)}
        self.idx_to_node = {i: node for i, node in enumerate(self.nodes)}
        N = len(self.nodes)

        # 2. Compute Telemetry Co-Movement Affinity Matrix (A_cov)
        # Multi-metric matrix: active users, DL throughput, and handover SR
        piv_users = df_full_year.pivot(index='Date', columns='ERBS Id', values='Avg RRC Connected users').reindex(columns=self.nodes).fillna(0)
        piv_dl = df_full_year.pivot(index='Date', columns='ERBS Id', values='E-UTRAN IP Throughput UE DL').reindex(columns=self.nodes).fillna(0)

        # Normalize across time for each node
        u_norm = (piv_users - piv_users.mean(axis=0)) / (piv_users.std(axis=0) + 1e-6)
        dl_norm = (piv_dl - piv_dl.mean(axis=0)) / (piv_dl.std(axis=0) + 1e-6)

        # Combined profile matrix: [2 * T, N]
        combined_profiles = np.vstack([u_norm.values, dl_norm.values])  # shape: (2T, N)
        combined_profiles = np.nan_to_num(combined_profiles, nan=0.0)

        # Pairwise Euclidean distance between node telemetry trajectories
        # ||x_i - x_j||^2 = ||x_i||^2 + ||x_j||^2 - 2 x_i^T x_j
        dot_prod = np.dot(combined_profiles.T, combined_profiles)
        sq_norms = np.diag(dot_prod)
        dist_sq = np.maximum(sq_norms[:, None] + sq_norms[None, :] - 2 * dot_prod, 0.0)
        
        # Scale distances to median for numerical stability
        median_dist = np.median(dist_sq) + 1e-6
        A_cov_dense = np.exp(-dist_sq / (2.0 * (self.sigma ** 2) * median_dist))
        np.fill_diagonal(A_cov_dense, 0.0)

        # Enforce k-NN sparsity on covariance graph
        A_cov = np.zeros((N, N), dtype=np.float32)
        for i in range(N):
            top_indices = np.argsort(A_cov_dense[i, :])[-self.top_k:]
            A_cov[i, top_indices] = A_cov_dense[i, top_indices]
        A_cov = 0.5 * (A_cov + A_cov.T)

        # 3. Compute Handover Coupling Matrix (A_ho)
        # Nodes with high handover SR share mobility boundaries
        ho_sr = df_full_year.groupby('ERBS Id')['Handover Success Rate ( 4G Intra System)'].mean().reindex(self.nodes).fillna(95.0).values
        avg_users = df_full_year.groupby('ERBS Id')['Avg RRC Connected users'].mean().reindex(self.nodes).fillna(1.0).values
        ho_weights = (ho_sr / 100.0) * np.log1p(avg_users)
        
        # Mobility interaction outer product conditioned on cov neighbors
        A_ho = (A_cov > 0).astype(float) * np.outer(ho_weights, ho_weights)
        if np.max(A_ho) > 0:
            A_ho = A_ho / np.max(A_ho)
        A_ho = 0.5 * (A_ho + A_ho.T)
        np.fill_diagonal(A_ho, 0.0)

        # 4. Compute Toponymic / Naming Cluster Affinity (A_topo)
        A_topo = np.zeros((N, N), dtype=np.float32)
        prefixes = [re.match(r'^([A-Za-z]+)', node).group(1) if re.match(r'^([A-Za-z]+)', node) else 'UNK' for node in self.nodes]
        for i in range(N):
            p_i = prefixes[i]
            for j in range(i + 1, N):
                if p_i == prefixes[j]:
                    A_topo[i, j] = 0.5
                    A_topo[j, i] = 0.5
        # Intersect topo with cov to ensure physical plausibility
        A_topo = A_topo * (A_cov > 0).astype(float)

        # 5. Composite Adjacency Matrix
        A_comp = alpha_cov * A_cov + alpha_ho * A_ho + alpha_topo * A_topo
        np.fill_diagonal(A_comp, 0.0)
        self.adj_matrix = A_comp

        # 6. Normalized Graph Laplacian: L = I - D^(-1/2) A D^(-1/2)
        deg = np.sum(A_comp, axis=1)
        deg_inv_sqrt = np.zeros_like(deg, dtype=np.float32)
        pos_mask = deg > 0
        deg_inv_sqrt[pos_mask] = 1.0 / np.sqrt(deg[pos_mask])
        D_inv_sqrt = np.diag(deg_inv_sqrt)

        I = np.eye(N, dtype=np.float32)
        L_norm = I - D_inv_sqrt @ A_comp @ D_inv_sqrt
        self.laplacian_norm = L_norm

        # 7. Scaled Laplacian for Chebyshev polynomial filters: L_tilde = (2 / lambda_max) * L - I
        # For normalized Laplacian, lambda_max <= 2, so L_tilde = L - I
        self.scaled_laplacian = L_norm - I

        # Precompute top neighbors cache for fast inspection
        self._build_neighbor_cache()
        return self

    def _build_neighbor_cache(self):
        N = len(self.nodes)
        for i, node in enumerate(self.nodes):
            row = self.adj_matrix[i, :]
            top_idx = np.argsort(row)[::-1][:self.top_k]
            neighbors = [(self.idx_to_node[j], float(row[j])) for j in top_idx if row[j] > 0]
            self.neighbor_cache[node] = neighbors

    def get_top_spatial_neighbors(self, erbs_id: str, k: int = 5) -> List[Tuple[str, float]]:
        """Returns the top-k most strongly coupled topological neighbor towers."""
        if erbs_id not in self.neighbor_cache:
            return []
        return self.neighbor_cache[erbs_id][:k]

    def get_graph_summary(self) -> Dict[str, float]:
        """Returns key structural metrics of the 1,067-node base station topology graph."""
        if self.adj_matrix is None:
            return {}
        N = len(self.nodes)
        num_edges = int(np.count_nonzero(self.adj_matrix) / 2)
        degrees = np.count_nonzero(self.adj_matrix, axis=1)
        return {
            "node_count": float(N),
            "edge_count": float(num_edges),
            "graph_density": float(num_edges / (N * (N - 1) / 2.0)),
            "mean_degree": float(np.mean(degrees)),
            "max_degree": float(np.max(degrees)),
            "min_degree": float(np.min(degrees)),
            "connected_components_estimate": float(np.sum(degrees == 0))
        }

    def export_topology_summary(self, out_path: str):
        """Exports the top topological neighbors for all base stations to CSV."""
        rows = []
        for node in self.nodes:
            nbrs = self.get_top_spatial_neighbors(node, k=5)
            nbr_str = "; ".join([f"{n} ({w:.3f})" for n, w in nbrs])
            degree = len(self.neighbor_cache.get(node, []))
            top_coupling = nbrs[0][1] if nbrs else 0.0
            rows.append({
                "ERBS_Id": node,
                "Topological_Degree": degree,
                "Strongest_Coupled_Neighbor": nbrs[0][0] if nbrs else "None",
                "Max_Edge_Weight": round(top_coupling, 4),
                "Top_Spatial_Neighbors": nbr_str
            })
        df_out = pd.DataFrame(rows)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        df_out.to_csv(out_path, index=False)
        print(f"[+] Exported Base Station Topology Graph to: {out_path}")
