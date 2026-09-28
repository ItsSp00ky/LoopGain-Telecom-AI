import pytest

from assistants import work_orders

ALERT = {
    "tower": "DOWN1M1",
    "level": "critical",
    "problems": [{"text": "cell availability 30% (target 95%, severe below 50%)"}],
}


def test_a_draft_saves_nothing_and_says_it_waits(tmp_path):
    path = tmp_path / "work_orders.jsonl"
    order = work_orders.draft(ALERT, "DOWN1M1", "site_visit", "2026-09-19")
    assert order["action_label"] == "Send a field team to the site"
    assert order["problems"] == ["cell availability 30% (target 95%, severe below 50%)"]
    assert "nothing is saved" in order["status"]
    assert not path.exists()


def test_only_a_known_action_can_be_drafted():
    with pytest.raises(ValueError, match="site_visit, remote_check, watch"):
        work_orders.draft(ALERT, "DOWN1M1", "reboot_everything", "2026-09-19")


def test_a_named_employee_confirms_and_it_is_saved(tmp_path):
    path = tmp_path / "runtime" / "work_orders.jsonl"
    order = work_orders.draft(ALERT, "DOWN1M1", "remote_check", "2026-09-19")
    saved = work_orders.confirm(order, " Taha ", " check the power ", path)
    assert saved["confirmed_by"] == "Taha" and saved["note"] == "check the power"
    assert saved["status"] == "open" and saved["work_order"] == order["draft_id"]
    assert work_orders.load(path) == [saved]


def test_nobody_can_confirm_without_a_name(tmp_path):
    order = work_orders.draft(None, "GOOD1M1", "watch", "2026-09-19")
    with pytest.raises(ValueError, match="name of the employee"):
        work_orders.confirm(order, "  ", "", tmp_path / "work_orders.jsonl")


def test_orders_load_newest_first(tmp_path):
    path = tmp_path / "work_orders.jsonl"
    for tower in ("A1", "B1"):
        work_orders.confirm(work_orders.draft(None, tower, "watch", "d"), "Taha", "", path)
    assert [order["tower"] for order in work_orders.load(path)] == ["B1", "A1"]
    assert work_orders.load(tmp_path / "missing.jsonl") == []
