import pytest

from prepaid_churn.data import id_column, load_raw, monthly_columns, split_month


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("arpu_6", ("arpu", 6)),
        ("total_rech_num_9", ("total_rech_num", 9)),
        ("last_date_of_month_7", ("last_date_of_month", 7)),
        ("jun_vbc_3g", ("vbc_3g", 6)),
        ("aug_vbc_3g", ("vbc_3g", 8)),
        ("aon", ("aon", None)),
        ("loc_og_t2o_mou", ("loc_og_t2o_mou", None)),
        ("vol_2g_mb", ("vol_2g_mb", None)),
    ],
)
def test_split_month(column, expected):
    assert split_month(column) == expected


def test_monthly_columns_aligns_months(raw):
    table = monthly_columns(raw.columns)
    assert list(table.columns) == [6, 7, 8]
    assert table.at["vbc_3g", 7] == "jul_vbc_3g"
    assert table.at["onnet_mou", 8] == "onnet_mou_8"
    assert "aon" not in table.index


def test_id_column(raw):
    assert id_column(raw) == "id"
    assert id_column(raw.rename(columns={"id": "mobile_number"})) == "mobile_number"
    with pytest.raises(ValueError):
        id_column(raw.drop(columns="id"))


def test_load_raw_missing_file_explains_download(tmp_path):
    with pytest.raises(FileNotFoundError, match="README"):
        load_raw(tmp_path / "train.csv")
