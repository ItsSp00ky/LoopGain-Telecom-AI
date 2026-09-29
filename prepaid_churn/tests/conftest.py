from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from prepaid_churn.data import column_name
from prepaid_churn.schema import DATA_BLOCK, GROUPS, VOICE_BLOCK

NAN = np.nan
MONTHS = (6, 7, 8)
MONTH_ENDS = {6: "6/30/2014", 7: "7/31/2014", 8: "8/31/2014"}

# Hand-made values per customer for months 6, 7 and 8; every other contract column is 0.
# - 0: active every month, bought data.
# - 1: no voice record in month 8 (voice block missing), no recharge in month 8, churns.
# - 2: voice only, never bought data (data block missing every month).
# - 3: inactive in month 8 but recharged, stays.
OVERRIDES = {
    "arpu": [[100, 90, 95], [50, 20, -5], [30, 30, 30], [10, 10, 0]],
    "onnet_mou": [[10, 12, 11], [5, 2, NAN], [7, 7, 7], [1, 1, 0]],
    "offnet_mou": [[20, 22, 21], [6, 3, NAN], [8, 8, 8], [1, 1, 0]],
    "total_ic_mou": [[15, 15, 15], [4, 1, 0], [5, 5, 5], [1, 1, 0]],
    "total_og_mou": [[30, 34, 32], [11, 5, 0], [15, 15, 15], [2, 2, 0]],
    "vol_2g_mb": [[100, 120, 90], [10, 0, 0], [0, 0, 0], [0, 0, 0]],
    "vol_3g_mb": [[500, 400, 450], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
    "vbc_3g": [[0.0, 1.5, 2.0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
    "total_rech_num": [[4, 5, 4], [2, 1, 0], [3, 3, 3], [1, 1, 1]],
    "total_rech_data": [[2, 2, 1], [1, NAN, NAN], [NAN, NAN, NAN], [NAN, NAN, NAN]],
    "date_of_last_rech_data": [
        ["6/20/2014", "7/21/2014", "8/19/2014"],
        ["6/5/2014", NAN, NAN],
        [NAN, NAN, NAN],
        [NAN, NAN, NAN],
    ],
}


def build_raw() -> pd.DataFrame:
    """Four customers shaped like the Kaggle train.csv that satisfy the data contract."""
    size = 4
    columns = {
        "id": [0, 1, 2, 3],
        "circle_id": [109] * size,
        "loc_og_t2o_mou": [0.0] * size,
        "aon": [900, 400, 1500, 60],
        "churn_probability": [0, 1, 0, 0],
    }
    for position, month in enumerate(MONTHS):
        name = {base: column_name(base, month) for g in GROUPS for base in g.bases}
        for base in name:
            columns[name[base]] = [0] * size
        for base, rows in OVERRIDES.items():
            columns[name[base]] = [row[position] for row in rows]
        voice_missing = pd.isna(columns[name["onnet_mou"]])
        data_missing = pd.isna(columns[name["total_rech_data"]])
        for base in VOICE_BLOCK:
            columns[name[base]] = np.where(voice_missing, NAN, columns[name[base]]).tolist()
        for base in DATA_BLOCK:
            if base != "date_of_last_rech_data":
                columns[name[base]] = np.where(data_missing, NAN, columns[name[base]]).tolist()
        columns[name["date_of_last_rech"]] = [
            f"{month}/15/2014" if count > 0 else NAN for count in columns[name["total_rech_num"]]
        ]
        columns[name["last_date_of_month"]] = [MONTH_ENDS[month]] * size
    return pd.DataFrame(columns)


@pytest.fixture
def raw() -> pd.DataFrame:
    return build_raw()


def build_population_raw() -> pd.DataFrame:
    """200 raw customers: 50 copies of the four hand-made ones, with distinct ids.

    Recharge amounts grow with the copy number, so a top-30% filter has something to cut.
    In every other copy customer 0, who stays active, churns in month 9, so the test
    window has churners among eligible customers.
    """
    base = build_raw()
    copies = []
    for copy in range(50):
        frame = base.copy()
        frame["id"] = base["id"] + 4 * copy
        frame.loc[0, "churn_probability"] = copy % 2
        for month in MONTHS:
            frame[f"total_rech_amt_{month}"] = 10 * (copy + 1)
        copies.append(frame)
    return pd.concat(copies, ignore_index=True)


def build_population() -> pd.DataFrame:
    from prepaid_churn.clean import clean
    from prepaid_churn.schema import validate

    return clean(validate(build_population_raw()))


@pytest.fixture
def population() -> pd.DataFrame:
    """The 200 customers of `build_population_raw`, validated and cleaned."""
    return build_population()


@pytest.fixture(scope="session")
def trained() -> dict:
    """Models, champion and release gate, trained once on the population (T8 tests)."""
    from prepaid_churn.evaluation import freeze, release_gate
    from prepaid_churn.training import train_models
    from prepaid_churn.windows import build_datasets

    datasets = build_datasets(build_population())
    models = train_models(datasets["train"])
    champion, choices = freeze(models, datasets["validation"], chosen_at="2026-09-19")
    gate = release_gate(champion, choices, models, datasets["test"])
    return {"datasets": datasets, "models": models, "champion": champion, "gate": gate}


@pytest.fixture
def passing_gate(trained) -> dict:
    """The real gate with every check set to pass: 200 copied customers cannot judge a model."""
    gate = deepcopy(trained["gate"])
    for check in gate["thresholds"].values():
        check["passed"] = True
    gate["passed"] = True
    return gate


@pytest.fixture
def bundle(trained, passing_gate):
    from prepaid_churn.bundle import build_bundle

    return build_bundle(
        trained["champion"], passing_gate, trained["datasets"]["validation"], "2026-09-19T12:00"
    )


# The four subscribers every integration test uses: one approved, one rejected, two left
# unreviewed, and one whose identifier is the literal text "NA".
# Taha's version from `test_client.py` is the shared one; `test_api.py`, `test_client.py`
# and `test_retention.py` had grown their own identical copies.
STAMP = "2026-09-20T12:00:00+00:00"


@pytest.fixture
def customers() -> pd.DataFrame:
    """Decision inputs: what `propose` needs to build a campaign."""
    return pd.DataFrame(
        {
            "subscriber_id": ["0001", "0002", "NA", "0004"],
            "churn_probability": [0.5, 0.4, 0.3, 0.2],
            "risk_band": ["high"] * 4,
            "value_tier": ["high"] * 4,
            "value_status": ["scenario"] * 4,
            "value_12m_base_lyd": [100.0] * 4,
            "bundle_held": ["PAYG"] * 4,
            "uses_voice": [True] * 4,
            "uses_data": [True] * 4,
        }
    )


@pytest.fixture
def portfolio() -> pd.DataFrame:
    """A bundle-backed `churn tiers` export for the same four subscribers."""
    return pd.DataFrame(
        {
            "subscriber_id": ["0001", "0002", "NA", "0004"],
            "churn_probability": [0.5, 0.4, 0.3, None],
            "risk_band": ["high", "high", "medium", "already_silent"],
            "reason_1": ["No recharge for 21 days"] * 3 + [None],
            "reason_2": ["Outgoing minutes down 80%"] * 3 + [None],
            "reason_3": [None] * 4,
            "value_tier": ["high", "high", "medium", "very_low"],
            "monthly_spend_lyd": [40.0, 30.0, 20.0, 5.0],
            "value_12m_base_lyd": [100.0, 80.0, 60.0, None],
            "value_status": ["scenario", "scenario", "scenario", "already_silent"],
            "scored_at": [STAMP] * 4,
        }
    )
