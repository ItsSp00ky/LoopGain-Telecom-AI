import sys
import os
import unittest
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd

_TEST_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _TEST_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from src.node_profiler import (
    calculate_health_index, profile_all_erbs_nodes, SLA_THRESHOLDS
)
from src.node_clustering import (
    build_clustering_features, perform_erbs_clustering
)
from src.summer_stress import (
    compute_summer_stress_benchmark
)
from src.export_synergy import (
    export_cross_subsystem_targets
)
from src.topology_graph import ERBSTopologyGraph
from src.spectral_gnn import (
    SpectralChebNetLayer, SpatialAttentionLayer, SpatioTemporalGraphForecaster
)


class TestERBSNodeAnalytics(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        n_days = 30
        dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
        nodes = ["NODE_A", "NODE_B", "NODE_SLEEPING", "NODE_DEGRADED"]

        records = []
        for node in nodes:
            for d in dates:
                if node == "NODE_A": # Healthy Commercial
                    rrc = np.random.uniform(99.6, 99.9)
                    erab_drop = np.random.uniform(0.1, 0.3)
                    avail = np.random.uniform(98.0, 100.0)
                    dl_tp = np.random.uniform(12.0, 20.0)
                    users = np.random.uniform(15.0, 25.0)
                elif node == "NODE_B": # Healthy Residential
                    rrc = np.random.uniform(99.5, 99.8)
                    erab_drop = np.random.uniform(0.1, 0.4)
                    avail = np.random.uniform(97.0, 99.5)
                    dl_tp = np.random.uniform(8.0, 14.0)
                    users = np.random.uniform(10.0, 18.0)
                elif node == "NODE_SLEEPING": # Sleeping Cell (High avail, low throughput, high drop)
                    rrc = np.random.uniform(94.0, 97.0)
                    erab_drop = np.random.uniform(1.5, 3.5)
                    avail = 99.0
                    dl_tp = np.random.uniform(0.5, 1.5)
                    users = np.random.uniform(1.0, 3.0)
                else: # Degraded
                    rrc = np.random.uniform(95.0, 98.0)
                    erab_drop = np.random.uniform(0.8, 1.8)
                    avail = np.random.uniform(80.0, 90.0)
                    dl_tp = np.random.uniform(3.0, 6.0)
                    users = np.random.uniform(5.0, 10.0)

                records.append({
                    "date": d,
                    "erbs_id": node,
                    "rrc_setup_sr": rrc,
                    "erab_estab_sr": 99.6,
                    "erab_drop_rate": erab_drop,
                    "handover_intra_sr": 0.98,
                    "handover_sr": 98.0,
                    "cell_availability_pct": avail,
                    "dl_throughput_mbps": dl_tp,
                    "ul_throughput_mbps": 1.2,
                    "connected_users": users
                })

        self.df_synthetic = pd.DataFrame(records)

    def test_health_index_bounds_and_ranking(self):
        profile_df, stats = profile_all_erbs_nodes(self.df_synthetic, contamination=0.25)
        self.assertEqual(len(profile_df), 4)

        # Ensure Health Index is bounded within [0, 100]
        self.assertTrue((profile_df["health_index"] >= 0).all())
        self.assertTrue((profile_df["health_index"] <= 100).all())

        # NODE_A should score significantly higher than NODE_SLEEPING
        score_a = profile_df[profile_df["erbs_id"] == "NODE_A"]["health_index"].iloc[0]
        score_sleeping = profile_df[profile_df["erbs_id"] == "NODE_SLEEPING"]["health_index"].iloc[0]
        self.assertGreater(score_a, score_sleeping)

        # Sleeping cell detector should flag NODE_SLEEPING
        sleeping_flag = profile_df[profile_df["erbs_id"] == "NODE_SLEEPING"]["is_sleeping_cell"].iloc[0]
        self.assertTrue(sleeping_flag)

    def test_behavioral_clustering_personas(self):
        feat_df = build_clustering_features(self.df_synthetic)
        cluster_df, meta = perform_erbs_clustering(feat_df, k_range=range(2, 4))

        self.assertIn("cluster_id", cluster_df.columns)
        self.assertIn("operational_persona", cluster_df.columns)
        self.assertIn("pca_dim1", cluster_df.columns)
        self.assertIn("pca_dim2", cluster_df.columns)
        self.assertTrue(len(meta["cluster_profiles"]) >= 2)

    def test_summer_stress_benchmark(self):
        # Create a summer dataframe where throughput drops
        summer_df = self.df_synthetic.copy()
        summer_df["dl_throughput_mbps"] = summer_df["dl_throughput_mbps"] * 0.70
        summer_df["erab_drop_rate"] = summer_df["erab_drop_rate"] * 1.5

        stress_df, stats = compute_summer_stress_benchmark(self.df_synthetic, summer_df)
        self.assertEqual(len(stress_df), 4)
        self.assertIn("delta_dl_throughput_mbps", stress_df.columns)
        self.assertTrue((stress_df["delta_dl_throughput_mbps"] < 0).all())

    def test_cross_subsystem_exports(self):
        profile_df, _ = profile_all_erbs_nodes(self.df_synthetic, contamination=0.25)
        feat_df = build_clustering_features(self.df_synthetic)
        cluster_df, _ = perform_erbs_clustering(feat_df, k_range=range(2, 4))

        with tempfile.TemporaryDirectory() as tmpdir:
            res = export_cross_subsystem_targets(profile_df, cluster_df, tmpdir)
            self.assertTrue(Path(res["antenna_targets_path"]).exists())
            self.assertTrue(Path(res["churn_targets_path"]).exists())

    def test_topology_graph_construction(self):
        # Build topology from synthetic dataset
        raw_df = pd.DataFrame({
            "Date": self.df_synthetic["date"].astype(str),
            "ERBS Id": self.df_synthetic["erbs_id"],
            "Avg RRC Connected users": self.df_synthetic["connected_users"],
            "E-UTRAN IP Throughput UE DL": self.df_synthetic["dl_throughput_mbps"],
            "Handover Success Rate ( 4G Intra System)": self.df_synthetic["handover_intra_sr"] * 100.0,
            "RRC Setup Success Rate": self.df_synthetic["rrc_setup_sr"],
            "E-RAB Drop Rate": self.df_synthetic["erab_drop_rate"]
        })
        topo = ERBSTopologyGraph(top_k_neighbors=2)
        topo.fit(raw_df)
        self.assertEqual(len(topo.nodes), 4)
        self.assertEqual(topo.adj_matrix.shape, (4, 4))
        # Zero self-loops
        self.assertTrue((np.diag(topo.adj_matrix) == 0.0).all())
        # Symmetrized
        self.assertTrue(np.allclose(topo.adj_matrix, topo.adj_matrix.T))
        # Normalized Laplacian diagonal should be close to 1.0 for connected nodes
        self.assertEqual(topo.laplacian_norm.shape, (4, 4))

    def test_chebnet_spectral_filtering(self):
        N, F = 4, 3
        X = np.random.randn(N, F).astype(np.float32)
        scaled_L = np.random.randn(N, N).astype(np.float32)
        layer = SpectralChebNetLayer(K=2)
        Z = layer.transform(X, scaled_L)
        # Output channels: (K+1)*F = 3*3 = 9
        self.assertEqual(Z.shape, (N, 9))
        self.assertTrue(np.isfinite(Z).all())

    def test_spatial_attention_layer(self):
        N, F = 4, 6
        H = np.random.randn(N, F).astype(np.float32)
        adj = np.array([
            [0, 1, 1, 0],
            [1, 0, 0, 1],
            [1, 0, 0, 1],
            [0, 1, 1, 0]
        ], dtype=np.float32)
        attn = SpatialAttentionLayer(in_features=F)
        alpha, H_nbr = attn.compute_attention(H, adj)
        self.assertEqual(alpha.shape, (N, N))
        self.assertEqual(H_nbr.shape, (N, F))
        # Each row with edges must sum to 1.0
        row_sums = np.sum(alpha, axis=1)
        self.assertTrue(np.allclose(row_sums, [1.0, 1.0, 1.0, 1.0]))

    def test_end_to_end_gnn_forecasting(self):
        raw_df = pd.DataFrame({
            "Date": self.df_synthetic["date"].astype(str),
            "ERBS Id": self.df_synthetic["erbs_id"],
            "Avg RRC Connected users": self.df_synthetic["connected_users"],
            "E-UTRAN IP Throughput UE DL": self.df_synthetic["dl_throughput_mbps"],
            "Handover Success Rate ( 4G Intra System)": self.df_synthetic["handover_intra_sr"] * 100.0,
            "RRC Setup Success Rate": self.df_synthetic["rrc_setup_sr"],
            "E-RAB Drop Rate": self.df_synthetic["erab_drop_rate"]
        })
        topo = ERBSTopologyGraph(top_k_neighbors=2)
        topo.fit(raw_df)
        gnn = SpatioTemporalGraphForecaster(topology=topo, lookback_window=7, K_cheb=2)
        res = gnn.train_and_benchmark(raw_df)

        self.assertIn("baseline_metrics", res)
        self.assertIn("gnn_metrics", res)
        self.assertIn("spillover_risk", res)
        # Spillover scores must be bounded in [0, 1]
        self.assertTrue((res["spillover_risk"] >= 0.0).all())
        self.assertTrue((res["spillover_risk"] <= 1.0).all())

        with tempfile.TemporaryDirectory() as tmpdir:
            gnn.export_artifacts(tmpdir)
            self.assertTrue(Path(tmpdir, "erbs_spatial_spillover_risk.csv").exists())
            self.assertTrue(Path(tmpdir, "erbs_gnn_vs_baseline_benchmark.csv").exists())


if __name__ == "__main__":
    unittest.main()
