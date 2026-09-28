"""The employee copilot: tower alerts, the GIS shortlist and customers at risk, with sources.

Run from this folder: `uv run streamlit run copilot_app.py --server.port 8502`; the keys come
from `.env`. It reads only the copilot key. The one thing it saves is a work order, and only
when a named employee presses Confirm: the model can draft one, never save it.
"""

import os

import pandas as pd
import streamlit as st

from assistants import copilot_tools, env, llm, network, sources, ui, work_orders
from assistants.grounding import mask_phone_numbers

env.load()
BASE_URL = os.environ.get("PREPAID_CHURN_URL", "http://127.0.0.1:8000")
COPILOT_KEY = os.environ.get("PREPAID_CHURN_COPILOT_KEY", "")

EXAMPLES = [
    "Which towers need attention today?",
    "شن المشكلة في البرج NT952M1؟",
    "Where should we build the next sites in Tripoli, and why?",
    "How much revenue is at risk from customers leaving?",
]

LEVEL_LABELS = {"critical": "🔴 critical", "major": "🟠 major", "warning": "🟡 warning"}


def _new_conversation() -> None:
    st.session_state.messages = []
    st.session_state.turns = []


def _add_draft(order: dict) -> None:
    st.session_state.drafts.append(order)


def _drop_draft(draft_id: str) -> None:
    st.session_state.drafts = [d for d in st.session_state.drafts if d["draft_id"] != draft_id]


ui.page(
    "EMPLOYEE COPILOT",
    "Network and customer copilot",
    "Tower alerts, planning priorities and customers at risk, every answer with its sources.",
    ":material/cell_tower:",
)

if "messages" not in st.session_state:
    _new_conversation()
st.session_state.setdefault("drafts", [])

with st.sidebar:
    st.subheader("Signed in as")
    employee = st.text_input(
        "Your name",
        placeholder="for example Taha",
        help="Saved with every work order you confirm. In a real app this comes from the login.",
    ).strip()
    ui.service_status(BASE_URL)
    st.subheader("Try asking")
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            st.session_state.pending = example
    if st.button("New conversation", icon=":material/refresh:", width="stretch"):
        _new_conversation()

orders = work_orders.load(sources.WORK_ORDERS)
open_orders = {order["tower"] for order in orders if order["status"] == "open"}

# The alerts come from code, not from the model, so they show before anyone asks.
try:
    found = network.find_alerts(network.load_towers(sources.TOWER_KPIS))
except (OSError, ValueError, KeyError) as error:
    found = None
    st.error(f"The tower data could not be read: {error}", icon=":material/error:")

if found:
    counts = found["counts"]
    attention = [a for a in found["alerts"] if a["level"] in copilot_tools.ATTENTION]
    headline = (
        f"{counts['critical']} critical and {counts['major']} major tower alerts "
        f"on {found['data_date']}, the latest day in the network data."
    )
    if counts["critical"]:
        st.error(headline, icon=":material/cell_tower:")
        # Once per visit, a pop-up that shows wherever the page is scrolled.
        if not st.session_state.get("alerted"):
            st.session_state.alerted = True
            st.toast(
                f"{counts['critical']} towers are critical on {found['data_date']}.",
                icon=":material/cell_tower:",
            )
    elif counts["major"]:
        st.warning(headline, icon=":material/cell_tower:")
    else:
        st.success(
            f"No critical or major tower alerts on {found['data_date']}.",
            icon=":material/cell_tower:",
        )
    with st.expander(
        f"Tower alerts ({len(attention)} need attention, {counts['warning']} warnings)",
        icon=":material/notifications_active:",
    ):
        show_warnings = st.toggle("Show warnings too")
        rows = found["alerts"] if show_warnings else attention
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Tower": a["tower"],
                        "Level": LEVEL_LABELS[a["level"]],
                        "What crossed its limit": a["short"],
                        "Work order": "open" if a["tower"] in open_orders else "",
                    }
                    for a in rows
                ],
                columns=["Tower", "Level", "What crossed its limit", "Work order"],
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Tower": st.column_config.TextColumn(width="small"),
                "Level": st.column_config.TextColumn(width="small"),
                "What crossed its limit": st.column_config.TextColumn(width="large"),
                "Work order": st.column_config.TextColumn(width="small"),
            },
        )
        st.caption(
            "Critical: availability below 50%, or up but carrying under a quarter of its usual "
            "users. Major: a KPI past its severe limit. Warning: a KPI past the network team's "
            "target, or no report that day. Setup is connection setup success, session is data "
            "session setup success. Ask the copilot about a tower for its targets and last 7 days."
        )
        if rows:
            left, right = st.columns(2)
            tower = left.selectbox("Tower", [a["tower"] for a in rows])
            action = right.selectbox(
                "Action", list(work_orders.ACTIONS), format_func=work_orders.ACTIONS.get
            )
            if st.button("Draft a work order", icon=":material/edit_note:"):
                alert = next(a for a in rows if a["tower"] == tower)
                _add_draft(work_orders.draft(alert, tower, action, found["data_date"]))

