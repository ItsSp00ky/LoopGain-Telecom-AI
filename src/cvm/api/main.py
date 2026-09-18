"""Layer 6 -- prediction and decision API.

Run locally:
    uvicorn cvm.api.main:app --reload

Swagger UI at /docs, ReDoc at /redoc.

Latency budget: p95 < 200 ms on a single CPU container, verified with locust
against the Cell2Cell holdout.

These endpoints are also the platform integration surface: Components 4 and 5
consume them read-only. Breaking one is a cross-team event. See
docs/INTEGRATION.md.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cvm import __version__
from cvm.api.routers import advance, cohort, health, offer, score, subscriber
from cvm.config import seed_everything, settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)
log = logging.getLogger("cvm.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models once at startup, not per request.

    A cold model load inside a request handler is the fastest way to blow the
    200 ms p95 budget, so everything the tabular endpoints need is warmed here.
    """
    seed = seed_everything()
    log.info("Starting AI CVM Suite API v%s (env=%s, seed=%d)", __version__, settings.env, seed)

    # TODO(E4): populate app.state from cvm.models.registry once M1/M2/M4 land.
    #   app.state.models = load_registry(settings.artifact_dir / "models")
    #   app.state.feature_store = duckdb.connect(settings.feature_store, read_only=True)
    app.state.models = {}
    app.state.feature_store = None
    app.state.started_at = time.time()

    yield

    log.info("Shutting down")
    if app.state.feature_store is not None:
        app.state.feature_store.close()


app = FastAPI(
    title="AI CVM Suite API",
    version=__version__,
    lifespan=lifespan,
    description=(
        "Decision-intelligence layer over prepaid telecom telemetry.\n\n"
        "**Four outputs per subscriber:** calibrated silent-churn probability, "
        "value and loyalty tier, a margin-constrained priced offer, and a "
        "personalised airtime advance limit.\n\n"
        "Identifiers are salted SHA-256 hashes throughout. No raw MSISDN exists "
        "anywhere in this system. Every pricing and advance decision is logged "
        "with its inputs, weights, active constraints and reason codes, and is "
        "replayable.\n\n"
        "**This is the CVM branch of a larger telecom AI platform.** The endpoints "
        "below are the integration surface: the Employee Copilot and the Customer "
        "Chatbot, owned by other team members, consume them read-only. See "
        "docs/INTEGRATION.md."
    ),
    openapi_tags=[
        {"name": "health", "description": "Liveness and readiness."},
        {"name": "score", "description": "M1 -- silent churn probability and time-to-churn."},
        {"name": "offer", "description": "M3 -- next-best offer and price quote, guardrailed."},
        {"name": "advance", "description": "M4 -- learned airtime advance limit."},
        {"name": "subscriber", "description": "The Subscriber 360 view."},
        {
            "name": "cohort",
            "description": "Integration surface -- cohort queries for the Copilot and Chatbot.",
        },
    ],
)

# The Streamlit surfaces are separate origins in the compose network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env != "prod" else [],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]
):
    """Attach a request id and log server-side latency.

    The X-Response-Time header is what the locust run in Day 13 measures, so it
    must reflect handler time rather than including client-side overhead.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    started = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
    if elapsed_ms > 200 and request.url.path.startswith(("/v1/score", "/v1/offer", "/v1/advance")):
        log.warning("p95 budget at risk: %s took %.1f ms", request.url.path, elapsed_ms)
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Structured errors, and never leak a stack trace to the caller."""
    request_id = getattr(request.state, "request_id", None)
    log.exception("Unhandled error on %s (request_id=%s)", request.url.path, request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "An unexpected error occurred. Quote the request id when reporting it.",
            "request_id": request_id,
        },
    )


app.include_router(health.router)
app.include_router(score.router, prefix="/v1")
app.include_router(offer.router, prefix="/v1")
app.include_router(advance.router, prefix="/v1")
app.include_router(subscriber.router, prefix="/v1")
app.include_router(cohort.router, prefix="/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": "AI CVM Suite",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }
