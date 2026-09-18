"""Layer 1 -- ingestion and landing.  Owner: E1

raw -> Parquet, partitioned by snapshot_date, with three things guaranteed on
the way through:

1. Pandera schema contracts pass (src/cvm/ingest/schemas.py).
2. Exact duplicates are dropped -- the UCI set carries ~300 (~9.5%).
3. Every identifier is SHA-256 + salt. No raw MSISDN survives this layer.
"""