import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from prepaid_churn.api import (
    API_KEY_HEADER,
    CHATBOT_KEY_VARIABLE,
    COPILOT_KEY_VARIABLE,
    ApiKeys,
    build_app,
    create_app,
    keys_from_environment,
)
from prepaid_churn.bundle import save_bundle
from prepaid_churn.campaign import build_campaign, review_campaign, review_file, save_campaign
from prepaid_churn.cli import build_parser
from prepaid_churn.demo import sms_parts
from prepaid_churn.operator_market import load_offers
from prepaid_churn.privacy import pseudonymize
from prepaid_churn.retention import load_policy, propose
from prepaid_churn.service import (
    ServiceConfigurationError,
    ServicePaths,
    gift_message,
    load_state,
    refresh_campaign,
)

STAMP = "2026-09-20T12:00:00+00:00"
CHATBOT_KEY = "chatbot-key-for-the-tests-only"
COPILOT_KEY = "copilot-key-for-the-tests-only"


@pytest.fixture
def keys():
    return ApiKeys(CHATBOT_KEY, COPILOT_KEY)


@pytest.fixture
def offers():
    return load_offers()


@pytest.fixture
def policy():
    # The mechanism tests keep a preferred morning offer with a larger assumed share, so they
    # exercise the preference; the shipped policy assumes the same 5% for every offer (decision 46).
    return replace(load_policy(), holdout_fraction=0.0, offpeak_share_saved=0.10)


@pytest.fixture
def served(tmp_path, bundle, customers, offers, policy, portfolio):
    """A state loaded the way the real service loads it.

    Subscriber 0001 is approved, 0002 is rejected, and "NA" and 0004 stay unreviewed, so
    every case the chatbot has to treat the same way is present at once.
    """
    save_bundle(bundle, tmp_path / "bundle")
    decisions, comparison = propose(customers, offers, policy)
    campaign = build_campaign(customers, decisions, comparison, offers, policy, STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "approved", ["0001"], reviewed_at=STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "rejected", ["0002"], reviewed_at=STAMP)
    campaign_path = save_campaign(campaign, tmp_path / "campaign")
    portfolio_path = tmp_path / "tiers.csv"
    portfolio.to_csv(portfolio_path, index=False)
    return load_state(
        ServicePaths(
            bundle_dir=tmp_path / "bundle",
            portfolio_path=portfolio_path,
            campaign_path=campaign_path,
        )
    )


@pytest.fixture
def client(served, keys):
    return TestClient(create_app(served, keys))


def chatbot(client, url):
    return client.get(url, headers={API_KEY_HEADER: CHATBOT_KEY})


def copilot(client, url):
    return client.get(url, headers={API_KEY_HEADER: COPILOT_KEY})


def test_literal_na_id_survives_the_csv_and_copilot_lookup(client):
    response = copilot(client, "/subscribers/NA/risk")
    assert response.status_code == 200
    assert response.json()["subscriber_id"] == "NA"
    assert response.json()["churn_probability"] == 0.3


def test_non_ascii_presented_key_is_unauthorized_instead_of_crashing(client):
    response = client.get("/catalogue", headers={API_KEY_HEADER: b"\xe9"})
    assert response.status_code == 401


@pytest.mark.parametrize("key", ["é" * 32, " " * 32, "a" * 31 + "\n"])
def test_configured_keys_must_be_usable_http_credentials(key):
    with pytest.raises(ServiceConfigurationError, match="ASCII"):
        ApiKeys(key, COPILOT_KEY)


def test_retired_approved_offer_is_withheld_and_health_explains(served, offers, tmp_path, keys):
    current_path = tmp_path / "current.csv"
    offers.loc[offers.offer_id.ne("SABAH_1")].to_csv(current_path, index=False)
    state = load_state(
        ServicePaths(
            tmp_path / "bundle",
            tmp_path / "tiers.csv",
            tmp_path / "campaign" / "proposals.json",
            current_path,
        )
    )
    client = TestClient(create_app(state, keys))
    assert chatbot(client, "/subscribers/0001/retention").status_code == 404
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["latest_outputs"]["approved_offers"] == 0
    assert "no longer in the current catalogue" in health["problems"][0]


