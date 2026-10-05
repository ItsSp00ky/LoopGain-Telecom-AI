"""Measured service: the GIS release's review of handset signal readings in Libya (T25).

Mahmoud and Ahmed's release summarises volunteer phone readings per small hexagonal area
(H3 resolution 8) and per network and radio technology. The copilot passes those
summaries on as they are: it never turns them into coverage, never compares the networks
with them, and never presents them as support for a planning site, because the release
itself says they are none of those things.
"""

import json
import statistics
from pathlib import Path

# An area needs at least this many readings before it is shown as one of the weakest.
MIN_READINGS = 5
DEFAULT_WEAKEST = 5
MAX_WEAKEST = 10

TECHNOLOGIES = ("GSM", "UMTS", "LTE")

CAVEATS = (
    "Signal strength in dBm from volunteer phones: not LTE RSRP, not a coverage map.",
    "The sample is uneven between networks and technologies, so it cannot compare networks.",
    "No eligible reading lies within 5 km of any of the 20 planning priorities, so the readings "
    "do not validate them.",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def network_code(mcc, mnc) -> str:
    """The network as its public MCC-MNC code, such as 606-01; never the operator's name."""
    return f"{int(mcc)}-{int(mnc):02d}"


def _centre(geometry: dict) -> tuple[float, float]:
    ring = geometry["coordinates"][0][:-1]
    longitude = sum(point[0] for point in ring) / len(ring)
    latitude = sum(point[1] for point in ring) / len(ring)
    return round(latitude, 4), round(longitude, 4)


def areas(geojson: dict) -> list[dict]:
    """One row per measured area: network, technology, readings and signal, and its centre."""
    rows = []
    for feature in geojson["features"]:
        p = feature["properties"]
        latitude, longitude = _centre(feature["geometry"])
        rows.append(
            {
                "network": network_code(p["mcc"], p["mnc"]),
                "technology": p["net_type"],
                "readings": int(p["sample_count"]),
                "days": int(p["day_count"]),
                "devices": int(p["device_count"]),
                "median_dbm": p["median_dbm"],
                "p10_dbm": p["p10_dbm"],
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return rows


def measured_service(
    rows: list[dict],
    manifest: dict,
    pilot: dict,
    *,
    network: str | None = None,
    technology: str | None = None,
    count: int | str | None = None,
) -> dict:
    """The measured-service review: totals, signal by network and technology, weakest areas."""
    if network:
        rows = [r for r in rows if r["network"] == network.strip()]
    if technology:
        rows = [r for r in rows if r["technology"] == technology.strip().upper()]
    groups = {}
    for row in rows:
        groups.setdefault((row["network"], row["technology"]), []).append(row)
    by_group = [
        {
            "network": key[0],
            "technology": key[1],
            "areas": len(members),
            "readings": sum(m["readings"] for m in members),
            "median_of_area_medians_dbm": round(
                statistics.median(m["median_dbm"] for m in members), 1
            ),
        }
        for key, members in sorted(groups.items())
    ]
    shown = min(max(int(count or DEFAULT_WEAKEST), 1), MAX_WEAKEST)
    candidates = [r for r in rows if r["readings"] >= MIN_READINGS]
    weakest = sorted(candidates, key=lambda r: (r["median_dbm"], -r["readings"]))[:shown]
    days = sorted([*pilot.get("training_days", []), *pilot.get("holdout_days", [])])
    return {
        "eligible_readings": manifest.get("eligible_measurements"),
        "collection_days": days,
        "areas_matched": len(rows),
        "by_network_and_technology": by_group,
        "weakest_areas": weakest,
        "weakest_areas_rule": f"lowest median signal among areas with at least {MIN_READINGS} "
        "readings; a lower (more negative) dBm is a weaker signal",
        "priorities_with_readings_within_5km": (manifest.get("planning_support") or {}).get(
            "with_observations_5km"
        ),
        "caveats": list(CAVEATS),
    }


def support_by_site(manifest: dict) -> dict[str, dict]:
    """For each ranked site, how far the nearest measurement is and how many lie within 5 km."""
    rows = (manifest.get("planning_support") or {}).get("rows") or []
    return {
        row["candidate_id"]: {
            "nearest_measurement_m": round(row["nearest_measurement_m"]),
            "readings_within_5km": row["observations_within_5km"],
        }
        for row in rows
        if row.get("nearest_measurement_m") is not None
    }
