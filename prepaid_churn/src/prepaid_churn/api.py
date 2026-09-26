"""The read-only HTTP service the chatbot and the copilot call (ticket T15, decision 21).

FastAPI is here for one reason: the response models below generate the OpenAPI page at
`/docs`, so the integration documentation is produced from the code that answers the
request and cannot drift from it (the same rule as the two generated contracts).

The app has no write path.
It creates nothing, changes nothing and approves nothing, and no language model sits in
any path that sets an offer, a price or a limit (decision 17).
Every answer comes from `service.py`, which only reads files that `churn score`,
`churn tiers`, `churn decide` and `churn approve` already wrote.

Two boundaries this module owns, which `campaign.py` explicitly left to T15:

- Access control. The chatbot and the copilot hold different keys, and each key is
  accepted only on its own endpoints, so a leaked chatbot key cannot read the portfolio.
- De-identification. An identifier shaped like a Libyan mobile number is refused rather
  than looked up, because the module's IDs are pseudonymous by contract (decision 17)
  and a real number arriving here means an operator exported one by mistake.
"""

import hmac
import os
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from prepaid_churn.privacy import looks_like_phone_number
from prepaid_churn.service import (
    ServiceConfigurationError,
    ServicePaths,
    ServiceState,
    ServiceUnavailable,
    catalogue,
    health,
    load_state,
    portfolio_summary,
    refresh_campaign,
    retention,
    subscriber,
)

CHATBOT = "chatbot"
COPILOT = "copilot"
API_KEY_HEADER = "X-API-Key"
CHATBOT_KEY_VARIABLE = "PREPAID_CHURN_CHATBOT_KEY"
COPILOT_KEY_VARIABLE = "PREPAID_CHURN_COPILOT_KEY"
# Short enough to type into a teammate's config, long enough that guessing it is not the
# easy way in. Both keys are chosen by whoever deploys the service, never by this module.
MIN_KEY_LENGTH = 24


class ApiKeys:
    """One key per consumer, compared in constant time."""

    def __init__(self, chatbot: str, copilot: str):
        for name, key in ((CHATBOT, chatbot), (COPILOT, copilot)):
            if len(key) < MIN_KEY_LENGTH:
                raise ServiceConfigurationError(
                    f"The {name} API key must be at least {MIN_KEY_LENGTH} characters."
                )
            if not key.isascii() or any(not 33 <= ord(character) <= 126 for character in key):
                raise ServiceConfigurationError(
                    f"The {name} API key must use printable ASCII without spaces."
                )
        if hmac.compare_digest(chatbot, copilot):
            raise ServiceConfigurationError(
                "The chatbot and copilot keys must differ, or the two consumers are not "
                "separated and either one can read the other's endpoints."
            )
        self._keys = {CHATBOT: chatbot, COPILOT: copilot}

    def consumer(self, presented: str) -> str | None:
        """Which consumer presented this key, or None.

        Every key is compared even after a match, so the time taken does not reveal which
        key was tried first.
        """
        found = None
        # HTTP headers can contain non-ASCII bytes; compare_digest(str, str) raises on
        # those instead of returning False. Malformed credentials must be a 401, not a 500.
        if not presented.isascii():
            return None
        for name, key in self._keys.items():
            if hmac.compare_digest(presented, key):
                found = name
        return found


def keys_from_environment(environ: dict | None = None) -> ApiKeys:
    """Read both keys, and refuse to start without them.

    There is deliberately no default and no development fallback.
    A service that invents a key when one is missing is a service that ships with a known
    key, and the chatbot endpoint answers questions about named subscribers.
    """
    environ = os.environ if environ is None else environ
    missing = [
        name for name in (CHATBOT_KEY_VARIABLE, COPILOT_KEY_VARIABLE) if not environ.get(name)
    ]
    if missing:
        raise ServiceConfigurationError(
            f"Set {' and '.join(missing)} before starting the service. "
            "Each consumer gets its own key and neither has a default."
        )
    return ApiKeys(environ[CHATBOT_KEY_VARIABLE], environ[COPILOT_KEY_VARIABLE])


