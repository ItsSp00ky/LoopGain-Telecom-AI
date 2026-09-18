"""Layer 3 -- transform and feature store.  Owner: E1

Produces three artefacts:

    features_offline.parquet   point-in-time correct, for training
    sequences_offline.npz      90 x k daily tensors, for the M1 LSTM
    features_online.duckdb     serving + RAG retrieval, keyed by hash

All features are computed over an observation window ending strictly before the
label window opens. Splits are temporal, never random. Any field used to
generate the synthetic label is excluded. tests/leakage/ enforces all three,
and that job is required in CI.
"""