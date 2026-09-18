# Copilot Starter Kit

**This folder is not part of `ali_branch`.** Nothing here is imported, tested
or shipped by the CVM component. It is scaffolding for whoever owns
**Component 5 — Employee Telecom Copilot**, handed over so that work is not
duplicated.

Copy it into your own repository. Do not import it from here.

---

## What is in the box

| File | What it was going to be |
|---|---|
| `agent.py` | The LangChain agent: tool assembly, the read-only system prompt, `run_agent()` |
| `tools/duckdb_sql.py` | SQL tool with a statement denylist — *see the warning below* |
| `tools/model_api.py` | Tool that calls the CVM scoring endpoints, with an endpoint allowlist |
| `tools/rag.py` | RAG retriever over model cards, the data dictionary and guardrail configs |
| `rag_index.py` | Chroma index construction and refresh |
| `router_copilot.py` | A FastAPI `/v1/copilot/ask` router, if you serve the agent over HTTP |
| `streamlit_Home.py` | Chat surface with visible tool-call traces |
| `m7_copilot.yaml` | Config: model, tools, constraints, and the rehearsed demo questions |
| `copilot.Dockerfile` | CPU-only image — hosted inference, no local weights |
| `*.py.txt` | Package `__init__` files, renamed so they do not get picked up here |

The files are stubs with `NotImplementedError` bodies, but the docstrings carry
the design reasoning, the constraints and the intended signatures.

---

## Read this before you start

### Do not use `duckdb_sql.py` against the CVM feature store

It was written when the Copilot and CVM lived in one repository. They no
longer do, and querying our DuckDB file directly is now the wrong seam. Use
**`POST /v1/cohort/query`** instead. Reasons, in full, in
[../../INTEGRATION.md](../../INTEGRATION.md#1-why-http-and-not-a-shared-library) —
briefly: the store will be replaced at scale, direct queries bypass the
guardrails, and decisions taken outside the API are never written to the audit
log.

Keep the file if you have your *own* database to query. Point it at that.

### `model_api.py` is the one to keep

That is the correct integration pattern, and its endpoint allowlist already
matches the published contract.

### The four constraints are structural, not advisory

They are in `m7_copilot.yaml` and encoded in the stubs. Keep them:

- The LLM never sets prices or credit limits — it reads and explains.
- No write path: read-only connections, allowlisted endpoints, read-only mounts.
- Every answer cites the tool output it came from.
- No grounding, no answer — refuse rather than guess.

A system prompt is advisory. A read-only mount is not. Enforce at the
connection level and the prompt becomes a second layer rather than the only one.

---

## Your first three steps

1. Read [../../INTEGRATION.md](../../INTEGRATION.md) — especially §4, the worked
   example for *"Which Benghazi subscribers are at risk because of coverage,
   and what should we offer them?"*. That is your flagship demo question and
   the contract is written around it.
2. Start the CVM stack (`docker compose up` in this repo), open
   <http://localhost:8000/docs>, and call `/v1/cohort/query` by hand until the
   shape is familiar. Generate a typed client from `/openapi.json`.
3. Build `model_api.py` first, then the agent, then RAG. RAG is the layer to cut
   if the sprint gets tight — an agent with cohort + scoring tools already
   answers most questions.

## Questions

Ask Ali. The contract is deliberately narrow; if something you need is missing
from it, raise that **before** building around the gap.