# ---------------------------------------------------------------------------
# Response models. These are the integration contract; changing a field is a
# breaking change for the chatbot and the copilot (decision 10).
# ---------------------------------------------------------------------------


class LatestOutputs(BaseModel):
    loaded_at: str = Field(
        description=(
            "When this process started and read its outputs; the campaign is read again "
            "whenever a review changes it, which `approved_offers` shows."
        )
    )
    scored_at: str | None = Field(
        default=None,
        description="Latest scoring time in the portfolio export; null without a bundle.",
    )
    campaign_id: str | None = Field(default=None, description="Fingerprint of the campaign held.")
    campaign_created_at: str | None = Field(default=None, description="When it was proposed.")
    subscribers_in_portfolio: int
    approved_offers: int = Field(description="Approved rows; unreviewed and rejected are not here.")


class HealthResponse(BaseModel):
    status: str = Field(description="`ok` only when nothing below is missing or broken.")
    bundle_loaded: bool
    smoke_prediction_passed: bool = Field(
        description="The bundle predicted its stored sample row; loaded alone is not usable."
    )
    model_version: str | None = None
    problems: list[str] = Field(description="Why the status is degraded, one message each.")
    latest_outputs: LatestOutputs


class CatalogueOffer(BaseModel):
    """One operator package, exactly as `data/operator/offers.csv` records it (T16)."""

    model_config = ConfigDict(extra="ignore")

    offer_id: str
    operator: str
    family_ar: str | None = None
    family_en: str | None = None
    name_ar: str | None = None
    name_en: str | None = None
    price_lyd: float
    validity_ar: str | None = None
    validity_hours: float | None = None
    data_gb: float | None = Field(default=None, description="Null when the package states none.")
    data_unlimited: bool | None = None
    voice_minutes: float | None = None
    voice_unlimited: bool | None = None
    network: str | None = None
    valid_from_hour: float | None = Field(
        default=None, description="Start of the daily window, when the package has one."
    )
    valid_to_hour: float | None = None
    collected: str | None = Field(
        default=None, description="When this row was collected; prices change."
    )


class CatalogueResponse(BaseModel):
    count: int
    offers: list[CatalogueOffer]


class RetentionResponse(BaseModel):
    """The approved offer for one subscriber.

    There is no churn probability, risk band or value field here, and there never may be:
    the chatbot speaks to the customer, and the customer is not told how likely the
    operator thinks they are to leave (decision 10).
    """

    model_config = ConfigDict(extra="forbid")

    subscriber_id: str
    recommended_offer_id: str
    offer_reason_en: str | None = None
    offer_reason_ar: str | None = None
    reviewed_at: str | None = Field(default=None, description="When a named reviewer approved it.")
    campaign_id: str | None = None
    offer: CatalogueOffer | None = Field(
        default=None, description="The package itself, from the catalogue."
    )


class GroupSummary(BaseModel):
    name: str
    customers: int
    monthly_spend_lyd: float | None = Field(
        default=None,
        description="Assumed monthly recharge at the frozen T18 LYD rate, not observed revenue.",
    )
    lyd_at_risk: float | None = Field(
        default=None,
        description=(
            "12-month value weighted by each customer's churn probability, so it is an "
            "expected loss under the T10 scenario assumptions rather than the value of "
            "everyone in the group. Null when this export carries no risk estimate."
        ),
    )


