"""Dataset B -- Cell2Cell (Duke / Teradata).  Owner: E1

Two files, 100,000 rows each, joined 1:1 on Customer_ID:

    Client.csv   50 cols  commercial, handset, 3/6-month revenue aggregates
    Record.csv   51 cols  behavioural means, service quality, churn label

This is the original two-file distribution rather than a preprocessed single
table, which is why it carries columns the condensed cuts drop -- including the
two that matter most to this project.

WHY IT MATTERS BEYOND ROW COUNT
-------------------------------
Two features carry most of this project's differentiation, and neither had an
empirical reference before this source:

    incoming/outgoing ratio  <- recv_vce_Mean / plcd_vce_Mean
    off-peak usage share     <- mou_opkv_Mean / (mou_peav_Mean + mou_opkv_Mean)

Both are 0% null across all 100,000 rows. The generator now reproduces measured
distributions instead of invented ones. Also present: inonemin_Mean (calls under
a minute, which drives revenue under a 3-minute block tariff), data-side
failures, care-contact volume, and avg3/avg6 aggregates giving a real
two-horizon decay ratio.

TWO THINGS THAT WILL BITE
-------------------------
1. The label is balanced at ~49.6% churn. Training on it and then calibrating
   would calibrate to a 50% prior and silently destroy the claim that a 0.31
   means 31%. Use this source for feature structure; take the base rate from
   conf/market.yaml. `assert_prior_corrected` exists to make that explicit.

2. Twenty-two columns are US household marketing data -- ethnicity, marital
   status, income, child age brackets, dwelling and vehicle attributes. Several
   are protected or proxy-protected. They are dropped at the ingestion boundary
   so they cannot reach a feature matrix by accident later, and `load()` refuses
   to return them at all.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings
from cvm.ingest.hashing import hash_column

log = logging.getLogger(__name__)

# Mirrors conf/data.yaml#sources.cell2cell.drop_columns. Kept here too so a
# direct caller of load() cannot bypass the exclusion by skipping the config.
FORBIDDEN_COLUMNS: tuple[str, ...] = (
    "ethnic",
    "marital",
    "income",
    "adults",
    "kid0_2",
    "kid3_5",
    "kid6_10",
    "kid11_15",
    "kid16_17",
    "ownrent",
    "dwlltype",
    "dwllsize",
    "numbcars",
    "HHstatin",
    "infobase",
    "prizm_social_one",
    "creditcd",
    "lor",
    "rv",
    "truck",
    "forgntvl",
    "area",
)

LABEL = "churn"


def _conf() -> dict:
    return load_conf("data")["sources"]["cell2cell"]


def _paths() -> tuple:
    conf = _conf()
    base = settings.data_dir.parent / conf["path"].lstrip("./")
    if not base.exists():  # config path is repo-relative; data_dir may be absolute
        base = (settings.raw_dir / "telecom" / "telecom").resolve()
    return base / conf["files"]["client"], base / conf["files"]["record"]


def fetch() -> None:
    """No-op: this source is supplied locally at data/raw/telecom/telecom.

    Present so the source has the same interface as the downloadable ones and
    `download_data.py` can report it as satisfied rather than missing.
    """
    client, record = _paths()
    missing = [p for p in (client, record) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Cell2Cell is supplied locally, not downloaded. Expected "
            + " and ".join(str(p) for p in missing)
            + ". See data/README.md#b--cell2cell."
        )
    log.info("cell2cell: both files present at %s", client.parent)


def load() -> pd.DataFrame:
    """Join Client.csv and Record.csv on Customer_ID, minus the forbidden columns.

    Must drop FORBIDDEN_COLUMNS before returning, and must not return the raw
    `churn` prevalence as though it were a base rate.
    """
    fetch()
    conf = _conf()
    client_path, record_path = _paths()
    key = conf["join_on"]

    client = pd.read_csv(client_path)
    record = pd.read_csv(record_path)

    # Drop the protected columns BEFORE the join, so they never exist in a
    # frame this function could accidentally return early.
    present = [c for c in FORBIDDEN_COLUMNS if c in client.columns or c in record.columns]
    client = client.drop(columns=[c for c in FORBIDDEN_COLUMNS if c in client.columns])
    record = record.drop(columns=[c for c in FORBIDDEN_COLUMNS if c in record.columns])
    log.info("cell2cell: dropped %d protected/marketing columns at the boundary", len(present))

    if not client[key].is_unique or not record[key].is_unique:
        raise ValueError(f"{key} is not unique in both files; the 1:1 join assumption is wrong")

    df = client.merge(record, on=key, how="inner", validate="one_to_one")
    if len(df) != conf["expected_rows"]:
        log.warning("cell2cell: joined %d rows, expected %d", len(df), conf["expected_rows"])

    df = hash_column(df, key)
    df["snapshot_date"] = pd.Timestamp("2026-09-18")
    df["source"] = "cell2cell"

    # Stated, not silently carried. See the docstring and conf/data.yaml.
    log.info(
        "cell2cell: churn prevalence in file is %.4f -- BALANCED, not a base rate. "
        "Take the base rate from conf/market.yaml.",
        df[LABEL].mean(),
    )

    leaked = [c for c in FORBIDDEN_COLUMNS if c in df.columns]
    if leaked:
        raise AssertionError(f"forbidden columns survived the join: {leaked}")
    return df


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise ratio, undefined where the denominator is zero.

    Returning NaN rather than inf or 0 matters: a subscriber who placed no calls
    has no *measured* incoming/outgoing ratio, and coercing that to zero would
    pull the quantiles the synthesis engine fits against.
    """
    den = denominator.where(denominator > 0)
    return (numerator / den).replace([float("inf"), float("-inf")], pd.NA).astype("float64")


