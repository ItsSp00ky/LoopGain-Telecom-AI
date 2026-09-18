"""Dataset A -- Iranian Churn Dataset (UCI 563). PRIMARY source.  Owner: E1

Closest public analogue on four axes at once: prepaid, MENA-region, carries a
network-quality feature (call failures), and its 9-month observation / 3-month
prediction gap is exactly the operational framing a real campaign needs.

Two mandatory corrections before this data is usable:

* ~300 exact duplicate rows (~9.5%) -- deduplicate.
* The pre-computed `Customer Value` field partially encodes the outcome --
  drop it from the feature matrix. This is why our reported metrics are lower
  than the published ~97% accuracy / ~0.99 AUC, and that gap is a headline
  result, not an embarrassment.

NO IDENTIFIER EXISTS IN THIS SOURCE. The rows are already anonymous, so the
surrogate `subscriber_id_hashed` this module attaches is a hash of the source
name and the row's position -- deterministic, reproducible, and transparently
synthetic. It is NOT a hashed MSISDN and must never be described as one.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings
from cvm.ingest.hashing import assert_no_raw_identifiers, hash_identifier

log = logging.getLogger(__name__)

CACHE_NAME = "uci_iranian_563.csv"
LABEL = "Churn"

# The published CSV uses doubled spaces in three headers. Left as-is they
# produce two spellings of the same column depending on how it was read, which
# is the kind of bug that costs an afternoon.
COLUMN_RENAMES = {
    "Call  Failure": "Call Failure",
    "Subscription  Length": "Subscription Length",
    "Charge  Amount": "Charge Amount",
}


def _conf() -> dict:
    return load_conf("data")["sources"]["uci_iranian"]


def fetch() -> pd.DataFrame:
    """Download via ucimlrepo (id=563). Cached under data/raw/."""
    cache = settings.raw_dir / CACHE_NAME
    if cache.exists():
        log.info("uci_iranian: using cache %s", cache)
        return pd.read_csv(cache)

    from ucimlrepo import fetch_ucirepo

    uci_id = _conf()["uci_id"]
    log.info("uci_iranian: fetching UCI id=%s", uci_id)
    repo = fetch_ucirepo(id=uci_id)
    df = pd.concat([repo.data.features, repo.data.targets], axis=1)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    log.info("uci_iranian: cached %d rows to %s", len(df), cache)
    return df


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop exact-match duplicates. Returns (clean_df, n_dropped).

    Log n_dropped to MLflow -- it is evidence for pitch point 4.
    """
    before = len(df)
    clean = df.drop_duplicates(keep="first").reset_index(drop=True)
    dropped = before - len(clean)

    quality = _conf()["quality"]
    expected, tol = quality["expected_duplicate_rows"], quality["duplicate_row_tolerance"]
    if abs(dropped - expected) > tol:
        # Not fatal: the source could legitimately be revised. But the number is
        # quoted in the proposal, so a silent change must not pass unnoticed.
        log.warning(
            "uci_iranian: dropped %d duplicates, expected ~%d (+/-%d). "
            "The figure in the proposal needs updating.",
            dropped,
            expected,
            tol,
        )

    log.info(
        "uci_iranian: dropped %d exact duplicates of %d rows (%.1f%%)",
        dropped,
        before,
        100 * dropped / before,
    )
    return clean, dropped


def load(drop_leaky: bool = True) -> pd.DataFrame:
    """Fetch, validate, deduplicate, and optionally drop `Customer Value`.

    ``drop_leaky=False`` exists only to reproduce the inflated published
    figures for the honest-vs-naive comparison in the report.
    """
    conf = _conf()
    df = fetch().rename(columns=COLUMN_RENAMES)

    if LABEL not in df.columns:
        raise ValueError(f"{LABEL!r} missing. Columns: {sorted(df.columns)}")
    if len(df) != conf["expected_rows"]:
        log.warning("uci_iranian: %d rows, expected %d", len(df), conf["expected_rows"])

    df, _ = deduplicate(df)

    if drop_leaky:
        leaky = [c for c in conf["leaky_columns"] if c in df.columns]
        df = df.drop(columns=leaky)
        log.info("uci_iranian: dropped leaky columns %s", leaky)

    # Surrogate id -- see the module docstring. Position-based, so it is stable
    # only after deduplication, which is why it is assigned here and not in
    # fetch().
    salt = settings.require_salt()
    df.insert(
        0,
        "subscriber_id_hashed",
        pd.Series(
            [hash_identifier(f"uci_iranian:{i}", salt) for i in range(len(df))], dtype="string"
        ),
    )
    df["snapshot_date"] = pd.Timestamp("2026-09-18")
    df["source"] = "uci_iranian"

    assert_no_raw_identifiers(df)
    return df


def duplicate_audit() -> dict[str, float]:
    """The dedup measurement, for the report and for the leakage test.

    Separate from ``load`` because the number is a *result* -- it is quoted in
    the proposal and belongs in the report table, not only in a log line.
    """
    raw = fetch().rename(columns=COLUMN_RENAMES)
    _, dropped = deduplicate(raw)
    return {
        "rows_raw": float(len(raw)),
        "duplicates_dropped": float(dropped),
        "duplicate_share": dropped / len(raw),
        "rows_clean": float(len(raw) - dropped),
    }
