"""The customer chatbot: the operator's packages, and the offer approved for the signed-in customer.

Run from this folder: `uv run streamlit run chatbot_app.py`; the keys come from `.env`.
It reads only the chatbot key, so it cannot reach a churn probability even by mistake.
"""

import os

import streamlit as st

from assistants import chatbot_tools, env, llm, ui

env.load()
BASE_URL = os.environ.get("PREPAID_CHURN_URL", "http://127.0.0.1:8000")
CHATBOT_KEY = os.environ.get("PREPAID_CHURN_CHATBOT_KEY", "")

EXAMPLES = [
    "شن أرخص باقة نت 5G؟",
    "Is there an offer for me today?",
    "نبي باقة فيها مكالمات",
    "Where is your nearest shop in Tripoli?",
]


def _new_conversation(subscriber: str) -> None:
    st.session_state.messages = []
    st.session_state.turns = []
    st.session_state.signed_in_as = subscriber


ui.page(
    "CUSTOMER ASSISTANT",
    "Packages and offers",
    "Ask which packages fit you, or whether there is an offer waiting for you.",
    ":material/support_agent:",
)

with st.sidebar:
    st.subheader("Signed in as")
    subscriber = st.text_input(
        "Subscriber ID",
        placeholder="for example 70016",
        help="The pseudonymous subscriber ID. In a real app this comes from the customer's login.",
    ).strip()
    ui.service_status(BASE_URL)
    st.subheader("Try asking")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending = example
    if st.button("New conversation", icon=":material/refresh:", width="stretch"):
        _new_conversation(subscriber)

# The conversation belongs to one customer: signing in as someone else starts a new one.
if st.session_state.get("signed_in_as") != subscriber or "messages" not in st.session_state:
    _new_conversation(subscriber)

missing = [
    name
    for name, value in (
        ("PREPAID_CHURN_CHATBOT_KEY", CHATBOT_KEY),
        ("GROQ_API_KEY", os.environ.get("GROQ_API_KEY")),
    )
    if not value
]
if missing:
    st.error(f"Set {' and '.join(missing)} before starting the chatbot.")
    st.stop()

ui.note(
    "Answers come only from the operator's catalogue and the offers it approved. "
    "For balance, bills or faults, contact the operator's customer service."
)

turns = iter(st.session_state.turns)
for message in st.session_state.messages:
    if message["role"] == "user":
        ui.user_message(message["content"])
    else:
        ui.assistant_message(next(turns))

prompt = st.chat_input("Ask about packages or offers") or st.session_state.pop("pending", None)
if prompt:
    ui.user_message(prompt)
    with st.spinner("Looking it up..."):
        turn = chatbot_tools.answer(
            prompt,
            st.session_state.messages,
            subscriber,
            BASE_URL,
            CHATBOT_KEY,
            llm.groq_complete(),
        )
    st.session_state.messages += [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": turn.reply},
    ]
    st.session_state.turns.append(turn)
    ui.assistant_message(turn)
