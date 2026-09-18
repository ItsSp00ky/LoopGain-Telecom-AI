"""Download every public dataset into data/raw and data/external.

    python scripts/download_data.py              # all sources
    python scripts/download_data.py --only A,C   # just the ones you need

Deliberately separate from `cvm.ingest.run`: a network failure or a missing
Kaggle credential should be an obvious, separate failure from a schema break.
Nothing here transforms data -- it only fetches.

Credentials needed (see .env.example):
    A  UCI 563     none
    B  Cell2Cell   none -- supplied locally at data/raw/telecom/telecom
    C  IBM Telco   KAGGLE_USERNAME + KAGGLE_KEY, or ~/.kaggle/kaggle.json
"""

from __future__ import annotations

import argparse
import logging
import sys

from cvm.config import settings

logging.basicConfig(level="INFO", format="%(levelname)-8s %(message)s")
log = logging.getLogger("download")

# Core sources from the proposal. Fetched by default.
SOURCES = {
    "A": ("UCI Iranian Churn (563)", "cvm.ingest.uci_iranian"),
    "B": ("Cell2Cell (local, two-file)", "cvm.ingest.cell2cell"),
    "C": ("IBM Telco Customer Churn", "cvm.ingest.ibm_telco"),
}

# Recommended additions. Opt in with --only, because several are large and
# you have limited disk. See data/README.md#recommended-additions.
OPTIONAL_SOURCES = {
    "F": ("Criteo Uplift (real treatment/control)", "cvm.ingest.criteo_uplift"),
    "G": ("Hillstrom MineThatData (uplift warm-up)", "cvm.ingest.hillstrom"),
    "H": ("KKBox WSDM (real daily sequences)", "cvm.ingest.kkbox"),
    "J": ("UCI Online Retail II (502, CLV validation)", "cvm.ingest.online_retail"),
}

ALL_SOURCES = {**SOURCES, **OPTIONAL_SOURCES}

# Rough download sizes, so --only can be chosen against available disk.
APPROX_MB = {
    "A": 1,
    "B": 0,
    "C": 5,  # B is already on disk
    "F": 300,
    "G": 5,
    "H": 30_000,
    "J": 45,
}


def check_credentials(ids: list[str]) -> list[str]:
    """Report missing credentials up front rather than failing three minutes in."""
    problems = []
    kaggle_ids = {"C", "H"}  # B is supplied locally
    if kaggle_ids & set(ids) and not (settings.kaggle_key or settings.kaggle_username):
        problems.append(
            f"Kaggle credentials missing (datasets {sorted(kaggle_ids & set(ids))}). Set "
            "KAGGLE_USERNAME and KAGGLE_KEY in .env, or place kaggle.json in ~/.kaggle/."
        )
    if "H" in ids:
        problems.append(
            "Dataset H (KKBox) is a competition dataset -- you must accept the rules at "
            "https://www.kaggle.com/c/kkbox-churn-prediction-challenge/rules first, "
            "or the download returns 403."
        )
    return problems


def check_disk(ids: list[str]) -> str | None:
    """Warn before a 30 GB download fills the drive."""
    import shutil

    needed_mb = sum(APPROX_MB.get(i, 0) for i in ids)
    free_mb = shutil.disk_usage(settings.data_dir.anchor or ".").free / 1024 / 1024
    if needed_mb > free_mb * 0.8:
        return (
            f"Requested sources need roughly {needed_mb / 1024:.1f} GB but only "
            f"{free_mb / 1024:.1f} GB is free. Fetch fewer at a time -- see "
            "data/README.md#disk-budget."
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        default="A,B,C",
        help=(
            "Comma-separated source ids. Default A,B,C (the core set). "
            "Optional extras: F Criteo uplift, G Hillstrom, H KKBox, "
            "J Online Retail II."
        ),
    )
    parser.add_argument("--list", action="store_true", help="List every source and exit.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if the file already exists."
    )
    args = parser.parse_args()

    if args.list:
        for sid, (name, _) in ALL_SOURCES.items():
            tag = "core" if sid in SOURCES else "optional"
            log.info("%s  %-8s %-45s ~%s MB", sid, tag, name, APPROX_MB.get(sid, "?"))
        return 0

    ids = [s.strip().upper() for s in args.only.split(",") if s.strip()]
    unknown = set(ids) - set(ALL_SOURCES)
    if unknown:
        log.error("Unknown source ids: %s. Known: %s", sorted(unknown), sorted(ALL_SOURCES))
        return 2

    for problem in check_credentials(ids):
        log.warning(problem)
    if (disk := check_disk(ids)) is not None:
        log.warning(disk)

    failed = []
    for sid in ids:
        name, module = ALL_SOURCES[sid]
        log.info("[%s] %s", sid, name)
        try:
            # TODO(E1): import the module and call fetch().
            #   mod = importlib.import_module(module)
            #   mod.fetch()
            raise NotImplementedError(f"{module}.fetch()")
        except NotImplementedError as exc:
            log.warning("  not implemented yet: %s", exc)
            failed.append(sid)
        except Exception:
            log.exception("  failed")
            failed.append(sid)

    if failed:
        log.warning("Incomplete: %s. See data/README.md for manual download steps.", failed)
        return 1

    log.info("All sources present. Next: pwsh tasks.ps1 pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
