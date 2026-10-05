"""Tower alerts and network figures, from the network team's committed daily KPIs (T25).

Maher's `erbs_cell_kpi_full_year.csv` holds one row per base station per day. The copilot
decides in code which towers need attention on the latest day in that file: the rules
below are the whole logic, and every alert names the KPI, its value and the limit it
crossed, so an engineer can check it against the file.

The targets are the network team's own (`SLA_THRESHOLDS` in
`network_kpi_prediction/erbs_node_analytics/src/node_profiler.py`). The severe limits are
the copilot's (decision 55): three come from the same file's sleeping-cell rule (download
under 2 Mbps, drops over 1%, connection setup under 98%), and the others mark a value far
enough past its target that one day of it is worth a person's time.
"""

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

COLUMNS = {
    "Date": "date",
    "ERBS Id": "tower",
    "4G Cell Av. (%)": "availability_pct",
    "E-RAB Drop Rate": "drop_rate_pct",
    "RRC Setup Success Rate": "connection_setup_pct",
    "E-RAB Establishment Success Rate": "session_setup_pct",
    "Handover Success Rate": "handover_pct",
    "E-UTRAN IP Throughput UE DL": "download_mbps",
    "Avg RRC Connected users": "users",
}


@dataclass(frozen=True)
class Rule:
    column: str
    kpi: str
    unit: str
    low_is_bad: bool
    # The network team's SLA target; download speed has none, only a severe limit.
    target: float | None
    # Past this, one day is a major alert (a critical one for availability).
    severe: float
    # The word the alert table uses, where the full name would not fit.
    short: str

    def crossed(self, value: float, limit: float | None) -> bool:
        if limit is None:
            return False
        return value < limit if self.low_is_bad else value > limit


RULES = (
    Rule("availability_pct", "cell availability", "%", True, 95.0, 50.0, "availability"),
    Rule("drop_rate_pct", "call drop rate", "%", False, 0.5, 1.0, "drops"),
    Rule("connection_setup_pct", "connection setup success", "%", True, 99.5, 98.0, "setup"),
    Rule("session_setup_pct", "data session setup success", "%", True, 99.5, 98.0, "session"),
    Rule("handover_pct", "handover success", "%", True, 97.5, 90.0, "handover"),
    Rule("download_mbps", "download speed", "Mbps", True, None, 2.0, "download"),
)

# A tower that is up but carries under a quarter of its usual users is a sleeping cell,
# which availability alone never shows. "Usual" is its median over the 28 days before, and
# only a tower that usually carries at least 5 users can be judged this way.
SLEEPING_SHARE = 0.25
SLEEPING_MIN_USUAL_USERS = 5.0
USUAL_DAYS = 28
RECENT_DAYS = 7

LEVELS = ("critical", "major", "warning")

# What an alert can be about: each rule's short name, a sleeping cell, or a missing report.
KINDS = tuple(rule.short for rule in RULES) + ("sleeping", "no_report")


def _number(value: float) -> float:
    """Two decimals, as the file writes them, so a reply can copy the figure exactly."""
    return round(float(value), 2)


def _with_unit(value: float, unit: str) -> str:
    return f"{value:g}{unit}" if unit == "%" else f"{value:g} {unit}"


def load_towers(path: Path) -> pd.DataFrame:
    """The file's last five weeks, with short column names; read once per file version."""
    return _towers(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=2)
def _towers(path: str, version: int) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=list(COLUMNS), parse_dates=["Date"]).rename(columns=COLUMNS)
    frame["tower"] = frame["tower"].astype(str).str.strip()
    latest = frame["date"].max()
    recent = frame["date"] > latest - pd.Timedelta(days=USUAL_DAYS + RECENT_DAYS)
    return frame[recent].sort_values(["tower", "date"]).reset_index(drop=True)


def name_group(tower: str) -> str:
    """The letters a tower name starts with: a naming group, not a verified area."""
    match = re.match(r"[A-Za-z]+", tower)
    return match.group(0).upper() if match else ""


def _windows(towers: pd.DataFrame) -> tuple[pd.Timestamp, pd.DataFrame, pd.DataFrame, pd.Series]:
    latest = towers["date"].max()
    today = towers[towers["date"] == latest].set_index("tower")
    week = towers[towers["date"] > latest - pd.Timedelta(days=RECENT_DAYS)]
    before = towers[
        (towers["date"] < latest) & (towers["date"] >= latest - pd.Timedelta(days=USUAL_DAYS))
    ]
    usual_users = before.groupby("tower")["users"].median()
    return latest, today, week, usual_users


