"""Dataset C -- IBM Telco Customer Churn (extended).  Owner: E1

Three roles, all small and fast so the Week-1 baseline is never blocked on
pipeline work:

* CLTV -- an independent lifetime-value benchmark for M2.
* Churn Reason -- a labelled categorical explanation, useful for sanity-
  checking that our churn drivers look like real ones.
* Churn Score -- a vendor baseline to beat.

PROTECTED ATTRIBUTES AND US GEOGRAPHY ARE DROPPED AT THE BOUNDARY, exactly as
in Cell2Cell. This source carries Gender, Senior Citizen, Partner and
Dependents -- direct protected or proxy-protected attributes -- plus street-level
Latitude/Longitude, Zip Code and City. A Libyan prepaid operator holds none of
it, geography is out of scope for this branch entirely, and the proposal's
commitment is that these never reach a feature matrix rather than that they are
merely excluded from pricing. Excluding at the boundary is the difference
between a policy and a guarantee.

Note what this dataset is NOT: it is postpaid, contract-based, and US. It is
here as an independent CLTV reference point and a fast first baseline, never as
evidence about prepaid behaviour.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings
from cvm.ingest.hashing import assert_no_raw_identifiers, hash_column

log = logging.getLogger(__name__)

CACHE_NAME = "Telco_customer_churn.xlsx"
ID_COLUMN = "CustomerID"

# Same principle as cell2cell.FORBIDDEN_COLUMNS: duplicated in code so a direct
# caller of load() cannot bypass the exclusion by skipping the config.
FORBIDDEN_COLUMNS: tuple[str, ...] = (
    # Protected and proxy-protected
    "Gender",
    "Senior Citizen",
    "Partner",
    "Dependents",
    # US geography, to street level. Geography is not modelled in this branch.
    "Country",
    "State",
    "City",
    "Zip Code",
    "Lat Long",
    "Latitude",
    "Longitude",
    # Constant column, present only as a spreadsheet pivot artefact.
    "Count",
)


def _conf() -> dict:
    return load_conf("data")["sources"]["ibm_telco"]


def fetch() -> pd.DataFrame:
    """Download the extended IBM sample into data/raw/.

    Cached: if the workbook is already on disk this does not touch the network,
    which is why the Kaggle credential is only needed once.
    """
    cache = settings.raw_dir / CACHE_NAME
    if cache.exists():
        log.info("ibm_telco: using cache %s", cache)
        return pd.read_excel(cache)

    if not (settings.kaggle_username and settings.kaggle_key):
        raise RuntimeError(
            f"{cache} is missing and Kaggle credentials are not set. Either place "
            "the workbook there by hand, or set KAGGLE_USERNAME and KAGGLE_KEY in "
            ".env. Dataset: " + _conf()["dataset"]
        )

    import kaggle  # imported here: the credential check must fail first

    cache.parent.mkdir(parents=True, exist_ok=True)
    kaggle.api.dataset_download_files(
        _conf()["dataset"], path=str(cache.parent), unzip=True, quiet=False
    )
    log.info("ibm_telco: downloaded to %s", cache.parent)
    return pd.read_excel(cache)


def load() -> pd.DataFrame:
    conf = _conf()
    df = fetch()

    present = [c for c in FORBIDDEN_COLUMNS if c in df.columns]
    df = df.drop(columns=present)
    log.info(
        "ibm_telco: dropped %d protected/geographic columns at the boundary: %s",
        len(present),
        present,
    )

    if len(df) != conf["expected_rows"]:
        log.warning("ibm_telco: %d rows, expected %d", len(df), conf["expected_rows"])

    missing = [c for c in conf["benchmark_columns"] if c not in df.columns]
    if missing:
        raise ValueError(
            f"benchmark columns missing: {missing}. The point of this source is "
            "CLTV, Churn Reason and Churn Score -- without them it adds nothing "
            "the other two do not."
        )

    # `Total Charges` arrives with blanks for brand-new accounts and is read as
    # text. Silently coercing those to 0 would invent eleven customers with a
    # lifetime spend of nothing, which is exactly the kind of thing that then
    # shows up in a CLTV benchmark.
    if "Total Charges" in df.columns and df["Total Charges"].dtype == object:
        coerced = pd.to_numeric(df["Total Charges"], errors="coerce")
        log.info("ibm_telco: %d blank Total Charges left as null", int(coerced.isna().sum()))
        df["Total Charges"] = coerced

    df = hash_column(df, ID_COLUMN)
    df["snapshot_date"] = pd.Timestamp("2026-09-18")
    df["source"] = "ibm_telco"

    observed = float((df["Churn Label"] == "Yes").mean()) if "Churn Label" in df else float("nan")
    log.info("ibm_telco: churn rate %.4f (config says %.2f)", observed, conf["churn_rate"])

    leaked = [c for c in FORBIDDEN_COLUMNS if c in df.columns]
    if leaked:
        raise AssertionError(f"forbidden columns survived: {leaked}")
    assert_no_raw_identifiers(df)
    return df


def reason_taxonomy() -> dict[str, str]:
    """Map IBM's free-text Churn Reason values onto our six reason codes.

    The value is the sanity check, not the mapping itself: if our SHAP drivers
    point at causes that never appear in a real operator's exit-survey
    taxonomy, the model is finding something other than churn.

    Unmapped values return `other` rather than raising -- IBM's list is longer
    than our six codes by design, and forcing a one-to-one mapping would mean
    inventing reason codes to fill it.
    """
    return {
        # price
        "Price too high": "price",
        "Extra data charges": "price",
        "Long distance charges": "price",
        "Lack of affordable download/upload speed": "price",
        # competitor
        "Competitor made better offer": "competitor",
        "Competitor had better devices": "competitor",
        "Competitor offered more data": "competitor",
        "Competitor offered higher download speeds": "competitor",
        # network
        "Network reliability": "network",
        "Poor expertise of online support": "network",
        "Service dissatisfaction": "network",
        "Limited range of services": "network",
        # care
        "Attitude of support person": "care",
        "Attitude of service provider": "care",
        "Poor expertise of phone support": "care",
        # lifecycle
        "Moved": "lifecycle",
        "Deceased": "lifecycle",
        "Don't know": "other",
    }


def map_reasons(reasons: pd.Series) -> pd.Series:
    """Apply `reason_taxonomy`, defaulting to `other`."""
    taxonomy = reason_taxonomy()
    mapped = reasons.map(taxonomy)
    unmapped = sorted(set(reasons.dropna()) - set(taxonomy))
    if unmapped:
        log.info("ibm_telco: %d reason values mapped to 'other': %s", len(unmapped), unmapped)
    return mapped.fillna("other").where(reasons.notna())
