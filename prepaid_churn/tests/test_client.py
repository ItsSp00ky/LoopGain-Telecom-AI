"""The contract test of T20: the example client against a service on a real port.

`test_api.py` calls the app in process, which proves the app answers.
This file proves the seam the other components will use: a real socket, a client that
imports nothing from the app, and the four refusals a consumer has to handle.
The service is started here the way `churn serve` starts it, so a mistake in the wiring
between the two shows up as a failing test rather than during integration week.
"""

import socket
import threading
import time
from contextlib import closing, contextmanager
from dataclasses import replace

import pytest
import uvicorn

from prepaid_churn import api, client
from prepaid_churn.almadar import load_offers
from prepaid_churn.api import (
    CHATBOT_KEY_VARIABLE,
    COPILOT_KEY_VARIABLE,
    ApiKeys,
    create_app,
)
from prepaid_churn.bundle import save_bundle
from prepaid_churn.campaign import build_campaign, review_campaign, save_campaign
from prepaid_churn.cli import main
from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.retention import load_policy, propose
from prepaid_churn.service import ServicePaths, load_state

STAMP = "2026-09-20T12:00:00+00:00"
CHATBOT_KEY = "chatbot-key-for-the-tests-only"
COPILOT_KEY = "copilot-key-for-the-tests-only"
STARTUP_SECONDS = 20
GUIDE_PATH = PROJECT_ROOT / "docs" / "integration.md"


@contextmanager
def running(app):
    """The app on a real port for the length of one test, then stopped.

    Port 0 lets the operating system pick a free port, so tests never collide with a
    service someone left running on 8000.
    """
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTUP_SECONDS
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("The service did not start.")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=STARTUP_SECONDS)


@pytest.fixture
def service(tmp_path, bundle, customers, portfolio):
    """A loaded service on a real port: bundle, catalogue, portfolio and one approval."""
    offers, policy = load_offers(), replace(load_policy(), holdout_fraction=0.0)
    save_bundle(bundle, tmp_path / "bundle")
    decisions, comparison = propose(customers, offers, policy)
    campaign = build_campaign(customers, decisions, comparison, offers, policy, STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "approved", ["0001"], reviewed_at=STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "rejected", ["0002"], reviewed_at=STAMP)
    campaign_path = save_campaign(campaign, tmp_path / "campaign")
    portfolio_path = tmp_path / "tiers.csv"
    portfolio.to_csv(portfolio_path, index=False)
    state = load_state(
        ServicePaths(
            bundle_dir=tmp_path / "bundle",
            portfolio_path=portfolio_path,
            campaign_path=campaign_path,
        )
    )
    with running(create_app(state, ApiKeys(CHATBOT_KEY, COPILOT_KEY))) as base_url:
        yield base_url


def test_the_copied_header_name_matches_the_service():
    """The client is copied outside this repository, so its copy of the header is pinned."""
    assert client.API_KEY_HEADER == api.API_KEY_HEADER


def test_the_example_client_reads_what_each_consumer_needs(service):
    state = client.health(service)
    assert state["status"] == "ok" and state["problems"] == []
    assert state["latest_outputs"]["approved_offers"] == 1

    packages = client.catalogue(service, CHATBOT_KEY)
    assert len(packages) == len(load_offers())
    assert {"offer_id", "price_lyd", "collected"} <= set(packages[0])

    offer = client.offer_for(service, CHATBOT_KEY, "0001")
    assert offer["subscriber_id"] == "0001" and offer["offer"]["offer_id"]
    assert "churn_probability" not in offer
    assert offer["offer_reason_ar"] in client.offer_sentence(offer)

    summary = client.portfolio_summary(service, COPILOT_KEY)
    assert summary["subscribers"] == 4 and summary["risk_available"]
    assert {group["name"] for group in summary["by_risk_band"]} >= {"high", "medium"}


