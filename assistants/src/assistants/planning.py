"""The GIS team's ranked candidate sites, as the copilot reads them (T25).

Mahmoud and Ahmed's integrated release ranks places in Tripoli for a new site: 40%
population, 30% distance from known sites, 20% road access and 10% terrain, after strict
eligibility checks. The copilot passes on their numbers and reason codes as they are; it
never re-scores a site. The distance columns named after each operator are left out, so
no answer can name one (decision 45).
"""

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

WEIGHTS = {"population": 40, "gap_to_known_sites": 30, "road_access": 20, "terrain": 10}

COMPONENTS = {
    "demand_component": "population",
    "known_site_gap_component": "gap_to_known_sites",
    "road_access_component": "road_access",
    "terrain_component": "terrain",
}

# What each component measures, from 0 to 1; higher always helps a site's score.
COMPONENT_MEANING = {
    "population": "people living around the site (1 = the densest catchment)",
    "gap_to_known_sites": "distance from the nearest known site (1 = far, a coverage gap; "
    "near 0 = close to a site already)",
    "road_access": "closeness to a road, for building and upkeep (1 = next to a road)",
    "terrain": "how suitable the ground is (1 = flat and prominent)",
}

MEASUREMENT_NOTE = (
    "Distance to the nearest handset signal reading is context only: no reading within 5 km "
    "neither supports nor rules out a site."
)

LIMITS = (
    "A planning heuristic for Tripoli, not a coverage or traffic prediction; every site needs "
    "engineering review. It cannot tell whether an area needs a new site or more capacity."
)


@lru_cache(maxsize=4)
def _csv(path: str, version: int) -> pd.DataFrame:
    return pd.read_csv(path)


def load(path: Path) -> pd.DataFrame:
    return _csv(str(path), path.stat().st_mtime_ns)


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _codes(value) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return [code for code in value.split(";") if code]


def _whole(value) -> int | None:
    return None if pd.isna(value) else round(float(value))


def site_view(row: pd.Series) -> dict:
    """One candidate as the model sees it: rank, place, score and why."""
    rank = row.get("recommendation_rank")
    return {
        "rank": None if pd.isna(rank) else int(rank),
        "candidate": row["candidate_id"],
        "municipality": row.get("municipality_name"),
        "latitude": round(float(row["canonical_latitude"]), 5),
        "longitude": round(float(row["canonical_longitude"]), 5),
        "score": round(float(row["planning_priority_score"]), 1),
        "components": {name: round(float(row[column]), 2) for column, name in COMPONENTS.items()},
        "reason_codes": _codes(row.get("reason_codes")),
        "population_within_5km": _whole(row.get("population_sum_5km")),
        "distance_to_nearest_known_site_m": _whole(row.get("dist_to_nearest_site_m")),
        "distance_to_road_m": _whole(row.get("dist_to_nearest_road_m")),
        "status": row.get("candidate_status"),
        "eligible": bool(row.get("eligible")),
        "rejection_reasons": _codes(row.get("rejection_reasons")),
    }


def expansion_priorities(
    shortlist: pd.DataFrame,
    manifest: dict,
    candidates_total: int,
    eligible_total: int,
    municipality: str | None = None,
    top_n: int | None = None,
    support: dict[str, dict] | None = None,
) -> dict:
    """The ranked sites, best first, optionally in one municipality.

    `support` gives each site's distance to the nearest handset measurement, from the same
    release; it is context, never validation of a site.
    """
    rows = shortlist.sort_values("recommendation_rank")
    if municipality:
        wanted = municipality.strip().casefold()
        rows = rows[rows["municipality_name"].str.casefold().str.contains(wanted, regex=False)]
    count = min(max(int(top_n or 5), 1), 20)
    sites = [_with_support(site_view(row), support) for _, row in rows.head(count).iterrows()]
    return {
        "scope": manifest.get("scope"),
        "score_version": manifest.get("score_version"),
        "inventory_version": manifest.get("inventory_version"),
        "weights_pct": WEIGHTS,
        "component_meaning": COMPONENT_MEANING,
        "constraints": manifest.get("constraints"),
        "candidates_checked": candidates_total,
        "candidates_eligible": eligible_total,
        "sites_on_shortlist": int(len(shortlist)),
        "matched": int(len(rows)),
        "shown": min(count, int(len(rows))),
        "shown_ranges": _ranges(sites),
        "sites": sites,
        "limits": LIMITS,
        "measurement_note": MEASUREMENT_NOTE if support is not None else None,
    }


def _with_support(view: dict, support: dict[str, dict] | None) -> dict:
    if support is not None and view["candidate"] in support:
        view["measurements"] = support[view["candidate"]]
    return view


def _ranges(sites: list[dict]) -> dict:
    """The lowest and highest of each figure over the sites shown, so a summary of them
    ("39674 to 100277 people") quotes real numbers instead of rounding its own."""
    ranges = {}
    for field in (
        "population_within_5km",
        "distance_to_nearest_known_site_m",
        "distance_to_road_m",
        "score",
    ):
        values = [site[field] for site in sites if site[field] is not None]
        if values:
            ranges[field] = {"lowest": min(values), "highest": max(values)}
    return ranges


def explain_location(
    candidates: pd.DataFrame,
    shortlist: pd.DataFrame,
    site: str | int | None,
    support: dict[str, dict] | None = None,
) -> dict | None:
    """One candidate by its ID or its shortlist rank, with why it passed or failed."""
    if site is None or str(site).strip() == "":
        return None
    text = str(site).strip()
    if text.isdigit():
        found = shortlist[shortlist["recommendation_rank"] == int(text)]
    else:
        found = shortlist[shortlist["candidate_id"] == text]
        if found.empty:
            found = candidates[candidates["candidate_id"] == text]
    if found.empty:
        return None
    return {
        **_with_support(site_view(found.iloc[0]), support),
        "weights_pct": WEIGHTS,
        "component_meaning": COMPONENT_MEANING,
        "limits": LIMITS,
    }
