"""Embeds assistants' own chatbot and copilot Streamlit apps - not a re-implementation.

Both already call prepaid_churn's key-protected API directly, over HTTP, from their
own process; this page only frames their existing, already-running UI so a user
doesn't have to leave the platform shell to reach them.
"""

import streamlit as st
from _shared import CHATBOT_APP_URL, COPILOT_APP_URL, app_reachable, configure, hero

configure("Assistants", icon="support_agent")

hero(
    "Customer Chatbot & Employee Copilot",
    "The language model only picks a tool and phrases what came back - every "
    "package, price, offer and figure comes from the churn service, never the prompt.",
)

chatbot_tab, copilot_tab = st.tabs([":material/chat: Customer chatbot", ":material/engineering: Employee copilot"])

with chatbot_tab:
    if not app_reachable(CHATBOT_APP_URL):
        st.warning(
            f"The chatbot isn't reachable at {CHATBOT_APP_URL} yet. Start the full "
            "platform with the churn keys set (see assistants/README.md), or run it "
            "directly from `assistants/` with `uv run streamlit run chatbot_app.py "
            "--server.port 8503`."
        )
    else:
        st.iframe(CHATBOT_APP_URL, height=900)

with copilot_tab:
    if not app_reachable(COPILOT_APP_URL):
        st.warning(
            f"The copilot isn't reachable at {COPILOT_APP_URL} yet. Start the full "
            "platform with the churn keys set (see assistants/README.md), or run it "
            "directly from `assistants/` with `uv run streamlit run copilot_app.py "
            "--server.port 8502`."
        )
    else:
        st.iframe(COPILOT_APP_URL, height=900)
