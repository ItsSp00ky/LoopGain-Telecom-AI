# Loop Gain assistants

The two conversational parts of the Loop Gain platform, in one project with one look:

- **Customer chatbot** (`chatbot_app.py`): which Almadar packages fit a customer, and whether Almadar approved an offer for them.
  Built with Ali, whose chatbot role is in the action plan.
- **Employee copilot** (`copilot_app.py`, next): questions about customers at risk, the GIS planning shortlist and the network forecasts, answered with sources.

Both follow the same rule: the language model only picks a tool and phrases what came back.
Every package, price, offer and figure comes from the prepaid service or a teammate's published output, and code, not the prompt, stops anything else from reaching the reader.
The reasons are in decision 38 of [../prepaid_churn/docs/decisions.md](../prepaid_churn/docs/decisions.md).

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
| Say whether Almadar approved an offer for the signed-in customer | `my_offer` over `GET /subscribers/{id}/retention` | The tool takes no arguments: the ID comes from the sign-in, is never sent to Groq, and cannot be swapped for another customer's |
| Find an Almadar shop | `find_service_point` | Waiting for the service-point list; until then it says the locations are not available |

It never sees a churn probability: the chatbot key is refused on the copilot's endpoints (403).
Every reply is checked before it is shown:

- A number that no tool returned and the customer did not write replaces the reply with a safe answer built only from the tool results (`grounding.py`).
- A reply holding a Libyan phone number is replaced the same way, even when the customer typed it.
- A tool error, an unreachable service, or Groq being down or rate-limited gives "not available right now", never a guess.

Under each reply, "What I looked up" shows every tool call and exactly what it returned.
Tool results come in the customer's language only, detected from their message, and the model is told which language to reply in.

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

It pauses between questions to stay inside the free plan's per-minute limit, so twenty questions take about ten minutes.

## Look

Both apps share `.streamlit/config.toml`, the palette of the team's GIS demo page, and `src/assistants/ui.py`, which adds the eyebrow line, Arabic running right to left, and the orange limits note.
Run both apps from this folder so the theme applies.
