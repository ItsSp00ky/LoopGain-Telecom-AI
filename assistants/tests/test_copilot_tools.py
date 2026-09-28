import json

from assistants import copilot_tools, sources
from assistants.llm import ModelReply, ToolCall, ToolRequest

PORTFOLIO = {
    "model_version": "lightgbm-test",
    "scored_at": "2026-09-28T16:29:26+00:00",
    "subscribers": 30000,
    "by_risk_band": [
        {"name": "high", "customers": 1209, "monthly_spend_lyd": 68450.4, "lyd_at_risk": 37393.2}
    ],
    "by_value_tier": [
        {"name": "very_high", "customers": 4799, "monthly_spend_lyd": 872294.1, "lyd_at_risk": None}
    ],
    "release_gate_passed": True,
    "test_metrics": {"lightgbm": {"pr_auc": 0.34770}, "logistic_regression": {"pr_auc": 0.2769}},
}

RISK = {
    "subscriber_id": "70016",
    "churn_probability": 0.1126316,
    "risk_band": "medium",
    "reasons": ["Days since the last recharge, at the end of this month: 13"],
    "value_tier": "medium",
    "value_status": "scenario",
    "value_12m_low_lyd": 254.005,
    "value_12m_base_lyd": 347.57,
    "value_12m_high_lyd": 486.49,
    "monthly_spend_lyd": 57.9239,
    "scored_at": "2026-09-28T16:29:26+00:00",
    "model_version": "lightgbm-test",
}


class FakeService:
    """The prepaid service's copilot endpoints, faked at the client, recording each call."""

    def __init__(self):
        self.calls = []

    def portfolio_summary(self, base_url, key):
        self.calls.append(("portfolio", key))
        return PORTFOLIO

    def risk_for(self, base_url, key, subscriber_id):
        self.calls.append(("risk", key, subscriber_id))
        return RISK if subscriber_id == "70016" else None


def _tools(drafts=None, open_orders=frozenset(), client=None):
    tools = copilot_tools.build_tools(
        "http://service",
        "copilot-key",
        (drafts if drafts is not None else []).append,
        open_orders,
        client or FakeService(),
    )
    return {tool.name: tool for tool in tools}


def test_alerts_show_critical_and_major_by_default(copilot_data):
    result = _tools()["tower_alerts"].run()
    assert result["levels_shown"] == ["critical", "major"]
    assert [a["tower"] for a in result["alerts"]] == ["DOWN1M1", "SLEEP1M1", "DROP1M1"]
    assert result["matched"] == 3 and result["counts"]["warning"] == 2


def test_alerts_filter_by_level_group_and_count(copilot_data):
    tools = _tools()
    warnings = tools["tower_alerts"].run(level="warning")
    assert [a["tower"] for a in warnings["alerts"]] == ["WARN1M1", "GONE1M1"]
    assert tools["tower_alerts"].run(count=1)["shown"] == 1
    assert tools["tower_alerts"].run(name_group="drop")["matched"] == 1
    assert tools["tower_alerts"].run(name_group="tr")["matched"] == 0


def test_alerts_about_one_problem_count_every_level(copilot_data):
    tools = _tools()
    sleeping = tools["tower_alerts"].run(problem="sleeping")
    assert [a["tower"] for a in sleeping["alerts"]] == ["SLEEP1M1"]
    setup = tools["tower_alerts"].run(problem="setup")
    assert setup["levels_shown"] == ["critical", "major", "warning"]
    assert [a["tower"] for a in setup["alerts"]] == ["WARN1M1"]
    assert tools["tower_alerts"].run(problem="no_report")["alerts"][0]["tower"] == "GONE1M1"


def test_alerts_count_what_they_leave_out(copilot_data):
    tools = _tools()
    assert tools["tower_alerts"].run(count=1)["not_shown"] == 2
    assert tools["tower_alerts"].run()["not_shown"] == 0


def test_alerts_say_they_are_not_a_forecast(copilot_data):
    note = _tools()["tower_alerts"].run()["note"]
    assert note.startswith("Alerts for 2026-09-19, the latest day") and "Not a forecast" in note


def test_a_tower_with_an_open_work_order_says_so(copilot_data):
    tools = _tools(open_orders={"DOWN1M1"})
    alerts = tools["tower_alerts"].run()["alerts"]
    assert alerts[0]["open_work_order"] is True and "open_work_order" not in alerts[1]
    assert tools["tower_status"].run(tower="down1m1")["open_work_order"] is True


