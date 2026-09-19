import numpy as np
import pandas as pd
import pytest

NAN = np.nan


@pytest.fixture
def raw() -> pd.DataFrame:
    """Four hand-made customers shaped like the Kaggle train.csv.

    - 0: active every month, bought data.
    - 1: no voice record in month 8 (minute columns missing), no recharge in month 8, churns.
    - 2: voice only, never bought data (data recharge columns missing every month).
    - 3: inactive in month 8 but recharged, stays.
    """
    columns = {
        "id": [0, 1, 2, 3],
        "circle_id": [109, 109, 109, 109],
        "aon": [900, 400, 1500, 60],
        "churn_probability": [0, 1, 0, 0],
    }
    monthly = {
        "arpu": [[100, 90, 95], [50, 20, -5], [30, 30, 30], [10, 10, 0]],
        "onnet_mou": [[10, 12, 11], [5, 2, NAN], [7, 7, 7], [1, 1, 0]],
        "offnet_mou": [[20, 22, 21], [6, 3, NAN], [8, 8, 8], [1, 1, 0]],
        "total_ic_mou": [[15, 15, 15], [4, 1, 0], [5, 5, 5], [1, 1, 0]],
        "total_og_mou": [[30, 34, 32], [11, 5, 0], [15, 15, 15], [2, 2, 0]],
        "vol_2g_mb": [[100, 120, 90], [10, 0, 0], [0, 0, 0], [0, 0, 0]],
        "vol_3g_mb": [[500, 400, 450], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
        "total_rech_num": [[4, 5, 4], [2, 1, 0], [3, 3, 3], [1, 1, 1]],
        "total_rech_data": [[2, 2, 1], [1, NAN, NAN], [NAN, NAN, NAN], [NAN, NAN, NAN]],
        "date_of_last_rech_data": [
            ["6/20/2014", "7/21/2014", "8/19/2014"],
            ["6/5/2014", NAN, NAN],
            [NAN, NAN, NAN],
            [NAN, NAN, NAN],
        ],
    }
    for base, rows in monthly.items():
        for position, month in enumerate((6, 7, 8)):
            columns[f"{base}_{month}"] = [row[position] for row in rows]
    columns["jun_vbc_3g"] = [0.0, 0.0, 0.0, 0.0]
    columns["jul_vbc_3g"] = [1.5, 0.0, 0.0, 0.0]
    columns["aug_vbc_3g"] = [2.0, 0.0, 0.0, 0.0]
    return pd.DataFrame(columns)
