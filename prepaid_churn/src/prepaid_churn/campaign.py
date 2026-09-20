"""Local proposal snapshots and named human reviews (T11, decision 14).

The JSON snapshot is authoritative. CSVs are derived views, never review inputs.
Review events only resolve pending proposals, so an interrupted CSV refresh can
omit a newly approved row but cannot publish a rejected or unreviewed row.
"""

import datetime
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from prepaid_churn.retention import NO_OFFER, RetentionError, RetentionPolicy, fingerprint

RELEASE_COLUMNS = [
    "subscriber_id",
    "recommended_offer_id",
    "offer_reason_en",
    "offer_reason_ar",
    "status",
    "reviewer",
    "reviewed_at",
    "review_note",
    "campaign_id",
]
REVIEW_FIELDS = {"subscriber_id", "reviewer", "decision", "reviewed_at", "note", "campaign_id"}


def utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def records(frame: pd.DataFrame) -> list[dict]:
    # pandas serializes NaN as JSON null, keeping missing risk explicit.
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))


def build_campaign(
    inputs: pd.DataFrame,
    decisions: pd.DataFrame,
    comparison: pd.DataFrame,
    offers: pd.DataFrame,
    policy: RetentionPolicy,
    created_at: str | None = None,
) -> dict:
    snapshot = {
        "schema_version": 1,
        "created_at": created_at or utc_now(),
        "policy": asdict(policy),
        "inputs": records(inputs),
        "offers": records(offers),
        "rows": records(decisions),
        "columns": list(decisions.columns),
        "comparison": records(comparison),
    }
    return {"snapshot": snapshot, "campaign_id": fingerprint(snapshot), "reviews": []}


def validate_campaign(campaign: dict) -> dict:
    try:
        if set(campaign) != {"snapshot", "campaign_id", "reviews"}:
            raise ValueError("unknown campaign schema")
        snapshot = campaign["snapshot"]
        if (
            type(snapshot["schema_version"]) is not int
            or snapshot["schema_version"] != 1
            or fingerprint(snapshot) != campaign["campaign_id"]
        ):
            raise ValueError("proposal snapshot checksum or schema mismatch")
        rows = snapshot["rows"]
        by_id = {row["subscriber_id"]: row for row in rows}
        if len(by_id) != len(rows):
            raise ValueError("duplicate subscriber IDs")
        for row in rows:
            if row["status"] not in ("proposed", "no_offer"):
                raise ValueError("snapshot contains a reviewed status instead of a proposal")
            if (row["status"] == "no_offer") != (row["recommended_offer_id"] == NO_OFFER):
                raise ValueError("proposal status and offer disagree")
            if row["status"] == "proposed" and (
                row["holdout"]
                or row["risk_band"] not in ("medium", "high")
                or row["expected_cost_lyd"] <= 0
                or row["expected_net_value_lyd"] <= 0
            ):
                raise ValueError("ineligible proposal")
        seen = set()
        for event in campaign["reviews"]:
            if set(event) != REVIEW_FIELDS or event["campaign_id"] != campaign["campaign_id"]:
                raise ValueError("review belongs to another snapshot or has missing fields")
            subscriber = event["subscriber_id"]
            if (
                subscriber in seen
                or subscriber not in by_id
                or by_id[subscriber]["status"] != "proposed"
            ):
                raise ValueError("review must resolve one pending proposal exactly once")
            if event["decision"] not in ("approved", "rejected") or not event["reviewer"].strip():
                raise ValueError("review needs a named reviewer and an approval or rejection")
            stamp = datetime.datetime.fromisoformat(event["reviewed_at"])
            if stamp.utcoffset() != datetime.timedelta(0) or not isinstance(event["note"], str):
                raise ValueError("review needs a UTC timestamp and a text note")
            seen.add(subscriber)
        return campaign
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise RetentionError(f"Invalid campaign: {error}") from None


