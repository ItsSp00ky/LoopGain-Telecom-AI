"""What the demo app shows, as pure functions (ticket T14, decision 22).

The Streamlit screens in `app/` are a thin surface over this module.
Nothing here recomputes a score, a tier or an offer.
Every figure comes from a file that `churn tiers`, `churn operator-view` and `churn decide`
already wrote, and the loading goes through `service.load_state`, so the screens and the
T15 endpoints answer from the same state and cannot drift apart.

The one thing the app may write is a review, and it writes it through `campaign.review_file`
like `churn approve` does: the same lock, the same atomic replacement and the same audit
event (decision 14).
"""

import datetime
import os
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from prepaid_churn.campaign import campaign_rows, load_campaign
from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.operator_market import OFFERS_PATH, load_offers
from prepaid_churn.retention import REASONS
from prepaid_churn.service import ServicePaths, ServiceState, gift_message, load_state
from prepaid_churn.value import TIERS

# Every screen names what it is missing and the command that produces it.
# A screen that renders empty charts with no explanation is worse than one that says which
# command to run: during a demo the second is recoverable (Ali's `missing_banner`).
PRODUCED_BY = {
    "portfolio": "uv run churn tiers --tiers-only",
    "campaign": "uv run churn decide --tiers-only --output-dir artifacts/campaigns/<name>",
    "bundle": "uv run churn bundle",
    "operator view": "uv run churn operator-view",
}

RISK_BANDS = ("high", "medium", "low", "already_silent")
VALUE_TIERS = tuple(reversed(TIERS))


CAMPAIGN_DIR_VARIABLE = "PREPAID_CHURN_CAMPAIGN_DIR"
PORTFOLIO_VARIABLE = "PREPAID_CHURN_PORTFOLIO"


CAMPAIGNS_DIR = PROJECT_ROOT / "artifacts" / "campaigns"


@dataclass(frozen=True)
class DemoPaths:
    portfolio_path: Path = PROJECT_ROOT / "artifacts" / "scores" / "tiers.csv"
    view_path: Path = PROJECT_ROOT / "artifacts" / "scores" / "operator_view.csv"
    campaign_dir: Path = CAMPAIGNS_DIR / "retention"
    bundle_dir: Path = PROJECT_ROOT / "artifacts" / "bundle"
    offers_path: Path = OFFERS_PATH
    # The base the app proposes on, and the frozen tiers it values it with. Both are what
    # `churn decide` uses; the app runs the same path rather than a shortcut of its own.
    base_path: Path = PROJECT_ROOT / "data" / "raw" / "test.csv"
    tiers_path: Path = PROJECT_ROOT / "artifacts" / "tiers" / "tiers.json"

    @property
    def campaign_path(self) -> Path:
        return self.campaign_dir / "proposals.json"

    @classmethod
    def from_environment(cls, environ: dict | None = None) -> "DemoPaths":
        """The defaults, with the campaign and the portfolio overridable.

        Both genuinely vary: `churn decide --output-dir` writes each campaign to its own
        directory and `churn tiers --output` writes each export to its own file, so the
        app has to be told which pair to show rather than only ever reading the first.
        """
        environ = os.environ if environ is None else environ
        overrides = {}
        if directory := environ.get(CAMPAIGN_DIR_VARIABLE):
            overrides["campaign_dir"] = Path(directory)
        if portfolio := environ.get(PORTFOLIO_VARIABLE):
            overrides["portfolio_path"] = Path(portfolio)
        return cls(**overrides)

    def service(self) -> ServicePaths:
        return ServicePaths(
            bundle_dir=self.bundle_dir,
            portfolio_path=self.portfolio_path,
            campaign_path=self.campaign_path,
            offers_path=self.offers_path,
        )


