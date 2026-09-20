"""
Data cleaning and consolidation pipeline for Libyan Cell Tower Dataset.
Resolves regional scoping collisions, deduplicates radio antennas,
imputes operators, and clusters antennas into Physical Sites.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree

from antenna_cell_placement.config import (
    RAW_SQLITE_PATH,
    CLEANED_RADIO_TOWERS_CSV,
    CLEANED_PHYSICAL_SITES_CSV,
    CLEANED_PHYSICAL_SITES_GEOJSON,
    COLLOCATION_DISTANCE_THRESHOLD_M,
    CRS_WGS84,
    CRS_PROJECTED_LIBYA,
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

        raw_mcc = data.get("mcc") or mcc
        raw_mnc = data.get("mnc") or mnc
        raw_operator = data.get("operator")

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
            "visible": bool(data.get("visible", False)),
            "first_seen_ms": int(data.get("firstseendate", 0) or 0),
            "last_seen_ms": int(data.get("lastseendate", 0) or 0),
            "channels": [int(c) for c in data.get("channels", []) if c is not None],
            "bands": [int(b) for b in data.get("bandNumbers", []) if b is not None and b > 0],
            "bandwidths": [float(bw) for bw in data.get("bandwidths", []) if bw is not None and bw > 0],
            "tower_type": str(data.get("towerAttributes", {}).get("TOWER_TYPE", "MACRO")),
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

        if all_bws:
            tot_bw = sum(all_bws)
        else:
            # Standard spectral bandwidth allocations in Libya:
            # LTE: 20MHz nominal (or 10MHz if Band 20 only)
            # UMTS: 5MHz nominal per carrier
            # GSM: 0.4MHz nominal (2x200kHz carriers)
            if rat == "LTE":
                tot_bw = 10.0 if (all_bands == [20]) else 20.0
            elif rat == "UMTS":
                tot_bw = 5.0 * max(1, len(all_channels))
            else:
                tot_bw = 0.4 * max(1, len(all_channels))

        valid_mcc = group["mcc"].dropna()
        mcc_val = valid_mcc.iloc[0] if not valid_mcc.empty else "606"

        valid_mnc = group["mnc"].dropna()
        mnc_val = valid_mnc.iloc[0] if not valid_mnc.empty else None

        valid_op = group["operator"].dropna()
        op_val = valid_op.iloc[0] if not valid_op.empty else None

        first_seen = group["first_seen_ms"].min()
        last_seen = group["last_seen_ms"].max()
        active_days = round((last_seen - first_seen) / (1000 * 86400), 1) if (last_seen and first_seen) else 0.0

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
            "visible": bool(group["visible"].any()),
            "first_seen_ms": int(first_seen),
            "last_seen_ms": int(last_seen),
            "active_days": max(0.0, active_days),
            "observation_count": len(group),
            "channels_str": ",".join(map(str, all_channels)),
            "channel_count": len(all_channels),
            "bands_str": ",".join(map(str, all_bands)),
            "band_count": len(all_bands),
            "primary_band": all_bands[0] if all_bands else (-1),
            "total_bandwidth_mhz": round(float(tot_bw), 1),
            "tower_type": group["tower_type"].iloc[0],
            "has_timing_advance": int(group["has_timing_advance"].max()),
            "has_signal_strength": int(group["has_signal_strength"].max()),
        })

    return pd.DataFrame(towers)


def impute_operators(df_towers: pd.DataFrame) -> pd.DataFrame:
    """
    Impute operator (Libyana vs Al-Madar) using:
    1. Source MCC/MNC (606 0 -> Libyana, 606 1 -> Al-Madar)
    2. Spatial collocation with known 2G/3G sites
    3. Region ID taxonomy and carrier channel signatures
    """
    df = df_towers.copy()
    operator_list = []
    attribution_method = []

    # Identify known towers
    known_libyana_indices = set(df[(df["mnc"] == "0") | (df["raw_operator"] == "Libyana")].index)
    known_madar_indices = set(df[(df["mnc"] == "1") | (df["raw_operator"] == "Al-Madar")].index)

    # Build spatial index for known towers
    gdf_all = gpd.GeoDataFrame(
        df,
        geometry=[Point(lon, lat) for lon, lat in zip(df["longitude"], df["latitude"])],
        crs=CRS_WGS84
    ).to_crs(CRS_PROJECTED_LIBYA)

    known_lib_coords = np.array([(pt.x, pt.y) for pt in gdf_all.loc[list(known_libyana_indices), "geometry"]])
    known_mad_coords = np.array([(pt.x, pt.y) for pt in gdf_all.loc[list(known_madar_indices), "geometry"]])

    tree_lib = cKDTree(known_lib_coords) if len(known_lib_coords) > 0 else None
    tree_mad = cKDTree(known_mad_coords) if len(known_mad_coords) > 0 else None

    # Al-Madar characteristic low-number region IDs in Libya CellMapper data
    almadar_region_ids = {"0", "1", "2", "3", "4", "5", "6", "8", "10", "14"}

    for idx, row in df.iterrows():
        # Case 1: Explicitly given
        if row["raw_operator"] in ["Libyana", "Al-Madar"]:
            operator_list.append(row["raw_operator"])
            attribution_method.append("source_record")
            continue
        if row["mnc"] == "0":
            operator_list.append("Libyana")
            attribution_method.append("mnc_code")
            continue
        if row["mnc"] == "1":
            operator_list.append("Al-Madar")
            attribution_method.append("mnc_code")
            continue

        # Case 2: LTE tower without explicit MNC
        pt = gdf_all.loc[idx, "geometry"]
        dist_lib, _ = tree_lib.query([pt.x, pt.y]) if tree_lib else (999999, -1)
        dist_mad, _ = tree_mad.query([pt.x, pt.y]) if tree_mad else (999999, -1)

        # Collocation within 100m
        if dist_lib < 100 and dist_lib < dist_mad:
            operator_list.append("Libyana")
            attribution_method.append("spatial_collocation_libyana")
            continue
        if dist_mad < 100 and dist_mad < dist_lib:
            operator_list.append("Al-Madar")
            attribution_method.append("spatial_collocation_almadar")
            continue

        # Heuristic based on region ID and channels
        reg = str(row["region_id"]).strip()
        channels = [int(c) for c in str(row["channels_str"]).split(",") if c]

        if reg in almadar_region_ids:
            operator_list.append("Al-Madar")
            attribution_method.append("region_taxonomy_almadar")
        elif 1400 in channels:
            operator_list.append("Libyana")
            attribution_method.append("exclusive_earfcn_1400")
        else:
            # Libyana standard high-range TAC numbering
            operator_list.append("Libyana")
            attribution_method.append("region_taxonomy_libyana")

    df["operator"] = operator_list
    df["operator_attribution_method"] = attribution_method
    df["mnc"] = df["operator"].map({"Libyana": "0", "Al-Madar": "1"})

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
        queue = [i]
        visited.add(i)

        while queue:
            curr = queue.pop(0)
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

        # Compute distances to centroid
        for idx in indices:
            d_x = coords[idx, 0] - coords[cluster[0], 0]
            d_y = coords[idx, 1] - coords[cluster[0], 1]
            towers.loc[idx, "collocated_distance_m"] = round(float(np.sqrt(d_x**2 + d_y**2)), 2)

        rats = sorted(list(site_towers["rat"].unique()))
        subtypes = sorted(list(site_towers["rat_subtype"].unique()))
        ops = sorted(list(site_towers["operator"].unique()))

        all_bands = sorted(list(set(
            int(b) for b_str in site_towers["bands_str"] if b_str for b in str(b_str).split(",") if b and b.isdigit()
        )))

        # Determine generation hierarchy (4G > 3G > 2G)
        max_gen = 4 if "LTE" in rats else (3 if "UMTS" in rats else 2)

        has_macro = any(site_towers["tower_type"].str.upper() == "MACRO")
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
            "operators": ",".join(ops),
            "has_libyana": int("Libyana" in ops),
            "has_almadar": int("Al-Madar" in ops),
            "operator_count": len(ops),
            "is_multi_operator": int(len(ops) > 1),
            "is_multi_tech": int(len(rats) > 1),
            "total_bandwidth_mhz": round(float(site_towers["total_bandwidth_mhz"].sum()), 1),
            "total_carrier_count": int(site_towers["channel_count"].sum()),
            "bands_deployed": ",".join(map(str, all_bands)),
            "band_count": len(all_bands),
            "primary_tower_type": "MACRO" if has_macro else "MICRO",
            "is_visible": int(site_towers["visible"].any()),
            "first_seen_ms": int(site_towers["first_seen_ms"].min()),
            "last_seen_ms": int(site_towers["last_seen_ms"].max()),
            "has_timing_advance": has_ta,
            "has_signal_strength": has_ss,
        })

    df_sites = pd.DataFrame(sites)
    return towers, df_sites


def export_cleaned_datasets(
    df_towers: pd.DataFrame,
    df_sites: pd.DataFrame,
    output_dir: Path = CLEANED_RADIO_TOWERS_CSV.parent
) -> Dict[str, Path]:
    """Export cleaned data to CSV and GeoJSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save CSVs
    towers_path = output_dir / "cleaned_radio_towers.csv"
    sites_path = output_dir / "cleaned_physical_sites.csv"
    geojson_path = output_dir / "cleaned_physical_sites.geojson"

    df_towers.to_csv(towers_path, index=False)
    df_sites.to_csv(sites_path, index=False)

    # Create GeoJSON FeatureCollection
    gdf_sites = gpd.GeoDataFrame(
        df_sites,
        geometry=[Point(lon, lat) for lon, lat in zip(df_sites["canonical_longitude"], df_sites["canonical_latitude"])],
        crs=CRS_WGS84
    )
    gdf_sites.to_file(geojson_path, driver="GeoJSON")

    return {
        "towers_csv": towers_path,
        "sites_csv": sites_path,
        "sites_geojson": geojson_path,
    }


