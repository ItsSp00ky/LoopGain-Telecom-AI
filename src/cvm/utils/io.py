"""Parquet helpers. Thin on purpose.

Every read and write in the project goes through these two functions so that
the compression, the index handling and the directory creation are decided
once. A module that calls `to_parquet` directly is a module that will one day
write an index column nothing else expects.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def write_parquet(df: pd.DataFrame, path: Path | str, *, index: bool = False) -> Path:
    """Write, creating the parent directory. Index dropped unless asked for.

    A pandas RangeIndex written to Parquet comes back as a column called
    `__index_level_0__`, which then appears in a feature matrix and is a
    perfectly good predictor of nothing at all.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=index)
    log.debug("wrote %d x %d to %s", len(df), df.shape[1], path)
    return path


def read_parquet(path: Path | str, columns: list[str] | None = None) -> pd.DataFrame:
    """Read, with a message that names the missing file and what writes it."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. It is produced by an earlier phase -- see "
            "docs/ROADMAP.md for which one."
        )
    return pd.read_parquet(path, columns=columns)
