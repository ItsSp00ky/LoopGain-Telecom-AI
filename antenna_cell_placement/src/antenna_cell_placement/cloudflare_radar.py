"""Regional digital-demand features derived from Cloudflare Radar data.

Radar measures Internet traffic observed by Cloudflare, not mobile-radio demand or
coverage.  Consequently these features are kept out of the suitability classifier
and are exposed as a bounded, independent prior for ranking otherwise suitable
deployment candidates.
"""

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from antenna_cell_placement.config import CLOUDFLARE_REGIONAL_FEATURES_PATH


# Cloudflare/GeoNames labels differ from the OCHA admin-2 names used by the project.
CLOUDFLARE_TO_OCHA_MUNICIPALITY = {
    "Tripoli": "Tripoli",
    "Banghazi": "Benghazi",
    "Misratah": "Misrata",
    "Sabha District": "Sebha",
    "Az Zawiyah": "Azzawya",
    "Al Jabal al Akhdar": "Al Jabal Al Akhdar",
    "Al Marqab": "Almargeb",
    "Al Butnan": "Tobruk",
    "An Nuqat al Khams": "Zwara",
    "Darnah": "Derna",
    "Jabal al Gharbi": "Al Jabal Al Gharbi",
    "Al Jafarah": "Aljfara",
    "Al Wahat": "Ejdabia",
    "Surt": "Sirt",
    "Al Marj": "Almarj",
    "Al Jufrah": "Aljufra",
    "Nalut": "Nalut",
    "Murzuq District": "Murzuq",
    "Wadi ash Shati'": "Wadi Ashshati",
    "Wadi al Hayat": "Ubari",
    "Al Kufrah": "Alkufra",
    "Ghat": "Ghat",
}

REQUIRED_COLUMNS = {
    "place_name",
    "http_requests_share_52w_pct",
    "digital_connectivity_index",
    "annual_stability_score_52w",
    "annual_traffic_growth_52w_pct",
}

OUTPUT_COLUMNS = [
    "cloudflare_http_requests_share_52w_pct",
    "cloudflare_digital_connectivity_index",
    "cloudflare_annual_stability_score_52w",
    "cloudflare_annual_traffic_growth_52w_pct",
    "cloudflare_regional_demand_score",
    "cloudflare_priority_factor",
    "cloudflare_data_available",
]


def load_regional_features(
    path: Path = CLOUDFLARE_REGIONAL_FEATURES_PATH,
) -> pd.DataFrame:
    """Load, validate, and map the 22 Radar locations to OCHA municipalities."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["municipality_name", *OUTPUT_COLUMNS])

    radar = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(radar.columns)
    if missing:
        raise ValueError(
            f"Cloudflare regional feature file is missing columns: {sorted(missing)}"
        )
    if radar["place_name"].duplicated().any():
        raise ValueError("Cloudflare regional feature file contains duplicate places")

    radar["municipality_name"] = radar["place_name"].map(
        CLOUDFLARE_TO_OCHA_MUNICIPALITY
    )
    unmapped = radar.loc[radar["municipality_name"].isna(), "place_name"].tolist()
    if unmapped:
        raise ValueError(f"Unmapped Cloudflare place names: {unmapped}")

    numeric_columns = REQUIRED_COLUMNS - {"place_name"}
    for column in numeric_columns:
        radar[column] = pd.to_numeric(radar[column], errors="coerce")
    if radar[list(numeric_columns)].isna().any().any():
        raise ValueError("Cloudflare regional features contain non-numeric values")
    if not np.isfinite(radar[list(numeric_columns)].to_numpy()).all():
        raise ValueError("Cloudflare regional features contain non-finite values")
    if (radar["http_requests_share_52w_pct"] < 0).any():
        raise ValueError("Cloudflare annual HTTP request shares cannot be negative")

    # Percentile scaling prevents Tripoli's 54% share from overwhelming local
    # population, terrain, accessibility, and coverage-gap evidence.
    radar["cloudflare_regional_demand_score"] = radar[
        "http_requests_share_52w_pct"
    ].rank(method="average", pct=True)
    radar["cloudflare_priority_factor"] = (
        0.9 + 0.2 * radar["cloudflare_regional_demand_score"]
    )
    radar["cloudflare_data_available"] = True

    radar = radar.rename(
        columns={
            "http_requests_share_52w_pct": "cloudflare_http_requests_share_52w_pct",
            "digital_connectivity_index": "cloudflare_digital_connectivity_index",
            "annual_stability_score_52w": "cloudflare_annual_stability_score_52w",
            "annual_traffic_growth_52w_pct": "cloudflare_annual_traffic_growth_52w_pct",
        }
    )
    return radar[["municipality_name", *OUTPUT_COLUMNS]].copy()


def add_regional_features(
    frame: pd.DataFrame,
    path: Path = CLOUDFLARE_REGIONAL_FEATURES_PATH,
    municipality_column: str = "municipality_name",
) -> pd.DataFrame:
    """Add Radar context to locations, using a neutral factor when unavailable."""
    if municipality_column not in frame.columns:
        raise KeyError(f"Missing municipality column: {municipality_column}")

    result = frame.drop(columns=OUTPUT_COLUMNS, errors="ignore").copy()
    radar = load_regional_features(path)
    if not radar.empty:
        join_table = radar.rename(columns={"municipality_name": municipality_column})
        result = result.merge(
            join_table,
            how="left",
            on=municipality_column,
            validate="many_to_one",
        )
        result.index = frame.index
    else:
        for column in OUTPUT_COLUMNS:
            result[column] = np.nan

    result["cloudflare_data_available"] = result[
        "cloudflare_data_available"
    ].fillna(False).astype(bool)
    result["cloudflare_regional_demand_score"] = result[
        "cloudflare_regional_demand_score"
    ].fillna(0.5)
    result["cloudflare_priority_factor"] = result[
        "cloudflare_priority_factor"
    ].fillna(1.0)
    return result