with st.expander(f"Work orders ({len(orders)})", icon=":material/assignment:"):
    if not orders:
        st.caption("No work orders yet. Confirmed drafts appear here.")
    for order in orders:
        st.markdown(
            f"**{order['tower']}** · {order['action_label']} · {order['status']}  \n"
            f"Confirmed by {order['confirmed_by']} at {order['confirmed_at']}"
            + (f" · {order['note']}" if order["note"] else "")
        )

ui.note(
    "Answers come from the network team's daily tower KPIs, the GIS team's release and the "
    "prepaid churn service. The copilot never acts: it drafts, and you confirm."
)

turns = iter(st.session_state.turns)
for message in st.session_state.messages:
    if message["role"] == "user":
        ui.user_message(message["content"])
    else:
        ui.assistant_message(next(turns))

for order in list(st.session_state.drafts):
    key = order["draft_id"]
    with st.container(border=True):
        st.markdown(f"**Work order draft: {order['tower']}**")
        st.caption(
            f"Alert level: {order['alert_level'] or 'no alert'} · data of {order['data_date']} "
            "· not saved yet"
        )
        if order["problems"]:
            st.markdown("\n".join(f"- {problem}" for problem in order["problems"]))
        chosen = st.selectbox(
            "Action",
            list(work_orders.ACTIONS),
            index=list(work_orders.ACTIONS).index(order["action"]),
            format_func=work_orders.ACTIONS.get,
            key=f"action-{key}",
        )
        note = st.text_input("Note (optional)", key=f"note-{key}")
        left, right = st.columns(2)
        if left.button(
            "Confirm",
            key=f"confirm-{key}",
            type="primary",
            icon=":material/check:",
            disabled=not employee,
            width="stretch",
        ):
            final = {**order, "action": chosen, "action_label": work_orders.ACTIONS[chosen]}
            work_orders.confirm(final, employee, note, sources.WORK_ORDERS)
            _drop_draft(key)
            st.toast(f"Work order for {order['tower']} saved.", icon=":material/check:")
            st.rerun()
        if right.button("Discard", key=f"discard-{key}", width="stretch"):
            _drop_draft(key)
            st.rerun()
        if not employee:
            st.caption("Type your name in the sidebar to confirm.")

missing = [
    name
    for name, value in (
        ("PREPAID_CHURN_COPILOT_KEY", COPILOT_KEY),
        ("GROQ_API_KEY", os.environ.get("GROQ_API_KEY")),
    )
    if not value
]
if missing:
    st.error(f"Set {' and '.join(missing)} in .env to ask the copilot questions.")
    st.stop()

prompt = st.chat_input("Ask about towers, sites or customers") or st.session_state.pop(
    "pending", None
)
if prompt:
    # A phone number is neither kept in the conversation nor sent to the model.
    prompt = mask_phone_numbers(prompt)
    ui.user_message(prompt)
    with st.spinner("Looking it up..."):
        turn = copilot_tools.answer(
            prompt,
            st.session_state.messages,
            BASE_URL,
            COPILOT_KEY,
            llm.groq_complete(),
            _add_draft,
            open_orders,
        )
    st.session_state.messages += [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": turn.reply},
    ]
    st.session_state.turns.append(turn)
    # Run the page again so a draft from this turn shows in its place, under the reply.
    st.rerun()
