import json
from datetime import date, timedelta

import pytest

from assistants import env, sources


@pytest.fixture(autouse=True)
def no_local_env_file(monkeypatch, tmp_path):
    """Tests never read the developer's real `.env`, which may hold a live Groq key."""
    monkeypatch.setattr(env, "ENV_FILE", tmp_path / "missing.env")


LAST_DAY = date(2026, 9, 19)

TOWER_HEADER = (
    "Date,ERBS Id,RRC Setup Success Rate,E-RAB Establishment Success Rate,E-RAB Drop Rate,"
    "Handover Success Rate ( 4G Intra System),Handover Success Rate,4G Cell Av. (%),"
    "E-UTRAN IP Throughput UE DL,E-UTRAN IP Throughput UE UL,Avg RRC Connected users"
)

HEALTHY = {
    "rrc": 99.8,
    "erab": 99.8,
    "drop": 0.2,
    "ho": 99.0,
    "avail": 100.0,
    "dl": 10.0,
    "users": 20.0,
}


def _tower_day(tower: str, day: date) -> dict | None:
    """One hand-made row: each tower is healthy except for its one story."""
    row = dict(HEALTHY)
    last = day == LAST_DAY
    days_left = (LAST_DAY - day).days
    if tower == "DOWN1M1" and days_left < 3:
        row["avail"] = 30.0 if last else 90.0
    elif tower == "SLEEP1M1" and last:
        row["users"] = 2.0
    elif tower == "DROP1M1" and days_left < 7:
        row["drop"] = 1.5 if last else 0.6
    elif tower == "WARN1M1" and last:
        row["rrc"] = 99.2
    elif tower == "GONE1M1" and last:
        return None
    return row


TOWERS = ["GOOD1M1", "DOWN1M1", "SLEEP1M1", "DROP1M1", "WARN1M1", "GONE1M1", "TR5M1"]


def tower_csv() -> str:
    lines = [TOWER_HEADER]
    for offset in range(30, -1, -1):
        day = LAST_DAY - timedelta(days=offset)
        for tower in TOWERS:
            row = _tower_day(tower, day)
            if row is None:
                continue
            lines.append(
                f"{day},{tower},{row['rrc']},{row['erab']},{row['drop']},0.99,{row['ho']},"
                f"{row['avail']},{row['dl']},1.2,{row['users']}"
            )
    return "\n".join(lines) + "\n"


def network_csv() -> str:
    lines = [
        "Date,RRC Setup Success Rate,E-RAB Establishment Success Rate,E-RAB Drop Rate,"
        "Handover Success Rate ( 4G Intra System),Handover Success Rate,"
        "E-UTRAN IP Throughput UE DL,E-UTRAN IP Throughput UE UL"
    ]
    for offset in range(9, -1, -1):
        day = LAST_DAY - timedelta(days=2 + offset)
        lines.append(f"{day},99.6,99.7,0.2,0.98,98.5,6.0,1.0")
    return "\n".join(lines) + "\n"


def traffic_csv() -> str:
    lines = ["Date,4G Overall Accumulated Data Volume (GB)"]
    for offset in range(9, -1, -1):
        day = LAST_DAY + timedelta(days=2 - offset)
        lines.append(f"{day},{1000.0 if offset else 1100.0}")
    return "\n".join(lines) + "\n"


SITE_COLUMNS = (
    "candidate_id,recommendation_rank,municipality_name,canonical_latitude,canonical_longitude,"
    "planning_priority_score,demand_component,known_site_gap_component,road_access_component,"
    "terrain_component,reason_codes,population_sum_5km,dist_to_nearest_site_m,"
    "dist_to_nearest_road_m,candidate_status,eligible,rejection_reasons,dist_to_almadar_site_m"
)
SITES = [
    "candidate-aaa111,1,Tripoli,32.8,13.4,66.68,0.97,0.02,0.99,0.76,"
    "high_population_catchment;good_road_access,68900.2,3288.4,31.2,engineering_review,True,,3300",
    "candidate-bbb222,2,Aljfara,32.7,13.0,66.41,0.92,0.09,0.96,0.75,"
    "high_population_catchment,41935.8,4571.1,164.3,engineering_review,True,,4600",
    "candidate-ccc333,3,Tripoli,32.9,13.2,60.02,0.8,0.1,0.9,0.7,"
    "good_road_access,20000,3500,50,engineering_review,True,,3600",
]
REJECTED = [
    "candidate-ddd444,,Aljfara,32.76,12.95,47.82,0.91,0.0,0.22,0.71,"
    "ineligible;too_close_to_known_site,34950.1,1851.9,3121.9,ineligible,False,"
    "too_close_to_known_site,1900",
]

MANIFEST = {
    "scope": "Tripoli",
    "score_version": "explainable-gis-v2-test",
    "constraints": {"min_gap_distance_m": 3000.0, "top_k": 20},
}


def _area(mnc, net_type, readings, median, lon):
    """One hand-made measured area: a small square around (lon, 32.8)."""
    ring = [[lon, 32.8], [lon + 0.02, 32.8], [lon + 0.02, 32.82], [lon, 32.82], [lon, 32.8]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            "mcc": 606,
            "mnc": mnc,
            "net_type": net_type,
            "sample_count": readings,
            "day_count": 2,
            "device_count": 1,
            "median_dbm": median,
            "p10_dbm": median - 5,
        },
    }


MEASURED_AREAS = {
    "type": "FeatureCollection",
    "features": [
        _area(1, "LTE", 20, -80.0, 13.0),
        _area(1, "LTE", 10, -95.0, 13.1),
        _area(1, "LTE", 3, -120.0, 13.2),
        _area(0, "UMTS", 12, -90.0, 13.3),
    ],
}
MEASUREMENT_MANIFEST = {
    "eligible_measurements": 45,
    "planning_support": {
        "with_observations_5km": 0,
        "rows": [
            {
                "candidate_id": "candidate-aaa111",
                "nearest_measurement_m": 8034.97,
                "observations_within_1km": 0,
                "observations_within_5km": 0,
            }
        ],
    },
}
MEASUREMENT_PILOT = {"training_days": ["2026-09-23"], "holdout_days": ["2026-09-26"]}


@pytest.fixture
def copilot_data(monkeypatch, tmp_path):
    """The teammates' files, hand-made, with every copilot path pointed at them."""
    folder = tmp_path / "data"
    folder.mkdir()
    files = {
        "TOWER_KPIS": ("towers.csv", tower_csv()),
        "NETWORK_KPIS": ("network.csv", network_csv()),
        "TRAFFIC_VOLUME": ("traffic.csv", traffic_csv()),
        "SHORTLIST": ("shortlist.csv", "\n".join([SITE_COLUMNS, *SITES]) + "\n"),
        "CANDIDATES": ("candidates.csv", "\n".join([SITE_COLUMNS, *SITES, *REJECTED]) + "\n"),
        "MANIFEST": ("manifest.json", json.dumps(MANIFEST)),
    }
    files.update(
        {
            "MEASURED_AREAS": ("areas.geojson", json.dumps(MEASURED_AREAS)),
            "MEASUREMENT_MANIFEST": ("measurements.json", json.dumps(MEASUREMENT_MANIFEST)),
            "MEASUREMENT_PILOT": ("pilot.json", json.dumps(MEASUREMENT_PILOT)),
        }
    )
    for name, (filename, text) in files.items():
        path = folder / filename
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(sources, name, path)
    monkeypatch.setattr(sources, "WORK_ORDERS", tmp_path / "runtime" / "work_orders.jsonl")
    return folder