@pytest.mark.parametrize("ids", [["same", "same", "NA", "0004"], ["", "0002", "NA", "0004"]])
def test_malformed_portfolio_ids_fail_at_load(served, portfolio, tmp_path, keys, ids):
    portfolio["subscriber_id"] = ids
    portfolio.to_csv(tmp_path / "tiers.csv", index=False)
    state = load_state(
        ServicePaths(
            tmp_path / "bundle", tmp_path / "tiers.csv", tmp_path / "campaign" / "proposals.json"
        )
    )
    client = TestClient(create_app(state, keys))
    assert client.get("/health").json()["status"] == "degraded"
    assert copilot(client, "/subscribers/0001/risk").status_code == 503


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_needs_no_key_and_says_what_is_being_served(client, bundle):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["bundle_loaded"] is True
    assert body["smoke_prediction_passed"] is True
    assert body["model_version"] == bundle.version
    assert body["problems"] == []
    outputs = body["latest_outputs"]
    assert outputs["subscribers_in_portfolio"] == 4
    assert outputs["approved_offers"] == 1  # the rejected and unreviewed rows are not here
    assert outputs["scored_at"] == STAMP
    assert outputs["campaign_created_at"] == STAMP


def test_health_reports_degraded_rather_than_pretending(tmp_path, keys):
    """An empty checkout is the normal state before the pipeline has been run."""
    state = load_state(
        ServicePaths(
            bundle_dir=tmp_path / "missing",
            portfolio_path=tmp_path / "missing.csv",
            campaign_path=tmp_path / "missing.json",
        )
    )
    body = TestClient(create_app(state, keys)).get("/health").json()
    assert body["status"] == "degraded"
    assert body["bundle_loaded"] is False
    assert body["smoke_prediction_passed"] is False
    assert len(body["problems"]) == 2  # the bundle and the portfolio; no campaign is not a fault
    assert body["latest_outputs"]["approved_offers"] == 0


# ---------------------------------------------------------------------------
# /catalogue
# ---------------------------------------------------------------------------


def test_the_chatbot_gets_every_package_with_its_collection_date(client, offers):
    body = chatbot(client, "/catalogue").json()
    assert body["count"] == len(offers)
    assert {row["offer_id"] for row in body["offers"]} == set(offers["offer_id"])
    assert all(row["collected"] for row in body["offers"])
    assert all(row["operator"] == "Libyan mobile operator" for row in body["offers"])
    morning = next(row for row in body["offers"] if row["offer_id"] == "SABAH_1")
    assert (morning["valid_from_hour"], morning["valid_to_hour"]) == (6, 11)


# ---------------------------------------------------------------------------
# /subscribers/{id}/retention
# ---------------------------------------------------------------------------


def test_an_approved_offer_reaches_the_chatbot_with_the_package(client):
    body = chatbot(client, "/subscribers/0001/retention").json()
    assert body["subscriber_id"] == "0001"
    assert body["recommended_offer_id"] == "SABAH_1"
    assert "06:00-11:00" in body["offer_reason_en"]
    assert "06:00-11:00" in body["offer_reason_ar"]
    assert body["reviewed_at"] == STAMP
    assert body["offer"]["name_en"]
    assert body["offer"]["name_ar"]
    assert body["offer"]["price_lyd"] == 1
    assert body["customer_message_en"] == (
        "Your gift: Morning, unlimited data and calls from 06:00 to 11:00 for a day."
    )
    assert body["customer_message_ar"] == (
        "هديتك: الصبح، إنترنت ومكالمات لا محدودة من 06:00 إلى 11:00 لمدة يوم."
    )


def test_the_customer_message_never_carries_the_policy_s_reason(client):
    """The reason says the operator computed the customer's value (decision 51)."""
    body = chatbot(client, "/subscribers/0001/retention").json()
    assert body["offer_reason_en"] not in body["customer_message_en"]
    assert body["offer_reason_ar"] not in body["customer_message_ar"]
    assert "value" not in body["customer_message_en"]


@pytest.mark.parametrize(
    ("subscriber_id", "why"),
    [
        ("0002", "a reviewer rejected it"),
        ("NA", "nobody reviewed it"),
        ("0004", "nobody reviewed it"),
        ("0009", "there is no proposal at all"),
    ],
)
def test_only_an_approved_offer_is_ever_returned(client, subscriber_id, why):
    response = chatbot(client, f"/subscribers/{subscriber_id}/retention")
    assert response.status_code == 404, why
    # The same answer for every case, so the customer is not told an offer was refused.
    assert response.json()["detail"] == "No approved retention offer for this subscriber."


