"""
Configuration and constants for Antenna Cell Placement AI Module.
Samsung Innovation Campus (SIC) Capstone Project - Team Loop Gain.
"""

from pathlib import Path

# Base Paths
MODULE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = MODULE_DIR / "data"
EXTERNAL_DATA_DIR = DATA_DIR / "external"
CLEANED_DATA_DIR = DATA_DIR / "cleaned"
MODELS_DIR = MODULE_DIR / "models"
REPORTS_DIR = MODULE_DIR / "eval_reports"
RAW_DATA_DIR = MODULE_DIR / "Libyan_cells_dataset"

# Input Raw Data Files
RAW_SQLITE_PATH = RAW_DATA_DIR / "cells.sqlite3"
RAW_JSON_PATH = RAW_DATA_DIR / "cells.json"
RAW_GEOJSON_PATH = RAW_DATA_DIR / "cells.geojson"
OPENCELLID_RAW_PATH = DATA_DIR / "606.csv"
OPENCELLID_CLEANED_PATH = CLEANED_DATA_DIR / "opencellid_cells.csv"
OPENCELLID_REPORT_PATH = REPORTS_DIR / "opencellid_quality.json"
CLOUDFLARE_RADAR_DIR = DATA_DIR / "cloudflare_radar_libya"
CLOUDFLARE_REGIONAL_FEATURES_PATH = (
    CLOUDFLARE_RADAR_DIR / "libya_best_places_features_dataset.csv"
)
CLOUDFLARE_ASSESSMENT_PATH = REPORTS_DIR / "cloudflare_radar_assessment.json"

# External Data Paths
WORLDPOP_TIF_PATH = EXTERNAL_DATA_DIR / "lby_pd_2020_1km.tif"
DEM_RASTER_PATH = EXTERNAL_DATA_DIR / "dem" / "DEM" / "lyb_strm_250m"
ROADS_SHP_PATH = EXTERNAL_DATA_DIR / "roads" / "LYB_Roads.shp"
ADMIN1_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin1.geojson"
ADMIN2_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin2.geojson"
POP_PLACES_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_populatedplaces.geojson"

# Output Cleaned Files
CLEANED_RADIO_TOWERS_CSV = CLEANED_DATA_DIR / "cleaned_radio_towers.csv"
CLEANED_PHYSICAL_SITES_CSV = CLEANED_DATA_DIR / "cleaned_physical_sites.csv"
CLEANED_PHYSICAL_SITES_GEOJSON = CLEANED_DATA_DIR / "cleaned_physical_sites.geojson"
CLEANED_SITES_PARQUET = CLEANED_DATA_DIR / "cleaned_cells_combined.parquet"
CLEANED_MAP_HTML = CLEANED_DATA_DIR / "cleaned_cells_map.html"

# Model Artifacts
SUITABILITY_MODEL_PATH = MODELS_DIR / "cell_placement_suitability_model.joblib"
EQUIPMENT_MODEL_PATH = MODELS_DIR / "equipment_recommendation_model.joblib"
MODEL_METRICS_PATH = REPORTS_DIR / "model_benchmark.json"
RECOMMENDATIONS_CSV = REPORTS_DIR / "recommended_cell_placements.csv"

# Geographic Bounding Box for Libya
LIBYA_BBOX = {
    "min_lat": 19.5,
    "max_lat": 33.2,
    "min_lon": 9.3,
    "max_lon": 25.2,
}

# Coordinate Reference Systems
CRS_WGS84 = "EPSG:4326"
CRS_PROJECTED_LIBYA = "EPSG:32633"  # UTM Zone 33N (meters) for accurate spatial distance

# Clustering & Collocation Parameters
COLLOCATION_DISTANCE_THRESHOLD_M = 50.0  # meters within which antennas share a physical site

# Mobile Country & Network Codes for Libya
MCC_LIBYA = "606"
MNC_LIBYANA = "0"
MNC_ALMADAR = "1"

OPERATOR_NAMES = {
    ("606", "0"): "Libyana",
    ("606", "1"): "Al-Madar",
    ("606", "00"): "Libyana",
    ("606", "01"): "Al-Madar",
}
