# Testing walkthrough — empty clone to working demo

Numbered steps, each with a **checkpoint**: exactly what you should see if it
worked, and what to do if it did not. Run them in order.

**On this machine, steps 0–2 and 8 are already done** — the `cvm` conda env is
built (Python 3.11.16), git and `gh` are configured, and there are eight
commits on `ali_branch`. Step 3 (`.env`) is the one thing still outstanding.

Steps 0–9 set up and verify the skeleton. Steps 10–14 are the verify loop you
repeat as each module lands.

> **For the build ORDER — what to write next, and the check after each phase —
> see [ROADMAP.md](ROADMAP.md).** This file is the environment and the
> per-module verify loop; the roadmap is the sequence. Keeping the order in one
> place only is deliberate.

All commands are PowerShell, run from the repo root (`D:\Sic`). Activate the
env first with `conda activate cvm`.

---

## Step 0 · Fix the PATH and configure git

Git, GitHub CLI and Docker are installed in non-standard locations on this
machine. Open a **new** PowerShell window (installers update PATH, but only new
shells see it) and check:

```powershell
git --version; gh --version; docker --version; conda --version
```

**Checkpoint:** four version strings, no "not recognized".

> **If a command is not recognised**, the installer did not add it to PATH.
> Add it for your user permanently:
> ```powershell
> [Environment]::SetEnvironmentVariable('Path', $env:Path + ';D:\Git\cmd;D:\GITHUB_CLI', 'User')
> ```
> Then open a new window again.

Set your git identity — commits fail without it:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

And authenticate the CLI (opens a browser; choose HTTPS and "login with a web browser"):

```powershell
gh auth login
```

**Checkpoint:** `gh auth status` prints `Logged in to github.com as <you>`.

---

## Step 1 · Create the Python 3.11 environment

This takes 10–20 minutes. Do not use Anaconda base — it is Python 3.14 and half
the stack will not resolve.

```powershell
conda env create -f environment.yml
conda activate cvm
```

**Checkpoint:**

```powershell
python --version
```
must print exactly `Python 3.11.x`. Your prompt should show `(cvm)`.

> **If conda solving hangs for more than ~15 minutes**, install mamba and retry:
> `conda install -n base -c conda-forge mamba`, then
> `mamba env create -f environment.yml`.

---

## Step 2 · Install CPU torch, then the package  ·  **done on this machine**

**Order matters.** SDV/CTGAN pulls torch; the default wheel bundles a CUDA
runtime nothing in this project uses (~1.5 GB wasted on a machine with 20 GB
free). Nothing here needs a GPU — that is a scope decision, not a limitation.

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[all]"
```

**Checkpoint:**

```powershell
python -c "import cvm; print(cvm.__version__)"
```
prints `0.1.0`.

```powershell
python -c "import torch; print(torch.__version__)"
```
should end in `+cpu`. If it does not, the CUDA wheel got in first; uninstall
torch and redo this step in order.

One package is missing from a fresh install and is needed by M3, which is the
centre of the pipeline:

```powershell
python -c "import sklift; print('scikit-uplift', sklift.__version__)"
```

> **If a package fails to build on Windows**, install the narrower slice for
> the work you are doing: `pip install -e ".[ml,ui,rtl,dev]"` covers the API,
> the pricing engine and the dashboards. Add `gan` when you reach the
> synthesis engine.

---

## Step 3 · Create `.env` with a real salt

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` and paste the generated value into `CVM_HASH_SALT`.

**Checkpoint:**

```powershell
python -c "from cvm.config import settings; print(len(settings.require_salt()))"
```
prints `64`.

> **If you see `CVM_HASH_SALT is not set`**, `.env` is not being read — check
> you are in the repo root. **If you see "still the placeholder"**, you copied
> the file but did not edit it. Both errors are deliberate: the code refuses to
> hash identifiers without a real salt.

---

## Step 4 · Run the test suite

This is the real proof that the skeleton works.

```powershell
pytest -v
```