def test_the_chatbot_is_never_told_a_churn_probability(client, served, keys):
    """Two layers have to fail before a probability could leak, so both are exercised."""
    body = chatbot(client, "/subscribers/0001/retention").json()
    assert not {"churn_probability", "risk_band", "value_tier"} & set(body)

    # Even if the released frame grew a risk column, the response model drops it.
    leaky = served.approved.copy()
    leaky["churn_probability"] = 0.87
    leaky["value_12m_base_lyd"] = 100.0
    leaky_client = TestClient(create_app(replace(served, approved=leaky), keys))
    text = json.dumps(chatbot(leaky_client, "/subscribers/0001/retention").json())
    assert "0.87" not in text
    assert "churn" not in text
    assert "probability" not in text


def test_an_approval_reaches_the_chatbot_without_a_restart(client, tmp_path):
    """A reviewer approves while the service runs, and the next request serves it."""
    assert chatbot(client, "/subscribers/0004/retention").status_code == 404
    review_file(tmp_path / "campaign" / "proposals.json", "Ali Marghem", "approved", ["0004"])
    response = chatbot(client, "/subscribers/0004/retention")
    assert response.status_code == 200
    assert response.json()["subscriber_id"] == "0004"
    assert client.get("/health").json()["latest_outputs"]["approved_offers"] == 2


def test_an_unchanged_campaign_is_not_read_again(served):
    """While nobody reviews, a request costs one `stat` and keeps the state it had."""
    assert refresh_campaign(served) is served


def test_the_reviewer_name_stays_inside_the_operator(client):
    """The chatbot speaks to the customer; which employee approved the campaign is ours."""
    text = json.dumps(chatbot(client, "/subscribers/0001/retention").json())
    assert "Ali Marghem" not in text
    assert "reviewer" not in text


@pytest.mark.parametrize(
    "number",
    ["0912345678", "+218912345678", "091 234 5678", "091-234-5678", "0945678901"],
)
def test_an_id_shaped_like_a_phone_number_is_refused(client, number):
    response = chatbot(client, f"/subscribers/{number}/retention")
    assert response.status_code == 422
    assert "pseudonymous" in response.json()["detail"]


def test_a_pseudonymous_id_is_looked_up_rather_than_refused(client):
    """A salted digest must not trip the phone-number check, or nothing works."""
    digest = pseudonymize("0912345678", "a-salt-long-enough-to-use")
    assert chatbot(client, f"/subscribers/{digest}/retention").status_code == 404


# ---------------------------------------------------------------------------
# The customer message (decision 51)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offer_id", "english", "arabic"),
    [
        ("DAY_50MB", "Your gift: Net 50MB for a day.", "هديتك: نت 50MB لمدة يوم."),
        ("WK_1", "Your gift: Net 1 for 7 days.", "هديتك: نت 1 لمدة 7 أيام."),
        (
            "GOLD_7",
            "Your gift: Golden 7, unlimited data for 7 days.",
            "هديتك: ذهبي 7، إنترنت لا محدود لمدة 7 أيام.",
        ),
        (
            "FAM_70",
            "Your gift: Family 70, 70 GB of data and 300 minutes for 30 days.",
            "هديتك: فاميلي 70، إنترنت 70 قيقا و300 دقيقة لمدة 30 يوماً.",
        ),
        ("HR5G_2", "Your gift: Net 2 hours 5G for 2 hours.", "هديتك: نت ساعتين 2_5G لمدة ساعتين."),
        ("SOC_D", "Your gift: Social daily for a day.", "هديتك: سوشيال يومي لمدة يوم."),
    ],
)
def test_the_message_says_what_the_package_gives_and_for_how_long(
    offers, offer_id, english, arabic
):
    """Units are the operator's own (ميقا, قيقا, دقيقة); nothing is said that it does not state."""
    offer = offers.set_index("offer_id").loc[offer_id].to_dict() | {"offer_id": offer_id}
    assert gift_message(offer, "en") == english
    assert gift_message(offer, "ar") == arabic


