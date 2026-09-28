"""Work orders for towers: the copilot drafts, an employee confirms (T25, decision 55).

The model can only call `draft`, which saves nothing. `confirm` is called by the screen
when a named employee presses Confirm, and it is the one place a work order is written.
There is no way for the model to reach it, so nothing happens without a person.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

ACTIONS = {
    "site_visit": "Send a field team to the site",
    "remote_check": "Remote check by the network operations centre",
    "watch": "Watch the tower for three more days",
}


def draft(alert: dict | None, tower: str, action: str, data_date: str) -> dict:
    """A work order waiting for a person; built only from the tower's alert."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of: {', '.join(ACTIONS)}.")
    return {
        "draft_id": uuid.uuid4().hex[:8],
        "tower": tower,
        "action": action,
        "action_label": ACTIONS[action],
        "alert_level": alert["level"] if alert else None,
        "problems": [problem["text"] for problem in alert["problems"]] if alert else [],
        "data_date": data_date,
        "status": "waiting for an employee to confirm it on screen; nothing is saved or sent",
    }


def confirm(order: dict, employee: str, note: str, path: Path) -> dict:
    """Save a draft a named employee confirmed; the only write in the copilot."""
    employee = employee.strip()
    if not employee:
        raise ValueError("A work order needs the name of the employee who confirms it.")
    record = {
        "work_order": order["draft_id"],
        "tower": order["tower"],
        "action": order["action"],
        "action_label": order["action_label"],
        "alert_level": order["alert_level"],
        "problems": order["problems"],
        "data_date": order["data_date"],
        "note": note.strip(),
        "confirmed_by": employee,
        "confirmed_at": f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}",
        "status": "open",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load(path: Path) -> list[dict]:
    """Every confirmed work order, newest first."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in reversed(lines) if line.strip()]
