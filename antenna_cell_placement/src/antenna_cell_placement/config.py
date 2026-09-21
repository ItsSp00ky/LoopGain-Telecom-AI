"""Paths and constants for the Libya telecom GIS planning package."""

from pathlib import Path

# Base Paths
MODULE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = MODULE_DIR / "data"
EXTERNAL_DATA_DIR = DATA_DIR / "external"
REPORTS_DIR = MODULE_DIR / "eval_reports"
RAW_DATA_DIR = MODULE_DIR / "Libyan_cells_dataset"

# Input Raw Data Files
RAW_SQLITE_PATH = RAW_DATA_DIR / "cells.sqlite3"
OPENCELLID_RAW_PATH = DATA_DIR / "606.csv"
CLOUDFLARE_RADAR_DIR = DATA_DIR / "cloudflare_radar_libya"
CLOUDFLARE_REGIONAL_FEATURES_PATH = (
    CLOUDFLARE_RADAR_DIR / "libya_best_places_features_dataset.csv"
)

# External Data Paths
WORLDPOP_TIF_PATH = EXTERNAL_DATA_DIR / "lby_pd_2020_1km.tif"
WORLDCOVER_DIR = EXTERNAL_DATA_DIR / "worldcover_2021"
OSM_BUILDINGS_DIR = EXTERNAL_DATA_DIR / "osm_libya_2026_09_19"
OSM_BUILDINGS_GPKG = OSM_BUILDINGS_DIR / "libya-260919-free.gpkg"
OSM_HEIGHT_PBF = OSM_BUILDINGS_DIR / "libya-260919.osm.pbf"
OSM_HEIGHT_MANIFEST = OSM_BUILDINGS_DIR / "height_manifest.json"
OOKLA_DIR = EXTERNAL_DATA_DIR / "ookla_mobile_2025q2_2026q1"
OOKLA_TILES_GPKG = OOKLA_DIR / "libya_mobile_performance_tiles.gpkg"
OOKLA_MANIFEST = OOKLA_DIR / "manifest.json"
VIIRS_DIR = EXTERNAL_DATA_DIR / "viirs_nightlights_2024"
VIIRS_MANIFEST = VIIRS_DIR / "manifest.json"
VIIRS_FLARES_CSV = VIIRS_DIR / "libya_gas_flares_2024.csv"
DEM_RASTER_PATH = EXTERNAL_DATA_DIR / "dem" / "DEM" / "lyb_strm_250m"
ROADS_SHP_PATH = EXTERNAL_DATA_DIR / "roads" / "LYB_Roads.shp"
ADMIN1_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin1.geojson"
ADMIN0_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin0.geojson"
ADMIN2_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_admin2.geojson"
POP_PLACES_GEOJSON_PATH = EXTERNAL_DATA_DIR / "admin_boundaries" / "lby_populatedplaces.geojson"

# Retained artifacts are proposed placements, their visualization, and compact
# gate evidence. Large intermediate tables are built in memory.
RECOMMENDATIONS_CSV = REPORTS_DIR / "recommended_cell_placements.csv"
RECOMMENDATIONS_GEOJSON = REPORTS_DIR / "recommended_cell_placements.geojson"
RECOMMENDATIONS_MAP_HTML = REPORTS_DIR / "libya_cell_coverage_map.html"
H3_EVALUATION_REPORT = REPORTS_DIR / "step_07_h3_evaluation.json"
WORLDCOVER_EVALUATION_REPORT = REPORTS_DIR / "step_08_worldcover_evaluation.json"
BUILDINGS_EVALUATION_REPORT = REPORTS_DIR / "step_09_buildings_evaluation.json"
BUILDING_HEIGHT_EVALUATION_REPORT = REPORTS_DIR / "step_10_building_height_evaluation.json"
OSM_CONTEXT_EVALUATION_REPORT = REPORTS_DIR / "step_11_osm_context_evaluation.json"
OOKLA_EVALUATION_REPORT = REPORTS_DIR / "step_12_ookla_evaluation.json"
VIIRS_EVALUATION_REPORT = REPORTS_DIR / "step_13_viirs_evaluation.json"

# Coordinate Reference Systems
CRS_WGS84 = "EPSG:4326"
CRS_PROJECTED_LIBYA = "EPSG:32633"  # UTM Zone 33N (meters) for accurate spatial distance

# Clustering & Collocation Parameters
COLLOCATION_DISTANCE_THRESHOLD_M = 50.0  # meters within which antennas share a physical site

# Operator names are assigned only when an input explicitly supplies one of
# these MNC representations. Missing MNCs remain unknown.
OPERATOR_BY_MNC = {
    "0": "Libyana",
    "00": "Libyana",
    "1": "Al-Madar",
    "01": "Al-Madar",
}
