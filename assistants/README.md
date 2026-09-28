# Loop Gain assistants

The two conversational parts of the Loop Gain platform, in one project with one look:

- **Customer chatbot** (`chatbot_app.py`): which of the operator's packages fit a customer, and whether the operator approved an offer for them.
  Built with Ali, whose chatbot role is in the action plan.
- **Employee copilot** (`copilot_app.py`): alerts for towers in trouble, the GIS team's ranked sites and customers at risk, answered with sources; it drafts work orders that only an employee can confirm.

Both follow the same rule: the language model only picks a tool and phrases what came back.
Every package, price, offer and figure comes from the prepaid service or a teammate's published output, and code, not the prompt, stops anything else from reaching the reader.
The reasons are in decisions 54 (both) and 55 (the copilot) of [../prepaid_churn/docs/decisions.md](../prepaid_churn/docs/decisions.md).

## Run the chatbot

The settings live in `.env` in this folder, which is git-ignored, so they survive a new terminal.
Copy `.env.example` to `.env` once and fill it in: your Groq key, and two long random keys for the prepaid service.
A variable already set in the terminal wins over the file.

The chatbot talks to the prepaid service, so start that first, from `prepaid_churn/`, with the same two service keys in its environment (it does not read this folder's `.env`):

```bash
export PREPAID_CHURN_CHATBOT_KEY="<the chatbot key from .env>"
export PREPAID_CHURN_COPILOT_KEY="<the copilot key from .env>"
uv run churn serve --campaign-dir artifacts/campaigns/ui-2026-09-22-200
```

Then, from this folder:

```bash
uv sync
uv run streamlit run chatbot_app.py
```

On Windows PowerShell, set a variable with `$env:NAME = "..."` instead of `export`.
In campaign `ui-2026-09-22-200`, subscriber `70016` has an approved offer and every other subscriber has none.

## What the chatbot can and cannot do

| It can | Through | Guard in code |
|---|---|---|
| Find packages ("the cheapest 5G", "the 10 with the most data") | `find_packages` over `GET /catalogue` | Filtering and sorting are done in Python, so the model never compares prices; 5 packages by default, up to 10 on request, with the total that matched and the order used |
| Say whether the operator approved an offer for the signed-in customer | `my_offer` over `GET /subscribers/{id}/retention` | The tool takes no arguments: the ID comes from the sign-in, is never sent to Groq, and cannot be swapped for another customer's; without a sign-in the tool is not offered at all; the customer hears the service's customer message, never the policy's reason (decision 51) |
| Find one of the operator's shops | `find_service_point` | Waiting for the service-point list; until then it says the locations are not available |

It never sees a churn probability: the chatbot key is refused on the copilot's endpoints (403).
Every reply is checked before it is shown:

- A number that no tool returned and the customer did not write replaces the reply with a safe answer built only from the tool results (`grounding.py`).
- A reply holding a Libyan phone number is replaced the same way, even when the customer typed it.
- A tool error, an unreachable service, or Groq being down or rate-limited gives "not available right now", never a guess.

Under each reply, "What I looked up" shows every tool call and exactly what it returned.
Tool results come in the customer's language only, detected from their message, and the model is told which language to reply in.
A data volume or "unlimited" is given only when the service's `volume_source` says the operator states it (decision 52), and the chatbot never names the operator (decision 45).

## Run the copilot

With the prepaid service running as above, from this folder:

```bash
uv run streamlit run copilot_app.py --server.port 8502
```

It reads `PREPAID_CHURN_COPILOT_KEY` and `GROQ_API_KEY` from `.env`.
The tower alerts and the work orders work without either key; only the questions need them.
Type your name in the sidebar before confirming a work order: it is saved with the order.

## What the copilot can and cannot do

| It can | Through | Reads |
|---|---|---|
| Alert on towers in trouble, worst first | `tower_alerts`, and the alert panel on the page | Maher's daily tower KPIs |
| Explain one tower: every KPI against its limits, and its last 7 days | `tower_status` | the same file |
| Sum up the network: alert counts, network KPIs, 4G traffic | `network_overview` | the tower file, the network KPIs, the traffic volume |
| Say where to build next in Tripoli, and why | `expansion_priorities`, `explain_location` | the GIS release |
| Give customers and LYD at risk, or one subscriber's risk | `portfolio_summary`, `subscriber_risk` | the prepaid service, copilot key |
| Draft a work order for a tower | `draft_work_order` | nothing; it saves nothing |

**It cannot act alone.**
A draft appears under the conversation, or from the alert panel's "Draft a work order".
The employee can change the action or add a note, and only pressing Confirm, with a name in the sidebar, saves it to `runtime/work_orders.jsonl` (git-ignored).
The model has no way to reach that write, and every reply that drafts ends with a line, added in code, saying the draft waits for the employee.
If the employee asks for a work order and the model only describes one, a line added in code says that no draft was made and nothing is waiting.
Nothing is sent to any network system: a work order is a record for the team.

**It refuses**, with the reason: forecasts of future tower KPIs (none are committed), where a tower is (the data has no locations), sites outside Tripoli, whether an area needs a new site or more capacity (the GIS release cannot tell), lists of customers, approving or changing offers (a named review in the prepaid dashboard does that), and phone numbers.
A phone number in the employee's message is removed before the model sees it.

### The alert rules

For the latest day in the tower file, each KPI is checked against the network team's target and a severe limit:

| KPI | Target | Severe |
|---|---|---|
| Cell availability | 95% | below 50%: critical |
| Call drop rate | 0.5% | above 1%: major |
| Connection setup success | 99.5% | below 98%: major |
| Data session setup success | 99.5% | below 98%: major |
| Handover success | 97.5% | below 90%: major |
| Download speed | none | below 2 Mbps: major |

A tower that is up but carries under a quarter of its usual users (its median over the 28 days before, when that is at least 5) is a sleeping cell, and critical.
A KPI past its target only is a warning, and so is a tower that reported in the week before but not on the latest day.
The rules are in `src/assistants/network.py`, and every alert names the KPI, its value and the limit, so it can be checked against the file.

### The teammates' files it reads

All paths are in `src/assistants/sources.py`; if an owner moves a file, that is the only place to change.

| File | Owner |
|---|---|
| `network_kpi_prediction/data/erbs_cell_kpi_full_year.csv` | Maher |
| `network_kpi_prediction/data/macro_network_kpis_daily.csv` | Maher |
| `network_kpi_prediction/data/4g_traffic_volume_daily.csv` | Maher |
| `antenna_cell_placement/integrated_release/shortlist.csv` | Mahmoud and Ahmed |
| `antenna_cell_placement/integrated_release/candidates.csv` | Mahmoud and Ahmed |
| `antenna_cell_placement/integrated_release/manifest.json` | Mahmoud and Ahmed |

## The service-point list (waiting for Taha)

When it arrives, it goes in `data/service_points.csv` with these columns, one row per shop or service point:

| Column | Meaning |
|---|---|
| `name_ar`, `name_en` | Name of the shop or point |
| `city` | City, as customers say it |
| `address_ar` | Street address in Arabic |
| `lat`, `lon` | WGS84 coordinates |
| `opening_hours` | As the operator states them |
| `source` | Where the row came from (website page, photo, visit) |
| `collected` | Date the row was checked |

## The language model

`openai/gpt-oss-120b` on Groq, with low reasoning effort and temperature 0.
Groq shut down Llama 3.3 70B for free accounts on 2026-08-16 and named this model as its replacement.
The free plan allows 8K tokens a minute and 200K a day, which is about two or three chat turns a minute and sixty a day; the demo fits, a class of users does not.

## Checks

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```

The tests use hand-made data and a scripted model; nothing calls Groq or the network.
`tests/test_service_client.py` fails if `src/assistants/service_client.py` stops being an exact copy of the prepaid module's example client.

To ask the real model the evaluation questions in `eval/chatbot_questions.toml` and write `reports/chatbot_eval.md`, with the service running and `.env` filled in:

```bash
uv run python -m assistants.evaluate chatbot
```

The same with `copilot` asks `eval/copilot_questions.toml` and writes `reports/copilot_eval.md`.
It pauses between questions to stay inside the free plan's per-minute limit, so twenty questions take about ten minutes.
`--only id1,id2` asks just those questions and prints the answers without writing a report, which saves the free plan's daily tokens while fixing one answer.

## Look

Both apps share `.streamlit/config.toml`, the palette of the team's GIS demo page, and `src/assistants/ui.py`, which adds the eyebrow line, Arabic running right to left, and the orange limits note.
Run both apps from this folder so the theme applies.
