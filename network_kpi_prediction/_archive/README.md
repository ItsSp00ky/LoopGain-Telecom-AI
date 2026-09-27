# Deprecated & Archived Telemetry Prediction Artifacts

This directory stores archived, legacy, and superseded files from earlier iterations of the `network_kpi_prediction` subsystem. They have been preserved for historical provenance and reference.

---

## Catalog of Archived Files

| Archived File | Original Location | Status & Deprecation Rationale | Superseded By |
| :--- | :--- | :--- | :--- |
| **`legacy_scripts/main.py`** | `network_kpi_prediction/main.py` | Legacy 11-line forwarding wrapper. | Unified root CLI orchestrator: [`run_pipeline.py`](file:///e:/NET-ML/network_kpi_prediction/run_pipeline.py) |
| **`legacy_scripts/predict.py`** | `cellular_kpi_forecast/predict.py` | Legacy 11-line forwarding alias for `run_inference.py`. | Cellular CLI: `python run_cellular.py predict` or root CLI: `python run_pipeline.py predict` |
| **`legacy_scripts/cellular_requirements.txt`** | `cellular_kpi_forecast/requirements.txt` | Sub-package duplicate requirements file. | Subsystem root: [`requirements.txt`](file:///e:/NET-ML/network_kpi_prediction/requirements.txt) |
| **`docs/MODEL_ARCHITECTURE_AND_SPLIT_SUMMARY.md`** | `network_kpi_prediction/docs/MODEL_ARCHITECTURE_AND_SPLIT_SUMMARY.md` | Interim technical report lacking ERBS physical node analytics and multivariate radio KPI integration. | Full production capstone documentation: [`FULL_TELEMETRY_EXPLOITATION_REPORT.md`](file:///e:/NET-ML/network_kpi_prediction/docs/FULL_TELEMETRY_EXPLOITATION_REPORT.md) |

---

## Active Pipeline Entry Points

For all active operations, execute through the primary orchestrators:
- Root Pipeline: `python network_kpi_prediction/run_pipeline.py [catalog|split|train|plot|predict|audit|inspect|traffic-multi|test]`
- 3GPP Cellular Engine: `python network_kpi_prediction/cellular_kpi_forecast/run_cellular.py [split|train|plot|predict|test]`
- 4G Traffic Volume Engine: `python network_kpi_prediction/traffic_volume_forecast/run_traffic.py [clean|split|train|multivariate|forecast|test]`
- ERBS Node Intelligence: `python network_kpi_prediction/erbs_node_analytics/run_erbs_analytics.py [audit|inspect]`
