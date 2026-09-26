"""The screen pieces both assistants share, so they look and behave as one product.

Colours come from `.streamlit/config.toml`; the few rules below cover what a theme cannot:
the eyebrow line of the team's GIS page, Arabic messages running right to left, and the
orange limits note.
"""

import html
import json

import streamlit as st

from assistants import service_client
from assistants.llm import ToolCall, Turn

_CSS = """
<style>
.lg-eyebrow {
  margin: 0 0 -0.6rem 0;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.09em;
  color: #075a93;
}
/* Each paragraph takes its direction from its own text, so Arabic runs right to left and
   "5G" inside an Arabic sentence stays in place. */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stButton"] p,
textarea,
input {
  unicode-bidi: plaintext;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li {
  text-align: start;
}
/* The GIS page's 36px heading, one step smaller on a phone. */
h1 {
  font-size: 2.25rem !important;
}
@media (max-width: 640px) {
  h1 {
    font-size: 1.75rem !important;
  }
}
.lg-note {
  margin: 0.5rem 0 1rem 0;
  padding: 0.7rem 1rem;
  border-left: 4px solid #c35419;
  border-radius: 0 8px 8px 0;
  background: #fff6ed;
  font-size: 0.9rem;
}
</style>
"""


def page(product: str, title: str, lede: str, icon: str) -> None:
    """Page setup, the shared styles and the header: eyebrow, title and one-line lede."""
    st.set_page_config(page_title=f"{title} - Loop Gain", page_icon=icon, layout="centered")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<p class="lg-eyebrow">LOOP GAIN · {html.escape(product)}</p>', unsafe_allow_html=True
    )
    st.title(title)
    st.caption(lede)


def note(text: str) -> None:
    """The orange limits note of the GIS page, for what an answer cannot cover."""
    st.markdown(f'<div class="lg-note">{html.escape(text)}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=30, show_spinner=False)
def _health(base_url: str) -> dict:
    return service_client.health(base_url)


def service_status(base_url: str) -> None:
    """One line on whether the prepaid service answers, for the sidebar."""
    try:
        health = _health(base_url)
    except service_client.ServiceError:
        st.error(f"The prepaid service at {base_url} is not answering.", icon=":material/error:")
        return
    if health["status"] == "ok":
        st.success("Prepaid service: ok", icon=":material/check_circle:")
    else:
        problems = "; ".join(health.get("problems") or []) or "degraded"
        st.warning(f"Prepaid service: {problems}", icon=":material/warning:")


def sources(calls: list[ToolCall]) -> None:
    """What the answer was built from: every tool call and exactly what it returned."""
    if not calls:
        return
    with st.expander(f"What I looked up ({len(calls)})", icon=":material/fact_check:"):
        for call in calls:
            arguments = ", ".join(
                f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in call.arguments.items()
            )
            st.markdown(f"`{call.name}({arguments})`")
            st.json(call.result, expanded=False)


def assistant_message(turn: Turn) -> None:
    """One assistant reply with its sources, and a note when a safe answer replaced it."""
    with st.chat_message("assistant"):
        st.markdown(turn.reply)
        if turn.replaced_because:
            st.caption(f"Safe answer shown because {turn.replaced_because}.")
        sources(turn.calls)
