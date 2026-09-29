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

# Pilot City Configuration (H3 expansion-need analysis)
# Tripoli bbox covers the full Tripoli admin2 polygon (lon 13.07-13.60, lat 32.63-32.92)
# plus the western Janzour suburbs; the northern edge sits on the coastline.
PILOT_CITY_BBOXES = {
    "Tripoli": {"min_lat": 32.60, "max_lat": 32.95, "min_lon": 12.95, "max_lon": 13.65},
}
DEFAULT_PILOT_CITY = "Tripoli"

# H3 Planning Grid
H3_RESOLUTION = 8  # ~0.74 km^2 average hexagon area
H3_OUTPUT_DIR = CLEANED_DATA_DIR / "h3"
H3_GRID_GEOJSON_TEMPLATE = str(H3_OUTPUT_DIR / "h3_grid_{city}.geojson")
H3_FEATURE_TABLE_PARQUET_TEMPLATE = str(H3_OUTPUT_DIR / "h3_features_{city}.parquet")
H3_EXPANSION_SCORE_CSV_TEMPLATE = str(REPORTS_DIR / "h3_expansion_scores_{city}.csv")
H3_EXPANSION_SCORE_GEOJSON_TEMPLATE = str(REPORTS_DIR / "h3_expansion_scores_{city}.geojson")
H3_VALIDATION_JSON_TEMPLATE = str(REPORTS_DIR / "h3_validation_{city}.json")
H3_EXPANSION_MAP_HTML_TEMPLATE = str(REPORTS_DIR / "h3_expansion_map_{city}.html")

# Hexes that are mostly open water, or have no population and no road access,
# are excluded before scoring so they don't distort the normalization ranges.
H3_WATER_MASK_PCT = 50.0
H3_UNINHABITED_MAX_ROAD_DIST_M = 3000.0

# Phase 2 External Data Paths (buildings, land cover, OSM - Tripoli pilot)
BUILDINGS_DIR = EXTERNAL_DATA_DIR / "buildings"
MS_BUILDING_FOOTPRINTS_TILES = [
    BUILDINGS_DIR / "libya_122012230.csv.gz",
    BUILDINGS_DIR / "libya_122012231.csv.gz",
]
LANDCOVER_DIR = EXTERNAL_DATA_DIR / "landcover"
ESA_WORLDCOVER_TILES = [
    LANDCOVER_DIR / "ESA_WorldCover_10m_2021_v200_N30E012_Map.tif",
    LANDCOVER_DIR / "ESA_WorldCover_10m_2021_v200_N33E012_Map.tif",
]
OSM_DIR = EXTERNAL_DATA_DIR / "osm"
OSM_LIBYA_PBF = OSM_DIR / "libya-latest.osm.pbf"

# Integrated planning inputs. Raw downloads are deliberately excluded from Git.
ADMIN0_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin0.geojson"
WORLDCOVER_DIR = EXTERNAL_DATA_DIR / "worldcover_2021"
WORLDCOVER_EVALUATION_REPORT = REPORTS_DIR / "worldcover_integration.json"
OSM_BUILDINGS_DIR = EXTERNAL_DATA_DIR / "osm_libya_2026_09_19"
OSM_BUILDINGS_GPKG = OSM_BUILDINGS_DIR / "libya-260919-free.gpkg"
BUILDINGS_EVALUATION_REPORT = REPORTS_DIR / "buildings_integration.json"
OSM_CONTEXT_EVALUATION_REPORT = REPORTS_DIR / "osm_context_integration.json"
PLANNING_OUTPUT_DIR = REPORTS_DIR / "integrated_planning"
SOURCE_LOCK_PATH = MODULE_DIR / "sources" / "planning_sources.lock.json"

# Versioned reconciled inventory; legacy cleaned artifacts remain frozen.
INVENTORY_VERSION = "reconciled-geodesic-20260929-v1"
PLANNING_INVENTORY_DIR = DATA_DIR / "inventory_v3"
PLANNING_SITES_PATH = PLANNING_INVENTORY_DIR / "physical_sites.csv"
