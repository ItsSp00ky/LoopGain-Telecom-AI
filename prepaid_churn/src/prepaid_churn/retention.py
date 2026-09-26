"""Deterministic retention proposals, guardrails and equal-spend scenarios (T11).

Adapted from Ali's decision guardrails and budget design. All offers are bonus
grants from the existing catalogue. Effects and delivery costs are assumptions;
the engine does not learn uplift or change the catalogue's retail prices.
"""

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from prepaid_churn.bundle import Bundle
from prepaid_churn.clean import clean
from prepaid_churn.data import LABEL_COLUMN
from prepaid_churn.operator_market import OPERATOR_DIR, PAY_AS_YOU_GO, bundle_held, validate_offers
from prepaid_churn.schema import validate
from prepaid_churn.scoring import SCORING_WINDOW
from prepaid_churn.value import TIERS, TierModel, tier_export
from prepaid_churn.windows import window_features

POLICY_PATH = OPERATOR_DIR / "retention.toml"
NO_OFFER = "NO_OFFER"
REASONS = {
    "already_silent": ("No offer: already inactive.", "لا عرض: المشترك غير نشط حالياً."),
    "risk_unavailable": (
        "No offer: churn risk is unavailable.",
        "لا عرض: تقدير مخاطر المغادرة غير متاح.",
    ),
    "holdout": ("No offer: random campaign holdout.", "لا عرض: ضمن المجموعة الضابطة العشوائية."),
    "low_risk": ("No offer: low churn risk.", "لا عرض: مخاطر المغادرة منخفضة."),
    "no_eligible_offer": (
        "No offer passes relevance, eligibility and spend guards.",
        "لا عرض يستوفي شروط الملاءمة والأهلية وحد الإنفاق.",
    ),
    "nonpositive_value": (
        "No offer has positive assumed net value.",
        "لا عرض يحقق قيمة صافية موجبة وفق الافتراضات.",
    ),
    "budget": (
        "No offer: the remaining campaign budget cannot fund the best candidate.",
        "لا عرض: الميزانية المتبقية لا تغطي العرض المرشح.",
    ),
}
DECISION_COLUMNS = [
    "bundle_held",
    "holdout",
    "recommended_offer_id",
    "offer_reason_en",
    "offer_reason_ar",
    "decision_code",
    "status",
    "expected_cost_lyd",
    "expected_net_value_lyd",
    "share_saved",
    "policy_version",
]


class RetentionError(ValueError):
    """An invalid policy, decision input or review record."""


@dataclass(frozen=True)
class RetentionPolicy:
    budget_lyd: float
    max_value_fraction: float
    holdout_fraction: float
    seed: int
    share_saved: float
    offpeak_share_saved: float
    base_monthly_offer_id: str
    preferred_offer_id: str
    share_of_price_metered: float
    share_of_price_unlimited: float

    @property
    def version(self) -> str:
        return "retention-v1-" + fingerprint(asdict(self))[:12]