def test_the_copilot_can_look_up_the_customer_on_the_phone(service):
    """The question T20's walkthrough found no endpoint for."""
    found = client.risk_for(service, COPILOT_KEY, "0001")
    assert found["risk_band"] == "high" and found["churn_probability"] == 0.5
    assert found["reasons"] == ["No recharge for 21 days", "Outgoing minutes down 80%"]
    assert found["value_tier"] == "high" and found["value_12m_base_lyd"] == 100.0
    assert client.risk_for(service, COPILOT_KEY, "not-in-the-export") is None


def test_the_two_subscriber_endpoints_do_not_open_each_other(service):
    """They share a path prefix, so each key has to be refused on the other's lookup."""
    with pytest.raises(client.ServiceError) as refused:
        client.get(service, "/subscribers/0001/risk", CHATBOT_KEY)
    assert refused.value.status == 403
    with pytest.raises(client.ServiceError) as also_refused:
        client.get(service, "/subscribers/0001/retention", COPILOT_KEY)
    assert also_refused.value.status == 403


def test_the_chatbot_cannot_tell_a_refused_offer_from_one_that_never_existed(service):
    """Rejected, unreviewed and unknown all come back as None, with no way to tell them apart."""
    for subscriber_id in ("0002", "NA", "0004", "does-not-exist"):
        assert client.offer_for(service, CHATBOT_KEY, subscriber_id) is None
    assert "No approved offer" in client.offer_sentence(None)


def test_the_check_reports_a_working_seam(service):
    result = client.check(service, CHATBOT_KEY, COPILOT_KEY, "0001")
    assert result.failures == []
    assert "Every check passed." in result.text
    for refusal in ("with the chatbot key", "with the copilot key", "with no key", "phone number"):
        assert refusal in result.text
    assert "subscriber lookup with the chatbot key" in result.text
    assert "high risk, probability 0.5" in result.text


def test_a_refusal_that_does_not_happen_is_a_failure():
    """The check has to fail when access control lets a call through, not only when it errors."""
    result = client.CheckResult()
    result.expect("a call that should be refused", 403, lambda: {"offers": []})
    assert result.failures == ["a call that should be refused"]
    assert "expected 403, got an answer" in result.text
    assert "1 checks failed" in result.text


def test_a_service_that_is_not_there_says_so():
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    with pytest.raises(client.ServiceError, match="churn serve"):
        client.health(f"http://127.0.0.1:{closed_port}")


def test_the_command_runs_the_check(service, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv(CHATBOT_KEY_VARIABLE, CHATBOT_KEY)
    monkeypatch.setenv(COPILOT_KEY_VARIABLE, COPILOT_KEY)
    report = tmp_path / "integration_check.md"
    main(
        ["check-integration", "--url", service, "--subscriber-id", "0001", "--output", str(report)]
    )
    printed = capsys.readouterr().out
    assert "Every check passed." in printed
    assert report.read_text(encoding="utf-8").startswith(f"# Integration check of {service}")


def test_the_command_needs_both_keys(service, monkeypatch, capsys):
    monkeypatch.delenv(CHATBOT_KEY_VARIABLE, raising=False)
    monkeypatch.setenv(COPILOT_KEY_VARIABLE, COPILOT_KEY)
    with pytest.raises(SystemExit) as exit_code:
        main(["check-integration", "--url", service, "--subscriber-id", "0001"])
    assert exit_code.value.code == 1
    assert CHATBOT_KEY_VARIABLE in capsys.readouterr().err


def test_the_guide_describes_the_service_that_is_running(service):
    """The other owners read `integration.md`, so a route or a key it misses is a bug here.

    The guide is read against the live OpenAPI document rather than the source, because
    that is what a consumer generates their client from.
    """
    guide = GUIDE_PATH.read_text(encoding="utf-8")
    paths = client.get(service, "/openapi.json")["paths"]
    for path, methods in paths.items():
        assert set(methods) == {"get"}, f"{path} is not read-only"
        assert path.replace("{subscriber_id}", "{id}") in guide, f"{path} is not in the guide"
    for name in (api.API_KEY_HEADER, CHATBOT_KEY_VARIABLE, COPILOT_KEY_VARIABLE):
        assert name in guide
    packages = len(load_offers())
    assert f"{packages} packages" in guide, f"the guide does not say the catalogue has {packages}"
