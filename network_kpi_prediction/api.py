"""Read-only HTTP service over the 4G traffic volume forecast pipeline.

Matches the GIS/churn API pattern: a thin FastAPI wrapper that calls the existing
pipeline functions (`run_clean_stage`, `run_train_stage` in
`traffic_volume_forecast/run_traffic.py`) rather than reimplementing them. The
clean+train+forecast pipeline finishes in under 2 seconds on the shipped dataset
(165 train / 35 val / 36 test days, honest chronological split - see
`run_train_stage`), so this API runs it directly instead of requiring a
separately-scheduled batch job the way GIS's H3+rooftop run does.

Of the three pipelines this module ships (cellular_kpi_forecast, erbs_node_analytics,
traffic_volume_forecast), only traffic_volume_forecast is wired up here. It is the
lightest and fastest of the three and is enough for the platform's KPI page in this
pass; wrapping the other two is future work, not something this file claims to do.
"""

import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException

_TRAFFIC_PKG = Path(__file__).resolve().parent / "traffic_volume_forecast"
if str(_TRAFFIC_PKG) not in sys.path:
    sys.path.insert(0, str(_TRAFFIC_PKG))

from run_traffic import run_clean_stage, run_train_stage  # noqa: E402
from src.data_cleaning import resolve_raw_traffic_file  # noqa: E402

app = FastAPI(title="Network KPI Forecast API", description=__doc__)

_lock = threading.Lock()
_cache = {}


def _run_forecast(horizon_days: int = 30):
    """Run the real pipeline once per horizon and cache the result in memory.

    Not persisted to disk: the champion model and forecast are cheap enough here
    (~2s) that re-running per process start is simpler than a cache-invalidation
    story, unlike GIS's H3+rooftop run which is genuinely too slow to redo on
    every request.
    """
    with _lock:
        if horizon_days not in _cache:
            run_clean_stage()
            result = run_train_stage(horizon_days=horizon_days)
            _cache[horizon_days] = {
                "champion_model": result["champion_name"],
                "test_metrics": {
                    key: float(value) for key, value in result["final_metrics"].items()
                },
                "forecast": result["forecast_df"].assign(
                    date=lambda frame: frame["date"].dt.strftime("%Y-%m-%d")
                ).to_dict("records"),
            }
        return _cache[horizon_days]


@app.get("/health")
def health():
    raw_path = resolve_raw_traffic_file()
    return {"status": "ok" if raw_path.exists() else "degraded", "raw_data_path": str(raw_path)}


@app.get("/traffic/{horizon_days}day")
def traffic_forecast(horizon_days: int):
    if horizon_days not in (7, 14, 30, 60, 90):
        raise HTTPException(422, "horizon_days must be one of 7, 14, 30, 60, 90")
    try:
        result = _run_forecast(horizon_days)
    except FileNotFoundError as error:
        raise HTTPException(503, f"Raw traffic data not available: {error}") from error
    return result
