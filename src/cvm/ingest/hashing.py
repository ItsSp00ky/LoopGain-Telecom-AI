"""Identifier hashing. The single place a raw identifier may be touched.

No raw MSISDN exists anywhere in this repository. That commitment is only
credible if there is exactly one function that does the hashing and it is
impossible to bypass -- so every loader routes through here, and the salt is
required rather than defaulted.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from cvm.config import settings


def hash_identifier(raw: str, salt: str | None = None) -> str:
    """Return the salted SHA-256 hex digest of one raw identifier.

    Raises if no salt is configured: an unsalted hash is trivially reversible
    for a 9-digit number space and cannot be reconciled across runs.
    """
    salt = salt or settings.require_salt()
    return hashlib.sha256(f"{salt}{raw}".encode()).hexdigest()


def hash_column(
    df: pd.DataFrame,
    source_column: str,
    target_column: str = "subscriber_id_hashed",
    drop_source: bool = True,
) -> pd.DataFrame:
    """Hash an identifier column and drop the original.

    ``drop_source`` defaults to True on purpose. Keeping the raw column "just
    for debugging" is how it ends up in a Parquet file and then in a commit.
    """
    raise NotImplementedError("TODO(E1)")


def assert_no_raw_identifiers(df: pd.DataFrame) -> None:
    """Fail if any column looks like it holds a raw Libyan MSISDN.

    Pattern: optional +218, then 091/092 (Libyana) or 094/095 (Almadar),
    then 7 digits. Called at the end of every loader and asserted in
    tests/unit/test_privacy.py.
    """
    raise NotImplementedError("TODO(E1)")