"""Dataset J -- UCI Online Retail II (id 502).  VALIDATION SOURCE.  Owner: E1

Just over a million invoice lines, 2009-2011, one online retailer.

WHY A RETAIL DATASET IS IN A TELECOM PROJECT. BG/NBD and Gamma-Gamma are
repeat-purchase models. M2 asks them to treat a *recharge* as a transaction,
which is a defensible reading -- prepaid top-ups are non-contractual, the
customer is alive-or-dead-unobserved, and that is exactly the regime BG/NBD
assumes. But "defensible reading" is not "validated model", and the honest way
to close that gap is to fit the same estimators on real repeat purchases first,
where the answer can be checked against a held-out period.

This is precisely what Criteo is for uplift, one layer down: validate the
method on real data, then apply it to generated data and say which is which.

The `lifetimes` library's own worked examples use this dataset, so a wrong
answer here means our plumbing is wrong rather than the model being unsuitable.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

CACHE_NAME = "online_retail_ii.parquet"
CUSTOMER = "Customer ID"
INVOICE, INVOICE_DATE = "Invoice", "InvoiceDate"
QUANTITY, PRICE = "Quantity", "Price"


def _conf() -> dict:
    return load_conf("data")["sources"]["online_retail"]


# NOT ucimlrepo. Dataset 502 exists in the UCI repository but is not available
# through the Python import API -- it is published as a two-sheet Excel
# workbook, so `fetch_ucirepo(id=502)` raises DatasetNotFoundError. The static
# archive URL is the documented alternative.
ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"


def fetch() -> pd.DataFrame:
    """Download the UCI archive for dataset 502. Cached as Parquet.

    The workbook has ONE SHEET PER YEAR (2009-2010 and 2010-2011) and both are
    needed -- a single sheet is half the period, which halves every observed
    inter-purchase time and quietly biases BG/NBD toward shorter lifetimes.
    """
    cache = settings.external_dir / CACHE_NAME
    if cache.exists():
        log.info("online_retail: using cache %s", cache)
        return pd.read_parquet(cache)

    import io
    import urllib.request
    import zipfile

    log.info("online_retail: downloading %s (~45 MB)", ARCHIVE_URL)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=300) as response:
        payload = response.read()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith((".xlsx", ".xls")))
        log.info("online_retail: reading every sheet of %s", name)
        with archive.open(name) as workbook:
            sheets = pd.read_excel(io.BytesIO(workbook.read()), sheet_name=None)

    log.info("online_retail: %d sheets: %s", len(sheets), list(sheets))
    df = pd.concat(sheets.values(), ignore_index=True)

    # A hand-maintained Excel workbook has mixed types in every text column:
    # `Invoice` numbers a credit note C489449, `StockCode` is alphanumeric, and
    # `Description` has stray numerics. Parquet needs one type per column, and
    # every one of these is an identifier or a label rather than a quantity, so
    # string is the correct type as well as the writable one. Coercing the whole
    # object dtype is the general fix; naming columns one at a time is
    # whack-a-mole against a file nobody validated.
    object_columns = [c for c in df.columns if df[c].dtype == object]
    for column in object_columns:
        df[column] = df[column].astype("string")
    log.info(
        "online_retail: coerced %d text columns to string: %s", len(object_columns), object_columns
    )

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    log.info("online_retail: cached %d rows to %s", len(df), cache)
    return df


def load() -> pd.DataFrame:
    """Clean invoice lines: real customers, real sales, no returns.

    Three exclusions, each of which would otherwise corrupt a lifetime value:

    * **No customer id** -- roughly a quarter of the lines. They cannot be
      attributed to anyone, so they cannot contribute to anyone's CLV.
    * **Credit notes** (negative quantity, invoice prefixed `C`). A return is
      not a purchase with a minus sign in front of it; treating it as one lets
      a customer have a negative frequency.
    * **Zero or negative price** -- adjustments and samples, not revenue.
    """
    df = fetch()
    before = len(df)

    df = df.dropna(subset=[CUSTOMER])
    df = df[~df[INVOICE].astype(str).str.upper().str.startswith("C")]
    df = df[(df[QUANTITY] > 0) & (df[PRICE] > 0)]

    df = df.assign(
        **{
            CUSTOMER: df[CUSTOMER].astype("int64").astype(str),
            INVOICE_DATE: pd.to_datetime(df[INVOICE_DATE]),
            "line_revenue": df[QUANTITY] * df[PRICE],
        }
    ).reset_index(drop=True)

    log.info(
        "online_retail: %d of %d lines kept (%.1f%% dropped as unattributed, returns or non-sales)",
        len(df),
        before,
        100 * (1 - len(df) / before),
    )
    return df


def summary(calibration_end: str | None = None) -> pd.DataFrame:
    """The recency/frequency/T/monetary summary BG/NBD and Gamma-Gamma consume.

    ``calibration_end`` splits the period in two: fit on everything up to that
    date, then score the observed behaviour after it. Without a holdout the
    "validation" is a fit statistic, which is the thing this dataset exists to
    avoid.
    """
    from lifetimes.utils import calibration_and_holdout_data, summary_data_from_transaction_data

    df = load()
    if calibration_end is None:
        return summary_data_from_transaction_data(
            df,
            customer_id_col=CUSTOMER,
            datetime_col=INVOICE_DATE,
            monetary_value_col="line_revenue",
            freq="D",
        )

    end = df[INVOICE_DATE].max()
    log.info("online_retail: calibration to %s, holdout to %s", calibration_end, end.date())
    return calibration_and_holdout_data(
        df,
        customer_id_col=CUSTOMER,
        datetime_col=INVOICE_DATE,
        monetary_value_col="line_revenue",
        calibration_period_end=calibration_end,
        observation_period_end=end,
        freq="D",
    )
