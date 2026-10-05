"""Small, read-only projection of the Overview's five metrics for the Android home.

Uses the same service URLs and server-side copilot key as the Streamlit shell.
No subscriber rows, credentials, model computation or write operations are exposed.
Run: uvicorn mobile_summary:app --port 8511 (from platform_app).
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import math
import os

import requests
from fastapi import FastAPI, Response

app = FastAPI(title="LoopGain Mobile Summary", docs_url=None, redoc_url=None)
SPECS = (
    ("kpi", "KPI SLA breaches", "network"),
    ("steering", "Critical towers", "steering"),
    ("traffic", "4G traffic forecast", "network"),
    ("gis", "Candidate sites", "gis"),
    ("churn", "Revenue at risk", "churn"),
)

def setting(name, default=""):
    if os.environ.get(name):
        return os.environ[name]
    env_file = Path(__file__).resolve().parents[1] / "assistants" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return default

def fetch(base, path, headers=None, timeout=5):
    try:
        response = requests.get(base.rstrip("/") + path, headers=headers or {}, timeout=(3, timeout))
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else None
    except (requests.RequestException, ValueError):
        # Never forward a request exception: it can contain hosts or credentials.
        return None

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Missing or invalid numeric evidence")
    return value

def build_summary(sources):
    cards, attention = [], []
    for key, label, route in SPECS:
        card = dict(id=key, label=label, route=route, available=False, value="—", note="Data unavailable", source_date=None)
        data = sources.get(key)
        try:
            if not isinstance(data, dict):
                raise ValueError("Unavailable source")
            if key == "kpi":
                breaches, checked = number(data["breaches"]), number(data["checked"])
                if not checked or breaches > checked:
                    raise ValueError("Invalid SLA count")
                date = str(data["as_of"])
                card.update(value=f"{breaches:,.0f} / {checked:,.0f}", note=f"Latest observations · {date}", source_date=date)
                if breaches:
                    attention.append(dict(title="Review KPI breaches", note=f"{breaches:,.0f} of {checked:,.0f} readings breach SLA · {date}", route=route))
            elif key == "steering":
                latest = data["latest_day"]
                critical = number(latest["alerts_by_category"].get("CRITICAL", 0))
                proposals = number(latest["recommendations"])
                date = str(data["window_end"])
                card.update(value=f"{critical:,.0f}", note=f"Backtest · {date} · {proposals:,.0f} proposals", source_date=date)
                if critical:
                    attention.append(dict(title="Review congestion", note=f"{critical:,.0f} critical towers in the backtest. Proposed changes need review.", route=route))
            elif key == "traffic":
                first = data["forecast"][0]
                value = number(first["predicted_kpi_volume_gb"])
                date = str(first["date"])
                card.update(value=f"{value / 1e6:,.2f} PB", note=f"Forecast for {date}", source_date=date)
            elif key == "gis":
                features = data["features"]
                if not isinstance(features, list):
                    raise ValueError("Invalid shortlist")
                card.update(value=f"{len(features):,}", note="Planning priorities for engineering review")
                if features:
                    attention.append(dict(title="Review planning priorities", note=f"{len(features):,} candidate sites await engineering review. Coverage improvement is not verified.", route=route))
            else:
                bands = data["by_risk_band"]
                if not bands:
                    raise ValueError("Missing risk values")
                risk = sum(number(b["lyd_at_risk"]) for b in bands)
                subscribers = number(data["subscribers"])
                card.update(value=f"{risk / 1000:,.0f}k LYD", note=f"Probability-weighted 12-month value · {subscribers:,.0f} subscribers")
                high = next((b for b in bands if b.get("name") == "high"), None)
                if high and number(high["customers"]):
                    attention.append(dict(title="Review retention priorities", note=f"{number(high['customers']):,.0f} subscribers are in the high-risk band.", route=route))
            card["available"] = True
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            # One missing/malformed source must not hide the other four cards.
            card.update(available=False, value="—", note="Data unavailable", source_date=None)
        cards.append(card)
    available = sum(card["available"] for card in cards)
    return dict(schema_version=1, fetched_at=datetime.now(timezone.utc).isoformat(), available=available,
                total=len(cards), cards=cards, attention=attention)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/dashboard/summary")
def dashboard_summary(response: Response):
    kpi = setting("PLATFORM_KPI_API_URL", "http://127.0.0.1:8002")
    gis = setting("PLATFORM_GIS_API_URL", "http://127.0.0.1:8001")
    churn = setting("PLATFORM_CHURN_API_URL", "http://127.0.0.1:8000")
    key = setting("PREPAID_CHURN_COPILOT_KEY")
    jobs = {
        "kpi": (kpi, "/kpis/status", None, 5),
        "steering": (kpi, "/steering/summary", None, 15),
        "traffic": (kpi, "/traffic/30day", None, 30),
        "gis": (gis, "/shortlist", None, 5),
    }
    if key:
        jobs["churn"] = (churn, "/portfolio/summary", {"X-API-Key": key}, 5)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {name: pool.submit(fetch, *args) for name, args in jobs.items()}
        sources = {name: future.result() for name, future in futures.items()}
    response.headers["Cache-Control"] = "no-store"
    return build_summary(sources)