@dataclass(frozen=True)
class DemoState:
    """Everything the screens read, loaded once."""

    service: ServiceState
    decisions: pd.DataFrame | None = None
    view: pd.DataFrame | None = None
    campaign: dict | None = None
    campaign_path: Path | None = None
    missing: tuple[tuple[str, str], ...] = ()

    @property
    def portfolio(self) -> pd.DataFrame | None:
        return self.service.portfolio

    @property
    def offers(self) -> pd.DataFrame:
        return self.service.offers

    @property
    def model_version(self) -> str | None:
        return self.service.model_version

    @property
    def has_risk(self) -> bool:
        portfolio = self.portfolio
        return portfolio is not None and "churn_probability" in portfolio.columns


def load_demo(paths: DemoPaths) -> DemoState:
    """Read what exists and record what does not, rather than failing on a missing file."""
    missing: list[tuple[str, str]] = []
    campaign, decisions = None, None
    if paths.campaign_path.exists():
        # Parsed here and handed to the service, which needs the same snapshot for the
        # released rows. A campaign of 30,000 customers is an 80 MB file, and reading it
        # twice was most of the app's loading time.
        campaign = load_campaign(paths.campaign_path)
        decisions = campaign_rows(campaign)
        decisions["subscriber_id"] = decisions["subscriber_id"].astype(str)
    else:
        missing.append(("campaign", PRODUCED_BY["campaign"]))

    service = load_state(paths.service(), campaign)
    if service.portfolio is None:
        missing.append(("portfolio", PRODUCED_BY["portfolio"]))
    if service.bundle is None:
        missing.append(("bundle", PRODUCED_BY["bundle"]))

    view = None
    if paths.view_path.exists():
        view = pd.read_csv(paths.view_path, converters={"id": str})
    else:
        missing.append(("operator view", PRODUCED_BY["operator view"]))

    return DemoState(
        service=service,
        decisions=decisions,
        view=view,
        campaign=campaign,
        campaign_path=paths.campaign_path if campaign is not None else None,
        missing=tuple(missing),
    )


def expected_churners(portfolio: pd.DataFrame | None) -> float | None:
    """The sum of calibrated probabilities, not a count above a threshold.

    Calibration is what makes that sum mean anything, and it is the honest headline:
    counting everyone above the high threshold answers a different question (Ali's
    Executive Overview note).
    Returns None when the export carries no risk, because zero would be a claim.
    """
    if portfolio is None or "churn_probability" not in portfolio.columns:
        return None
    return float(portfolio["churn_probability"].sum(skipna=True))


def revenue_at_risk(portfolio: pd.DataFrame | None) -> float | None:
    """12-month value weighted by each customer's churn probability.

    Not the value of everyone in a risky band: a base of 40,000 at 5% risk is not 40,000
    values at risk, and quoting it that way overstates the headline in the flattering
    direction, which is exactly when to be careful.
    """
    if portfolio is None or not {"churn_probability", "value_12m_base_lyd"} <= set(
        portfolio.columns
    ):
        return None
    return float((portfolio["value_12m_base_lyd"] * portfolio["churn_probability"]).sum())


def group_counts(
    portfolio: pd.DataFrame | None, column: str, order: tuple[str, ...]
) -> pd.DataFrame:
    """Customers, assumed monthly spend and expected value at risk, per group."""
    empty = pd.DataFrame(columns=["group", "customers", "monthly_spend_lyd", "lyd_at_risk"])
    if portfolio is None or column not in portfolio.columns:
        return empty
    seen = portfolio[column].astype(str)
    has_risk = {"churn_probability", "value_12m_base_lyd"} <= set(portfolio.columns)
    rows = []
    for name in [*order, *sorted(set(seen) - set(order))]:
        group = portfolio.loc[seen == name]
        if group.empty:
            continue
        rows.append(
            {
                "group": name,
                "customers": int(len(group)),
                "monthly_spend_lyd": float(group["monthly_spend_lyd"].sum(skipna=True))
                if "monthly_spend_lyd" in group.columns
                else None,
                "lyd_at_risk": float(
                    (group["value_12m_base_lyd"] * group["churn_probability"]).sum()
                )
                if has_risk
                else None,
            }
        )
    return pd.DataFrame(rows, columns=list(empty.columns))


