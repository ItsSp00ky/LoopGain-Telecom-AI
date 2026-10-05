import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistants import llm, service_client, sources, work_orders
from assistants.llm import ModelReply, ToolRequest

APP = str(Path(__file__).parents[1] / "copilot_app.py")


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("PREPAID_CHURN_COPILOT_KEY", "copilot-key-for-tests")
    monkeypatch.setenv("GROQ_API_KEY", "not-used-by-the-fake")
    monkeypatch.setattr(service_client, "health", lambda base_url: {"status": "ok"})


def _labelled(widgets, label):
    return [widget for widget in widgets if widget.label == label]


def test_the_alerts_show_before_anyone_asks_even_without_keys(monkeypatch, copilot_data):
    monkeypatch.delenv("PREPAID_CHURN_COPILOT_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(service_client, "health", lambda base_url: {"status": "ok"})
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert app.title[0].value == "Network and customer copilot"
    assert app.error[0].value.startswith(
        "2 critical and 1 major tower alerts on 2026-09-19, the latest day"
    )
    table = app.dataframe[0].value
    assert list(table["Tower"]) == ["DOWN1M1", "SLEEP1M1", "DROP1M1"]
    assert "PREPAID_CHURN_COPILOT_KEY and GROQ_API_KEY" in app.error[-1].value
    assert len(app.chat_input) == 0


def test_warnings_show_when_asked(copilot_data, keys):
    app = AppTest.from_file(APP).run()
    app.toggle[0].set_value(True).run()
    assert list(app.dataframe[0].value["Tower"])[-2:] == ["WARN1M1", "GONE1M1"]


def test_a_draft_is_saved_only_when_a_named_employee_confirms(copilot_data, keys):
    app = AppTest.from_file(APP).run()
    _labelled(app.button, "Draft a work order")[0].click().run()
    confirm = _labelled(app.button, "Confirm")[0]
    assert confirm.disabled
    assert not sources.WORK_ORDERS.exists()

    _labelled(app.text_input, "Your name")[0].set_value("Taha").run()
    _labelled(app.selectbox, "Action")[-1].set_value("remote_check").run()
    _labelled(app.text_input, "Note (optional)")[0].set_value("check the power").run()
    _labelled(app.button, "Confirm")[0].click().run()

    assert not app.exception
    [order] = work_orders.load(sources.WORK_ORDERS)
    assert order["tower"] == "DOWN1M1" and order["confirmed_by"] == "Taha"
    assert order["action"] == "remote_check" and order["note"] == "check the power"
    assert _labelled(app.button, "Confirm") == []
    assert app.dataframe[0].value["Work order"].iloc[0] == "open"


def test_a_discarded_draft_leaves_nothing(copilot_data, keys):
    app = AppTest.from_file(APP).run()
    _labelled(app.button, "Draft a work order")[0].click().run()
    _labelled(app.button, "Discard")[0].click().run()
    assert _labelled(app.button, "Confirm") == []
    assert not sources.WORK_ORDERS.exists()


def test_a_chat_draft_waits_under_the_reply_and_phone_numbers_are_removed(
    monkeypatch, copilot_data, keys
):
    seen = []

    def complete(messages, tools):
        seen.append(messages)
        if messages[-1]["role"] == "user":
            arguments = json.dumps({"tower": "DROP1M1", "action": "watch"})
            return ModelReply(None, [ToolRequest("1", "draft_work_order", arguments)])
        return ModelReply("I drafted a watch order for **DROP1M1**.")

    monkeypatch.setattr(llm, "groq_complete", lambda api_key=None: complete)
    app = AppTest.from_file(APP).run()
    app.chat_input[0].set_value("Watch DROP1M1, the owner is 0912345678").run()

    assert not app.exception
    user, reply = [m.markdown[0].value for m in app.chat_message]
    assert "[phone number removed]" in user and "0912345678" not in json.dumps(seen)
    assert reply.startswith("I cannot look anyone up by phone number")
    assert "is waiting below" in reply
    assert _labelled(app.button, "Confirm")
    assert not sources.WORK_ORDERS.exists()
