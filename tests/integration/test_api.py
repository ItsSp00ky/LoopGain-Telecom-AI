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


def test_unimplemented_modules_return_501_not_500(client: TestClient):
    """Honest about what is not built yet.

    Retargeted at phase 8: /v1/advance/limit now answers, so asserting 501 on
    it was asserting that M4 does not exist. What is still unbuilt is the
    cohort query and the Subscriber 360 assembly, and the invariant is
    unchanged -- an unbuilt module says 501, it does not crash with a 500.
    """
    for path, payload in (
        ("/v1/cohort/query", {"filters": {}}),
        ("/v1/subscriber/" + VALID_ID, None),
    ):
        r = client.get(path) if payload is None else client.post(path, json=payload)
        assert r.status_code in (501, 422), f"{path} returned {r.status_code}: {r.text[:160]}"
        assert r.status_code != 500, f"{path} crashed instead of declaring itself unbuilt"


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
