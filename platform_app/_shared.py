"""Shared config, theme and HTTP helpers for the unified platform shell.

Each backend (GIS, network KPI, churn) stays its own process on its own port - this
shell calls them over HTTP, the same way `assistants/chatbot_app.py` already calls
churn's API. Nothing here writes to any module's data; every page is read-only.
"""

import os
from pathlib import Path

import requests
import streamlit as st

GIS_API_URL = os.environ.get("PLATFORM_GIS_API_URL", "http://127.0.0.1:8001")
KPI_API_URL = os.environ.get("PLATFORM_KPI_API_URL", "http://127.0.0.1:8002")
CHURN_API_URL = os.environ.get("PLATFORM_CHURN_API_URL", "http://127.0.0.1:8000")
CHURN_APP_URL = os.environ.get("PLATFORM_CHURN_APP_URL", "http://127.0.0.1:8501")
CHATBOT_APP_URL = os.environ.get("PLATFORM_CHATBOT_APP_URL", "http://127.0.0.1:8503")
COPILOT_APP_URL = os.environ.get("PLATFORM_COPILOT_APP_URL", "http://127.0.0.1:8502")
ASSISTANTS_ENV = Path(__file__).resolve().parents[1] / "assistants" / ".env"


def env_setting(name: str) -> str:
    """A setting from the environment, else from assistants/.env (git-ignored).

    The same rule the assistants and run_platform.py use: the environment wins, so the
    shell sees the same keys however it was started.
    """
    if os.environ.get(name):
        return os.environ[name]
    if ASSISTANTS_ENV.exists():
        for line in ASSISTANTS_ENV.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return ""


CHURN_COPILOT_KEY = env_setting("PREPAID_CHURN_COPILOT_KEY")

LOGO = Path(__file__).resolve().parent / "static" / "logo.svg"

BRAND_CSS = """
<style>
:root {
    --lg-navy: #0b1f3a;
    --lg-blue: #1454a3;
    --lg-teal: #12b3a8;
    --lg-amber: #f0a63c;
    --lg-red: #e0533d;
    --lg-card: #ffffff;
    --lg-line: #e3e9f3;
    --lg-text: #16233b;
    --lg-muted: #5b6b85;
}
.block-container { padding-top: 2.2rem; max-width: 1320px; }

/* Bordered st.container() becomes the platform's card. */
[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stVerticalBlock"][class*="border"] {
    background: var(--lg-card);
    border-color: var(--lg-line) !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 10px rgba(16, 30, 54, 0.05);
}

[data-testid="stMetricLabel"] p { color: var(--lg-muted); font-weight: 600; font-size: 0.86rem; }
[data-testid="stMetricValue"] { color: var(--lg-navy); font-weight: 700; }

.lg-hero {
    background: linear-gradient(120deg, var(--lg-navy) 0%, var(--lg-blue) 100%);
    border-radius: 16px;
    padding: 1.7rem 2rem;
    color: white;
    margin-bottom: 1.2rem;
    box-shadow: 0 8px 24px rgba(11, 31, 58, 0.16);
}
.lg-hero h1 { color: white; margin: 0 0 0.3rem 0; font-size: 1.9rem; padding: 0; }
.lg-hero p { color: #cfe0f7; margin: 0; font-size: 0.98rem; max-width: 60rem; }
.lg-badge {
    display: inline-block; background: rgba(255,255,255,0.14); color: white;
    border-radius: 999px; padding: 0.18rem 0.7rem; font-size: 0.76rem;
    margin-right: 0.4rem; margin-top: 0.7rem;
}

.lg-pill {
    display: inline-block; border-radius: 999px; padding: 0.12rem 0.6rem;
    font-size: 0.74rem; font-weight: 700; letter-spacing: 0.02em;
}
.lg-pill-ok { background: #e3f8f0; color: #0a8f6c; }
.lg-pill-partial { background: #fdf1de; color: #a8680a; }
.lg-pill-down { background: #fbe6e6; color: #b3261e; }
.lg-muted { color: var(--lg-muted); font-size: 0.86rem; }

.lg-alert { display: flex; gap: 0.8rem; align-items: baseline; padding: 0.55rem 0;
            border-bottom: 1px solid var(--lg-line); }
.lg-alert:last-child { border-bottom: none; }
.lg-alert b { color: var(--lg-navy); font-size: 1.15rem; min-width: 4.5rem; display: inline-block; }
.lg-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; display: inline-block; flex: none; }
</style>
"""


def apply_brand():
    """Theme CSS and sidebar logo; called once per run by the Home.py router."""
    st.logo(str(LOGO), size="large")
    st.sidebar.markdown(BRAND_CSS, unsafe_allow_html=True)
    st.sidebar.caption("Team Loop Gain · SIC AI Capstone · read-only views over each module's own outputs")


def configure(title: str, icon: str = "satellite"):
    """Per-page title and wide layout, so a page also renders correctly on its own."""
    st.set_page_config(page_title=f"{title} · LoopGain Telecom AI", page_icon=f":material/{icon}:", layout="wide")


def hero(title: str, subtitle: str, badges: list[str] | None = None):
    badge_html = "".join(f'<span class="lg-badge">{b}</span>' for b in (badges or []))
    st.markdown(
        f'<div class="lg-hero"><h1>{title}</h1><p>{subtitle}</p>{badge_html}</div>',
        unsafe_allow_html=True,
    )


def status_pill(status: str, label: str | None = None) -> str:
    default, css = {
        "ok": ("Live", "lg-pill-ok"),
        "degraded": ("Partial", "lg-pill-partial"),
    }.get(status, ("Offline", "lg-pill-down"))
    return f'<span class="lg-pill {css}">{label or default}</span>'


@st.cache_data(ttl=30, show_spinner=False)
def get_json(base_url: str, path: str, timeout: float = 5.0, headers: tuple | None = None):
    """GET a JSON endpoint; return (data, error) so a page can degrade, not crash.

    Cached for 30 s so moving between pages doesn't refetch everything; `headers`
    is a tuple of pairs because cached arguments must be hashable.
    """
    try:
        response = requests.get(f"{base_url}{path}", timeout=timeout, headers=dict(headers or ()))
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as error:
        return None, str(error)


def service_status(base_url: str, path: str = "/health"):
    # GIS re-fingerprints every planning source (about 800 MB) per health check, which
    # takes a few seconds, so a short timeout would wrongly report it offline.
    data, error = get_json(base_url, path, timeout=20.0)
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
    return get_json(CHURN_API_URL, "/portfolio/summary", headers=(("X-API-Key", CHURN_COPILOT_KEY),))


def groq_key_configured() -> bool:
    """Whether the assistants will find a Groq key (checks presence only, never the value)."""
    return bool(env_setting("GROQ_API_KEY"))
