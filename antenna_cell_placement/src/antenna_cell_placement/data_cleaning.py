"""
Data cleaning and consolidation pipeline for Libyan Cell Tower Dataset.
Resolves regional scoping collisions, deduplicates radio antennas, preserves
source attribution, and clusters antennas into physical sites in memory.
"""

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree

from antenna_cell_placement.config import (
    RAW_SQLITE_PATH,
    COLLOCATION_DISTANCE_THRESHOLD_M,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
    OPERATOR_BY_MNC,
)


def load_raw_records_from_sqlite(db_path: Path = RAW_SQLITE_PATH) -> pd.DataFrame:
    """Load and parse all raw source records from SQLite database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT source_record_id, mcc, mnc, rat, raw_json FROM source_records")
    rows = cur.fetchall()
    conn.close()

    records = []
    for rid, mcc, mnc, rat, rj_str in rows:
        data = json.loads(rj_str)
        site_id = str(data.get("siteID", "")).strip()
        region_id = str(data.get("regionID", "")).strip()
        lat = data.get("latitude")
        lon = data.get("longitude")

        if lat is None or lon is None:
            continue

        raw_mcc = data.get("mcc") if data.get("mcc") is not None else mcc
        raw_mnc = data.get("mnc") if data.get("mnc") is not None else mnc
        raw_operator = data.get("operator")
        raw_visible = data.get("visible")
        first_seen = data.get("firstseendate")
        last_seen = data.get("lastseendate")

        records.append({
            "record_id": rid,
            "mcc": str(raw_mcc) if raw_mcc is not None else None,
            "mnc": str(raw_mnc) if raw_mnc is not None else None,
            "operator": raw_operator,
            "rat": rat,
            "rat_subtype": data.get("RATSubType", rat),
            "site_id": site_id,
            "region_id": region_id,
            "latitude": float(lat),
            "longitude": float(lon),
            "visible": bool(raw_visible) if raw_visible is not None else pd.NA,
            "first_seen_ms": int(first_seen) if first_seen else pd.NA,
            "last_seen_ms": int(last_seen) if last_seen else pd.NA,
            "channels": [int(c) for c in data.get("channels", []) if c is not None],
            "bands": [int(b) for b in data.get("bandNumbers", []) if b is not None and b > 0],
            "bandwidths": [float(bw) for bw in data.get("bandwidths", []) if bw is not None and bw > 0],
            "tower_type": data.get("towerAttributes", {}).get("TOWER_TYPE"),
            "has_timing_advance": 1 if any("LOC_TA" in k for k in data.get("towerAttributes", {}).keys()) else 0,
            "has_signal_strength": 1 if any("LOC_SS" in k for k in data.get("towerAttributes", {}).keys()) else 0,
        })

    return pd.DataFrame(records)


def deduplicate_radio_towers(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicates raw observations by grouping strictly on (rat, region_id, site_id).
    This fixes the regional scoping collision where distinct towers were collapsed.
    """
    grouped = df_raw.groupby(["rat", "region_id", "site_id"])
    towers = []

    for (rat, region_id, site_id), group in grouped:
        all_channels = sorted(list(set(c for sublist in group["channels"] for c in sublist)))
        all_bands = sorted(list(set(b for sublist in group["bands"] for b in sublist)))
        all_bws = [bw for sublist in group["bandwidths"] for bw in sublist]

        # Missing source bandwidth remains missing. It cannot be reconstructed
        # reliably from RAT, channel count, or a presumed spectrum allocation.
        tot_bw = sum(all_bws) if all_bws else np.nan

        valid_mcc = group["mcc"].dropna()
        mcc_val = valid_mcc.iloc[0] if not valid_mcc.empty else None

        valid_mnc = group["mnc"].dropna()
        mnc_val = valid_mnc.iloc[0] if not valid_mnc.empty else None

        valid_op = group["operator"].dropna()
        op_val = valid_op.iloc[0] if not valid_op.empty else None

        first_values = pd.to_numeric(group["first_seen_ms"], errors="coerce").dropna()
        last_values = pd.to_numeric(group["last_seen_ms"], errors="coerce").dropna()
        first_seen = int(first_values.min()) if not first_values.empty else pd.NA
        last_seen = int(last_values.max()) if not last_values.empty else pd.NA
        active_days = (
            round((last_seen - first_seen) / (1000 * 86400), 1)
            if pd.notna(first_seen) and pd.notna(last_seen)
            else np.nan
        )
        tower_types = group["tower_type"].dropna()
        visible_values = group["visible"].dropna()

        towers.append({
            "tower_id": len(towers) + 1,
            "rat": rat,
            "rat_subtype": group["rat_subtype"].iloc[-1],
            "region_id": region_id,
            "site_id": site_id,
            "mcc": mcc_val,
            "mnc": mnc_val,
            "raw_operator": op_val,
            "latitude": group["latitude"].median(),
            "longitude": group["longitude"].median(),
            "visible": bool(visible_values.any()) if not visible_values.empty else pd.NA,
            "first_seen_ms": first_seen,
            "last_seen_ms": last_seen,
            "active_days": max(0.0, active_days) if np.isfinite(active_days) else np.nan,
            "observation_count": len(group),
            "channels_str": ",".join(map(str, all_channels)),
            "channel_count": len(all_channels),
            "bands_str": ",".join(map(str, all_bands)),
            "band_count": len(all_bands),
            "primary_band": all_bands[0] if all_bands else np.nan,
            "total_bandwidth_mhz": round(float(tot_bw), 1) if np.isfinite(tot_bw) else np.nan,
            "bandwidth_data_available": bool(all_bws),
            "tower_type": tower_types.iloc[0] if not tower_types.empty else pd.NA,
            "tower_type_data_available": not tower_types.empty,
            "has_timing_advance": int(group["has_timing_advance"].max()),
            "has_signal_strength": int(group["has_signal_strength"].max()),
        })

    return pd.DataFrame(towers)