class ThresholdCheck(BaseModel):
    description: str
    value: float | None = None
    required: str
    passed: bool


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str | None = None
    generated_at: str
    scored_at: str | None = None
    subscribers: int
    risk_available: bool = Field(
        description="False when no gated bundle scored this export; then lyd_at_risk is null."
    )
    by_risk_band: list[GroupSummary]
    by_value_tier: list[GroupSummary]
    success_thresholds: dict[str, ThresholdCheck] = Field(
        description="The four checks of decision 13, measured once on the frozen test window."
    )
    test_metrics: dict[str, dict[str, float | None]] = Field(
        description="Test metrics per model from the same frozen evaluation."
    )
    release_gate_passed: bool | None = None


class SubscriberResponse(BaseModel):
    """What the copilot is told about one subscriber (T20).

    The opposite rule to `RetentionResponse`: the employee asking is allowed to see the
    risk and the value, because they are deciding what to do for this customer.
    The reasons are the model's own factors from the scoring export, each a short label
    with the customer's value, so the copilot quotes them rather than inventing an
    explanation. A `low` subscriber gets one line saying so instead (decision 40).
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    subscriber_id: str
    churn_probability: float | None = Field(
        default=None, description="Calibrated probability; null when no bundle scored the export."
    )
    risk_band: str | None = None
    reasons: list[str] = Field(
        default_factory=list,
        description=(
            "Why the model raised this customer's risk, in the order it ranked them; "
            "a `low` subscriber gets one line saying the risk is low instead."
        ),
    )
    value_tier: str | None = None
    value_status: str | None = Field(
        default=None, description="`scenario`, or `already_silent` when there is nothing to model."
    )
    value_12m_low_lyd: float | None = None
    value_12m_base_lyd: float | None = None
    value_12m_high_lyd: float | None = None
    monthly_spend_lyd: float | None = Field(
        default=None, description="Assumed monthly recharge at the frozen T18 rate."
    )
    model_version: str | None = None
    tier_version: str | None = None
    scored_at: str | None = None


# ---------------------------------------------------------------------------
# Access control and identifier checks
# ---------------------------------------------------------------------------


def _consumer(expected: str):
    """Accept this consumer's key, and only on this consumer's endpoints."""

    def dependency(
        request: Request,
        x_api_key: str = Header(default="", alias=API_KEY_HEADER, description="Your consumer key."),
    ) -> str:
        # Read from the app rather than a module global, so two apps in one process
        # (which is what the tests are) cannot end up sharing one set of keys.
        keys: ApiKeys = request.app.state.keys
        presented = keys.consumer(x_api_key)
        if presented is None:
            raise HTTPException(
                status_code=401,
                detail=f"Send your consumer key in the {API_KEY_HEADER} header.",
            )
        if presented != expected:
            raise HTTPException(
                status_code=403,
                detail=f"This key is not accepted on {expected} endpoints.",
            )
        return presented

    return dependency


def checked_subscriber_id(
    subscriber_id: str = Path(description="The pseudonymous subscriber ID, never a phone number."),
) -> str:
    """Refuse an identifier shaped like a Libyan mobile number.

    Looking it up anyway would mean answering questions about a raw number, and would hide
    the export mistake that produced it. `prepaid_churn.privacy.pseudonymize` is the
    supported way for an operator to hash numbers before they export.
    """
    if looks_like_phone_number(subscriber_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "That identifier looks like a Libyan mobile number. This service only "
                "accepts pseudonymous IDs; hash the number before exporting it."
            ),
        )
    return subscriber_id


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------


def create_app(state: ServiceState, keys: ApiKeys) -> FastAPI:
    """Build the app around an already-loaded state, so tests can inject their own."""
    app = FastAPI(
        title="Prepaid customer module - integration service",
        version="1",
        description=(
            "Read-only access to this module's released outputs for the team's customer "
            "chatbot and employee copilot (ticket T15, decisions 10 and 17).\n\n"
            "Nothing can be created, changed or approved through this service. A "
            "retention offer appears here only after a named reviewer approved it with "
            "`churn approve` (decision 14).\n\n"
            "Send your consumer key in the `X-API-Key` header. The chatbot key and the "
            "copilot key are accepted only on their own endpoints.\n\n"
            "Subscriber IDs are pseudonymous. An ID shaped like a Libyan mobile number "
            "is refused."
        ),
        openapi_tags=[
            {"name": "health", "description": "Readiness; no key required."},
            {"name": "chatbot", "description": "For the customer chatbot."},
            {"name": "copilot", "description": "For the employee copilot."},
        ],
    )
    app.state.service = state
    app.state.keys = keys
    # The endpoints run in a thread pool, so two requests can notice the same review at
    # once; the lock makes one of them read the campaign and the other use that read.
    refresh_lock = threading.Lock()

    def with_current_campaign() -> ServiceState:
        """The state, with the campaign reread if a review changed it (decision 47)."""
        with refresh_lock:
            app.state.service = refresh_campaign(app.state.service)
            return app.state.service

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def read_health() -> dict:
        """Whether the bundle predicts and which outputs this process is serving.

        No key is required: a liveness probe has no secret to offer, and the answer holds
        no customer data. It reports nothing beyond versions, counts and timestamps.
        """
        return health(with_current_campaign())

    @app.get(
        "/catalogue",
        response_model=CatalogueResponse,
        tags=["chatbot"],
        dependencies=[Depends(_consumer(CHATBOT))],
    )
    def read_catalogue() -> dict:
        """Every operator package the chatbot may talk about, with its collection date."""
        offers = catalogue(app.state.service)
        return {"count": len(offers), "offers": offers}

    @app.get(
        "/subscribers/{subscriber_id}/retention",
        response_model=RetentionResponse,
        tags=["chatbot"],
        dependencies=[Depends(_consumer(CHATBOT))],
        responses={404: {"description": "No offer has been approved for this subscriber."}},
    )
    def read_retention(subscriber_id: str = Depends(checked_subscriber_id)) -> dict:
        """The approved offer for one subscriber, and nothing else about them.

        404 covers every case the chatbot must treat the same way: no campaign, no
        proposal, a proposal nobody reviewed, and a proposal a reviewer rejected. Telling
        the customer which one it was would tell them an offer was considered and refused.
        """
        offer = retention(with_current_campaign(), subscriber_id)
        if offer is None:
            raise HTTPException(
                status_code=404,
                detail="No approved retention offer for this subscriber.",
            )
        return offer

    @app.get(
        "/portfolio/summary",
        response_model=PortfolioResponse,
        tags=["copilot"],
        dependencies=[Depends(_consumer(COPILOT))],
    )
    def read_portfolio() -> dict:
        """Customers and LYD at risk by risk band and value tier, with the model evidence."""
        try:
            return portfolio_summary(app.state.service)
        except ServiceUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get(
        "/subscribers/{subscriber_id}/risk",
        response_model=SubscriberResponse,
        tags=["copilot"],
        dependencies=[Depends(_consumer(COPILOT))],
        responses={404: {"description": "This subscriber is not in the scored export."}},
    )
    def read_subscriber(subscriber_id: str = Depends(checked_subscriber_id)) -> dict:
        """One subscriber's risk, reasons and value, for the employee helping them.

        404 means the export does not hold this ID, which is a different thing from the
        chatbot's 404: here nothing is being hidden, the subscriber was simply not scored.
        """
        try:
            found = subscriber(app.state.service, subscriber_id)
        except ServiceUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if found is None:
            raise HTTPException(
                status_code=404,
                detail="This subscriber is not in the scored export.",
            )
        return found

    return app


def build_app(paths: ServicePaths, keys: ApiKeys | None = None) -> FastAPI:
    """Load every output, then serve it; the campaign is reread when a review changes it.

    Called by `churn serve`.

    The keys are resolved before anything is read, so a missing one fails immediately
    rather than after a bundle load whose result was about to be served without them.
    """
    keys = keys or keys_from_environment()
    return create_app(load_state(paths), keys)