def guardrail_rejections(decisions: pd.DataFrame | None) -> pd.DataFrame:
    """How many customers each guardrail removed, with the reason in plain language.

    A campaign tool that cannot say who it excluded and why is one nobody should sign off
    (Ali's Campaign Builder note).
    """
    empty = pd.DataFrame(columns=["code", "reason", "customers"])
    if decisions is None or "decision_code" not in decisions.columns:
        return empty
    codes = decisions["decision_code"].dropna().astype(str)
    counts = codes[codes.isin(REASONS)].value_counts()
    rows = [
        {"code": code, "reason": REASONS[code][0], "customers": int(count)}
        for code, count in counts.items()
    ]
    return pd.DataFrame(rows, columns=list(empty.columns))


MISSING_TEXT = frozenset({"nan", "none", "nat", ""})
# Columns that `campaign_rows` builds with dtype="str", which turns a missing value into
# the literal text "nan" rather than a null. Only these are normalised, so a real ID like
# "NA" is never touched.
STRINGIFIED_COLUMNS = ("reviewer", "reviewed_at", "review_note")


def _present(value) -> object | None:
    """None for a value that is missing, including one pandas already made into text.

    An unreviewed proposal showed "reviewed by nan" on screen, because the reviewer column
    is cast to str and an absent name became the string "nan", which is perfectly truthy.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, str) and value.strip().lower() in MISSING_TEXT:
        return None
    return value


def subscriber_view(state: DemoState, subscriber_id: str) -> dict | None:
    """Everything the subscriber screen shows for one customer, or None if unknown.

    Built from a one-row frame rather than a Series throughout.
    A Series holds one dtype, so turning one back into a frame makes every column
    `object`, which is the bug that silently blanked a whole panel on `Ali_Branch`.
    """
    subscriber_id = str(subscriber_id)
    found = {}
    for name, frame, key in (
        ("portfolio", state.portfolio, "subscriber_id"),
        ("decision", state.decisions, "subscriber_id"),
        ("view", state.view, "id"),
    ):
        if frame is None or key not in frame.columns:
            continue
        rows = frame.loc[frame[key].astype(str) == subscriber_id]
        if not rows.empty:
            found[name] = rows.head(1)
    if not found:
        return None
    merged: dict = {"subscriber_id": subscriber_id}
    for one_row in found.values():
        merged |= {name: one_row.iloc[0][name] for name in one_row.columns}
    for column in STRINGIFIED_COLUMNS:
        if column in merged:
            merged[column] = _present(merged[column])
    merged["reasons"] = [
        merged[column]
        for column in ("reason_1", "reason_2", "reason_3")
        if isinstance(merged.get(column), str) and merged[column].strip()
    ]
    return merged


def offer_row(state: DemoState, offer_id: object) -> dict | None:
    offers = state.offers
    rows = offers.loc[offers["offer_id"].astype(str) == str(offer_id)]
    return None if rows.empty else rows.iloc[0].to_dict()


def pending_proposals(decisions: pd.DataFrame | None) -> pd.DataFrame:
    """Proposals nobody has reviewed yet; only these can be approved or rejected."""
    if decisions is None or "status" not in decisions.columns:
        return pd.DataFrame()
    return decisions.loc[decisions["status"].astype(str) == "proposed"]


def campaign_totals(decisions: pd.DataFrame | None) -> dict:
    """Counts and assumed money for the campaign builder, by review status."""
    if decisions is None or decisions.empty:
        return {"rows": 0, "proposed": 0, "approved": 0, "rejected": 0, "holdout": 0, "offers": 0}
    status = decisions["status"].astype(str)
    offered = decisions["recommended_offer_id"].astype(str).ne("NO_OFFER")
    holdout = decisions["holdout"] if "holdout" in decisions.columns else pd.Series(dtype=bool)
    return {
        "rows": int(len(decisions)),
        "proposed": int(status.eq("proposed").sum()),
        "approved": int(status.eq("approved").sum()),
        "rejected": int(status.eq("rejected").sum()),
        "holdout": int(holdout.fillna(False).astype(bool).sum()) if len(holdout) else 0,
        "offers": int(offered.sum()),
        "expected_cost_lyd": _total(decisions, "expected_cost_lyd", offered),
        "expected_net_value_lyd": _total(decisions, "expected_net_value_lyd", offered),
    }


def _total(decisions: pd.DataFrame, column: str, mask: pd.Series) -> float | None:
    if column not in decisions.columns:
        return None
    return float(decisions.loc[mask, column].sum(skipna=True))


def budget_preview(campaign: dict, budget_lyd: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-run T11's allocation over the campaign's own stored inputs at another budget.

    This is a preview and nothing else.
    It never becomes a proposal, nothing in it can be approved, and the authoritative
    snapshot is untouched: approving always acts on what `churn decide` wrote, so a
    reviewer cannot approve a row they were shown by a slider.
    No model runs here either.
    The inputs, catalogue and policy all come out of the snapshot, and only the budget
    changes, which is what makes the comparison a fair one.
    """
    from dataclasses import replace

    from prepaid_churn.retention import RetentionPolicy, propose

    snapshot = campaign["snapshot"]
    policy = replace(RetentionPolicy(**snapshot["policy"]), budget_lyd=float(budget_lyd))
    inputs = pd.DataFrame(snapshot["inputs"])
    inputs["subscriber_id"] = inputs["subscriber_id"].astype(str)
    return propose(inputs, pd.DataFrame(snapshot["offers"]), policy)


