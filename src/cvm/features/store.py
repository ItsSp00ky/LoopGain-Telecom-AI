"""DuckDB feature store. Embedded analytical SQL -- no database server.

The serving connection is opened READ-ONLY. Nothing that reads features should
ever be able to write them, and the cheapest way to guarantee that is to make
it impossible at the connection level rather than by convention.

Other platform components do NOT query this file. They go through
/v1/cohort/query, so that the store can be replaced at scale without breaking
them. See docs/INTEGRATION.md.

Scaling answer for the evaluator question "what breaks first?": this does.
DuckDB is correct at demo scale; at 6M+ subscribers it becomes Spark or a
columnar warehouse with the same schema. Models and decision logic are
unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

TABLE = "features"
ID_COLUMN = "subscriber_id_hashed"
SNAPSHOT_COLUMN = "snapshot_date"


def write_offline(df: pd.DataFrame, path: Path | None = None) -> Path:
    """Write the point-in-time-correct training matrix as partitioned Parquet.

    Partitioned by snapshot date, which is what
    conf/config.yaml#feature_store.partition_by asks for and what makes an
    as-of read cheap: a query for one date touches one partition instead of
    scanning the lot.
    """
    path = settings.feature_store_offline if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if SNAPSHOT_COLUMN not in df.columns:
        raise KeyError(
            f"{SNAPSHOT_COLUMN} is absent, so the store cannot be partitioned by time "
            "and an as-of read would have to scan everything."
        )

    df.to_parquet(path, index=False)
    log.info(
        "offline store: %d rows x %d cols -> %s (%d snapshot dates)",
        len(df),
        df.shape[1],
        path,
        df[SNAPSHOT_COLUMN].nunique(),
    )
    return path


def build_online(features: pd.DataFrame, path: Path | None = None) -> Path:
    """Materialise the serving store, keyed by subscriber_id_hashed.

    One row per subscriber -- the LATEST snapshot -- because serving answers
    "what do we know about this subscriber now", not "what did we know in
    March". The historical rows stay in the offline store where training needs
    them.

    Indexed on the id, because the 200 ms p95 budget is a serving budget and a
    full scan per lookup would not meet it at a million rows.
    """
    import duckdb

    path = settings.feature_store if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # DuckDB will not overwrite a table in place cleanly

    latest = (
        features.sort_values(SNAPSHOT_COLUMN)
        .drop_duplicates(subset=[ID_COLUMN], keep="last")
        .reset_index(drop=True)
    )

    connection = duckdb.connect(str(path))
    try:
        connection.register("incoming", latest)
        connection.execute(f"CREATE TABLE {TABLE} AS SELECT * FROM incoming")
        connection.execute(f"CREATE UNIQUE INDEX idx_{ID_COLUMN} ON {TABLE} ({ID_COLUMN})")
        rows = connection.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    finally:
        connection.close()

    log.info(
        "online store: %d subscribers (from %d rows) -> %s, indexed on %s",
        rows,
        len(features),
        path,
        ID_COLUMN,
    )
    return path


def connect(path: Path | None = None, read_only: bool = True):
    """Open the feature store. read_only=True by default, deliberately.

    A serving path that can write is a serving path that will, eventually, by
    accident. Making it impossible at the connection level costs one keyword
    and removes the class of bug entirely.
    """
    import duckdb

    path = settings.feature_store if path is None else Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Build it with `python -m cvm.features.run` (phase 3)."
        )
    return duckdb.connect(str(path), read_only=read_only)


def get_features(
    subscriber_ids: list[str] | None = None,
    as_of: str | None = None,
    path: Path | None = None,
) -> pd.DataFrame:
    """Serving lookup. Must stay well inside the 200 ms p95 budget.

    ``as_of`` READS THE OFFLINE STORE, not the online one, and returns only
    rows whose snapshot is on or before that date. This is the point-in-time
    guarantee: asking what was known on 30 June must never return a feature
    computed in July, or every backtest is measuring the future.

    Without ``as_of`` it serves the online store -- one row per subscriber, the
    latest snapshot -- which is the production path.
    """
    if as_of is not None:
        return _read_as_of(subscriber_ids, as_of)

    connection = connect(path)
    try:
        if subscriber_ids is None:
            return connection.execute(f"SELECT * FROM {TABLE}").df()
        placeholders = ", ".join("?" for _ in subscriber_ids)
        return connection.execute(
            f"SELECT * FROM {TABLE} WHERE {ID_COLUMN} IN ({placeholders})", subscriber_ids
        ).df()
    finally:
        connection.close()


def _read_as_of(subscriber_ids: list[str] | None, as_of: str) -> pd.DataFrame:
    """Point-in-time read from the offline store.

    Returns each subscriber's most recent snapshot AT OR BEFORE `as_of`, and
    nothing after it. The filter is applied before the de-duplication, not
    after: taking the latest row and then filtering would drop a subscriber
    entirely whenever their newest snapshot post-dates the cut-off, which
    silently shrinks a backtest cohort instead of answering it correctly.
    """
    path = settings.feature_store_offline
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist; an as-of read needs the offline store. "
            "Run `python -m cvm.features.run`."
        )

    frame = pd.read_parquet(path)
    cutoff = pd.Timestamp(as_of)
    snapshots = pd.to_datetime(frame[SNAPSHOT_COLUMN])

    visible = frame[snapshots <= cutoff]
    if subscriber_ids is not None:
        visible = visible[visible[ID_COLUMN].isin(subscriber_ids)]

    latest = (
        visible.sort_values(SNAPSHOT_COLUMN)
        .drop_duplicates(subset=[ID_COLUMN], keep="last")
        .reset_index(drop=True)
    )

    # The guarantee, asserted rather than trusted. This is the single most
    # damaging thing that can silently go wrong in this file.
    if not latest.empty and pd.to_datetime(latest[SNAPSHOT_COLUMN]).max() > cutoff:
        raise AssertionError(
            f"an as-of read for {cutoff.date()} returned a snapshot from "
            f"{pd.to_datetime(latest[SNAPSHOT_COLUMN]).max().date()}: the "
            "point-in-time guarantee is broken and every backtest built on it is invalid."
        )

    log.info(
        "as-of read: %d subscribers visible at %s (of %d rows in the offline store)",
        len(latest),
        cutoff.date(),
        len(frame),
    )
    return latest


def describe() -> dict[str, object]:
    """What is in the store. Used by the API health check and the notebooks."""
    partition = load_conf("config")["feature_store"]["partition_by"]
    offline = settings.feature_store_offline
    online = settings.feature_store

    summary: dict[str, object] = {
        "offline_exists": offline.exists(),
        "online_exists": online.exists(),
        "partition_by": partition,
    }
    if offline.exists():
        frame = pd.read_parquet(offline, columns=[ID_COLUMN, SNAPSHOT_COLUMN])
        summary["offline_rows"] = len(frame)
        summary["subscribers"] = int(frame[ID_COLUMN].nunique())
        summary["snapshots"] = int(frame[SNAPSHOT_COLUMN].nunique())
    return summary