**Checkpoint:** roughly **60 passed**, a handful of **xfailed**, **0 failed**.

The `xfail`s are intentional markers for behaviour not yet built (the data-level
leakage checks, the M4 behavioural guards). They are *supposed* to be there
right now, and you remove each marker as you implement that piece.

Run the two gates on their own — these are the ones CI treats as required:

```powershell
pytest tests/guardrails -m guardrail -v --no-cov
pytest tests/leakage -m leakage -v --no-cov
```

**Checkpoint:** both all-green.

> **If the guardrail tests fail**, do not adjust the thresholds in
> `conf/pricing.yaml` to make them pass. The failure message names the
> constraint and the numbers; read it. These tests encode commitments the
> project is evaluated on.

---

## Step 5 · Check linting

```powershell
ruff check src tests apps scripts
black --check src tests apps scripts
```

**Checkpoint:** `All checks passed!` and `... files would be left unchanged`.

> If black wants to reformat, run `black src tests apps scripts` and commit the
> result. Install the hooks so this happens automatically: `pre-commit install`.

---

## Step 6 · Start the API and read the contract

```powershell
uvicorn cvm.api.main:app --reload
```

Open <http://localhost:8000/docs>.

**Checkpoint:** Swagger UI listing six endpoint groups — health, score, offer,
advance, subscriber, cohort.

In a second terminal:

```powershell
curl http://localhost:8000/health
```

**Checkpoint:** JSON with `"status":"degraded"` and every entry in
`models_loaded` set to `false`.

**`degraded` is the correct answer right now** — no models are trained. An API
reporting `ok` with nothing loaded would be a bug; a partial deploy is meant to
be visible.

Now prove the privacy contract holds:

```powershell
curl -X POST http://localhost:8000/v1/score/churn -H "Content-Type: application/json" -d "{\"subscriber_ids\":[\"0912345678\"]}"
```

**Checkpoint:** HTTP **422**. A raw Libyan MSISDN is rejected by the schema —
there is no endpoint anywhere that accepts one.

Stop the server with `Ctrl+C`.

---

## Step 7 · Start Docker and build the stack

Launch **Docker Desktop** from the Start menu and wait for the whale icon to
stop animating.

```powershell
docker info --format "{{.ServerVersion}}"
```

**Checkpoint:** prints a version. If it says "cannot connect to the Docker
daemon", Docker Desktop is not running yet — wait, then retry.

Give Docker at least 4 GB in Settings → Resources → Advanced, then:

```powershell
docker compose build
```

First build takes 8–15 minutes.

**Checkpoint:** three images built with no errors.

```powershell
docker compose up
```

**Checkpoint:** four containers start — `cvm-api`, `cvm-ui`, `cvm-channel-sim`,
`cvm-mlflow` — and `cvm-api` reaches `healthy` within about a minute.

Open each:

| URL | Expect |
|---|---|
| <http://localhost:8000/docs> | Swagger |
| <http://localhost:8501> | Command Center, with placeholder metrics |
| <http://localhost:8502> | Channel simulator, Arabic/English toggle |
| <http://localhost:5000> | MLflow, empty experiment list |

**This is deliverable D1 passing.** `docker compose up` reproduces the system
from a clean clone.

Shut down with `Ctrl+C`, then `docker compose down`.

> **If a port is already in use**, something else on your machine has it. Change
> the host side of the mapping in `docker-compose.yml` (e.g. `"8001:8000"`).
> **If the build runs out of disk**, `docker system prune -a` reclaims space
> from earlier builds.

---

## Step 7b · Drive it yourself

Step 7 proves the stack *starts*. This one proves it *works*, which is not the
same thing and once was not true: the serving image resolved a newer
scikit-learn than the one that pickled the artefacts, every container reported
healthy, and `/v1/score/churn` returned 500 on the first request. **Always make
it answer a real question before you believe it.**

The three ids below are real rows from the current feature store, chosen
because they disagree with each other.

### 1 · The API, on a subscriber the engine refuses to treat

