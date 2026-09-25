"""
AI Antenna Cell Placement Optimization Package.
Team Loop Gain - Samsung Innovation Campus (SIC) Capstone Project.
"""

from antenna_cell_placement.config import (
    RAW_SQLITE_PATH,
    CLEANED_PHYSICAL_SITES_CSV,
    CLEANED_SITES_PARQUET,
    SUITABILITY_MODEL_PATH,
    EQUIPMENT_MODEL_PATH,
    RECOMMENDATIONS_CSV,
)
# Lazy compatibility exports: importing the public planner never imports ML.
_EXPORTS = {
    'clean_pipeline': 'data_cleaning',
    'GeospatialFeatureExtractor': 'feature_engineering',
    'enrich_physical_sites_pipeline': 'feature_engineering',
    'train_all_models_pipeline': 'placement_model',
    'SUITABILITY_FEATURE_COLS': 'placement_model',
    'CellSiteOptimizer': 'site_optimizer',
    'run_optimizer_pipeline': 'site_optimizer',
    'generate_interactive_map': 'map_visualizer',
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    value = getattr(import_module('antenna_cell_placement.' + _EXPORTS[name]), name)
    globals()[name] = value
    return value

__all__ = [
    "clean_pipeline",
    "GeospatialFeatureExtractor",
    "enrich_physical_sites_pipeline",
    "train_all_models_pipeline",
    "CellSiteOptimizer",
    "run_optimizer_pipeline",
    "generate_interactive_map",
    "SUITABILITY_FEATURE_COLS",
]
