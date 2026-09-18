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

import pandas as pd

# Mirrors conf/data.yaml#sources.cell2cell.drop_columns. Kept here too so a
# direct caller of load() cannot bypass the exclusion by skipping the config.
FORBIDDEN_COLUMNS: tuple[str, ...] = (
    "ethnic", "marital", "income", "adults",
    "kid0_2", "kid3_5", "kid6_10", "kid11_15", "kid16_17",
    "ownrent", "dwlltype", "dwllsize", "numbcars", "HHstatin",
    "infobase", "prizm_social_one", "creditcd", "lor", "rv", "truck",
    "forgntvl", "area",
)


def fetch() -> None:
    """No-op: this source is supplied locally at data/raw/telecom/telecom.

    Present so the source has the same interface as the downloadable ones and
    `download_data.py` can report it as satisfied rather than missing.
    """
    raise NotImplementedError("TODO(E1): verify the two files exist and match expected shape")


def load() -> pd.DataFrame:
    """Join Client.csv and Record.csv on Customer_ID, minus the forbidden columns.

    Must drop FORBIDDEN_COLUMNS before returning, and must not return the raw
    `churn` prevalence as though it were a base rate.
    """
    raise NotImplementedError("TODO(E1)")


def measured_distributions() -> dict[str, dict[str, float]]:
    """Empirical quantiles for the features the synthesis engine generates.

    This is the whole point of the source: the overlays in cvm.synthesis fit
    against these rather than against invented shapes. Recompute and commit the
    numbers whenever the source file changes.
    """
    raise NotImplementedError("TODO(E1)")


def assert_prior_corrected(y: pd.Series, target_rate: float) -> None:
    """Fail if a model is about to be fitted on the balanced prevalence.

    Guards the calibration claim. ~49.6% in the file versus a real rate an order
    of magnitude lower is not a nuance -- it is the difference between a
    calibrated probability and a meaningless one.
    """
    raise NotImplementedError("TODO(E2)")