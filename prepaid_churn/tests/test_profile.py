import pytest

from prepaid_churn.profile import (
    build_report,
    constant_columns,
    duplicates,
    inactivity_by_month,
    label_vs_month_8,
    markdown_table,
    missing_agreement,
    missing_by_month,
    negative_values,
    zero_usage_when_minutes_missing,
)


def test_missing_by_month(raw):
    missing = missing_by_month(raw)
    assert missing.at["onnet_mou", 8] == 0.25
    assert missing.at["onnet_mou", 6] == 0.0
    assert missing.at["total_rech_data", 7] == 0.75


def test_missing_agreement_with_minutes(raw):
    agreement = missing_agreement(raw, "onnet_mou")
    assert agreement.at["offnet_mou", 8] == 1.0
    assert "onnet_mou" not in agreement.index


def test_missing_agreement_with_data_recharge(raw):
    agreement = missing_agreement(raw, "date_of_last_rech_data")
    assert agreement.at["total_rech_data", 6] == 1.0
    assert agreement.at["total_rech_data", 8] == 1.0


def test_missing_agreement_unknown_reference(raw):
    assert missing_agreement(raw, "not_a_column").empty


def test_zero_usage_when_minutes_missing(raw):
    result = zero_usage_when_minutes_missing(raw)
    assert result.at[8, "customers_with_missing_minutes"] == 1
    assert result.at[8, "share_with_zero_totals"] == 1.0
    assert result.at[6, "customers_with_missing_minutes"] == 0


def test_constant_columns_ignores_missing_values(raw):
    constant = constant_columns(raw)
    assert "circle_id" in constant
    assert "jun_vbc_3g" in constant
    # One real value plus missing values is still constant.
    assert "total_rech_data_8" in constant
    assert "total_rech_data_6" not in constant


def test_duplicates(raw):
    assert duplicates(raw) == {"duplicate_ids": 0, "duplicate_rows_ignoring_id": 0}
    doubled = raw.iloc[[0, 0]].assign(id=[0, 5])
    assert duplicates(doubled)["duplicate_rows_ignoring_id"] == 1


def test_negative_values(raw):
    negatives = negative_values(raw)
    assert list(negatives.index) == ["arpu_8"]
    assert negatives.at["arpu_8", "minimum"] == -5


def test_inactivity_by_month(raw):
    month_8 = inactivity_by_month(raw).loc[8]
    assert month_8["usage_inactive"] == 0.5
    assert month_8["recharge_inactive"] == 0.25
    assert month_8["both"] == 0.25
    assert month_8["usage_only"] == 0.25
    assert month_8["recharge_only"] == 0.0


def test_label_vs_month_8(raw):
    result = label_vs_month_8(raw)
    assert result["label_rate"] == 0.25
    assert result["churners_already_inactive_in_month_8"] == 1.0
    assert result["label_rate_if_inactive_in_month_8"] == 0.5
    assert result["label_rate_if_active_in_month_8"] == 0.0


def test_markdown_table_formats_missing_and_floats(raw):
    table = markdown_table(missing_by_month(raw).loc[["onnet_mou"]])
    assert table.splitlines()[0] == "|  | 6 | 7 | 8 |"
    assert "| onnet_mou | 0.0000 | 0.0000 | 0.2500 |" in table


@pytest.mark.parametrize("with_label", [True, False])
def test_build_report(raw, with_label):
    frame = raw if with_label else raw.drop(columns="churn_probability")
    report = build_report(frame)
    assert report.startswith("# T1 data profile")
    assert "Rows: 4." in report
    assert ("Month 9 label" in report) == with_label
