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
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


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
    raise NotImplementedError("TODO(E4)")


def replay(decision_log_id: str) -> dict[str, Any]:
    """Re-run a logged decision against its recorded inputs and weights.

    If the replayed outcome differs from the logged one, either the config
    changed or the code did -- and the audit trail must show which.
    """
    raise NotImplementedError("TODO(E4)")


def export_for_audit(since: datetime, until: datetime):
    raise NotImplementedError("TODO(E4)")