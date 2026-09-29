import pandas as pd

from prepaid_churn.clean import clean
from prepaid_churn.schema import validate


def test_drops_no_information_and_extra_columns(raw):
    cleaned = clean(validate(raw))
    assert "circle_id" not in cleaned.columns
    assert "loc_og_t2o_mou" not in cleaned.columns
    assert {"id", "aon", "churn_probability"} <= set(cleaned.columns)


def test_voice_block_missing_becomes_zero_with_flag(raw):
    cleaned = clean(validate(raw))
    assert cleaned["onnet_mou_8"].tolist() == [11, 0, 7, 0]
    assert cleaned["no_voice_record_8"].tolist() == [0, 1, 0, 0]
    assert cleaned["no_voice_record_6"].tolist() == [0, 0, 0, 0]


def test_data_block_missing_becomes_zero(raw):
    cleaned = clean(validate(raw))
    assert cleaned["total_rech_data_7"].tolist() == [2, 0, 0, 0]
    assert cleaned["fb_user_7"].tolist() == [0, 0, 0, 0]


def test_no_missing_values_left(raw):
    assert not clean(validate(raw)).isna().any().any()


def test_recharge_dates_become_days_to_month_end(raw):
    cleaned = clean(validate(raw))
    # Recharged on the 15th: 15 days to 30 June; no recharge in August: 31 (days in August).
    assert cleaned["days_since_last_rech_6"].tolist() == [15, 15, 15, 15]
    assert cleaned["days_since_last_rech_8"].tolist() == [16, 31, 16, 16]
    # Data recharge on 20 June: 10 days; never bought data: 30 (days in June).
    assert cleaned["days_since_last_rech_data_6"].tolist() == [10, 25, 30, 30]


def test_date_columns_are_removed(raw):
    cleaned = clean(validate(raw))
    assert not any(column.startswith(("date_of_", "last_date_of_")) for column in cleaned.columns)


def test_negative_arpu_is_kept(raw):
    assert clean(validate(raw))["arpu_8"].tolist() == [95, -5, 30, 0]


def test_cleaning_is_idempotent(raw):
    once = clean(validate(raw))
    pd.testing.assert_frame_equal(clean(once), once)


def test_extra_derived_columns_cannot_override_raw_activity(raw):
    expected = clean(validate(raw))
    raw["no_voice_record_8"] = 99
    raw["days_since_last_rech_8"] = -999
    pd.testing.assert_frame_equal(clean(validate(raw)), expected)
