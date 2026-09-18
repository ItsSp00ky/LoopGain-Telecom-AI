"""API request/response contracts (Pydantic v2).

These are frozen on Day 3 of the sprint so that the model, decision and
frontend tracks can proceed in parallel against a stable interface. Changing a
field here is a breaking change: announce it in stand-up and update the
Streamlit apps in the same PR.

Two rules the contracts encode:

* Identifiers are **always** the salted SHA-256 hash. There is no field
  anywhere in this module that can carry a raw MSISDN.
* Every decision response carries ``reason_codes`` and ``expected_margin_lyd``.
  An offer the system cannot explain is an offer it should not have made.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# A salted SHA-256 hex digest. 64 hex characters, nothing else.
SubscriberId = Annotated[
    str, StringConstraints(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)
]

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
LYD = Annotated[float, Field(ge=0.0, description="Amount in Libyan Dinar")]


class Tier(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class Segment(str, Enum):
    CHAMPIONS = "Champions"
    LOYAL_HIGH_VALUE = "Loyal High-Value"
    POTENTIAL_LOYALISTS = "Potential Loyalists"
    PROMISING_NEW = "Promising New"
    NEEDS_ATTENTION = "Needs Attention"
    AT_RISK_VALUABLE = "At-Risk Valuable"
    HIBERNATING = "Hibernating"
    LOST = "Lost"


class RetentionStage(str, Enum):
    NONE = "none"
    COOLING = "cooling"
    COLD = "cold"
    DORMANT = "dormant"


class ChurnArm(str, Enum):
    """Which arm of the M1 benchmark produced a score."""

    LIGHTGBM = "arm_a_lightgbm"
    LSTM = "arm_b_lstm"


# ---------------------------------------------------------------------------
# /v1/score/churn
# ---------------------------------------------------------------------------


class ChurnScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_ids: list[SubscriberId] = Field(min_length=1, max_length=10_000)
    arm: ChurnArm | Literal["both"] = Field(
        default=ChurnArm.LIGHTGBM,
        description="Which benchmark arm to score with. 'both' returns each separately.",
    )
    include_survival: bool = Field(
        default=False, description="Also return the M1b time-to-churn window."
    )
    as_of: date | None = Field(
        default=None,
        description=(
            "Point-in-time snapshot. Features are read from the window ending "
            "strictly before this date. Defaults to the latest snapshot."
        ),
    )


class ShapContribution(BaseModel):
    feature: str
    value: float
    contribution: float
    plain_language: str = Field(
        description="Human-readable explanation, e.g. 'has not topped up in 23 days'."
    )


class ChurnScore(BaseModel):
    subscriber_id: SubscriberId
    arm: ChurnArm
    # Calibrated with isotonic regression: a 0.31 means 31%. The pricing
    # engine consumes this as a monetary expectation, so it must be honest.
    churn_probability: Probability
    calibrated: bool = True
    decile: int = Field(ge=1, le=10, description="1 = highest risk")
    # M1b, present when include_survival is true
    time_to_churn_days: int | None = None
    survival_confidence_interval: tuple[int, int] | None = None
    top_drivers: list[ShapContribution] = Field(default_factory=list, max_length=10)
    model_version: str


class ChurnScoreResponse(BaseModel):
    scores: list[ChurnScore]
    scored_at: datetime
    as_of: date


# ---------------------------------------------------------------------------
# /v1/offer/next-best  and  /v1/price/quote
# ---------------------------------------------------------------------------


class Bundle(BaseModel):
    bundle_id: str
    name_en: str
    name_ar: str
    base_price_lyd: LYD
    data_mb: int = 0
    voice_min_onnet: int = 0
    voice_min_offnet: int = 0
    sms_count: int = 0
    validity_days: int


class OfferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_id: SubscriberId
    bundle_id: str | None = Field(
        default=None, description="Quote a specific bundle. Omit to let the engine choose."
    )
    campaign_budget_lyd: LYD | None = Field(
        default=None, description="Overrides the cohort budget in conf/pricing.yaml."
    )
    channel: Literal["ussd", "sms", "app", "api"] = "api"


class AppliedConstraint(BaseModel):
    """A guardrail that actually bound this decision.

    Recording which constraints bound -- not just which exist -- is what makes
    the decision log replayable and the offer defensible.
    """

    name: Literal[
        "margin_floor",
        "clv_ceiling",
        "budget",
        "cannibalisation",
        "fairness",
        "tier_d_max",
        "sleeping_dogs",
    ]
    binding: bool
    detail: str


class OfferResponse(BaseModel):
    subscriber_id: SubscriberId
    offer_id: str
    bundle: Bundle
    base_price_lyd: LYD
    price_lyd: LYD = Field(description="Post-discount price. Never below the margin floor.")
    discount_pct: float = Field(ge=0.0, le=1.0)
    bonus_mb: int = Field(default=0, description="Off-peak bonus data, if awarded.")
    # The operator's published off-peak window: 06:00-11:00 national. Present
    # only when the offer is time-restricted.
    valid_from_hour: int | None = Field(default=None, ge=0, le=23)
    valid_to_hour: int | None = Field(default=None, ge=0, le=23)
    tier: Tier
    retention_stage: RetentionStage
    # Value-add before discount: is this an off-peak grant rather than a cut?
    instrument: Literal["price_discount", "bonus_mb", "offpeak_data", "onnet_minutes", "none"]
    # Human-readable, shown to the subscriber. "loyalty reward - 6 years with us",
    # never an opaque personalised price.
    reason_codes: list[str]
    customer_facing_reason_ar: str
    customer_facing_reason_en: str
    expected_margin_lyd: float
    constraints: list[AppliedConstraint]
    decision_log_id: str = Field(description="Replay this decision with /v1/audit/{id}.")


# ---------------------------------------------------------------------------
# /v1/advance/limit
# ---------------------------------------------------------------------------


class AdvanceProduct(str, Enum):
    """Almadar's two emergency-credit services. They are mutually exclusive."""

    AIRTIME = "rasid_fi_waqtuh"   # رصيد في وقته — 1/3/5 LYD, *140#
    DATA = "net_fi_waqtuh"        # نت في وقته — flat 5 LYD / 2 GB, *000#


class AdvanceLimitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_id: SubscriberId
    product: AdvanceProduct = AdvanceProduct.AIRTIME
    requested_amount_lyd: LYD | None = None


class AdvanceSafetyCheck(BaseModel):
    guard: Literal[
        "affordability_ceiling",
        "chronic_distress_exclusion",
        "cooling_off",
        "clv_bounded_exposure",
        "lockout_risk",
        "tier_ceiling",
        "regulatory_cap",
    ]
    passed: bool
    detail: str


class AdvanceLimitResponse(BaseModel):
    subscriber_id: SubscriberId
    product: AdvanceProduct
    approved: bool
    # Airtime must be one of the operator's real denominations (1/3/5).
    # Data is flat 5 LYD, so the only decision there is grant or decline.
    limit_lyd: LYD = Field(description="0.0 when not approved.")
    # Learned, not allocated by "consumption".
    repayment_probability: Probability
    # The outcome the system exists to prevent: unpaid debt at day 14 blocks
    # re-subscription, locking the subscriber out of the service they reached
    # for. Flagged separately from approval so it is impossible to miss.
    #
    # NOT Libyana's line-reset outcome, which is undocumented for Almadar.
    lockout_risk: Probability
    lockout_flagged: bool
    # True when the requested debt exceeds one typical top-up. The 3 LYD card
    # versus 5 LYD data advance trap, surfaced per subscriber.
    exceeds_modal_recharge: bool
    modal_recharge_lyd: float
    binding_constraint: str = Field(
        description=(
            "Which term of min(f(PD), g(tier), h(CLV), affordability) produced the limit."
        )
    )
    safety_checks: list[AdvanceSafetyCheck]
    cooling_off_until: date | None = None
    # When declined, offer the cheapest thing they CAN afford rather than
    # nothing: 0.5 LYD for 50 MB works where a 5 LYD debt does not.
    fallback_offer_id: str | None = None
    # No fee is documented for either Almadar product. If one appears, it is
    # modelled as a fixed charge only and flagged for Shariah review.
    fee_lyd: float = 0.0
    fee_structure: Literal["fixed_charge"] = "fixed_charge"
    fee_review_status: Literal["FLAGGED_FOR_SHARIAH_REVIEW", "REVIEWED"] = (
        "FLAGGED_FOR_SHARIAH_REVIEW"
    )
    reason_codes: list[str]
    customer_facing_reason_ar: str
    decision_log_id: str


# ---------------------------------------------------------------------------
# /v1/subscriber/{id}  -- the 360 view behind the Command Center screen
# ---------------------------------------------------------------------------


class RfmLeScores(BaseModel):
    recency: int = Field(ge=1, le=5)
    frequency: int = Field(ge=1, le=5)
    monetary: int = Field(ge=1, le=5)
    loyalty: int = Field(ge=1, le=5)
    engagement: int = Field(ge=1, le=5)
    cell: str = Field(description="Concatenated R|F|M|L|E, e.g. '5|4|5|5|3'.")


class SubscriberProfile(BaseModel):
    subscriber_id: SubscriberId
    tenure_months: int
    # No district or cell id: all subscribers are modelled as geographically
    # equivalent. Network quality arrives as subscriber-level fields below.
    language_pref: Literal["ar", "ar-LY", "ber", "en"]
    rfm_le: RfmLeScores
    segment: Segment
    tier: Tier
    clv_12m_lyd: float
    churn: ChurnScore
    lstm_churn_probability: Probability | None = Field(
        default=None, description="Arm B, shown beside Arm A on the 360 screen."
    )
    retention_stage: RetentionStage
    # Dual-SIM share-of-wallet leakage. Rising incoming against flat outgoing
    # means this has quietly become their receiving SIM.
    leakage_score: Probability
    incoming_outgoing_ratio: float
    onnet_ratio: float
    # Subscriber-level network quality. Feeds M1 directly as churn features;
    # there is no network model in this branch.
    dropped_call_rate_30d: float
    service_outage_hours_30d: float
    recommended_offer: OfferResponse | None = None
    advance: AdvanceLimitResponse | None = None


# ---------------------------------------------------------------------------
# Cohort query -- the integration surface for the Copilot and Chatbot
#
# Those two components are owned by other team members and live outside this
# branch. They call this endpoint (and the scoring endpoints above) read-only;
# they do not import this package. See docs/INTEGRATION.md.
# ---------------------------------------------------------------------------


class CohortFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment: Segment | None = None
    tier: Tier | None = None
    retention_stage: RetentionStage | None = None
    min_churn_probability: Probability | None = None
    max_churn_probability: Probability | None = None
    min_clv_lyd: float | None = None
    min_dropped_call_rate: float | None = None
    limit: int = Field(default=1000, le=5000)


class CohortResponse(BaseModel):
    subscriber_ids: list[SubscriberId]
    total_matched: int
    returned: int
    total_revenue_at_risk_lyd: float
    filter_applied: CohortFilter


# ---------------------------------------------------------------------------
# /health and errors
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    models_loaded: dict[str, bool]
    feature_store_reachable: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str | None = None
