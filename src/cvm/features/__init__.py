"""Layer 3 -- transform and feature store.  Owner: E1

Produces two artefacts:

    features_offline.parquet   point-in-time correct, for training
    features_online.duckdb     serving + RAG retrieval, keyed by hash

All features are computed over an observation window ending strictly before the
label window opens. Splits are temporal, never random. Any field used to
generate the synthetic label is excluded. tests/leakage/ enforces all three,
and that job is required in CI.
"""
