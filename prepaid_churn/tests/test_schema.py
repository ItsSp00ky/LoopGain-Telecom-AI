import numpy as np
import pytest

from prepaid_churn.cli import CONTRACT_PATH
from prepaid_churn.schema import (
    DATA_BLOCK,
    GROUPS,
    VOICE_BLOCK,
    InvalidExportError,
    contract_markdown,
    validate,
)


def test_valid_export_passes(raw):
    validated = validate(raw)
    assert validated.shape == raw.shape


def test_unlabeled_export_passes(raw):
    validate(raw.drop(columns="churn_probability"))


def test_blocks_match_t1_findings():
    assert len(VOICE_BLOCK) == 27  # 29 minute columns minus 2 that are always 0
    assert len(DATA_BLOCK) == 10


def _problems(df) -> str:
    with pytest.raises(InvalidExportError) as error:
        validate(df)
    return str(error.value)


def test_missing_column(raw):
    assert "total_rech_num_7" in _problems(raw.drop(columns="total_rech_num_7"))


def test_wrong_type(raw):
    raw["total_og_mou_6"] = raw["total_og_mou_6"].astype(object)
    raw.loc[0, "total_og_mou_6"] = "abc"
    assert "total_og_mou_6" in _problems(raw)


def test_negative_minutes(raw):
    raw.loc[0, "total_og_mou_6"] = -1
    message = _problems(raw)
    assert "total_og_mou_6" in message
    assert "greater_than_or_equal_to" in message


def test_flag_out_of_range(raw):
    raw.loc[0, "fb_user_6"] = 2
    assert "fb_user_6" in _problems(raw)


def test_date_outside_its_month(raw):
    raw.loc[0, "date_of_last_rech_6"] = "7/1/2014"
    assert "date in month 6" in _problems(raw)


def test_partial_voice_block(raw):
    raw.loc[0, "offnet_mou_7"] = np.nan
    assert "voice block missing together in month 7" in _problems(raw)


def test_partial_data_block(raw):
    raw.loc[0, "fb_user_8"] = np.nan
    assert "data block missing together in month 8" in _problems(raw)


def test_recharge_date_without_recharge(raw):
    raw.loc[0, "date_of_last_rech_7"] = np.nan
    assert "recharge date missing only without recharges in month 7" in _problems(raw)


def test_duplicate_ids(raw):
    raw.loc[1, "id"] = 0
    assert "id" in _problems(raw)


def test_every_problem_is_reported(raw):
    raw.loc[0, "total_og_mou_6"] = -1
    message = _problems(raw.drop(columns="aon"))
    assert "2 problems" in message
    assert "aon" in message


def test_contract_lists_every_base_column():
    document = contract_markdown()
    for g in GROUPS:
        for base in g.bases:
            assert f"`{base}`" in document


def test_contract_document_is_current():
    assert CONTRACT_PATH.read_text(encoding="utf-8") == contract_markdown(), (
        "Run `uv run churn contract` to regenerate docs/data_contract.md."
    )