def test_an_unknown_tower_is_an_error_with_near_names(copilot_data):
    result = _tools()["tower_status"].run(tower="DROP1M")
    assert result["error"] == "No tower called 'DROP1M' in the data."
    assert result["similar_names"][0] == "DROP1M1"


def test_the_overview_and_the_planning_tools_read_the_teammates_files(copilot_data):
    tools = _tools()
    assert tools["network_overview"].run()["tower_alerts"]["critical"] == 2
    assert tools["expansion_priorities"].run(count=1)["sites"][0]["rank"] == 1
    assert tools["explain_location"].run(site="3")["score"] == 60.0
    assert "error" in tools["explain_location"].run(site="99")


def test_drafting_hands_the_screen_a_draft_and_saves_nothing(copilot_data):
    drafts = []
    result = _tools(drafts)["draft_work_order"].run(tower="down1m1", action="site_visit")
    [draft] = drafts
    # The screen gets the draft with its ID; the model gets it without, so it cannot quote it.
    assert draft["draft_id"] and "draft_id" not in result["draft"]
    assert {k: v for k, v in draft.items() if k != "draft_id"} == result["draft"]
    assert result["draft"]["tower"] == "DOWN1M1" and result["draft"]["alert_level"] == "critical"
    assert not sources.WORK_ORDERS.exists()
    assert "error" in _tools(drafts)["draft_work_order"].run(tower="NOPE9", action="watch")


def test_customer_tools_use_the_copilot_key_and_round_for_the_reply():
    service = FakeService()
    tools = _tools(client=service)
    portfolio = tools["portfolio_summary"].run()
    assert portfolio["by_risk_band"][0] == {
        "name": "high",
        "customers": 1209,
        "monthly_spend_lyd": 68450,
        "lyd_at_risk_12m": 37393,
    }
    assert portfolio["by_value_tier"][0]["lyd_at_risk_12m"] is None
    # The total is added up in code, so a reply never has to add figures itself.
    assert portfolio["total"] == {
        "customers": 1209,
        "monthly_spend_lyd": 68450,
        "lyd_at_risk_12m": 37393,
    }
    assert portfolio["test_pr_auc"] == {"lightgbm": 0.348, "logistic_regression": 0.277}
    risk = tools["subscriber_risk"].run(subscriber_id=" 70016 ")
    assert risk["churn_probability_pct"] == 11.3 and risk["monthly_spend_lyd"] == 57.9
    assert risk["value_12m_lyd"] == {"low": 254, "base": 348, "high": 486}
    assert service.calls == [("portfolio", "copilot-key"), ("risk", "copilot-key", "70016")]
    assert "error" in tools["subscriber_risk"].run(subscriber_id="99999")


def test_a_phone_number_never_reaches_the_service():
    service = FakeService()
    result = _tools(client=service)["subscriber_risk"].run(subscriber_id="0912345678")
    assert "Phone numbers are not accepted" in result["error"]
    assert service.calls == []


def _scripted(first_call, reply):
    """A model that calls one tool, then gives `reply`; it records what it was sent."""
    seen = []

    def complete(messages, tools):
        seen.append(messages)
        if messages[-1]["role"] == "user":
            name, arguments = first_call
            return ModelReply(None, [ToolRequest("1", name, json.dumps(arguments))])
        return ModelReply(reply)

    return complete, seen


def _answer(prompt, complete, drafts=None):
    return copilot_tools.answer(
        prompt,
        [],
        "http://service",
        "copilot-key",
        complete,
        (drafts if drafts is not None else []).append,
        client=FakeService(),
    )


def test_a_grounded_answer_is_kept(copilot_data):
    complete, _ = _scripted(
        ("tower_alerts", {}), "- **DOWN1M1**: cell availability 30% on 2026-09-19 (target 95%)."
    )
    turn = _answer("Which towers need attention?", complete)
    assert turn.replaced_because is None
    assert turn.reply.startswith("- **DOWN1M1**")


def test_an_invented_number_gets_the_alert_list_instead(copilot_data):
    complete, _ = _scripted(("tower_alerts", {}), "DOWN1M1 has been down for 12 days.")
    turn = _answer("Which towers need attention?", complete)
    assert "12" in turn.replaced_because
    assert turn.reply.splitlines()[0] == "On 2026-09-19: 2 critical, 1 major, 2 warning."
    assert "- **DOWN1M1** (critical): cell availability 30%" in turn.reply