```bash
curl -s -X POST http://localhost:8000/v1/offer/next-best -H "Content-Type: application/json" -d "{\"subscriber_id\":\"f1625300bd1f3880367bdc73e035a1b191b85700cd8221d3102a5df82f312e0f\"}"
```

**Expect `"offer_id":"NO_ACTION"`** with `reason_codes` containing
`no_action:sleeping_dog`.

This subscriber has a churn probability of **1.0000** — as certain as the model
gets — and the engine still recommends nothing. Their uplift is **−0.0573**:
contacting them makes them *more* likely to leave. `expected_value_lyd` is
**−16.36**. A propensity-ranked campaign would have put them at the very top of
the call list. That gap is the entire argument for M3.

### 2 · The same subscriber, at the credit desk

```bash
curl -s -X POST http://localhost:8000/v1/advance/limit -H "Content-Type: application/json" -d "{\"subscriber_id\":\"f1625300bd1f3880367bdc73e035a1b191b85700cd8221d3102a5df82f312e0f\"}"
```

**Expect `"approved":true` with `"limit_lyd":1.0`.** Not a contradiction: "do
not spend retention budget on them" and "they reliably repay 1 LYD" are
different questions. Repayment probability is **0.977**, and the binding
constraint is `tier_ceiling`, not risk.

### 3 · A subscriber worth treating

```bash
curl -s -X POST http://localhost:8000/v1/score/churn -H "Content-Type: application/json" -d "{\"subscriber_ids\":[\"d1b96ede93c81021e17dbfa335eab82808cb2fb93367930ee36d2661ae31b394\"],\"include_survival\":true}"
```

**Expect a calibrated probability, a decile, a time-to-churn window and SHAP
drivers with plain-language sentences.** Uplift **+0.2739** against a CLV of
**9,047.70 LYD** — expected gain **+2,473.24 LYD**.

Swap in the `f1625300…` id and the drivers should read like this — every one
raising risk, for a subscriber the model scores at 1.0000:

```
p=1.0000  decile=1  time_to_churn=22 days
  +4.9521 has not topped up in 117 days — raises churn risk
  +1.9362 recharges are irregular (variation 2.33) — raises churn risk
  +0.4418 recharges about every 91 days — raises churn risk
```

**Three things to check, because all three were once wrong:**

1. **It returns 200 at all.** If it 500s, the models loaded but cannot predict.
   `curl -s http://localhost:8000/health` — `model_errors` names the estimator
   and the exception.
2. **`time_to_churn_days` is a plausible number.** If it is
   `-9223372036854775808`, a NaN reached `astype(int)`; the contract allows
   `null` and that is what "we do not know" must look like.
3. **The contributions are not all zero.** A SHAP attribution is measured
   against a reference population. Explain a one-row batch against itself and
   every contribution is exactly `0.0` — which still renders, still validates,
   and still prints "lowers churn risk" under each one, because `0 > 0` is
   false.

### 4 · The cohort surface Components 4 and 5 consume

```bash
curl -s -X POST http://localhost:8000/v1/cohort/query -H "Content-Type: application/json" -d "{\"min_churn_probability\":0.8,\"limit\":3}"
```

**Expect 668 matched and ~118,522 LYD of revenue at risk.** Try adding
`"district":"Tripoli"` — it must be **rejected**. Geography is not an input to
any decision in this branch.

### 5 · The four screens — <http://localhost:8501>

| Screen | What to look for |
|---|---|
| Executive Overview | Revenue at risk, and the "against doing nothing" panel |
| Segment Explorer | **"Are the eight segments a shape in the data?"** — the honest answer is no; the screen says so and shows where rules and clusters disagree |
| Subscriber 360 | Paste either id above. SHAP waterfall, offer, advance. Paste a **phone number** instead and it must refuse |
| Campaign Builder | The budget LP. Push the budget down and watch which subscribers drop out |

### 6 · The subscriber's view — <http://localhost:8502>

