"""The decision audit log.  Owner: E4

Every pricing and advance decision persists its inputs, weights, active
constraints and reason codes, and is replayable on demand.

This is not telemetry. It is the mechanism behind two commitments:

* Full auditability (proposal section 6.5). "Why did this subscriber get 15 LYD
  and not 25?" must be answerable months later, from the log alone.
* Transparency to the customer. Every offer carries a human-readable reason --
  "loyalty reward, 6 years with us" -- not an opaque personalised price.

A decision that did not write here did not happen, and a PR that adds a decision
path without logging it gets rejected.

REPLAY NEEDS THE WEIGHTS, NOT JUST THE INPUTS, and that is why they are a
separate field rather than folded in. Re-running a decision against today's
config answers "what would we decide now", which is a different and much less
useful question than "why did we decide that then". Storing the weights as they
were at the time is what makes the second question answerable -- and comparing
the two is what tells an auditor whether the config moved or the code did.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from cvm.config import settings

log = logging.getLogger(__name__)

# JSON Lines, appended. A row per decision, flushed immediately: an audit log
# that buffers is an audit log that loses the last decisions before a crash,
# which are exactly the ones anyone will ask about.
LOG_NAME = "decision_log.jsonl"


def _path():
    path = settings.processed_dir / LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_decision(
    *,
    subscriber_id: str,
    decision_type: str,
    inputs: dict[str, Any],
    weights: dict[str, float],
    constraints: list[Any],
    reason_codes: list[str],
    outcome: dict[str, Any],
    model_versions: dict[str, str],
) -> str:
    """Persist one decision. Returns the decision_log_id."""
    decision_log_id = str(uuid.uuid4())
    record = {
        "decision_log_id": decision_log_id,
        "logged_at": datetime.now(UTC).isoformat(),
        "subscriber_id": subscriber_id,
        "decision_type": decision_type,
        "inputs": _serialisable(inputs),
        "weights": dict(weights),
        "constraints": _serialisable(constraints),
        "reason_codes": list(reason_codes),
        "outcome": _serialisable(outcome),
        "model_versions": dict(model_versions),
    }
    with _path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
        handle.flush()
    return decision_log_id


def replay(decision_log_id: str) -> dict[str, Any]:
    """Re-run a logged decision against its recorded inputs and weights.

    If the replayed outcome differs from the logged one, either the config
    changed or the code did -- and the audit trail must show which.

    The two are distinguished by re-running TWICE: once with the weights as
    they were recorded, and once with today's. If the recorded weights
    reproduce the outcome and today's do not, the config moved. If neither
    reproduces it, the code moved. Reporting only "differs" would leave an
    auditor to work that out by hand.
    """
    record = find(decision_log_id)
    if record is None:
        raise KeyError(f"{decision_log_id} is not in {_path()}")

    if record["decision_type"] != "offer":
        return {
            **record,
            "replayable": False,
            "note": f"no replay path for {record['decision_type']}",
        }

    from cvm.api.schemas import OfferRequest
    from cvm.decision import pricing

    payload = OfferRequest(subscriber_id=record["subscriber_id"])
    inputs = record["inputs"]

    def run_with(weights: dict) -> dict:
        """Replay under a given weight set WITHOUT touching the shared config.

        The first version swapped the weights into `load_conf("pricing")` and
        restored them in a `finally`. `load_conf` is cached, so `original` and
        the dict being cleared were THE SAME OBJECT -- the restore put back what
        the clear had just emptied, and every subsequent caller in the process
        got a config with no discount weights at all. An audit function that
        corrupts live pricing config is worse than one that does not exist.

        `decide_offer` takes the weights through its features dict instead, so
        nothing global moves.
        """
        response = pricing.decide_offer(payload, {**inputs, "discount_weights": dict(weights)})
        return {
            "offer_id": response.offer_id,
            "price_lyd": response.price_lyd,
            "discount_pct": response.discount_pct,
        }

    logged = {k: record["outcome"].get(k) for k in ("offer_id", "price_lyd", "discount_pct")}
    with_recorded = run_with(record["weights"])
    with_current = run_with(dict(pricing._conf()["discount_weights"]))

    matches_recorded = _close(logged, with_recorded)
    matches_current = _close(logged, with_current)

    if matches_recorded and matches_current:
        verdict = "reproduced; nothing has changed"
    elif matches_recorded:
        verdict = "the CONFIG changed -- the recorded weights still reproduce this decision"
    else:
        verdict = "the CODE changed -- even the recorded weights no longer reproduce it"

    log.info("replay %s: %s", decision_log_id, verdict)
    return {
        "decision_log_id": decision_log_id,
        "logged_outcome": logged,
        "replayed_with_recorded_weights": with_recorded,
        "replayed_with_current_weights": with_current,
        "reproduced": matches_recorded,
        "verdict": verdict,
    }


def find(decision_log_id: str) -> dict[str, Any] | None:
    """One record by id, or None."""
    path = _path()
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("decision_log_id") == decision_log_id:
                return record
    return None


def export_for_audit(since: datetime, until: datetime):
    """Every decision in a window, as a frame an auditor can filter.

    Returned rather than written, because an audit export that lands in the
    same directory as the log is an audit export nobody can prove was not
    edited alongside it.
    """
    import pandas as pd

    path = _path()
    if not path.exists():
        return pd.DataFrame()

    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            stamp = datetime.fromisoformat(record["logged_at"])
            if since <= stamp <= until:
                rows.append(record)

    frame = pd.DataFrame(rows)
    log.info("audit export: %d decisions between %s and %s", len(frame), since.date(), until.date())
    return frame


def _close(a: dict, b: dict, tolerance: float = 1e-6) -> bool:
    for key in a:
        left, right = a.get(key), b.get(key)
        if isinstance(left, int | float) and isinstance(right, int | float):
            if abs(float(left) - float(right)) > tolerance:
                return False
        elif left != right:
            return False
    return True


def _serialisable(value):
    """Numpy scalars and pandas types do not survive json.dumps unhelped."""
    import numpy as np

    if isinstance(value, dict):
        return {str(k): _serialisable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_serialisable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float | int | str | bool) or value is None:
        return value
    return str(value)
