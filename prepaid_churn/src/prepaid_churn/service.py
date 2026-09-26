"""Read-only integration state for the chatbot and the copilot (ticket T15, decision 21).

Every answer the service gives comes from a file that another command already wrote:
the gated bundle (T8), the operator's catalogue (T16), the value and risk export (T10) and
the reviewed campaign (T11).
Nothing here trains, scores, decides or approves, and there is no write path at all
(decision 17).

Two rules shape this module.

The approved campaign is read from the authoritative `proposals.json` and filtered
through `released_campaign`, never from the derived `released.csv`.
T11 made the JSON the authority so that editing a CSV cannot approve an offer, and a
service that served the CSV would quietly hand that authority back.

Everything is loaded into a frozen state, and the functions below only read it.
The campaign is the one output that changes while the service runs, because reviewers
approve offers with `churn approve`, so `refresh_campaign` rereads it when its file
changes (decision 47).
That is safe because `churn approve` replaces `proposals.json` in one step (`os.replace`
in `campaign.py`), so a read sees the old campaign or the new one, never half of each.
A new model or a new scoring run is still read at startup, and `/health` reports what the
service is holding.
"""

import datetime
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from prepaid_churn.bundle import Bundle, load_bundle, smoke_check
from prepaid_churn.campaign import RELEASE_COLUMNS, load_campaign, released_campaign
from prepaid_churn.operator_market import OFFERS_PATH, load_offers


class ServiceUnavailable(RuntimeError):
    """An output the endpoint needs has not been produced; the message says which."""


class ServiceConfigurationError(ValueError):
    """The service was asked to start without the access control it requires."""


# What the chatbot may be told about an approved offer.
# The reviewer's name is deliberately not here: the chatbot speaks to customers, and the
# name of the employee who approved a campaign is not something a customer needs.
CHATBOT_RELEASE_COLUMNS = (
    "subscriber_id",
    "recommended_offer_id",
    "offer_reason_en",
    "offer_reason_ar",
    "reviewed_at",
    "campaign_id",
)

# What the chatbot is told about the offered package itself, from the T16 catalogue.
CATALOGUE_COLUMNS = (
    "offer_id",
    "operator",
    "family_ar",
    "family_en",
    "name_ar",
    "name_en",
    "price_lyd",
    "validity_ar",
    "validity_hours",
    "data_gb",
    "data_unlimited",
    "voice_minutes",
    "voice_unlimited",
    "network",
    "valid_from_hour",
    "valid_to_hour",
    "collected",
)

# What the copilot may be told about one subscriber (T20).
# The employee is helping this customer, so the risk figures the chatbot may never see
# belong here; the reviewer's name and the offer do not, because the campaign endpoints
# already own those and a lookup is not a review.
SUBSCRIBER_COLUMNS = (
    "subscriber_id",
    "churn_probability",
    "risk_band",
    "value_tier",
    "value_status",
    "value_12m_low_lyd",
    "value_12m_base_lyd",
    "value_12m_high_lyd",
    "monthly_spend_lyd",
    "model_version",
    "tier_version",
    "scored_at",
)
REASON_COLUMNS = ("reason_1", "reason_2", "reason_3")

RISK_BANDS = ("high", "medium", "low", "already_silent")
VALUE_TIERS = ("very_high", "high", "medium", "low", "very_low")


@dataclass(frozen=True)
class ServicePaths:
    """Where the service reads from; `cli.py` owns the real artifact layout."""

    bundle_dir: Path
    portfolio_path: Path
    campaign_path: Path
    offers_path: Path = OFFERS_PATH


@dataclass(frozen=True)
class ServiceState:
    """Everything the endpoints answer from; only the campaign is ever read again."""

    offers: pd.DataFrame
    approved: pd.DataFrame
    loaded_at: str
    bundle: Bundle | None = None
    bundle_error: str | None = None
    smoke_passed: bool = False
    portfolio: pd.DataFrame | None = None
    portfolio_error: str | None = None
    campaign_id: str | None = None
    campaign_created_at: str | None = None
    campaign_error: str | None = None
    # Where the campaign was read from, and the file's modified time and size just before
    # that read; `refresh_campaign` compares them to notice a new review.
    campaign_path: Path | None = None
    campaign_signature: tuple[int, int] | None = None

    @property
    def model_version(self) -> str | None:
        return None if self.bundle is None else self.bundle.version

    @property
    def release_gate(self) -> dict | None:
        return None if self.bundle is None else self.bundle.manifest["release_gate"]


def utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def json_safe(value):
    """Replace NaN with null anywhere in a nested structure.

    The release gate stores NaN for a ranking metric that a single-class slice cannot
    produce, and `json.dumps` writes that as the literal `NaN`, which no HTTP client is
    required to parse. Null says "not available", which is what it means.
    """
    if isinstance(value, dict):
        return {name: json_safe(item) for name, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _plain(value):
    """One cell as a plain JSON value.

    A NaN that reaches the response is not valid JSON, and turning it into 0 would state
    a measurement the module does not have, so it becomes null.
    A collection date is a date, and the catalogue's consumers read it as text.
    """
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _json_safe(frame: pd.DataFrame) -> list[dict]:
    """Rows as plain JSON values, with missing values as null rather than NaN."""
    return [
        {name: _plain(value) for name, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _load_bundle(directory: Path) -> tuple[Bundle | None, str | None, bool]:
    """Load the gated bundle and prove it still predicts, reporting both separately.

    `load_bundle` already smoke checks, so this repeats one prediction on purpose:
    "loaded" is read by every consumer as "usable", and an artefact that deserialises but
    cannot predict is not usable (Ali's serving lesson, port log step 4).
    """
    try:
        bundle = load_bundle(directory)
    except Exception as error:
        return None, f"{type(error).__name__}: {error}", False
    try:
        smoke_check(bundle)
    except Exception as error:
        return bundle, f"{type(error).__name__}: {error}", False
    return bundle, None, True


def _load_campaign(
    path: Path, campaign: dict | None = None
) -> tuple[pd.DataFrame, str | None, str | None, str | None]:
    """The approved offers only, from the authoritative snapshot.

    `campaign` is an already-parsed snapshot, for a caller that needs the whole thing as
    well as the released rows. The demo app is that caller, and parsing its JSON twice was
    the slowest thing it did.
    """
    empty = pd.DataFrame(columns=list(RELEASE_COLUMNS))
    if campaign is None and not path.exists():
        return empty, None, None, None
    try:
        campaign = load_campaign(path) if campaign is None else campaign
        released = released_campaign(campaign)
    except Exception as error:
        # A campaign that cannot be validated serves no offers at all.
        # Falling back to the derived CSV here would publish rows the snapshot rejected.
        return empty, None, None, f"{type(error).__name__}: {error}"
    released["subscriber_id"] = released["subscriber_id"].astype(str)
    return (
        released,
        campaign["campaign_id"],
        campaign["snapshot"]["created_at"],
        None,
    )


def _file_signature(path: Path) -> tuple[int, int] | None:
    """When the file last changed and how big it is, or None when there is no file.

    Every review adds events to `proposals.json`, so the size alone grows with each one;
    the modified time covers a campaign replaced by another of the same size.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _withhold_retired(
    approved: pd.DataFrame, offers: pd.DataFrame, campaign_error: str | None
) -> tuple[pd.DataFrame, str | None]:
    """Drop approvals whose package has left the current catalogue, and say so (decision 33)."""
    unavailable = ~approved["recommended_offer_id"].isin(offers["offer_id"])
    if not unavailable.any():
        return approved, campaign_error
    return approved.loc[~unavailable].copy(), (
        f"{int(unavailable.sum())} approved offers are no longer in the current catalogue; "
        "they are withheld. Create and review a new campaign."
    )


def _load_portfolio(path: Path) -> tuple[pd.DataFrame | None, str | None]:
    if not path.exists():
        return None, f"{path.name} not found. Run `uv run churn tiers` first."
    try:
        portfolio = pd.read_csv(path, converters={"subscriber_id": str})
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"
    if "value_tier" not in portfolio.columns:
        return None, f"{path.name} has no value_tier column; it is not a `churn tiers` export."
    if "subscriber_id" not in portfolio.columns:
        return None, f"{path.name} has no subscriber_id column."
    ids = portfolio["subscriber_id"]
    if ids.isna().any() or ids.str.strip().eq("").any() or not ids.is_unique:
        return None, f"{path.name} needs nonempty, unique subscriber IDs."
    return portfolio, None


def load_state(paths: ServicePaths, campaign: dict | None = None) -> ServiceState:
    """Read every output the service serves.

    A missing bundle, campaign or export is recorded rather than raised: the endpoints
    that need one answer 503 with the reason, and the ones that do not keep working.

    `campaign` lets a caller pass a snapshot it has already parsed; the service itself
    never does. That state records no file signature, because nothing says the caller's
    copy matches the file, so `refresh_campaign` would read the file rather than trust it.
    """
    bundle, bundle_error, smoke_passed = _load_bundle(paths.bundle_dir)
    # The signature is taken before the read: a review saved during the read then shows up
    # as a change on the next request, instead of being recorded as already read.
    signature = None if campaign is not None else _file_signature(paths.campaign_path)
    approved, campaign_id, created_at, campaign_error = _load_campaign(
        paths.campaign_path, campaign
    )
    portfolio, portfolio_error = _load_portfolio(paths.portfolio_path)
    offers = load_offers(paths.offers_path)
    approved, campaign_error = _withhold_retired(approved, offers, campaign_error)
    return ServiceState(
        offers=offers,
        approved=approved,
        loaded_at=utc_now(),
        bundle=bundle,
        bundle_error=bundle_error,
        smoke_passed=smoke_passed,
        portfolio=portfolio,
        portfolio_error=portfolio_error,
        campaign_id=campaign_id,
        campaign_created_at=created_at,
        campaign_error=campaign_error,
        campaign_path=paths.campaign_path,
        campaign_signature=signature,
    )


def refresh_campaign(state: ServiceState) -> ServiceState:
    """The same state, or a copy holding the campaign as its file is now (decision 47).

    While nobody reviews, this costs one `stat` and returns the state it was given.
    After `churn approve`, the next call reads the campaign again, so a new approval
    reaches the chatbot without a restart. A campaign that fails to load serves no offers,
    exactly as at startup, and is read again when its file next changes.
    Only the campaign is read: the bundle, the catalogue and the portfolio stay as loaded.
    """
    if state.campaign_path is None:
        return state
    signature = _file_signature(state.campaign_path)
    if signature == state.campaign_signature:
        return state
    approved, campaign_id, created_at, campaign_error = _load_campaign(state.campaign_path)
    approved, campaign_error = _withhold_retired(approved, state.offers, campaign_error)
    return replace(
        state,
        approved=approved,
        campaign_id=campaign_id,
        campaign_created_at=created_at,
        campaign_error=campaign_error,
        campaign_signature=signature,
    )


def health(state: ServiceState) -> dict:
    """Whether the service can answer, and what it is holding.

    `status` is "ok" only when the bundle predicts and there is a portfolio to summarise.
    A degraded service that reports "ok" is worse than one that reports nothing, because
    the copilot would quote numbers from an export that is not there.
    """
    problems = [
        message
        for message in (state.bundle_error, state.portfolio_error, state.campaign_error)
        if message is not None
    ]
    return {
        "status": "ok" if not problems else "degraded",
        "bundle_loaded": state.bundle is not None,
        "smoke_prediction_passed": state.smoke_passed,
        "model_version": state.model_version,
        "problems": problems,
        "latest_outputs": {
            "loaded_at": state.loaded_at,
            "scored_at": _scored_at(state),
            "campaign_id": state.campaign_id,
            "campaign_created_at": state.campaign_created_at,
            "subscribers_in_portfolio": 0 if state.portfolio is None else len(state.portfolio),
            "approved_offers": len(state.approved),
        },
    }


def _scored_at(state: ServiceState) -> str | None:
    """When the portfolio was scored, which only a bundle-backed run records."""
    portfolio = state.portfolio
    if portfolio is None or "scored_at" not in portfolio.columns:
        return None
    stamps = portfolio["scored_at"].dropna()
    return None if stamps.empty else str(stamps.max())


def catalogue(state: ServiceState) -> list[dict]:
    """Every operator package the chatbot may talk about, with its collection date."""
    columns = [name for name in CATALOGUE_COLUMNS if name in state.offers.columns]
    return _json_safe(state.offers[columns])


def retention(state: ServiceState, subscriber_id: str) -> dict | None:
    """The approved offer for one subscriber, or None when there is not one.

    None covers every case the chatbot must treat the same way: no campaign, no proposal,
    a proposal nobody reviewed, and a proposal a reviewer rejected.
    Distinguishing them in the response would tell the customer that an offer was
    considered and refused.
    """
    rows = state.approved.loc[state.approved["subscriber_id"].astype(str) == str(subscriber_id)]
    if rows.empty:
        return None
    # Defence in depth: `released_campaign` already filters to approved rows, so this
    # only fires if that ever stops being true.
    rows = rows.loc[rows["status"].astype(str) == "approved"]
    if rows.empty:
        return None
    row = {
        name: value
        for name, value in _json_safe(rows.iloc[[0]])[0].items()
        if name in CHATBOT_RELEASE_COLUMNS
    }
    offer = _offer_details(state, row["recommended_offer_id"])
    return None if offer is None else row | {"offer": offer}


def _offer_details(state: ServiceState, offer_id: object) -> dict | None:
    offers = state.offers.loc[state.offers["offer_id"].astype(str) == str(offer_id)]
    if offers.empty:
        return None
    columns = [name for name in CATALOGUE_COLUMNS if name in offers.columns]
    return _json_safe(offers[columns].iloc[[0]])[0]


def subscriber(state: ServiceState, subscriber_id: str) -> dict | None:
    """One subscriber's risk, reasons and value for the copilot, or None when unknown.

    This is the question T20's walkthrough found no endpoint for: an employee is on the
    phone with a customer and asks the copilot what it knows about them.
    The portfolio summary cannot answer it, and without it the copilot can quote totals
    but cannot help with the call it was opened for.

    It reads the same export the summary reads, so a subscriber is here only if
    `churn tiers` scored them; nothing is computed on the request.
    """
    portfolio = state.portfolio
    if portfolio is None:
        raise ServiceUnavailable(state.portfolio_error or "No portfolio export is available.")
    rows = portfolio.loc[portfolio["subscriber_id"].astype(str) == str(subscriber_id)]
    if rows.empty:
        return None
    row = _json_safe(rows.iloc[[0]])[0]
    reasons = [row[name] for name in REASON_COLUMNS if row.get(name) is not None]
    return {name: row.get(name) for name in SUBSCRIBER_COLUMNS} | {"reasons": reasons}


def _group_summary(portfolio: pd.DataFrame, column: str, order: tuple[str, ...]) -> list[dict]:
    """Customers, assumed monthly spend and expected revenue at risk, per group.

    `lyd_at_risk` is the 12-month value weighted by each customer's churn probability, not
    the value of everyone in the group.
    A group of 40,000 customers at 5% risk is not 40,000 values at risk, and reporting it
    that way inflates the copilot's headline by an order of magnitude (Ali's cohort note).
    It is null, not zero, when this export carries no risk estimate.
    """
    has_risk = {"churn_probability", "value_12m_base_lyd"} <= set(portfolio.columns)
    has_spend = "monthly_spend_lyd" in portfolio.columns
    groups = []
    seen = portfolio[column].astype(str)
    for name in [*order, *sorted(set(seen) - set(order))]:
        rows = portfolio.loc[seen == name]
        if rows.empty:
            continue
        weighted = rows["value_12m_base_lyd"] * rows["churn_probability"] if has_risk else None
        groups.append(
            {
                "name": name,
                "customers": int(len(rows)),
                "monthly_spend_lyd": (
                    float(rows["monthly_spend_lyd"].sum(skipna=True)) if has_spend else None
                ),
                "lyd_at_risk": None if weighted is None else float(weighted.sum(skipna=True)),
            }
        )
    return groups


def portfolio_summary(state: ServiceState) -> dict:
    """Customers and LYD at risk by risk band and value tier, with the model's evidence.

    The success thresholds and test metrics travel with the answer on purpose: the copilot
    is asked "how good is this model", and the honest answer is the frozen T7 evaluation
    rather than anything recomputed here.
    """
    portfolio = state.portfolio
    if portfolio is None:
        raise ServiceUnavailable(state.portfolio_error or "No portfolio export is available.")
    gate = state.release_gate or {}
    risk_available = "churn_probability" in portfolio.columns
    return {
        "model_version": state.model_version,
        "generated_at": state.loaded_at,
        "scored_at": _scored_at(state),
        "subscribers": int(len(portfolio)),
        "risk_available": risk_available,
        "by_risk_band": (
            _group_summary(portfolio, "risk_band", RISK_BANDS)
            if "risk_band" in portfolio.columns
            else []
        ),
        "by_value_tier": _group_summary(portfolio, "value_tier", VALUE_TIERS),
        "success_thresholds": json_safe(gate.get("thresholds", {})),
        "test_metrics": json_safe(gate.get("test_metrics", {})),
        "release_gate_passed": gate.get("passed"),
    }
