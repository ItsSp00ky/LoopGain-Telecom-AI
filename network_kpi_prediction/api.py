"""Read-only HTTP service over this module's traffic and per-band KPI pipelines.

Matches the GIS/churn API pattern: a thin FastAPI wrapper over existing pipeline
code and outputs, never a reimplementation.

- Traffic volume (`/traffic/...`): runs `traffic_volume_forecast`'s real
  clean -> chronological split -> benchmark -> retrain -> forecast pipeline live
  (under 2 seconds), cached per horizon. It serves the traffic-history-only model:
  the all-KPI exogenous variant (`run_traffic.py enriched`) did not beat it on
  held-out data once a same-day leak was fixed, so it isn't the default here.
- Every network KPI (`/kpis/...`): the 10 KPIs x 6 bands from the per-band carrier
  export. `/kpis/status` reports the latest observed values against each KPI's SLA
  straight from the raw data. Forecasts and their scorecard come from a completed
  `cellular_kpi_forecast/run_cellular.py train` run (about 80 seconds for all 60
  series, so it's a batch step like GIS's planning run, not per request). Every
  forecast carries `beats_naive`: whether that series' own held-out MASE is below 1.
  Only 21 of the 60 are, so a forecast without it should be read as a trend sketch,
  not a prediction.

- Congestion and traffic steering (`/steering/...`, `/towers/...`): serves the
  committed outputs of the sibling `traffic_steering_son/` module and the per-tower
  XGBoost forecasts of `tower_kpi_forecast/` that it consumes. Both cover the
  forecaster's backtest window (next-day predictions over held-out days), so the
  recommendations are "what would have been recommended on each day", not live
  orders. `Predicted_QoE_Boost` is a formula assuming a cell's capacity is shared
  equally among its users, not a measurement.

`erbs_node_analytics` (per-tower ST-GNN) is not wired up here yet.
"""

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

_MODULE_DIR = Path(__file__).resolve().parent
_TRAFFIC_PKG = _MODULE_DIR / "traffic_volume_forecast"
if str(_TRAFFIC_PKG) not in sys.path:
    sys.path.insert(0, str(_TRAFFIC_PKG))

from run_traffic import run_clean_stage, run_train_stage  # noqa: E402
from src.data_cleaning import resolve_raw_traffic_file  # noqa: E402

# Both pipelines name their package `src`, so the cellular config is loaded by path
# under its own name instead of `src.kpi_config` (which would resolve to traffic's).
_spec = importlib.util.spec_from_file_location(
    "cellular_kpi_config", _MODULE_DIR / "cellular_kpi_forecast" / "src" / "kpi_config.py"
)
kpi_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kpi_config)

CARRIER_CSV = _MODULE_DIR / "data" / "carrier_earfcndl_kpi_daily.csv"
CELLULAR_OUTPUT = _MODULE_DIR / "cellular_kpi_forecast" / "data" / "output"
METRICS_CSV = CELLULAR_OUTPUT / "model_metrics.csv"
FORECAST_CSV = CELLULAR_OUTPUT / "carrier_kpi_forecast_2026_2027.csv"
CELLULAR_RUN_HINT = "run `python run_cellular.py train` from network_kpi_prediction/cellular_kpi_forecast"

_REPO = _MODULE_DIR.parent
STEERING_OUTPUTS = _REPO / "traffic_steering_son" / "outputs"
ALERTS_CSV = STEERING_OUTPUTS / "congestion_alerts_summary.csv"
RECOMMENDATIONS_CSV = STEERING_OUTPUTS / "traffic_steering_recommendations.csv"
CLUSTERS_CSV = STEERING_OUTPUTS / "cluster_capacity_breakdown.csv"
TOWER_PREDICTIONS_CSV = _REPO / "tower_kpi_forecast" / "forecasts" / "tower_level_forecast_predictions.csv"
TOWER_KPIS = {
    "connected_users": "Avg RRC Connected users",
    "dl_throughput_mbps": "E-UTRAN IP Throughput UE DL",
    "availability_pct": "4G Cell Av. (%)",
    "erab_drop_rate": "E-RAB Drop Rate",
}
STEERING_RUN_HINT = "run `python src/run_traffic_steering.py` from traffic_steering_son"
_frames: dict = {}

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


def _records(frame: pd.DataFrame) -> list[dict]:
    # to_json maps NaN to null; the JSON response itself refuses NaN.
    return json.loads(frame.to_json(orient="records"))


def _observed() -> pd.DataFrame:
    """The raw per-band export with KPI columns renamed to the pipeline's own keys."""
    if not CARRIER_CSV.exists():
        raise HTTPException(503, f"Carrier KPI export not found at {CARRIER_CSV}")
    frame = pd.read_csv(CARRIER_CSV).rename(columns=kpi_config.RAW_COLUMN_TO_KPI_MAP)
    return frame.rename(columns={"Date": "date", "earfcndl": "band"})