@pytest.mark.parametrize("offer_id", ["DAY_QTR", "MO_20", "SLVR_1", "HR5G_1"])
def test_the_message_never_states_what_the_operator_does_not(offers, offer_id):
    """A volume read from the name, or unlimited as `Ali_Branch` reported it, is not said.

    `نت 1/4` would otherwise become 250 MB by our own conversion, and Silver "unlimited"
    although the operator's file only caps its speed.
    """
    offer = offers.set_index("offer_id").loc[offer_id].to_dict() | {"offer_id": offer_id}
    assert offer["volume_source"] != "stated"
    for language, words in (("en", ("GB", "MB", "unlimited")), ("ar", ("قيقا", "ميقا", "محدود"))):
        message = gift_message(offer, language)
        assert not any(
            word in message.replace(str(offer[f"name_{language}"]), "") for word in words
        )


def test_a_row_without_its_volume_source_says_no_volume(offers):
    """The trimmed catalogue columns carry no source, so they must not produce a promise."""
    offer = offers.set_index("offer_id").loc["GOLD_7"].to_dict() | {"offer_id": "GOLD_7"}
    del offer["volume_source"]
    assert gift_message(offer, "en") == "Your gift: Golden 7 for 7 days."


def test_a_missing_name_falls_back_instead_of_printing_nan(offers):
    offer = offers.set_index("offer_id").loc["SOC_D"].to_dict() | {"offer_id": "SOC_D"}
    offer["name_ar"] = float("nan")
    assert gift_message(offer, "ar") == "هديتك: Social daily لمدة يوم."


def test_every_package_s_message_fits_one_arabic_sms(offers):
    """One Arabic character makes the SMS 70 characters a part; two parts are billed twice."""
    for offer in offers.to_dict(orient="records"):
        assert sms_parts(gift_message(offer, "ar"))["parts"] == 1, offer["offer_id"]


def test_the_message_is_arabic_or_english(offers):
    with pytest.raises(ValueError, match="Arabic or English"):
        gift_message(offers.iloc[0].to_dict(), "fr")


# ---------------------------------------------------------------------------
# /portfolio/summary
# ---------------------------------------------------------------------------


def test_the_copilot_gets_the_portfolio_with_the_model_evidence(client, bundle):
    body = copilot(client, "/portfolio/summary").json()
    assert body["model_version"] == bundle.version
    assert body["subscribers"] == 4
    assert body["risk_available"] is True
    assert body["scored_at"] == STAMP
    bands = {group["name"]: group for group in body["by_risk_band"]}
    assert [group["name"] for group in body["by_risk_band"]] == ["high", "medium", "already_silent"]
    assert bands["high"]["customers"] == 2
    assert set(body["success_thresholds"]) == {
        "capture",
        "better_than_chance",
        "better_than_baseline",
        "calibration",
    }
    assert body["test_metrics"]
    assert body["release_gate_passed"] is True


def test_lyd_at_risk_is_weighted_by_each_customer_s_risk(client):
    """40,000 customers at 5% risk are not 40,000 values at risk (Ali's cohort note)."""
    bands = {
        group["name"]: group
        for group in copilot(client, "/portfolio/summary").json()["by_risk_band"]
    }
    assert bands["high"]["lyd_at_risk"] == pytest.approx(100 * 0.5 + 80 * 0.4)
    assert bands["high"]["lyd_at_risk"] != pytest.approx(180.0)  # not the unweighted value
    assert bands["already_silent"]["lyd_at_risk"] == pytest.approx(0.0)
    assert bands["high"]["monthly_spend_lyd"] == pytest.approx(70.0)


def test_a_tiers_only_export_reports_risk_as_unavailable_not_as_zero(served, keys, portfolio):
    """This checkout has no real bundle, so `churn tiers --tiers-only` is the normal case."""
    tiers_only = portfolio.drop(columns=["churn_probability", "risk_band", "scored_at"])
    tiers_only["value_12m_base_lyd"] = None
    tiers_only["value_status"] = "risk_unavailable"
    client = TestClient(create_app(replace(served, portfolio=tiers_only), keys))
    body = copilot(client, "/portfolio/summary").json()
    assert body["risk_available"] is False
    assert body["by_risk_band"] == []
    assert [group["name"] for group in body["by_value_tier"]] == ["high", "medium", "very_low"]
    assert all(group["lyd_at_risk"] is None for group in body["by_value_tier"])
    assert body["by_value_tier"][0]["customers"] == 2


