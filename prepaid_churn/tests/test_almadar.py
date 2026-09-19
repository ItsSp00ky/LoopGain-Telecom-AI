import pandas as pd
import pytest

from prepaid_churn.almadar import (
    STATUSES,
    InvalidCatalogueError,
    check_against_source,
    load_market,
    load_offers,
    validate_market,
    validate_offers,
)


@pytest.fixture
def two_offers() -> pd.DataFrame:
    """A metered bundle and the morning pass, as they appear in offers.csv."""
    common = {
        "operator": "Almadar Aljadid",
        "network": None,
        "voice_minutes": None,
        "members": None,
        "max_download_mbps": None,
        "max_upload_mbps": None,
        "source_file": "source/internet_offers_data_v4.csv",
        "collected": "2026-09-18",
        "notes": None,
    }
    return pd.DataFrame(
        [
            common
            | {
                "offer_id": "MO_20",
                "family_ar": "عروض شهرية",
                "family_en": "Monthly offers",
                "name_ar": "نت 20",
                "name_en": "Net 20",
                "price_lyd": 35,
                "validity_ar": "30 يوم",
                "validity_hours": 720,
                "data_gb": 20,
                "data_unlimited": 0,
                "volume_source": "name",
                "voice_unlimited": 0,
                "valid_from_hour": None,
                "valid_to_hour": None,
                "source_row": 11,
            },
            common
            | {
                "offer_id": "SABAH_1",
                "family_ar": "عروض الصبح",
                "family_en": "Morning offers",
                "name_ar": "الصبح",
                "name_en": "Morning",
                "price_lyd": 1,
                "validity_ar": "صلاحية 1 يوم",
                "validity_hours": 24,
                "data_gb": None,
                "data_unlimited": 1,
                "volume_source": "stated",
                "voice_unlimited": 1,
                "valid_from_hour": 6,
                "valid_to_hour": 11,
                "source_row": 57,
            },
        ]
    )


def _problems(offers: pd.DataFrame) -> str:
    with pytest.raises(InvalidCatalogueError) as error:
        validate_offers(offers)
    return str(error.value)


def test_valid_offers_pass(two_offers):
    assert len(validate_offers(two_offers)) == 2


def test_every_broken_rule_is_reported_at_once(two_offers):
    broken = pd.concat([two_offers, two_offers.iloc[[0]]], ignore_index=True)
    broken.loc[1, "price_lyd"] = -1
    broken.loc[1, "data_gb"] = 5  # unlimited data with a volume
    broken.loc[1, "valid_to_hour"] = None  # half a time window
    broken.loc[2, "operator"] = "Unknown Telecom"
    problems = _problems(broken)
    for expected in (
        "offer_id",
        "price_lyd",
        "operator",
        "unlimited data has no volume",
        "a time window has both a start and an end",
    ):
        assert expected in problems


def test_volume_source_must_match_the_volume(two_offers):
    two_offers.loc[0, "data_gb"] = None  # "name" but no number
    problems = _problems(two_offers)
    assert "a volume read from the name is a number" in problems
    assert "volume source is 'none'" in problems


def test_unlimited_voice_has_no_minutes(two_offers):
    two_offers.loc[1, "voice_minutes"] = 100
    assert "unlimited voice has no minute count" in _problems(two_offers)


def test_extra_columns_are_refused(two_offers):
    # The catalogue is shared with the chatbot, so its columns are fixed.
    assert "cost" in _problems(two_offers.assign(cost=1.0))


def test_real_catalogue_is_valid_and_complete():
    offers = load_offers()
    assert len(offers) == 57
    assert offers["family_en"].nunique() == 17
    assert offers[["source_file", "source_row", "collected"]].notna().all().all()


def test_real_catalogue_matches_the_operator_file():
    assert check_against_source(load_offers()) == []


def test_ali_catalogue_is_the_catalogue_without_mix():
    # Ali_Branch kept 37 packages in 12 families; the 20 Mix packages are the difference.
    offers = load_offers()
    without_mix = offers[~offers["offer_id"].str.startswith("MIX_")]
    assert len(without_mix) == 37
    assert without_mix["family_en"].nunique() == 12


def test_a_changed_price_is_caught():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "MO_20", "price_lyd"] = 30.0
    assert check_against_source(offers) == ["MO_20: price_lyd is 30.0, source says 35.0"]


def test_a_stated_volume_must_be_marked_stated():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "MIX_DIA_1", "volume_source"] = "name"
    assert check_against_source(offers) == [
        "MIX_DIA_1: the source states the volume (3.0), so volume_source must be 'stated'"
    ]


def test_missing_and_repeated_source_rows_are_caught():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "SABAH_1", "source_row"] = 56
    assert check_against_source(offers) == [
        "source/internet_offers_data_v4.csv: source rows missing [57], repeated [56], unknown []"
    ]


def test_real_market_facts_have_status_and_source():
    facts = load_market()
    assert all(table["status"] in STATUSES for table in facts.values())
    assert facts["recharge_cards"]["values_lyd"] == [5, 10, 20, 40, 100]
    assert facts["arpu"]["status"] == "assumption"


def test_market_facts_without_status_or_source_fail():
    with pytest.raises(InvalidCatalogueError) as error:
        validate_market({"arpu": {"monthly_lyd": 40.0}, "cards": [5, 10]})
    message = str(error.value)
    assert "arpu: status must be one of" in message
    assert "arpu: source is missing" in message
    assert "cards: must be a table" in message