def attribute_source_operators(df_towers: pd.DataFrame) -> pd.DataFrame:
    """Map only explicit source operator or MNC evidence to operator names."""
    df = df_towers.copy()
    operator_list = []
    attribution_method = []
    for _, row in df.iterrows():
        if row["raw_operator"] in ["Libyana", "Al-Madar"]:
            operator_list.append(row["raw_operator"])
            attribution_method.append("source_record")
            continue
        operator = OPERATOR_BY_MNC.get(str(row["mnc"]).strip()) if pd.notna(row["mnc"]) else None
        if operator:
            operator_list.append(operator)
            attribution_method.append("mnc_code")
            continue
        operator_list.append("Unknown")
        attribution_method.append("unknown")

    df["operator"] = operator_list
    df["operator_attribution_method"] = attribution_method
    return df


def consolidate_physical_sites(
    df_towers: pd.DataFrame,
    threshold_m: float = COLLOCATION_DISTANCE_THRESHOLD_M
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Clusters radio antennas within threshold_m into consolidated Physical Sites.
    Returns:
    - df_towers: towers with physical_site_id and collocation distance assigned
    - df_sites: consolidated physical mast sites with multi-tech & multi-operator aggregations
    """
    towers = df_towers.copy()
    gdf_towers = gpd.GeoDataFrame(
        towers,
        geometry=[Point(lon, lat) for lon, lat in zip(towers["longitude"], towers["latitude"])],
        crs=CRS_WGS84
    ).to_crs(CRS_PROJECTED_LIBYA)

    coords = np.array([(pt.x, pt.y) for pt in gdf_towers.geometry])
    tree = cKDTree(coords)

    # Connected components clustering via KDTree
    visited = set()
    site_clusters: List[List[int]] = []

    for i in range(len(coords)):
        if i in visited:
            continue
        # Find all points within distance
        cluster = []
        queue = deque([i])
        visited.add(i)

        while queue:
            curr = queue.popleft()
            cluster.append(curr)
            neighbors = tree.query_ball_point(coords[curr], threshold_m)
            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    queue.append(n)
        site_clusters.append(cluster)

    # Assign physical_site_id to towers
    towers["physical_site_id"] = 0
    towers["collocated_distance_m"] = 0.0

    sites = []
    for site_idx, cluster in enumerate(site_clusters, start=1):
        indices = cluster
        towers.loc[indices, "physical_site_id"] = site_idx

        site_towers = towers.loc[indices]
        centroid_lat = site_towers["latitude"].mean()
        centroid_lon = site_towers["longitude"].mean()
        centroid_xy = coords[indices].mean(axis=0)

        # Compute distances to centroid
        for idx in indices:
            d_x = coords[idx, 0] - centroid_xy[0]
            d_y = coords[idx, 1] - centroid_xy[1]
            towers.loc[idx, "collocated_distance_m"] = round(float(np.sqrt(d_x**2 + d_y**2)), 2)

        rats = sorted(list(site_towers["rat"].unique()))
        subtypes = sorted(list(site_towers["rat_subtype"].unique()))
        all_ops = sorted(site_towers["operator"].dropna().unique())
        known_ops = [op for op in all_ops if op != "Unknown"]

        all_bands = sorted(list(set(
            int(b) for b_str in site_towers["bands_str"] if b_str for b in str(b_str).split(",") if b and b.isdigit()
        )))

        # Determine generation hierarchy (4G > 3G > 2G)
        max_gen = 4 if "LTE" in rats else (3 if "UMTS" in rats else 2)

        observed_tower_types = {
            str(value).upper() for value in site_towers["tower_type"].dropna()
            if str(value).strip()
        }
        has_ta = int(site_towers["has_timing_advance"].max())
        has_ss = int(site_towers["has_signal_strength"].max())

        sites.append({
            "physical_site_id": site_idx,
            "canonical_latitude": centroid_lat,
            "canonical_longitude": centroid_lon,
            "radio_tower_count": len(site_towers),
            "technologies": ",".join(rats),
            "rat_subtypes": ",".join(subtypes),
            "has_gsm": int("GSM" in rats),
            "has_umts": int("UMTS" in rats),
            "has_lte": int("LTE" in rats),
            "tech_count": len(rats),
            "max_generation": max_gen,
            "operators": ",".join(all_ops) if all_ops else "Unknown",
            "has_libyana": int("Libyana" in known_ops),
            "has_almadar": int("Al-Madar" in known_ops),
            "operator_count": len(known_ops),
            "has_unknown_operator": int((site_towers["operator"] == "Unknown").any()),
            "is_multi_operator": int(len(known_ops) > 1),
            "is_multi_tech": int(len(rats) > 1),
            "total_bandwidth_mhz": (
                round(float(site_towers["total_bandwidth_mhz"].sum(min_count=1)), 1)
                if site_towers["total_bandwidth_mhz"].notna().any() else np.nan
            ),
            "bandwidth_data_available": bool(site_towers["total_bandwidth_mhz"].notna().any()),
            "bandwidth_observation_count": int(site_towers["total_bandwidth_mhz"].notna().sum()),
            "total_carrier_count": int(site_towers["channel_count"].sum()),
            "bands_deployed": ",".join(map(str, all_bands)),
            "band_count": len(all_bands),
            "primary_tower_type": (
                "MACRO" if "MACRO" in observed_tower_types
                else "MICRO" if observed_tower_types == {"MICRO"}
                else "Unknown"
            ),
            "tower_type_data_available": bool(observed_tower_types),
            "is_visible": (
                bool(site_towers["visible"].dropna().any())
                if not site_towers["visible"].dropna().empty else pd.NA
            ),
            "first_seen_ms": (
                int(pd.to_numeric(site_towers["first_seen_ms"], errors="coerce").min())
                if pd.to_numeric(site_towers["first_seen_ms"], errors="coerce").notna().any()
                else pd.NA
            ),
            "last_seen_ms": (
                int(pd.to_numeric(site_towers["last_seen_ms"], errors="coerce").max())
                if pd.to_numeric(site_towers["last_seen_ms"], errors="coerce").notna().any()
                else pd.NA
            ),
            "has_timing_advance": has_ta,
            "has_signal_strength": has_ss,
        })

    df_sites = pd.DataFrame(sites)
    return towers, df_sites


def clean_pipeline() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Build the cleaned tower and physical-site inventory in memory."""
    print("Loading raw source records from SQLite...")
    df_raw = load_raw_records_from_sqlite()
    print(f"Loaded {len(df_raw)} raw observations.")

    print("Deduplicating radio towers using strictly scoped (rat, region_id, site_id)...")
    df_towers = deduplicate_radio_towers(df_raw)
    print(f"Identified {len(df_towers)} unique radio antenna towers.")

    print("Attributing operators only where the source provides operator or MNC evidence...")
    df_towers = attribute_source_operators(df_towers)

    print(f"Consolidating collocated antennas into Physical Sites (threshold: {COLLOCATION_DISTANCE_THRESHOLD_M}m)...")
    df_towers, df_sites = consolidate_physical_sites(df_towers, threshold_m=COLLOCATION_DISTANCE_THRESHOLD_M)
    print(f"Consolidated into {len(df_sites)} unique physical cell sites.")
    print(f"Multi-technology physical sites: {(df_sites['is_multi_tech'] == 1).sum()}")
    print(f"Multi-operator shared sites: {(df_sites['is_multi_operator'] == 1).sum()}")

    return df_towers, df_sites


if __name__ == "__main__":
    clean_pipeline()
