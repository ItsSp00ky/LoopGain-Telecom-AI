import math

from assistants import network, sources


def _alerts(copilot_data):
    return network.find_alerts(network.load_towers(sources.TOWER_KPIS))


def test_each_tower_story_gets_its_level_worst_first(copilot_data):
    found = _alerts(copilot_data)
    assert found["data_date"] == "2026-09-19"
    assert found["towers_reporting"] == 6
    assert found["counts"] == {"critical": 2, "major": 1, "warning": 2}
    order = [(a["tower"], a["level"]) for a in found["alerts"]]
    assert order == [
        ("DOWN1M1", "critical"),
        ("SLEEP1M1", "critical"),
        ("DROP1M1", "major"),
        ("WARN1M1", "warning"),
        ("GONE1M1", "warning"),
    ]


def test_an_alert_names_the_kpi_its_value_and_its_limits(copilot_data):
    alerts = {a["tower"]: a for a in _alerts(copilot_data)["alerts"]}
    down = alerts["DOWN1M1"]["problems"][0]
    assert down["kpi"] == "cell availability" and down["value"] == 30.0
    assert down["days_missed_in_last_7"] == 3
    assert down["text"] == "cell availability 30% (target 95%, severe below 50%)"
    assert alerts["DROP1M1"]["problems"][0]["days_missed_in_last_7"] == 7
    assert alerts["WARN1M1"]["summary"] == (
        "connection setup success 99.2% (target 99.5%, severe below 98%)"
    )


def test_a_tower_up_but_carrying_almost_nobody_is_a_sleeping_cell(copilot_data):
    alerts = {a["tower"]: a for a in _alerts(copilot_data)["alerts"]}
    sleeping = alerts["SLEEP1M1"]["problems"]
    assert [p["kpi"] for p in sleeping] == ["users carried while up (sleeping cell)"]
    assert sleeping[0]["usual_users"] == 20.0
    assert "carrying 2 users against a usual 20 (10% of usual)" in sleeping[0]["text"]
    # The share is worked out here, so a reply never has to compute it.
    assert sleeping[0]["share_of_usual_pct"] == 10


def test_a_tower_that_stopped_reporting_is_a_warning(copilot_data):
    alerts = {a["tower"]: a for a in _alerts(copilot_data)["alerts"]}
    assert alerts["GONE1M1"]["summary"] == (
        "no KPIs reported on 2026-09-19; last report 2026-09-18"
    )


def test_a_value_missing_from_the_file_is_not_an_alert(copilot_data):
    towers = network.load_towers(sources.TOWER_KPIS).copy()
    last = (towers["tower"] == "DROP1M1") & (towers["date"] == towers["date"].max())
    towers.loc[last, "drop_rate_pct"] = math.nan
    assert "DROP1M1" not in {a["tower"] for a in network.find_alerts(towers)["alerts"]}


def test_a_later_severe_problem_outranks_an_earlier_warning():
    rule_order = [rule.column for rule in network.RULES]
    # Connection setup (a warning here) is checked before download speed (severe here).
    assert rule_order.index("connection_setup_pct") < rule_order.index("download_mbps")
    problems = [
        network._problem(network.RULES[2], 99.2, 1),
        network._problem(network.RULES[5], 1.0, 1),
    ]
    assert [p["level"] for p in problems] == ["warning", "major"]


def test_tower_status_shows_every_kpi_against_its_limits(copilot_data):
    towers = network.load_towers(sources.TOWER_KPIS)
    status = network.tower_status(towers, "DROP1M1")
    drop = next(k for k in status["kpis"] if k["kpi"] == "call drop rate")
    assert drop == {
        "kpi": "call drop rate",
        "value": 1.5,
        "unit": "%",
        "target": 0.5,
        "severe_limit": 1.0,
        "status": "past severe limit",
        "days_missed_in_last_7": 7,
        "average_last_7": 0.73,
    }
    assert status["alert_level"] == "major"
    assert status["users"] == 20.0 and status["usual_users"] == 20.0


def test_a_silent_tower_shows_as_not_reported(copilot_data):
    status = network.tower_status(network.load_towers(sources.TOWER_KPIS), "GONE1M1")
    assert status["reported_on_data_date"] is False
    assert status["days_reported_in_last_7"] == 6
    assert {k["status"] for k in status["kpis"]} == {"not reported"}


def test_towers_are_found_whatever_the_case_and_near_misses_are_suggested(copilot_data):
    towers = network.load_towers(sources.TOWER_KPIS)
    assert network.find_tower(towers, " drop1m1 ") == "DROP1M1"
    assert network.find_tower(towers, "NOPE9") is None
    assert network.similar_towers(towers, "DROP1M")[0] == "DROP1M1"
    assert network.similar_towers(towers, "ZZZZZZZZ") == []
    assert network.name_group("NT952M1") == "NT" and network.name_group("TR5M1") == "TR"


def test_the_overview_puts_towers_network_kpis_and_traffic_side_by_side(copilot_data):
    overview = network.network_overview(
        network.load_towers(sources.TOWER_KPIS),
        network.load_network(sources.NETWORK_KPIS),
        network.load_network(sources.TRAFFIC_VOLUME),
    )
    assert overview["tower_alerts"] == {
        "data_date": "2026-09-19",
        "towers_reporting": 6,
        "critical": 2,
        "major": 1,
        "warning": 2,
    }
    assert overview["network_kpis"]["data_date"] == "2026-09-17"
    assert overview["traffic_4g"] == {
        "data_date": "2026-09-21",
        "volume_gb": 1100,
        "average_previous_7_days_gb": 1000,
        "change_pct": 10.0,
    }