def fingerprint(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def validate_policy(policy: RetentionPolicy) -> RetentionPolicy:
    for name, value in asdict(policy).items():
        if name.endswith("offer_id"):
            if not isinstance(value, str) or not value.strip():
                raise RetentionError(f"{name} must name a catalogue offer.")
        elif name == "seed":
            if type(value) is not int or value < 0:
                raise RetentionError("seed must be a nonnegative integer.")
        elif type(value) not in (int, float) or not np.isfinite(value) or value < 0:
            raise RetentionError(f"{name} must be a finite nonnegative number.")
        elif name != "budget_lyd" and value > 1:
            raise RetentionError(f"{name} must be between 0 and 1.")
    if min(policy.share_of_price_metered, policy.share_of_price_unlimited) <= 0:
        raise RetentionError("Delivery cost shares must be positive.")
    return policy


def load_policy(path: Path = POLICY_PATH) -> RetentionPolicy:
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
        if set(config) != {"policy", "delivery_cost"}:
            raise ValueError("expected policy and delivery_cost tables")
        values = {}
        for name, status in (("policy", "assumption"), ("delivery_cost", "estimate")):
            table = dict(config[name])
            if table.pop("status") != status or not table.pop("source").strip():
                raise ValueError("each table needs its expected status and a source")
            values.update(table)
        return validate_policy(RetentionPolicy(**values))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise RetentionError(f"Invalid retention policy: {error}") from None


def dirhams(value: float, rounding=ROUND_FLOOR) -> int:
    return int((Decimal(str(value)) * 1000).to_integral_value(rounding=rounding))


def holdout_mask(ids: pd.Series, fraction: float, seed: int) -> pd.Series:
    """Seeded hash lottery: stable under row order and batch size, about fraction held out."""
    return ids.map(
        lambda subscriber: (
            int.from_bytes(hashlib.sha256(f"{seed}:{subscriber}".encode()).digest()[:8], "big")
            / 2**64
            < fraction
        )
    ).astype(bool)


def decision_inputs(
    export: pd.DataFrame, model: TierModel, bundle: Bundle | None, offers: pd.DataFrame
) -> pd.DataFrame:
    """Build risk, value, service use and inferred held bundle from the same export."""
    tiers = tier_export(export, model, bundle)
    cleaned = clean(validate(export.drop(columns=LABEL_COLUMN, errors="ignore"), labeled=False))
    window = window_features(cleaned, SCORING_WINDOW)
    tiers["bundle_held"] = bundle_held(window, model.rate, offers)
    for service, bases in {
        "voice": ("total_ic_mou", "total_og_mou"),
        "data": ("vol_2g_mb", "vol_3g_mb"),
    }.items():
        tiers[f"uses_{service}"] = (
            window[[f"{prefix}_{base}" for prefix in ("prev", "cur") for base in bases]]
            .gt(0)
            .any(axis=1)
        )
    if bundle is None:
        tiers["churn_probability"] = np.nan
        tiers["risk_band"] = np.where(
            tiers["value_status"].eq("already_silent"), "already_silent", "unavailable"
        )
    return tiers


def validate_inputs(frame: pd.DataFrame, offers: pd.DataFrame) -> None:
    required = {
        "subscriber_id",
        "churn_probability",
        "risk_band",
        "value_tier",
        "value_status",
        "value_12m_base_lyd",
        "bundle_held",
        "uses_voice",
        "uses_data",
    }
    if required - set(frame.columns):
        raise RetentionError(f"Decision inputs missing: {sorted(required - set(frame.columns))}")
    ids = frame["subscriber_id"]
    if ids.isna().any() or not ids.map(lambda x: isinstance(x, str) and bool(x.strip())).all():
        raise RetentionError("Subscriber IDs must be nonempty text.")
    if not ids.is_unique:
        raise RetentionError("Subscriber IDs must be unique.")
    if not frame["value_tier"].isin(TIERS).all():
        raise RetentionError("Every subscriber needs a valid value tier.")
    if not frame["bundle_held"].isin([PAY_AS_YOU_GO, *offers["offer_id"]]).all():
        raise RetentionError("Unknown held bundle; cannibalisation cannot be checked.")
    for column in ("uses_voice", "uses_data"):
        if not frame[column].map(lambda v: isinstance(v, bool)).all():
            raise RetentionError(f"{column} must be boolean.")
    statuses = {
        "scenario": {"low", "medium", "high"},
        "already_silent": {"already_silent"},
        "risk_unavailable": {"unavailable"},
    }
    for row in frame.itertuples(index=False):
        if row.value_status not in statuses or row.risk_band not in statuses[row.value_status]:
            raise RetentionError("Risk band and value status disagree.")
        numbers = (row.churn_probability, row.value_12m_base_lyd)
        if row.value_status == "scenario":
            if not all(isinstance(v, (int, float)) and np.isfinite(v) for v in numbers):
                raise RetentionError("Scored customers need finite risk and value.")
            if not 0 <= numbers[0] <= 1 or numbers[1] < 0:
                raise RetentionError("Risk or value is outside its allowed range.")
        elif not all(pd.isna(v) for v in numbers):
            raise RetentionError("Unscored customers must not have invented risk or value.")


def offer_candidates(
    frame: pd.DataFrame, offers: pd.DataFrame, policy: RetentionPolicy
) -> pd.DataFrame:
    """Best feasible offer per customer, before holdout, risk, positive value and budget gates.

    Iterate over the small catalogue and vectorize across customers, avoiding an
    N-by-57 Python object table. A sorted offer ID is the final deterministic tie-break.
    """
    catalogue = offers.set_index("offer_id")
    if (
        policy.base_monthly_offer_id not in catalogue.index
        or policy.preferred_offer_id not in catalogue.index
    ):
        raise RetentionError("The base monthly or preferred offer is absent from the catalogue.")
    base = catalogue.loc[policy.base_monthly_offer_id]
    if base["validity_hours"] < 720:
        raise RetentionError("The base monthly guard must refer to a monthly offer.")
    if pd.isna(catalogue.loc[policy.preferred_offer_id, "valid_from_hour"]):
        raise RetentionError("The preferred off-peak offer must have a catalogue time window.")
    held_price = frame["bundle_held"].map(catalogue["price_lyd"]).fillna(0).to_numpy()
    held_hours = frame["bundle_held"].map(catalogue["validity_hours"]).fillna(0).to_numpy()
    exposed = (held_hours >= 720) & (held_price > base["price_lyd"])
    value = frame["value_12m_base_lyd"].to_numpy(dtype=float)
    probability = frame["churn_probability"].to_numpy(dtype=float)
    ceiling = np.floor(np.nan_to_num(value) * policy.max_value_fraction * 1000 + 1e-9)
    best = pd.DataFrame(
        {"offer_id": NO_OFFER, "cost_dirhams": 0, "net_value": -np.inf, "share_saved": 0.0},
        index=frame.index,
    )
    ordered = offers.assign(preferred=offers["offer_id"].eq(policy.preferred_offer_id))
    ordered = ordered.sort_values(["preferred", "offer_id"], ascending=[False, True])
    for offer in ordered.itertuples(index=False):
        # The source export cannot establish device/5G coverage or family membership.
        if pd.notna(offer.network) or (pd.notna(offer.members) and offer.members > 1):
            continue
        data = offer.data_unlimited == 1 or pd.notna(offer.data_gb)
        voice = offer.voice_unlimited == 1 or pd.notna(offer.voice_minutes)
        relevant = (frame["uses_data"].to_numpy() & data) | (frame["uses_voice"].to_numpy() & voice)
        unlimited = bool(offer.data_unlimited or offer.voice_unlimited)
        share = policy.share_of_price_unlimited if unlimited else policy.share_of_price_metered
        cost = int(
            (Decimal(str(offer.price_lyd)) * Decimal(str(share)) * 1000).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        saved = policy.offpeak_share_saved if offer.preferred else policy.share_saved
        net = probability * saved * value - cost / 1000
        allowed = relevant & (cost <= ceiling) & np.isfinite(net)
        if unlimited and offer.price_lyd < base["price_lyd"]:
            allowed &= ~exposed
        better = allowed & (net > best["net_value"].to_numpy())
        best.loc[better, "offer_id"] = offer.offer_id
        best.loc[better, "cost_dirhams"] = cost
        best.loc[better, "net_value"] = net[better]
        best.loc[better, "share_saved"] = saved
    return best


def equal_spend_comparison(
    frame: pd.DataFrame, best: pd.DataFrame, selected: pd.Series, holdout: pd.Series
) -> pd.DataFrame:
    """Diagnostic expected allocations at exactly the selected spend, never executable rows."""
    spend = int(best.loc[selected, "cost_dirhams"].sum())
    rows = [
        {
            "strategy": "targeted",
            "expected_customers": float(selected.sum()),
            "expected_cost_lyd": spend / 1000,
            "assumed_net_value_lyd": float(best.loc[selected, "net_value"].sum()),
        }
    ]
    available = best["offer_id"].ne(NO_OFFER) & ~holdout
    pool = best.loc[available]
    total = int(pool["cost_dirhams"].sum())
    fraction = spend / total if total else 0
    rows.append(
        {
            "strategy": "untargeted_uniform",
            "expected_customers": len(pool) * fraction,
            "expected_cost_lyd": spend / 1000,
            "assumed_net_value_lyd": float(pool["net_value"].sum()) * fraction,
        }
    )
    order = (
        frame.loc[available]
        .sort_values(["churn_probability", "subscriber_id"], ascending=[False, True])
        .index
    )
    remaining, count, net = spend, 0.0, 0.0
    for index in order:
        candidate = best.loc[index]
        weight = min(1.0, remaining / candidate["cost_dirhams"])
        count += weight
        net += weight * candidate["net_value"]
        remaining -= min(remaining, int(candidate["cost_dirhams"]))
        if remaining == 0:
            break
    rows.append(
        {
            "strategy": "risk_only",
            "expected_customers": count,
            "expected_cost_lyd": spend / 1000,
            "assumed_net_value_lyd": net,
        }
    )
    return pd.DataFrame(rows)


def propose(
    frame: pd.DataFrame, offers: pd.DataFrame, policy: RetentionPolicy
) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = validate_policy(policy)
    offers = validate_offers(offers)
    if not np.isfinite(offers["price_lyd"]).all():
        raise RetentionError("Catalogue prices must be finite.")
    validate_inputs(frame, offers)
    frame = frame.reset_index(drop=True).copy()
    holdout = holdout_mask(frame["subscriber_id"], policy.holdout_fraction, policy.seed)
    best = offer_candidates(frame, offers, policy)
    code = pd.Series("candidate", index=frame.index, dtype="str")
    for reason, condition in (
        ("already_silent", frame["value_status"].eq("already_silent")),
        ("risk_unavailable", frame["value_status"].eq("risk_unavailable")),
        ("holdout", holdout),
        ("low_risk", frame["risk_band"].eq("low")),
        ("no_eligible_offer", best["offer_id"].eq(NO_OFFER)),
        ("nonpositive_value", best["net_value"].le(0)),
    ):
        code.loc[code.eq("candidate") & condition] = reason
    viable = code.eq("candidate")
    order = frame.loc[viable, ["subscriber_id"]].assign(net=best.loc[viable, "net_value"])
    selected = pd.Series(False, index=frame.index)
    remaining = dirhams(policy.budget_lyd)
    for index in order.sort_values(["net", "subscriber_id"], ascending=[False, True]).index:
        cost = int(best.at[index, "cost_dirhams"])
        if cost <= remaining:
            selected.at[index] = True
            remaining -= cost
    code.loc[viable & ~selected] = "budget"
    code.loc[selected] = "positive_value"
    result = frame.drop(columns=["uses_voice", "uses_data"]).copy()
    result["holdout"] = holdout
    result["recommended_offer_id"] = best["offer_id"].where(selected, NO_OFFER)
    result["decision_code"] = code
    result["status"] = pd.Series(np.where(selected, "proposed", "no_offer"), dtype="str")
    result["expected_cost_lyd"] = best["cost_dirhams"].where(selected, 0) / 1000
    result["expected_net_value_lyd"] = best["net_value"].where(selected, 0.0)
    result["share_saved"] = best["share_saved"].where(selected, 0.0)
    result["policy_version"] = policy.version
    catalogue = offers.set_index("offer_id")
    for language in ("en", "ar"):
        reasons = []
        for offer_id, reason in zip(result["recommended_offer_id"], code, strict=True):
            if offer_id == NO_OFFER:
                reasons.append(REASONS[reason][0 if language == "en" else 1])
                continue
            offer = catalogue.loc[offer_id]
            window = (
                f" ({int(offer.valid_from_hour):02d}:00-{int(offer.valid_to_hour):02d}:00)"
                if pd.notna(offer.valid_from_hour)
                else ""
            )
            reasons.append(
                f"Catalogue bonus: {offer.name_en}{window}; positive value under the stated "
                "retention assumptions."
                if language == "en"
                else f"مكافأة من الكتالوج: {offer.name_ar}{window}؛ "
                "قيمة موجبة وفق افتراضات الاحتفاظ."
            )
        result[f"offer_reason_{language}"] = pd.Series(reasons, dtype="str")
    return result, equal_spend_comparison(frame, best, selected, holdout)