# ---------------------------------------------------------------------------
# The customer message
# ---------------------------------------------------------------------------

# THE REAL LIMIT IS 70, NOT 160.
# Ported from `Ali_Branch`'s `apps/_shared.py` (port log step 10), because it is the one
# thing about an SMS preview that is easy to get wrong and expensive to get wrong.
# GSM-7 gives 160 characters per part, but a single Arabic character forces the whole
# message into UCS-2, where one part is 70 characters.
# A preview showing 160 would tell a campaign manager that an Arabic message fits in one
# SMS when it will actually send as three, and the operator is billed per part.
GSM7_LIMIT = 160
GSM7_CONCAT_LIMIT = 153
UCS2_LIMIT = 70
UCS2_CONCAT_LIMIT = 67  # a multi-part message spends 6 bytes per part on the UDH header

GSM7_BASIC = set(
    "@£$¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà\n\r"
)


def sms_parts(text: str) -> dict:
    """How this message would actually be sent, and billed."""
    unicode_needed = any(character not in GSM7_BASIC for character in text)
    if unicode_needed:
        encoding, limit, concat = "UCS-2", UCS2_LIMIT, UCS2_CONCAT_LIMIT
    else:
        encoding, limit, concat = "GSM-7", GSM7_LIMIT, GSM7_CONCAT_LIMIT
    length = len(text)
    parts = 1 if length <= limit else -(-length // concat)
    return {
        "encoding": encoding,
        "length": length,
        "limit": limit,
        "parts": parts,
        "remaining": (limit if parts == 1 else concat * parts) - length,
        "over_one_part": parts > 1,
    }


def customer_message(offer: dict | None, language: str = "ar") -> str:
    """The text an approved customer would receive, in Arabic or English (decision 51).

    It is the message the chatbot is given, `service.gift_message`: the package, what it
    gives and for how long. The policy's reason stays with staff, and no churn
    probability, risk band or value figure is available to it by construction
    (decision 10). A package that has left the catalogue has nothing current to describe,
    so it has no message.
    """
    if language not in ("ar", "en"):
        raise ValueError("The customer message is written in Arabic or English.")
    return "" if offer is None else gift_message(offer, language)


def utc_today() -> str:
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def campaign_directories(root: Path = CAMPAIGNS_DIR) -> pd.DataFrame:
    """Every campaign on disk, newest first, without opening the snapshots.

    A campaign of the whole base is an 80 MB file, so the picker reads the directory and
    the small released file instead: it has to be instant, and it is only choosing which
    campaign to load.
    """
    rows = []
    for snapshot in sorted(root.glob("*/proposals.json")):
        released = snapshot.parent / "released.csv"
        approved = 0
        if released.exists():
            with released.open(encoding="utf-8") as handle:
                approved = max(sum(1 for _ in handle) - 1, 0)
        rows.append(
            {
                "campaign": snapshot.parent.name,
                "approved": approved,
                "updated": datetime.datetime.fromtimestamp(
                    snapshot.stat().st_mtime, datetime.UTC
                ).strftime("%Y-%m-%d %H:%M"),
                "size_mb": round(snapshot.stat().st_size / 1e6, 1),
                "path": str(snapshot.parent),
            }
        )
    frame = pd.DataFrame(rows, columns=["campaign", "approved", "updated", "size_mb", "path"])
    return frame.sort_values("updated", ascending=False, ignore_index=True)


def propose_offers(
    paths: DemoPaths,
    output_dir: Path,
    subscribers: list[str] | None = None,
    budget_lyd: float | None = None,
    customers: int | None = None,
) -> dict:
    """Propose offers and save them as a new campaign, the way `churn decide` does.

    This is the app creating a campaign rather than reading one, so it runs exactly the
    T11 path: the frozen tiers, the gated bundle, the catalogue and the policy, with the
    same guardrails and the same holdout. The app chooses who is considered and how much
    may be spent, and nothing else; it never picks a package, and it never approves what
    it proposed (decision 14).

    `subscribers` limits it to named IDs, `customers` to the first N of the base. A
    campaign over the whole base takes about half a minute and writes an 80 MB snapshot,
    which is why the screens offer a size at all.
    """
    from prepaid_churn.bundle import load_bundle
    from prepaid_churn.campaign import build_campaign, save_campaign
    from prepaid_churn.data import load_raw
    from prepaid_churn.retention import decision_inputs, load_policy, propose
    from prepaid_churn.schema import ID
    from prepaid_churn.value import load_tiers

    raw = load_raw(paths.base_path)
    if subscribers:
        wanted = {str(one) for one in subscribers}
        raw = raw[raw[ID].astype(str).isin(wanted)]
        if raw.empty:
            raise ValueError(f"None of {sorted(wanted)} is in {paths.base_path.name}.")
    elif customers:
        raw = raw.head(customers)

    policy = load_policy()
    if budget_lyd is not None:
        policy = replace(policy, budget_lyd=float(budget_lyd))
    offers = load_offers(paths.offers_path)
    inputs = decision_inputs(
        raw, load_tiers(paths.tiers_path), load_bundle(paths.bundle_dir), offers
    )
    decisions, comparison = propose(inputs, offers, policy)
    campaign = build_campaign(inputs, decisions, comparison, offers, policy)
    save_campaign(campaign, output_dir)
    return campaign


def released_offers(state: DemoState) -> pd.DataFrame:
    """The approved offers of this campaign, with the package beside each one.

    This is the answer to "I approved something, where did it go": these rows are what
    `released.csv` holds and what the chatbot is served, and nothing else leaves the
    module.
    """
    approved = state.service.approved
    if approved is None or approved.empty:
        return pd.DataFrame()
    offers = state.service.offers.set_index("offer_id")
    package = offers.reindex(approved["recommended_offer_id"].astype(str))
    return pd.DataFrame(
        {
            "subscriber_id": approved["subscriber_id"].astype(str).to_numpy(),
            "offer_id": approved["recommended_offer_id"].astype(str).to_numpy(),
            "package": package["name_en"].to_numpy(),
            "package_ar": package["name_ar"].to_numpy(),
            "price_lyd": package["price_lyd"].to_numpy(),
            "reviewed_at": approved.get("reviewed_at", pd.Series(dtype="str")).to_numpy(),
            "reviewer": approved.get("reviewer", pd.Series(dtype="str")).to_numpy(),
            "reason_ar": approved.get("offer_reason_ar", pd.Series(dtype="str")).to_numpy(),
        }
    )
