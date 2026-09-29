"""Shared config and HTTP helpers for the unified platform shell.

Each backend (GIS, KPI, churn) stays its own process on its own port - this shell
calls them over HTTP, the same way `assistants/chatbot_app.py` already calls
churn's API. Nothing here writes to any module's data; every page is read-only.
"""

import os

import requests
import streamlit as st

GIS_API_URL = os.environ.get("PLATFORM_GIS_API_URL", "http://127.0.0.1:8001")
KPI_API_URL = os.environ.get("PLATFORM_KPI_API_URL", "http://127.0.0.1:8002")
CHURN_API_URL = os.environ.get("PLATFORM_CHURN_API_URL", "http://127.0.0.1:8000")
CHURN_APP_URL = os.environ.get("PLATFORM_CHURN_APP_URL", "http://127.0.0.1:8501")
CHATBOT_APP_URL = os.environ.get("PLATFORM_CHATBOT_APP_URL", "http://127.0.0.1:8503")
COPILOT_APP_URL = os.environ.get("PLATFORM_COPILOT_APP_URL", "http://127.0.0.1:8502")


def configure(title: str, icon: str = "satellite"):
    st.set_page_config(page_title=f"LoopGain Telecom AI - {title}", page_icon=":material/" + icon + ":", layout="wide")


def get_json(base_url: str, path: str, timeout: float = 5.0):
    """GET a JSON endpoint; return (data, error) so a page can degrade, not crash."""
    try:
        response = requests.get(f"{base_url}{path}", timeout=timeout)
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as error:
        return None, str(error)


def service_status(base_url: str, path: str = "/health"):
    data, error = get_json(base_url, path)
    if error:
        return "unreachable", error
    return data.get("status", "ok"), data