def _days_missed(week: pd.DataFrame) -> dict[str, pd.Series]:
    """For each rule, how many of the last 7 days each tower missed its limit."""
    missed = {}
    for rule in RULES:
        limit = rule.target if rule.target is not None else rule.severe
        values = week[rule.column]
        crossed = values < limit if rule.low_is_bad else values > limit
        missed[rule.column] = crossed.groupby(week["tower"]).sum()
    return missed


def _problem(rule: Rule, value: float, days: int) -> dict:
    severe = rule.crossed(value, rule.severe)
    limits = []
    if rule.target is not None:
        limits.append(f"target {_with_unit(rule.target, rule.unit)}")
    side = "below" if rule.low_is_bad else "above"
    limits.append(f"severe {side} {_with_unit(rule.severe, rule.unit)}")
    return {
        "kpi": rule.kpi,
        "value": _number(value),
        "unit": rule.unit,
        "target": rule.target,
        "severe_limit": rule.severe,
        "past_severe_limit": severe,
        "level": ("critical" if rule.column == "availability_pct" else "major")
        if severe
        else "warning",
        "days_missed_in_last_7": days,
        "text": f"{rule.kpi} {_with_unit(_number(value), rule.unit)} ({', '.join(limits)})",
        "short": f"{rule.short} {_with_unit(_number(value), rule.unit)}",
        "kind": rule.short,
    }


def _sleeping(row: pd.Series, usual: float | None) -> dict | None:
    if usual is None or pd.isna(usual) or usual < SLEEPING_MIN_USUAL_USERS:
        return None
    if pd.isna(row["users"]) or pd.isna(row["availability_pct"]):
        return None
    if row["availability_pct"] < 95.0 or row["users"] >= SLEEPING_SHARE * usual:
        return None
    return {
        "kpi": "users carried while up (sleeping cell)",
        "value": _number(row["users"]),
        "unit": "users",
        "usual_users": _number(usual),
        "share_of_usual_pct": round(row["users"] / usual * 100),
        "past_severe_limit": True,
        "level": "critical",
        "text": (
            f"up ({_number(row['availability_pct']):g}% available) but carrying "
            f"{_number(row['users']):g} users against a usual {_number(usual):g} "
            f"({round(row['users'] / usual * 100)}% of usual)"
        ),
        "short": f"sleeping: {_number(row['users']):g} of usual {_number(usual):g} users",
        "kind": "sleeping",
    }


def find_alerts(towers: pd.DataFrame) -> dict:
    """Every tower that needs attention on the latest day, worst first."""
    latest, today, week, usual_users = _windows(towers)
    missed = _days_missed(week)
    found = []
    for tower, row in today.iterrows():
        problems = []
        for rule in RULES:
            value = row[rule.column]
            if pd.isna(value):
                continue
            if rule.crossed(value, rule.target) or rule.crossed(value, rule.severe):
                problems.append(_problem(rule, value, int(missed[rule.column].get(tower, 0))))
        sleeping = _sleeping(row, usual_users.get(tower))
        if sleeping:
            problems.append(sleeping)
        if problems:
            worst = min(LEVELS.index(problem["level"]) for problem in problems)
            found.append(_alert(tower, LEVELS[worst], problems))

    # A tower that reported in the week before and not on the latest day may be down.
    silent = sorted(set(week["tower"]) - set(today.index))
    last_seen = week.groupby("tower")["date"].max()
    for tower in silent:
        seen = f"{last_seen[tower]:%Y-%m-%d}"
        problem = {
            "kpi": "no KPIs reported",
            "last_reported": seen,
            "past_severe_limit": False,
            "level": "warning",
            "text": f"no KPIs reported on {latest:%Y-%m-%d}; last report {seen}",
            "short": f"no report since {seen}",
            "kind": "no_report",
        }
        found.append(_alert(tower, "warning", [problem]))

    found.sort(key=_worst_first)
    return {
        "data_date": f"{latest:%Y-%m-%d}",
        "towers_reporting": int(len(today)),
        "counts": {level: sum(a["level"] == level for a in found) for level in LEVELS},
        "alerts": found,
    }


def _alert(tower: str, level: str, problems: list[dict]) -> dict:
    # The worst problem first, so a cut-off line still shows what matters most.
    problems = sorted(problems, key=lambda problem: LEVELS.index(problem["level"]))
    return {
        "tower": tower,
        "level": level,
        "name_group": name_group(tower),
        "problems": problems,
        "summary": "; ".join(problem["text"] for problem in problems),
        "short": " · ".join(problem["short"] for problem in problems),
    }


