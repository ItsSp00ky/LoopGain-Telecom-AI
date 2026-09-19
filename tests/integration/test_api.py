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


def test_health_is_honest_in_both_directions(client: TestClient):
    """A partial deploy must be visible. An API reporting "ok" with no models
    loaded is worse than one reporting nothing.

    This test asserted `degraded` until phase 8, when the registry started
    loading real artefacts and it began failing for the right reason. The
    invariant it was protecting is not "the API is incomplete" -- it is that
    /health tells the truth -- so it now checks BOTH directions rather than
    being deleted or pinned to whichever state happens to hold today.
    """
    body = client.get("/health").json()
    assert set(body["models_loaded"]) >= {"m1_churn_lightgbm", "m4_repayment_pd"}

    # Whatever the status is, it must follow from the parts.
    complete = all(body["models_loaded"].values()) and body["feature_store_reachable"]
    assert body["status"] == ("ok" if complete else "degraded")

    # And the downward direction: hide a model, and it must say so.
    original = dict(client.app.state.models)
    try:
        client.app.state.models = {k: v for k, v in original.items() if k != "m1_churn_lightgbm"}
        degraded = client.get("/health").json()
        assert degraded["status"] == "degraded"
        assert degraded["models_loaded"]["m1_churn_lightgbm"] is False
    finally:
        client.app.state.models = original


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


def test_nothing_returns_501_any_more(client: TestClient):
    """The end of an arc rather than a deleted test.

    This asserted 501 on /v1/advance/limit until phase 8 and on the cohort
    query and Subscriber 360 until phase 9. Every endpoint now answers, so the
    invariant it was protecting -- an unbuilt module declares itself rather
    than crashing -- has no subject left. Inverted: nothing may go back to 501
    without this failing, which is the useful direction now.

    A 4xx is fine. 501 means "not implemented", and nothing here is.
    """
    import pandas as pd

    from cvm.config import settings

    subscriber = VALID_ID
    if settings.feature_store_offline.exists():
        subscriber = str(
            pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"]).iloc[
                0, 0
            ]
        )

    cases = [
        ("POST", "/v1/score/churn", {"subscriber_ids": [subscriber]}),
        ("POST", "/v1/offer/next-best", {"subscriber_id": subscriber, "channel": "api"}),
        ("POST", "/v1/price/quote", {"subscriber_id": subscriber, "bundle_id": "MO_20"}),
        ("POST", "/v1/advance/limit", {"subscriber_id": subscriber, "product": "rasid_fi_waqtuh"}),
        ("POST", "/v1/cohort/query", {"limit": 10}),
        ("GET", f"/v1/subscriber/{subscriber}", None),
    ]
    for method, path, payload in cases:
        r = client.get(path) if method == "GET" else client.post(path, json=payload)
        assert r.status_code != 501, f"{path} went back to 501"
        assert r.status_code != 500, f"{path} crashed: {r.text[:160]}"


def test_the_decision_endpoints_no_longer_return_501(client: TestClient):
    """The mirror of the test above, so the pair covers both states.

    Needs a real subscriber: the engine reads features rather than inventing
    them, so an id that is not in the store is a 4xx rather than a decision.
    """
    import pandas as pd

    from cvm.config import settings

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    subscriber = str(
        pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"]).iloc[0, 0]
    )
    for path, payload in (
        ("/v1/offer/next-best", {"subscriber_id": subscriber, "channel": "api"}),
        ("/v1/advance/limit", {"subscriber_id": subscriber, "product": "rasid_fi_waqtuh"}),
    ):
        r = client.post(path, json=payload)
        assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"


@pytest.mark.slow
def test_tabular_scoring_meets_the_p95_budget(client: TestClient):
    """p95 < 200 ms on one CPU container. Verified properly with locust on day
    13; this is the early-warning version.

    The model-level figure was never the thing in doubt: 500 subscribers scored
    with SHAP drivers in 438 ms, 0.88 ms each, once the per-row SHAP call was
    batched. What this test adds is the serialisation, validation and feature
    store round-trip on top of that -- and that is where the first version lost
    its budget, reading the offline Parquet per request for 292 ms a call.
    """
    import time

    import numpy as np
    import pandas as pd

    from cvm.config import settings

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    ids = pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"])
    sample = ids["subscriber_id_hashed"].astype(str).head(25).tolist()

    # One warm call first: the budget is a steady-state figure, and the first
    # request pays for imports the container would have paid at startup.
    client.post("/v1/offer/next-best", json={"subscriber_id": sample[0], "channel": "api"})

    timings = []
    for subscriber in sample:
        start = time.perf_counter()
        response = client.post(
            "/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"}
        )
        timings.append((time.perf_counter() - start) * 1000)
        assert response.status_code == 200

    p95 = float(np.percentile(timings, 95))
    assert p95 < 200, f"p95 is {p95:.0f} ms against a 200 ms budget"


def test_health_reports_degraded_when_a_model_loads_but_cannot_predict(client: TestClient):
    """The gap that let a broken container pass its own healthcheck.

    `models_loaded` is read by every consumer as "usable". An artefact that
    deserialises and then raises on predict_proba is not usable, and reporting
    True because the bytes unpickled is exactly what marked the container
    healthy while /v1/score/churn returned 500.
    """
    original = dict(getattr(client.app.state, "model_errors", {}))
    try:
        client.app.state.model_errors = {
            "m1_churn_lightgbm": "AttributeError: 'SimpleImputer' object has no attribute '_fill_dtype'"
        }
        body = client.get("/health").json()

        assert body["status"] == "degraded"
        assert body["models_loaded"]["m1_churn_lightgbm"] is False
        # And it says WHY -- "degraded" with no message sends the operator to
        # the container logs to find a warning they were never going to read.
        assert "_fill_dtype" in body["model_errors"]["m1_churn_lightgbm"]

        # A failure in one model must not condemn the others.
        assert body["models_loaded"]["m4_repayment_pd"] is True
    finally:
        client.app.state.model_errors = original