def derived_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """The ratios this source exists to ground, on one frame.

    BOTH DECAY RATIOS, and the distinction is not cosmetic. The source carries
    avg3/avg6 aggregates for minutes *and* revenue, and they do not agree:
    minutes give a median of 1.012 with 46.8% of subscribers declining, revenue
    gives 1.000 with 42.2%. Usage turns down before spend does, which is the
    whole reason a decay ratio is an early warning at all -- so generating
    against one number and calling it the other would quietly flatten the
    signal the feature exists to carry.
    """
    return pd.DataFrame(
        {
            "incoming_outgoing_ratio": _ratio(df["recv_vce_Mean"], df["plcd_vce_Mean"]),
            "offpeak_data_ratio": _ratio(
                df["mou_opkv_Mean"], df["mou_peav_Mean"] + df["mou_opkv_Mean"]
            ),
            "usage_decay_ratio": _ratio(df["avg3mou"], df["avg6mou"]),
            "revenue_decay_ratio": _ratio(df["avg3rev"], df["avg6rev"]),
        }
    )


def measured_distributions() -> dict[str, dict[str, float]]:
    """Empirical quantiles for the features the synthesis engine generates.

    This is the whole point of the source: the overlays in cvm.synthesis fit
    against these rather than against invented shapes. Recompute and commit the
    numbers whenever the source file changes.
    """
    ratios = derived_ratios(load())
    out: dict[str, dict[str, float]] = {}
    for name in ratios.columns:
        s = ratios[name].dropna()
        out[name] = {
            "n": float(len(s)),
            "null_share": float(1 - len(s) / len(ratios)),
            "p10": float(s.quantile(0.10)),
            "median": float(s.median()),
            "p90": float(s.quantile(0.90)),
            "mean": float(s.mean()),
            # Only meaningful for the decay ratio, but cheap and harmless.
            "share_below_one": float((s < 1).mean()),
        }
    return out


def assert_prior_corrected(y: pd.Series, target_rate: float) -> None:
    """Fail if a model is about to be fitted on the balanced prevalence.

    Guards the calibration claim. ~49.6% in the file versus a real rate an order
    of magnitude lower is not a nuance -- it is the difference between a
    calibrated probability and a meaningless one.
    """
    observed = float(pd.Series(y).mean())
    tolerance = max(0.01, 0.5 * target_rate)
    if abs(observed - target_rate) > tolerance:
        raise ValueError(
            f"Label prevalence is {observed:.4f} but the market base rate is "
            f"{target_rate:.4f}. Fitting here would calibrate to the wrong prior and "
            "make every probability downstream meaningless -- a 0.31 would not mean "
            "31%. Resample, reweight, or pass the corrected labels. See "
            "conf/data.yaml#sources.cell2cell and conf/market.yaml#base."
        )
