"""Coordinate assessment uses the same features and rules as batch planning."""
import json
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints


def assess_coordinate(lat, lon, operator='all', constraints=PlanningConstraints()):
    optimizer = CellSiteOptimizer(operator=operator)
    result = optimizer.evaluate_coordinates([float(lon)], [float(lat)], constraints)
    result = optimizer.extractor.add_context(result)
    # pandas JSON maps missing numeric/nullable context to JSON null.
    return json.loads(result.to_json(orient='records'))[0]


def predict_site_suitability(lat, lon, **kwargs):
    """Compatibility name: returns explainable assessment, not ML suitability."""
    return assess_coordinate(lat, lon, **kwargs)