def test_the_portfolio_is_unavailable_rather_than_empty_when_nothing_was_scored(served, keys):
    client = TestClient(create_app(replace(served, portfolio=None), keys))
    response = copilot(client, "/portfolio/summary")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/catalogue", "/subscribers/0001/retention", "/portfolio/summary"])
def test_no_key_and_an_unknown_key_are_both_refused(client, url):
    assert client.get(url).status_code == 401
    assert client.get(url, headers={API_KEY_HEADER: "not-a-key-at-all-but-long"}).status_code == 401


@pytest.mark.parametrize("url", ["/catalogue", "/subscribers/0001/retention"])
def test_the_copilot_key_is_not_accepted_on_chatbot_endpoints(client, url):
    response = copilot(client, url)
    assert response.status_code == 403
    assert "chatbot" in response.json()["detail"]


def test_the_chatbot_key_is_not_accepted_on_copilot_endpoints(client):
    """A leaked chatbot key must not open the portfolio."""
    response = chatbot(client, "/portfolio/summary")
    assert response.status_code == 403
    assert "copilot" in response.json()["detail"]


def test_the_service_refuses_to_start_without_both_keys():
    for environ in ({}, {CHATBOT_KEY_VARIABLE: CHATBOT_KEY}, {COPILOT_KEY_VARIABLE: COPILOT_KEY}):
        with pytest.raises(ServiceConfigurationError, match="PREPAID_CHURN_"):
            keys_from_environment(environ)


def test_the_two_keys_must_differ_and_must_not_be_trivial():
    with pytest.raises(ServiceConfigurationError, match="must differ"):
        ApiKeys(CHATBOT_KEY, CHATBOT_KEY)
    with pytest.raises(ServiceConfigurationError, match="at least"):
        ApiKeys("short", COPILOT_KEY)


def test_keys_are_read_from_the_environment():
    keys = keys_from_environment(
        {CHATBOT_KEY_VARIABLE: CHATBOT_KEY, COPILOT_KEY_VARIABLE: COPILOT_KEY}
    )
    assert keys.consumer(CHATBOT_KEY) == "chatbot"
    assert keys.consumer(COPILOT_KEY) == "copilot"
    assert keys.consumer("something else entirely") is None


# ---------------------------------------------------------------------------
# The service as a whole
# ---------------------------------------------------------------------------


def test_the_service_has_no_write_path(client):
    """Nothing may be created, changed or approved through the API (ticket T15)."""
    methods = {
        method
        for path in client.app.openapi()["paths"].values()
        for method in path
        if method != "parameters"
    }
    assert methods == {"get"}


def test_the_openapi_page_documents_every_endpoint(client):
    paths = client.app.openapi()["paths"]
    assert set(paths) == {
        "/health",
        "/catalogue",
        "/subscribers/{subscriber_id}/retention",
        "/portfolio/summary",
        "/subscribers/{subscriber_id}/risk",  # added by T20, for the copilot
    }
    assert client.get("/docs").status_code == 200


def test_build_app_reads_the_keys_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(CHATBOT_KEY_VARIABLE, CHATBOT_KEY)
    monkeypatch.setenv(COPILOT_KEY_VARIABLE, COPILOT_KEY)
    paths = ServicePaths(
        bundle_dir=tmp_path / "missing",
        portfolio_path=tmp_path / "missing.csv",
        campaign_path=tmp_path / "missing.json",
    )
    assert TestClient(build_app(paths)).get("/health").json()["status"] == "degraded"


def test_build_app_refuses_to_start_without_keys(tmp_path, monkeypatch):
    """Failing here beats loading a bundle and then serving it without access control."""
    monkeypatch.delenv(CHATBOT_KEY_VARIABLE, raising=False)
    monkeypatch.delenv(COPILOT_KEY_VARIABLE, raising=False)
    paths = ServicePaths(
        bundle_dir=tmp_path / "missing",
        portfolio_path=tmp_path / "missing.csv",
        campaign_path=tmp_path / "missing.json",
    )
    with pytest.raises(ServiceConfigurationError, match="PREPAID_CHURN_"):
        build_app(paths)


def test_serve_is_a_churn_command():
    args = build_parser().parse_args(["serve", "--port", "9001"])
    assert (args.command, args.port, args.host) == ("serve", 9001, "127.0.0.1")