def _worst_first(alert: dict) -> tuple:
    severe = sum(bool(p.get("past_severe_limit")) for p in alert["problems"])
    days = max((p.get("days_missed_in_last_7", 0) for p in alert["problems"]), default=0)
    return (LEVELS.index(alert["level"]), -severe, -days, -len(alert["problems"]), alert["tower"])


def find_tower(towers: pd.DataFrame, name: str) -> str | None:
    """The tower's name as the file writes it, whatever the case the employee typed."""
    wanted = name.strip().upper()
    for tower in towers["tower"].unique():
        if tower.upper() == wanted:
            return tower
    return None


def similar_towers(towers: pd.DataFrame, name: str, count: int = 3) -> list[str]:
    names = list(towers["tower"].unique())
    upper = {n.upper(): n for n in names}
    close = difflib.get_close_matches(name.strip().upper(), list(upper), n=count, cutoff=0.6)
    return [upper[n] for n in close]


def tower_status(towers: pd.DataFrame, tower: str) -> dict:
    """One tower's latest day against every rule, with its last 7 days beside it."""
    latest, today, week, usual_users = _windows(towers)
    missed = _days_missed(week)
    mine = week[week["tower"] == tower]
    reported = tower in today.index
    kpis = []
    for rule in RULES:
        value = today.at[tower, rule.column] if reported else None
        if value is None or pd.isna(value):
            status = "not reported"
        elif rule.crossed(value, rule.severe):
            status = "past severe limit"
        elif rule.crossed(value, rule.target):
            status = "missed target"
        else:
            status = "ok"
        average = mine[rule.column].mean()
        kpis.append(
            {
                "kpi": rule.kpi,
                "value": None if status == "not reported" else _number(value),
                "unit": rule.unit,
                "target": rule.target,
                "severe_limit": rule.severe,
                "status": status,
                "days_missed_in_last_7": int(missed[rule.column].get(tower, 0)),
                "average_last_7": None if pd.isna(average) else _number(average),
            }
        )
    usual = usual_users.get(tower)
    alert = next((a for a in find_alerts(towers)["alerts"] if a["tower"] == tower), None)
    return {
        "tower": tower,
        "name_group": name_group(tower),
        "data_date": f"{latest:%Y-%m-%d}",
        "reported_on_data_date": reported,
        "days_reported_in_last_7": int(mine["date"].nunique()),
        "users": _number(today.at[tower, "users"])
        if reported and not pd.isna(today.at[tower, "users"])
        else None,
        "usual_users": None if usual is None or pd.isna(usual) else _number(usual),
        "kpis": kpis,
        "alert_level": alert["level"] if alert else None,
        "alert_summary": alert["summary"] if alert else None,
    }


def network_overview(towers: pd.DataFrame, network: pd.DataFrame, traffic: pd.DataFrame) -> dict:
    """The whole network in a few lines: tower alerts, network KPIs and 4G traffic."""
    alerts = find_alerts(towers)
    network = network.sort_values("Date")
    last = network.iloc[-1]
    week = network.tail(RECENT_DAYS)
    kpis = []
    for column, rule in (
        ("RRC Setup Success Rate", RULES[2]),
        ("E-RAB Establishment Success Rate", RULES[3]),
        ("E-RAB Drop Rate", RULES[1]),
        ("Handover Success Rate", RULES[4]),
        ("E-UTRAN IP Throughput UE DL", RULES[5]),
    ):
        value = last[column]
        meets = None if rule.target is None else not rule.crossed(value, rule.target)
        kpis.append(
            {
                "kpi": rule.kpi,
                "value": _number(value),
                "unit": rule.unit,
                "target": rule.target,
                "meets_target": meets,
                "average_last_7": _number(week[column].mean()),
            }
        )
    traffic = traffic.sort_values("Date")
    volume = traffic.columns[1]
    latest_volume = traffic.iloc[-1][volume]
    previous = traffic.iloc[-1 - RECENT_DAYS : -1][volume].mean()
    return {
        "tower_alerts": {
            "data_date": alerts["data_date"],
            "towers_reporting": alerts["towers_reporting"],
            **alerts["counts"],
        },
        "network_kpis": {"data_date": f"{last['Date']:%Y-%m-%d}", "kpis": kpis},
        "traffic_4g": {
            "data_date": f"{traffic.iloc[-1]['Date']:%Y-%m-%d}",
            "volume_gb": round(float(latest_volume)),
            "average_previous_7_days_gb": round(float(previous)),
            "change_pct": round((latest_volume / previous - 1) * 100, 1),
        },
    }


def load_network(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["Date"])
