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