def clean_pipeline() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Execute the full data cleaning and consolidation pipeline."""
    print("Loading raw source records from SQLite...")
    df_raw = load_raw_records_from_sqlite()
    print(f"Loaded {len(df_raw)} raw observations.")

    print("Deduplicating radio towers using strictly scoped (rat, region_id, site_id)...")
    df_towers = deduplicate_radio_towers(df_raw)
    print(f"Identified {len(df_towers)} unique radio antenna towers.")

    print("Imputing operators (Libyana vs Al-Madar) via spatial collocation and region taxonomy...")
    df_towers = impute_operators(df_towers)

    print(f"Consolidating collocated antennas into Physical Sites (threshold: {COLLOCATION_DISTANCE_THRESHOLD_M}m)...")
    df_towers, df_sites = consolidate_physical_sites(df_towers, threshold_m=COLLOCATION_DISTANCE_THRESHOLD_M)
    print(f"Consolidated into {len(df_sites)} unique physical cell sites.")
    print(f"Multi-technology physical sites: {(df_sites['is_multi_tech'] == 1).sum()}")
    print(f"Multi-operator shared sites: {(df_sites['is_multi_operator'] == 1).sum()}")

    print("Exporting cleaned datasets...")
    exported = export_cleaned_datasets(df_towers, df_sites)
    for k, p in exported.items():
        print(f"  - {k}: {p}")

    from antenna_cell_placement.config import OPENCELLID_RAW_PATH
    if OPENCELLID_RAW_PATH.exists():
        from antenna_cell_placement.opencellid import import_pipeline
        import_pipeline()

    return df_towers, df_sites


if __name__ == "__main__":
    clean_pipeline()