def review_campaign(
    campaign: dict,
    reviewer: str,
    decision: str = "approved",
    subscriber_ids: list[str] | None = None,
    note: str = "",
    reviewed_at: str | None = None,
) -> dict:
    validate_campaign(campaign)
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise RetentionError("A nonempty reviewer name is required.")
    if not isinstance(note, str):
        raise RetentionError("Review notes must be text.")
    if decision not in ("approved", "rejected"):
        raise RetentionError("A review must approve or reject.")
    resolved = {event["subscriber_id"] for event in campaign["reviews"]}
    pending = {
        row["subscriber_id"] for row in campaign["snapshot"]["rows"] if row["status"] == "proposed"
    } - resolved
    chosen = sorted(pending) if subscriber_ids is None else subscriber_ids
    if len(set(chosen)) != len(chosen) or not set(chosen) <= pending:
        raise RetentionError(
            "Requested IDs must be distinct pending proposals; nothing was reviewed."
        )
    result = deepcopy(campaign)
    for subscriber in chosen:
        result["reviews"].append(
            {
                "subscriber_id": subscriber,
                "reviewer": reviewer.strip(),
                "decision": decision,
                "reviewed_at": reviewed_at or utc_now(),
                "note": note,
                "campaign_id": campaign["campaign_id"],
            }
        )
    return validate_campaign(result)


def campaign_rows(campaign: dict) -> pd.DataFrame:
    validate_campaign(campaign)
    rows = pd.DataFrame(campaign["snapshot"]["rows"], columns=campaign["snapshot"]["columns"])
    rows["subscriber_id"] = rows["subscriber_id"].astype("str")
    reviews = {event["subscriber_id"]: event for event in campaign["reviews"]}
    for column, event_column in (
        ("reviewer", "reviewer"),
        ("reviewed_at", "reviewed_at"),
        ("review_note", "note"),
    ):
        rows[column] = pd.Series(
            [reviews.get(subscriber, {}).get(event_column) for subscriber in rows["subscriber_id"]],
            dtype="str",
        )
    rows["status"] = [
        reviews.get(row.subscriber_id, {}).get("decision", row.status)
        for row in rows.itertuples(index=False)
    ]
    rows["campaign_id"] = campaign["campaign_id"]
    return rows


def released_campaign(campaign: dict) -> pd.DataFrame:
    rows = campaign_rows(campaign)
    return rows.loc[rows["status"].eq("approved"), RELEASE_COLUMNS].reset_index(drop=True)


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_campaign(campaign: dict, path: Path) -> None:
    validate_campaign(campaign)
    # Commit the authority first, then regenerate review and release views.
    _atomic_text(path, json.dumps(campaign, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    _atomic_text(path.parent / "decisions.csv", campaign_rows(campaign).to_csv(index=False))
    _atomic_text(
        path.parent / "review_log.jsonl",
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in campaign["reviews"]),
    )
    _atomic_text(path.parent / "released.csv", released_campaign(campaign).to_csv(index=False))


def save_campaign(campaign: dict, directory: Path) -> Path:
    validate_campaign(campaign)
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RetentionError(
            "Campaign directory already exists; choose a new --output-dir."
        ) from None
    path = directory / "proposals.json"
    _write_campaign(campaign, path)
    return path


def load_campaign(path: Path) -> dict:
    try:
        return validate_campaign(json.loads(path.read_text("utf-8")))
    except json.JSONDecodeError as error:
        raise RetentionError(f"Invalid campaign JSON: {error}") from None


@contextmanager
def _review_lock(path: Path):
    lock = path.parent / ".review.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise RetentionError(
            "Another review holds .review.lock; retry after it finishes."
        ) from None
    try:
        with handle:
            yield
    finally:
        lock.unlink()


def review_file(
    path: Path,
    reviewer: str,
    decision: str = "approved",
    subscriber_ids: list[str] | None = None,
    note: str = "",
) -> dict:
    if path.name != "proposals.json":
        raise RetentionError("Review the authoritative proposals.json, never an exported CSV.")
    with _review_lock(path):
        reviewed = review_campaign(load_campaign(path), reviewer, decision, subscriber_ids, note)
        _write_campaign(reviewed, path)
    return reviewed