Switch to Arabic and watch the SMS counter. **One Arabic character forces UCS-2
and the limit collapses from 160 characters to 70** (67 per part once
concatenated). The preview shows the real part count, not a character count
divided by 160.

**Checkpoint for all of it:** every call returns 200, and
`curl -s http://localhost:8000/health` reports `"status":"ok"` with an empty
`model_errors`.

---

## Step 8 · Make the first commit  ·  **done — eight commits on `ali_branch`**

```powershell
git add -A
git commit -m "chore: scaffold CVM component (ali_branch)"
git log --oneline
```

**Checkpoint:** one commit, and `git status` reports a clean tree.

Verify nothing private or heavy slipped in:

```powershell
git ls-files | Select-String -Pattern "\.env$|\.parquet$|\.duckdb$|\.pkl$|__pycache__"
```

**Checkpoint:** **no output.** Any hit here means `.gitignore` is not doing its
job — fix it before pushing.

Push (create the repo on GitHub first, or let `gh` do it):

```powershell
gh repo create ai-cvm-suite --private --source=. --remote=origin
git push -u origin ali_branch
```

**Checkpoint:** CI runs on GitHub. Actions → the `CI` workflow → lint, test,
leakage, guardrails and privacy-scan jobs all green. The docker job takes
longest.

---

## Step 9 · Download data

Start small. The core five are modest; the recommended additions are not.

```powershell
python scripts/download_data.py --list
python scripts/download_data.py --only A,C
```

**Checkpoint:** right now every source logs `not implemented yet` — the
loaders are stubs. That is expected and it is your next coding task
(`src/cvm/ingest/`).

Before writing them, set up credentials so the loaders have something to use:

| Need | How |
|---|---|
| Kaggle (B, C, H) | kaggle.com → Settings → API → Create New Token → save `kaggle.json` to `%USERPROFILE%\.kaggle\` |
| KKBox (H) | additionally accept the competition rules, or the download 403s |

**Mind the disk.** Full links, sizes and a suggested order are in
[`../data/README.md`](../data/README.md). The script warns you if a request
would not fit.

---

## Step 10 · Verify each module as you build it

Repeat this loop for every module. It is the same five checks each time, and it
is *additional* to the phase checkpoint in [ROADMAP.md](ROADMAP.md) — that one
proves the phase produced the right numbers, this one proves the module is
wired in like every other.

Before the five, always:

```powershell
python scripts/progress.py
```

```powershell
# 1. Unit tests for the thing you just wrote
pytest tests/unit -k <module> -v

# 2. The two gates still pass
pytest tests/guardrails tests/leakage -v --no-cov

# 3. Lint
ruff check src; black --check src

# 4. It is reachable over HTTP
curl http://localhost:8000/health        # your model should now show true