def _sla_value(kpi: str, value: float, band: int) -> float:
    """The value the SLA is defined on.

    Downtime is recorded as a cluster total (cell-seconds summed over every cell in
    the band), while its SLA is per cell, so it's divided by the band's cell count.
    Every other KPI is already a rate or per-user value.
    """
    if kpi == "downtime_sec":
        return value / kpi_config.CARRIER_CLUSTER_CELLS[band]
    return value


def _scorecard() -> pd.DataFrame:
    if not METRICS_CSV.exists():
        raise HTTPException(503, f"No per-band KPI forecast run yet: {CELLULAR_RUN_HINT}")
    metrics = pd.read_csv(METRICS_CSV)
    metrics["beats_naive"] = metrics["test_mase"] < 1
    return metrics


def _check(band: int, kpi: str):
    if band not in kpi_config.CARRIER_BANDS:
        raise HTTPException(404, f"Unknown band {band}; known: {kpi_config.CARRIER_BANDS}")
    if kpi not in kpi_config.KPI_KEYS:
        raise HTTPException(404, f"Unknown KPI {kpi}; known: {kpi_config.KPI_KEYS}")


@app.get("/health")
def health():
    raw_path = resolve_raw_traffic_file()
    return {
        "status": "ok" if raw_path.exists() and CARRIER_CSV.exists() else "degraded",
        "raw_data_path": str(raw_path),
        "carrier_kpis_available": CARRIER_CSV.exists(),
        "kpi_forecast_run_available": METRICS_CSV.exists() and FORECAST_CSV.exists(),
    }


@app.get("/traffic/{horizon_days}day")
def traffic_forecast(horizon_days: int):
    if horizon_days not in (7, 14, 30, 60, 90):
        raise HTTPException(422, "horizon_days must be one of 7, 14, 30, 60, 90")
    try:
        result = _run_forecast(horizon_days)
    except FileNotFoundError as error:
        raise HTTPException(503, f"Raw traffic data not available: {error}") from error
    return result


@app.get("/kpis/catalog")
def kpi_catalog():
    """Every KPI with its unit, 3GPP category and SLA, and every band."""
    return {
        "kpis": [
            {
                "key": key,
                "name": meta["name"],
                "unit": meta["unit"],
                "category": meta["category"],
                "description": meta["desc"],
                "sla_target": meta["sla_target"],
                "sla_op": meta["sla_op"],
                "sla_description": meta["sla_desc"],
            }
            for key, meta in kpi_config.KPI_CONFIG.items()
        ],
        "bands": [
            {"band": band, "name": kpi_config.CARRIER_BAND_NAMES[band],
             "cells": kpi_config.CARRIER_CLUSTER_CELLS[band]}
            for band in kpi_config.CARRIER_BANDS
        ],
    }


@app.get("/kpis/status")
def kpi_status():
    """Latest observed value of every KPI on every band, checked against its SLA."""
    observed = _observed()
    rows = []
    for band, group in observed.groupby("band"):
        latest = group.sort_values("date").iloc[-1]
        for kpi in kpi_config.KPI_KEYS:
            value = latest.get(kpi)
            if pd.isna(value):
                rows.append({"band": int(band), "kpi": kpi, "date": latest["date"],
                             "value": None, "sla_value": None, "sla_met": None})
                continue
            sla_value = _sla_value(kpi, float(value), int(band))
            rows.append({
                "band": int(band), "kpi": kpi, "date": latest["date"],
                "value": float(value), "sla_value": sla_value,
                "sla_met": bool(kpi_config.check_sla_compliance(sla_value, kpi)),
            })
    breaches = sum(1 for row in rows if row["sla_met"] is False)
    return {"as_of": observed["date"].max(), "breaches": breaches, "checked": len(rows), "status": rows}


@app.get("/kpis/scorecard")
def kpi_scorecard():
    """Held-out accuracy of every band x KPI forecast, and whether it beats naive."""
    metrics = _scorecard()
    return {
        "series": len(metrics),
        "beat_naive": int(metrics["beats_naive"].sum()),
        "scorecard": _records(metrics),
    }


