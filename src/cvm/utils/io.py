"""Parquet and NPZ helpers, with the project's partitioning conventions baked in."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_parquet(df: pd.DataFrame, path: Path, partition_by: str = "snapshot_date") -> None:
    raise NotImplementedError("TODO(E1)")


def read_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    raise NotImplementedError("TODO(E1)")
