"""Embeds assistants' own chatbot and copilot Streamlit apps - not a re-implementation.

Both call prepaid_churn's key-protected API from their own process, and the copilot
also reads the GIS release and network KPI files (assistants/src/assistants/sources.py);
this page only frames their existing, already-running UI.
"""

import os
from pathlib import Path

import streamlit as st
from _shared import CHATBOT_APP_URL, COPILOT_APP_URL, app_reachable, configure, hero

configure("AI Assistants", icon="support_agent")

hero(
    "Customer Chatbot & Employee Copilot",
    "The language model only picks a tool and phrases what came back - every package, "
    "price, offer, tower and site figure comes from the platform's own services and "
    "outputs, never from the prompt.",
    badges=["Grounded answers", "No LLM sets a price or offer", "Arabic & English"],
)


def groq_key_configured() -> bool:
    """Whether the assistants will find a Groq key: their process env or assistants/.env.

    Checks only that a non-empty value is set; the value itself is never read out.
    """
    if os.environ.get("GROQ_API_KEY"):
        return True
    env_file = Path(__file__).resolve().parents[2] / "assistants" / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "GROQ_API_KEY":
            return bool(value.strip().strip('"').strip("'"))
    return False


if not groq_key_configured():
    st.info(
        "**Conversation is switched off on this machine.** Both assistants use Groq's API "
        "to understand questions, and no `GROQ_API_KEY` is set (neither in the environment "
        "nor in `assistants/.env`). The chatbot shows a setup message until one is added; "
        "the copilot's tower alerts and work orders still work without it. "
        "See `assistants/README.md` to add a key.",
        icon=":material/key:",
    )


def embed(url: str, name: str, command: str):
    if not app_reachable(url):
        st.warning(
            f"The {name} isn't reachable at {url} yet. Start the full platform with the "
            f"churn keys set (see assistants/README.md), or run it directly from "
            f"`assistants/` with `{command}`."
        )
        return
    st.link_button(f"Open the {name} full screen", url, icon=":material/open_in_new:")
    st.iframe(f"{url}/?embed=true&embed_options=light_theme", height=900)


chatbot_tab, copilot_tab = st.tabs([":material/chat: Customer chatbot", ":material/engineering: Employee copilot"])

with chatbot_tab:
    embed(CHATBOT_APP_URL, "chatbot", "uv run streamlit run chatbot_app.py --server.port 8503")

with copilot_tab:
    embed(COPILOT_APP_URL, "copilot", "uv run streamlit run copilot_app.py --server.port 8502")