# 5. The experiment is logged
#    -> the run appears at http://localhost:5000
```

A module is done when all five pass **and** the seven Definition-of-Done items
in [`../CONTRIBUTING.md`](../CONTRIBUTING.md#definition-of-done) are ticked.

### Module-specific checks

**Layer 1 — ingest**

```powershell
python -m cvm.ingest.run
pytest tests/unit -k "schema or privacy" -v
```
Checkpoint: Parquet files in `data/interim/`, Pandera contracts pass, and the
UCI dedup logs roughly **300 dropped rows**. Record that number — it is pitch
material.

**Layer 2 — synthesis**

```powershell
python -m cvm.synthesis.run
```
Checkpoint: 100k rows in `data/synthetic/` and the quality gate reports
KS-complement **≥ 0.85**, correlation delta **≤ 0.10**, detection AUC
**≤ 0.65**. A gate failure must exit non-zero — if the generator produces rows
a discriminator can spot at 0.80 AUC, retrain it, do not lower the threshold.

**Layer 3 — features**

```powershell
python -m cvm.features.run
pytest tests/leakage -v --no-cov
```
Checkpoint: `features_offline.parquet` and `features_online.duckdb` both
exist, and the previously-`xfail`ed point-in-time
tests now pass for real. **Do not move on until they do** — every metric
downstream is invalid if this layer leaks.

**M1 — churn**

Checkpoint: PR-AUC and lift reported, a calibration curve produced, and the
naive-vs-honest table filled in. Accuracy must not appear as a headline number.
Whichever arm wins, write the verdict paragraph.

**M3 — pricing**

```powershell
pytest tests/guardrails -m guardrail -v --no-cov
curl -X POST http://localhost:8000/v1/offer/next-best -H "Content-Type: application/json" -d "{\"subscriber_id\":\"<64-hex>\"}"
```
Checkpoint: the response carries `reason_codes`, `expected_margin_lyd`, a
`constraints` array showing which guardrail **bound**, and a `decision_log_id`.
Then replay that id and confirm you get the same decision back.

**M4 — advance**

Checkpoint: a chronically-distressed test subscriber is declined **regardless
of a high repayment probability**, and the response explains why. This is the
ethical core of the module — if it approves, something is wrong.

---

## Step 11 · Latency check

Once M1 and M3 serve real predictions:

```powershell
locust -f tests/integration/locustfile.py --host http://localhost:8000
```

**Checkpoint:** p95 **< 200 ms** for the tabular endpoints on a single CPU
container. The text endpoint has a looser budget — report it separately and
honestly rather than hiding it inside one headline figure.

(You will need to write `locustfile.py`; it is not scaffolded.)

---

## Step 12 · Clean-machine test

Appendix C, item 7, and the one people skip.

On **a teammate's laptop**, not yours:

```powershell
git clone <repo-url>; cd ai-cvm-suite; git checkout ali_branch
Copy-Item .env.example .env    # add a salt
docker compose up
```

**Checkpoint:** the Command Center loads and shows real numbers with no manual
fixing. If it needs a file that only exists on your machine, it is not done.

---

## Step 13 · Integration test with your teammate

When the Copilot owner is ready, give them
[`INTEGRATION.md`](INTEGRATION.md) and run the §4 worked example together:

```powershell
curl -X POST http://localhost:8000/v1/cohort/query -H "Content-Type: application/json" -d "{\"min_dropped_call_rate\":0.04,\"min_churn_probability\":0.5,\"min_clv_lyd\":300}"
```

**Checkpoint:** their agent answers *"Which Benghazi subscribers are at risk
because of coverage, and what should we offer them?"* using only your API, with
a visible tool-call trace and no invented numbers.

Do this **before** integration week, not during it. The most common failure in
a branched project is two components assuming different semantics for the same
field, and that is cheap to find early and expensive to find late.

---

## Step 14 · Pre-demo checklist

- [ ] `docker compose up` works from a clean clone on someone else's machine
- [ ] All four Command Center screens render on generated data
- [ ] Channel simulator renders Arabic RTL correctly (not backwards or disconnected)
- [ ] Every model has a filled-in card in `docs/model_cards/`
- [ ] `docs/data_dictionary.md` covers every generated field
- [ ] Naive-vs-honest metric tables are complete, with the gap explained
- [ ] The 5-minute demo video is recorded (live-demo insurance)
- [ ] `HANDOFF.md` §2 and §6 describe the current state, not the old one
- [ ] No `.env`, data file or model artefact is tracked in git

---

## Quick reference

| Task | Command |
|---|---|
| Activate env | `conda activate cvm` |
| Fast tests | `pwsh tasks.ps1 test` |
| Guardrails only | `pwsh tasks.ps1 guardrails` |
| Leakage only | `pwsh tasks.ps1 leakage` |
| Lint | `pwsh tasks.ps1 lint` |
| Auto-format | `pwsh tasks.ps1 fmt` |
| Full pipeline | `pwsh tasks.ps1 pipeline` |
| API (hot reload) | `pwsh tasks.ps1 api` |
| Command Center | `pwsh tasks.ps1 ui` |
| Whole stack | `pwsh tasks.ps1 up` |
| Clear caches | `pwsh tasks.ps1 clean` |