def test_a_draft_always_ends_with_the_line_that_it_waits_for_a_person(copilot_data):
    drafts = []
    complete, _ = _scripted(
        ("draft_work_order", {"tower": "DOWN1M1", "action": "site_visit"}),
        "Done, the field team is on its way.",
    )
    turn = _answer("Send a team to DOWN1M1", complete, drafts)
    assert len(drafts) == 1 and not sources.WORK_ORDERS.exists()
    assert turn.reply.endswith(
        "Work order draft for **DOWN1M1** is waiting below. Nothing is saved or sent until "
        "you press Confirm."
    )


def test_a_tower_lookup_reminds_the_model_to_draft_when_one_was_asked_for(copilot_data):
    tools = {
        tool.name: tool
        for tool in copilot_tools.build_tools(
            "http://service", "copilot-key", [].append, client=FakeService(), wants_order=True
        )
    }
    assert "call draft_work_order" in tools["tower_status"].run(tower="DOWN1M1")["next_step"]
    tools["draft_work_order"].run(tower="DOWN1M1", action="watch")
    assert "next_step" not in tools["tower_status"].run(tower="DOWN1M1")
    assert "next_step" not in _tools()["tower_status"].run(tower="DOWN1M1")


def test_a_draft_described_but_not_made_is_called_out(copilot_data):
    drafts = []
    complete, _ = _scripted(
        ("tower_status", {"tower": "DOWN1M1"}),
        "Draft work order: remote check for **DOWN1M1**.",
    )
    turn = _answer("What is wrong with DOWN1M1? Draft a remote check for it.", complete, drafts)
    assert drafts == []
    assert turn.reply.endswith(
        "No work order was drafted, so nothing is waiting for you to confirm. Ask again, or use "
        '"Draft a work order" in the Tower alerts panel.'
    )


def test_bold_tower_names_lose_the_code_box_around_them(copilot_data):
    complete, _ = _scripted(
        ("tower_status", {"tower": "DOWN1M1"}), "What is wrong with `**DOWN1M1**`:"
    )
    assert _answer("Status of DOWN1M1", complete).reply == "What is wrong with **DOWN1M1**:"


def test_a_phone_number_is_removed_before_the_model_sees_it(copilot_data):
    complete, seen = _scripted(("portfolio_summary", {}), "I can only look up subscriber IDs.")
    turn = _answer("Who is 091 234 5678?", complete)
    assert "234" not in json.dumps(seen) and "[phone number removed]" in json.dumps(seen)
    assert turn.reply.startswith("I cannot look anyone up by phone number")


def test_arabic_is_answered_in_arabic_even_by_the_fallback(copilot_data):
    complete, seen = _scripted(("tower_status", {"tower": "NOPE9"}), "")
    turn = _answer("شن وضع البرج NOPE9؟", complete)
    assert "Write your whole reply in Arabic" in seen[0][0]["content"]
    assert turn.reply.startswith("تعذّر ذلك")


def test_the_prompt_carries_the_date_of_the_tower_data(copilot_data):
    complete, seen = _scripted(("network_overview", {}), "Fine.")
    _answer("How is the network?", complete)
    assert "The tower data runs to 2026-09-19" in seen[0][0]["content"]


def test_every_fallback_is_built_from_its_tool_data(copilot_data):
    tools = _tools()
    calls = {
        "tower_status": {"tower": "DROP1M1"},
        "network_overview": {},
        "expansion_priorities": {"count": 2},
        "explain_location": {"site": "1"},
        "portfolio_summary": {},
        "subscriber_risk": {"subscriber_id": "70016"},
        "draft_work_order": {"tower": "GOOD1M1", "action": "watch"},
    }
    replies = {
        name: copilot_tools.fallback(
            [ToolCall(name, arguments, tools[name].run(**arguments))], "question"
        )
        for name, arguments in calls.items()
    }
    assert replies["tower_status"].startswith("**DROP1M1** on 2026-09-19 (major)")
    assert "2 critical, 1 major and 2 warning" in replies["network_overview"]
    assert replies["expansion_priorities"].splitlines()[0] == (
        "- Rank 1: Tripoli, score 66.7 (high_population_catchment, good_road_access); "
        "68900 people within 5 km, 3288 m from the nearest known site, 31 m from a road"
    )
    assert replies["expansion_priorities"].endswith("new site or more capacity.")
    assert replies["explain_location"].startswith("Rank 1, Tripoli: score 66.7")
    assert replies["portfolio_summary"] == (
        "1209 customers; LYD at risk over 12 months: 37393.\n"
        "- high: 1209 customers, 37393 LYD at risk"
    )
    assert replies["subscriber_risk"].startswith("Risk band medium, churn probability 11.3%")
    assert replies["draft_work_order"] == "This tower has no alert."
    assert copilot_tools.fallback([], "hello") == "I can't answer that from the data I have."
