"""Shared config, theme and HTTP helpers for the unified platform shell.

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
CHURN_COPILOT_KEY = os.environ.get("PREPAID_CHURN_COPILOT_KEY", "")

BRAND_CSS = """
<style>
:root {
    --lg-navy: #0b1f3a;
    --lg-blue: #1454a3;
    --lg-teal: #12b3a8;
    --lg-amber: #f0a63c;
    --lg-bg: #f4f7fb;
    --lg-card: #ffffff;
    --lg-text: #16233b;
}
.stApp { background: var(--lg-bg); }
[data-testid="stSidebar"] {
    background: var(--lg-navy);
}
[data-testid="stSidebar"] * { color: #dce6f5 !important; }
[data-testid="stSidebar"] a { color: #9fd6ff !important; }

.lg-hero {
    background: linear-gradient(120deg, var(--lg-navy) 0%, var(--lg-blue) 100%);
    border-radius: 16px;
    padding: 2rem 2.25rem;
    color: white;
    margin-bottom: 1.5rem;
    box-shadow: 0 8px 24px rgba(11, 31, 58, 0.18);
}
.lg-hero h1 { color: white; margin: 0 0 0.25rem 0; font-size: 2.1rem; }
.lg-hero p { color: #cfe0f7; margin: 0; font-size: 1.02rem; }
.lg-badge {
    display: inline-block; background: rgba(255,255,255,0.14); color: white;
    border-radius: 999px; padding: 0.2rem 0.75rem; font-size: 0.78rem;
    margin-right: 0.4rem; margin-top: 0.6rem; letter-spacing: 0.02em;
}

.lg-card {
    background: var(--lg-card); border-radius: 14px; padding: 1.25rem 1.4rem;
    box-shadow: 0 2px 10px rgba(16, 30, 54, 0.06); border: 1px solid #e7edf6;
    height: 100%;
}
.lg-card h3 { margin: 0 0 0.35rem 0; font-size: 1.05rem; color: var(--lg-text); }
.lg-card p.lg-desc { color: #55647e; font-size: 0.88rem; margin-bottom: 0.75rem; }
.lg-pill {
    display: inline-block; border-radius: 999px; padding: 0.15rem 0.65rem;
    font-size: 0.76rem; font-weight: 600; letter-spacing: 0.02em;
}
.lg-pill-ok { background: #e3f8f0; color: #0a8f6c; }
.lg-pill-degraded { background: #fdf1de; color: #b5720b; }
.lg-pill-down { background: #fbe6e6; color: #b3261e; }

.lg-metric-row [data-testid="stMetric"] {
    background: var(--lg-card); border-radius: 12px; padding: 0.9rem 1rem;
    border: 1px solid #e7edf6; box-shadow: 0 2px 8px rgba(16, 30, 54, 0.05);
}
</style>
"""


def configure(title: str, icon: str = "satellite"):
    st.set_page_config(page_title=f"LoopGain Telecom AI - {title}", page_icon=":material/" + icon + ":", layout="wide")
    st.markdown(BRAND_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, badges: list[str] | None = None):
    badge_html = "".join(f'<span class="lg-badge">{b}</span>' for b in (badges or []))
    st.markdown(
        f"""
        <div class="lg-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_pill(status: str) -> str:
    label, css = {
        "ok": ("Live", "lg-pill-ok"),
        "degraded": ("Degraded", "lg-pill-degraded"),
    }.get(status, ("Offline", "lg-pill-down"))
    return f'<span class="lg-pill {css}">{label}</span>'


def get_json(base_url: str, path: str, timeout: float = 5.0, headers: dict | None = None):
    """GET a JSON endpoint; return (data, error) so a page can degrade, not crash."""
    try:
        response = requests.get(f"{base_url}{path}", timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as error:
        return None, str(error)


def service_status(base_url: str, path: str = "/health"):
    data, error = get_json(base_url, path)
    if error:
        return "unreachable", error
    return data.get("status", "ok"), data


def app_reachable(base_url: str, timeout: float = 3.0) -> bool:
    """Whether a plain Streamlit app (no JSON /health) answers at all."""
    try:
        requests.get(base_url, timeout=timeout).raise_for_status()
        return True
    except requests.RequestException:
        return False


def churn_portfolio():
    """The copilot-scoped portfolio summary, or (None, reason) if unavailable.

    Needs PREPAID_CHURN_COPILOT_KEY set to the same value churn's API was started
    with (see assistants/README.md) - without it this degrades to a clear message,
    never a guess at the numbers.
    """
    if not CHURN_COPILOT_KEY:
        return None, "PREPAID_CHURN_COPILOT_KEY is not set for this shell"
    data, error = get_json(CHURN_API_URL, "/portfolio/summary", headers={"X-API-Key": CHURN_COPILOT_KEY})
    if error:
        return None, error
    return data, None
