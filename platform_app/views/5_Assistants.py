"""Embeds assistants' own chatbot and copilot Streamlit apps - not a re-implementation.

Both call prepaid_churn's key-protected API from their own process, and the copilot
also reads the GIS release and network KPI files (assistants/src/assistants/sources.py);
this page only frames their existing, already-running UI.
"""

import streamlit as st
from _shared import unavailable
from _shared import CHATBOT_APP_URL, COPILOT_APP_URL, app_available, configure, groq_key_configured, hero

configure("AI Assistants", icon="support_agent")

hero(
    "AI Assistants",
    "The language model only picks a tool and phrases what came back - every package, "
    "price, offer, tower and site figure comes from the platform's own services and "
    "outputs, never from the prompt.",
    badges=["Grounded answers", "No LLM sets a price or offer", "Arabic & English"],
)


if not groq_key_configured():
    st.info(
        "Conversation is not configured yet. The employee copilot’s tower alerts and "
        "work orders remain available. Ask your platform administrator to enable conversation.",
        icon=":material/key:",
    )


def embed(url: str, name: str, command: str):
    if not app_available(url):
        unavailable(f"The {name} is offline", name)
        return
    st.link_button(f"Open the {name} full screen", url, icon=":material/open_in_new:")
    st.caption("Loading the assistant below. If it stays blank, try opening it full screen.")
    st.iframe(f"{url}/?embed=true&embed_options=light_theme", height=900)


chatbot_tab, copilot_tab = st.tabs([":material/chat: Customer chatbot", ":material/engineering: Employee copilot"])

with chatbot_tab:
    embed(CHATBOT_APP_URL, "chatbot", "uv run streamlit run chatbot_app.py --server.port 8503")

with copilot_tab:
    embed(COPILOT_APP_URL, "copilot", "uv run streamlit run copilot_app.py --server.port 8502")
