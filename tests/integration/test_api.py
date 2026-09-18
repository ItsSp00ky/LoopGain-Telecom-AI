"""API integration tests. Contracts, not model quality."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cvm.api.main import app

pytestmark = pytest.mark.integration

VALID_ID = "a" * 64


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def test_root_advertises_the_docs(client: TestClient):
    assert client.get("/").json()["docs"] == "/docs"


def test_health_reports_degraded_before_models_are_loaded(client: TestClient):
    """A partial deploy must be visible. An API reporting "ok" with no models
    loaded is worse than one reporting nothing."""
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert set(body["models_loaded"]) >= {"m1_churn_lightgbm", "m4_repayment_pd"}


def test_openapi_schema_generates(client: TestClient):
    """Catches a malformed Pydantic contract before Swagger does."""
    spec = client.get("/openapi.json").json()
    assert "/v1/score/churn" in spec["paths"]
    assert "/v1/advance/limit" in spec["paths"]


def test_integration_surface_is_present(client: TestClient):
    """The endpoints other components consume. Breaking one is a cross-team
    event, so it breaks a test first. See docs/INTEGRATION.md."""
    paths = client.get("/openapi.json").json()["paths"]
    for endpoint in (
        "/v1/cohort/query",
        "/v1/score/churn",
        "/v1/offer/next-best",
        "/v1/advance/limit",
    ):
        assert endpoint in paths, f"{endpoint} is part of the published contract"


def test_cohort_filter_rejects_district(client: TestClient):
    """Geography is out of scope. A filter that silently accepted `district`
    would let a caller believe we model it."""
    r = client.post("/v1/cohort/query", json={"district": "Tripoli"})
    assert r.status_code == 422


def test_no_agent_endpoint_is_exposed(client: TestClient):
    """The Copilot is a separate component. This branch serves it; it does not
    host it. An agent endpoint appearing here means scope has drifted."""
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "copilot" in p or "chat" in p]


def test_every_response_carries_a_request_id_and_timing(client: TestClient):
    r = client.get("/health")
    assert r.headers["X-Request-ID"]
    assert float(r.headers["X-Response-Time-ms"]) >= 0


def test_raw_msisdn_is_rejected_by_the_scoring_contract(client: TestClient):
    """422, not 500, and certainly not a score."""
    raw = "0912345678"  # msisdn-fixture
    r = client.post("/v1/score/churn", json={"subscriber_ids": [raw]})
    assert r.status_code == 422


def test_unimplemented_modules_return_501_not_500(client: TestClient):
    """Honest about what is not built yet."""
    r = client.post("/v1/advance/limit", json={"subscriber_id": VALID_ID})
    assert r.status_code == 501


@pytest.mark.xfail(reason="models not trained yet", strict=False)
@pytest.mark.slow
def test_tabular_scoring_meets_the_p95_budget(client: TestClient):
    """p95 < 200 ms on one CPU container. Verified properly with locust on day
    13; this is the early-warning version."""
    raise NotImplementedError("TODO(E4)")