@app.get("/kpis/forecast/{band}/{kpi}")
def kpi_forecast(band: int, kpi: str, days: int = Query(30, ge=1, le=365), history_days: int = Query(90, ge=0, le=365)):
    """One band's forecast for one KPI, with its recent history and its own trust flag."""
    _check(band, kpi)
    metrics = _scorecard()
    if not FORECAST_CSV.exists():
        raise HTTPException(503, f"No per-band KPI forecast run yet: {CELLULAR_RUN_HINT}")

    row = metrics[(metrics["carrier"] == band) & (metrics["kpi"] == kpi)]
    if row.empty:
        raise HTTPException(404, f"The forecast run has no model for band {band} / {kpi}")
    row = row.iloc[0]

    forecast = pd.read_csv(FORECAST_CSV)
    forecast = forecast[forecast["carrier_freq"] == band].sort_values("date").head(days)
    forecast = forecast[["date", kpi, f"{kpi}_p05", f"{kpi}_p95"]].rename(
        columns={kpi: "value", f"{kpi}_p05": "p05", f"{kpi}_p95": "p95"}
    )
    breach_days = int(sum(
        not kpi_config.check_sla_compliance(_sla_value(kpi, value, band), kpi)
        for value in forecast["value"]
    ))

    observed = _observed()
    history = observed[observed["band"] == band].sort_values("date").tail(history_days)
    history = history[["date", kpi]].rename(columns={kpi: "value"})

    return {
        "band": band,
        "kpi": kpi,
        "model": row["best_model"],
        "test_mase": float(row["test_mase"]),
        "test_r2": float(row["test_r2_bench"]),
        "beats_naive": bool(row["beats_naive"]),
        "forecast_breach_days": breach_days,
        "history": _records(history),
        "forecast": _records(forecast),
    }


def _frame(path: Path, hint: str) -> pd.DataFrame:
    """Read a committed output once per file version; these are tens of thousands of rows."""
    if not path.exists():
        raise HTTPException(503, f"{path.name} not found: {hint}")
    key = (path, path.stat().st_mtime)
    if key not in _frames:
        _frames[key] = pd.read_csv(path)
    return _frames[key]


@app.get("/steering/summary")
def steering_summary():
    """Congestion alerts and steering recommendations over the backtest window."""
    alerts = _frame(ALERTS_CSV, STEERING_RUN_HINT)
    recs = _frame(RECOMMENDATIONS_CSV, STEERING_RUN_HINT)
    latest = alerts["Date"].max()
    today = alerts[alerts["Date"] == latest]
    return {
        "window_start": alerts["Date"].min(),
        "window_end": latest,
        # The alerts file holds only HIGH and CRITICAL rows, so this is towers that
        # were alerted at least once, not every tower.
        "towers_with_alerts": int(alerts["ERBS Id"].nunique()),
        "alerts_by_category": alerts["Congestion_Category"].value_counts().to_dict(),
        "recommendations_by_priority": recs["Priority"].value_counts().to_dict(),
        "latest_day": {
            "alerts_by_category": today["Congestion_Category"].value_counts().to_dict(),
            "recommendations": int((recs["Date"] == latest).sum()),
        },
    }


@app.get("/steering/recommendations")
def steering_recommendations(
    date: str | None = Query(None, description="YYYY-MM-DD; defaults to the latest day"),
    priority: str | None = Query(None, pattern="^(HIGH|MEDIUM|LOW)$"),
    limit: int = Query(100, ge=1, le=1000),
):
    """CIO handover-offset recommendations for one day, highest risk first."""
    recs = _frame(RECOMMENDATIONS_CSV, STEERING_RUN_HINT)
    day = date or recs["Date"].max()
    rows = recs[recs["Date"] == day]
    if priority:
        rows = rows[rows["Priority"] == priority]
    total = len(rows)
    rows = rows.sort_values("Risk_Score", ascending=False).head(limit)
    return {"date": day, "total": total, "count": len(rows), "recommendations": _records(rows)}


@app.get("/steering/clusters")
def steering_clusters():
    """Per-cluster capacity: towers, load, speed, congestion risk and spare headroom."""
    clusters = _frame(CLUSTERS_CSV, STEERING_RUN_HINT)
    return {"clusters": _records(clusters.sort_values("Avg_Congestion_Risk", ascending=False))}


@app.get("/towers/{tower_id}/forecast")
def tower_forecast(tower_id: str):
    """One tower's next-day predictions against what actually happened, per KPI."""
    preds = _frame(TOWER_PREDICTIONS_CSV, "run `python src/train_and_evaluate.py` from tower_kpi_forecast")
    rows = preds[preds["ERBS Id"] == tower_id].sort_values("Date")
    if rows.empty:
        raise HTTPException(404, f"No predictions for tower {tower_id}")
    series = {}
    for key, column in TOWER_KPIS.items():
        frame = rows[["Date", f"{column} (Actual)", f"{column} (Predicted)"]]
        series[key] = _records(frame.set_axis(["date", "actual", "predicted"], axis=1))
    return {"tower": tower_id, "series": series}
