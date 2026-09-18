"""Entry point: `python -m cvm.ingest.run`  (step 1 of 3 in the pipeline)

Downloads nothing. Assumes `python scripts/download_data.py` has already run,
so that a network failure is a separate, obvious failure mode from a schema
break.

TWO KINDS OF SOURCE, LANDED DIFFERENTLY.

*Subscriber sources* (A, B, C) become per-subscriber snapshots: hashed id,
snapshot date, one row per subscriber. They share a contract, so they land in
one place and are validated against `SubscriberSnapshot`.

*Validation sources* (F, G, J) do not. Criteo is a treatment/outcome table with
anonymous features, Hillstrom is a three-armed experiment, Online Retail II is
invoice lines. Forcing them into a subscriber schema would mean inventing
subscribers. They are checked for reachability and cached in their own shapes,
which is all M2 and M3 need of them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from cvm.config import load_conf, settings
from cvm.ingest.hashing import assert_no_raw_identifiers
from cvm.ingest.schemas import SubscriberSnapshot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Landed:
    name: str
    rows: int
    columns: int
    path: str | None
    note: str = ""


def _subscriber_loaders() -> dict[str, Callable[[], pd.DataFrame]]:
    from cvm.ingest import cell2cell, ibm_telco, uci_iranian

    return {
        "uci_iranian": uci_iranian.load,
        "cell2cell": cell2cell.load,
        "ibm_telco": ibm_telco.load,
    }


def _validation_checks() -> dict[str, Callable[[], tuple[int, int]]]:
    """Reachability probes, not landings. Each returns (rows, columns)."""

    def criteo() -> tuple[int, int]:
        from cvm.ingest.criteo_uplift import load

        x, _, _ = load(sample_10pct=True)
        return len(x), x.shape[1]

    def hillstrom() -> tuple[int, int]:
        from cvm.ingest.hillstrom import load

        x, _, _ = load()
        return len(x), x.shape[1]

    def online_retail() -> tuple[int, int]:
        from cvm.ingest.online_retail import load

        df = load()
        return len(df), df.shape[1]

    return {"criteo_uplift": criteo, "hillstrom": hillstrom, "online_retail": online_retail}


def land_subscriber_source(name: str, loader: Callable[[], pd.DataFrame]) -> Landed:
    """Load one subscriber source, validate it, and write it to data/interim."""
    df = loader()

    # Belt and braces. Each loader already calls this; a source added later
    # might forget, and this is the boundary the whole privacy claim rests on.
    assert_no_raw_identifiers(df)

    SubscriberSnapshot.validate(df, lazy=True)

    out = settings.interim_dir / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    log.info("%s: landed %d rows x %d cols -> %s", name, len(df), df.shape[1], out)
    return Landed(name, len(df), df.shape[1], str(out))


def main() -> None:
    """Validate, deduplicate, hash, and land every source as Parquet."""
    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.require_salt()  # fail here, not three sources in
    settings.ensure_dirs()

    sources = load_conf("data")["sources"]
    results: list[Landed] = []
    failures: list[tuple[str, Exception]] = []

    for name, loader in _subscriber_loaders().items():
        if not sources.get(name, {}).get("enabled", False):
            log.info("%s: disabled in conf/data.yaml, skipping", name)
            continue
        try:
            results.append(land_subscriber_source(name, loader))
        except Exception as exc:
            log.error("%s: FAILED -- %s: %s", name, type(exc).__name__, exc)
            failures.append((name, exc))

    for name, probe in _validation_checks().items():
        if not sources.get(name, {}).get("enabled", False):
            log.info("%s: disabled in conf/data.yaml, skipping", name)
            continue
        try:
            rows, cols = probe()
            results.append(
                Landed(name, rows, cols, None, note="validation source, cached in its own shape")
            )
            log.info("%s: reachable, %d rows x %d cols", name, rows, cols)
        except Exception as exc:
            log.error("%s: FAILED -- %s: %s", name, type(exc).__name__, exc)
            failures.append((name, exc))

    print(f"\n{'SOURCE':<18}{'ROWS':>12}{'COLS':>7}  WHERE")
    print("-" * 74)
    for r in results:
        where = r.path or r.note
        print(f"{r.name:<18}{r.rows:>12,}{r.columns:>7}  {where}")
    print("-" * 74)

    if failures:
        print(f"\n{len(failures)} source(s) failed:")
        for name, exc in failures:
            print(f"  {name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    print(f"\n{len(results)} sources ingested. Next: python -m cvm.synthesis.run")


if __name__ == "__main__":
    main()
