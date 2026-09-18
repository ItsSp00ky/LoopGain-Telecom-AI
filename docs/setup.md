# Environment setup

Three environments, in order of how often you will use them:

1. **Local (Windows / macOS / Linux)** — day-to-day development, CPU only.
2. **Docker Compose** — the reproducibility deliverable (D1) and the demo host.
3. **Google Colab (free T4)** — one module only: the M1 LSTM benchmark arm.

Serving is CPU-only everywhere. Nothing in this project requires a GPU you
have to pay for.

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Git** | 2.40+ | Version control. Install first — nothing else works without it. |
| **Python** | **3.11 exactly** | TensorFlow, scikit-survival and SDV do not have wheels for 3.12+ yet. 3.10 is missing some typing syntax this codebase uses. |
| **Conda** (Miniconda or Anaconda) | any recent | The reliable way to get 3.11 alongside whatever else is on your machine, and the scientific wheels build far better from conda-forge on Windows. |
| **Docker Desktop** | 4.30+ | Deliverable D1: `docker compose up` from a clean clone. Needs WSL2 on Windows. |
| **VS Code** | any recent | Not required, but the whole team uses it. |
| GitHub CLI (`gh`) | optional | Makes PRs and issues one command instead of a browser trip. |

### Windows, in one go

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
winget install --id Docker.DockerDesktop -e
```

Close and reopen your terminal afterwards so `PATH` picks them up.

If you already have Anaconda you do **not** need to install Python separately —
step 2 creates a 3.11 environment for this project without touching your base.

> **Disk space.** The full environment is roughly 6–8 GB: torch (CPU) ~1 GB,
> TensorFlow ~600 MB, Docker images ~3 GB, datasets ~500 MB. Budget **10 GB
> free** before you start. If you are tight, see "Slimming down" at the end.

---

## 2. Local environment

```powershell
git clone https://github.com/ORG/REPO.git ai-cvm-suite
cd ai-cvm-suite

conda env create -f environment.yml
conda activate cvm
```

`environment.yml` installs Python 3.11 plus the scientific core from
conda-forge, then `pip install -e ".[all]"` for the rest.

**Install CPU torch first if disk space matters.** SDV/CTGAN pulls torch, and
the default PyPI wheel bundles a CUDA runtime you will never use here:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then finish setup:

```powershell
Copy-Item .env.example .env
pre-commit install
```

Open `.env` and set at minimum:

- `CVM_HASH_SALT` — generate one, do not use the placeholder:
  ```powershell
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `KAGGLE_USERNAME` / `KAGGLE_KEY` — for datasets B and C
- `GROQ_API_KEY` — **optional.** Only writes Arabic offer copy in the channel
  simulator; leave blank and it falls back to templated text.

Verify:

```powershell
pwsh tasks.ps1 test
```

The guardrail and config tests should pass immediately. The data-level leakage
tests are `xfail` until the pipeline lands — that is expected, and the xfails
are deliberate markers of what is not built yet.

### Installing only what you need

`[all]` is convenient but heavy. If you own one track, install its slice:

```powershell
pip install -e ".[ml,dev]"      # M1 Arm A, M2, M4 — classical ML, survival, CLV
pip install -e ".[dl,dev]"      # M1 Arm B — TensorFlow for the LSTM
pip install -e ".[gan,dev]"     # Layer 2 — CTGAN, TVAE, SDMetrics
pip install -e ".[ui,ml,rtl,dev]"  # API + pricing + dashboards + Arabic RTL
```

There is no `copilot` or `nlp` extra in this branch. LangChain, Chroma,
sentence-transformers, transformers, peft and CAMeL Tools were all removed
when the Copilot and the care-text classifier moved to other components —
roughly 4.5 GB of install saved. What remains of Arabic support is the `rtl`
extra: two small pure-Python packages that render offer copy correctly.

---

## 3. Docker

This is the deliverable, not a convenience. D1's acceptance criterion is that
`docker compose up` reproduces the system from a clean clone, and Appendix C
adds "on a machine that is not the author's".

```powershell
docker compose up --build
```

| Service | URL | Notes |
|---|---|---|
| api | <http://localhost:8000/docs> | Swagger |
| ui | <http://localhost:8501> | Command Center |
| channel-sim | <http://localhost:8502> | USSD + SMS, Arabic RTL |
| mlflow | <http://localhost:5000> | Experiment tracking |

`data/` and `artifacts/` are bind-mounted, so trained models on your host
appear in the containers without a rebuild.

Windows notes:

- Docker Desktop needs WSL2. It will prompt you if it is missing.
- Give Docker at least 4 GB of RAM in Settings → Resources.
- The first build takes 8–15 minutes. Subsequent builds are cached.

---

## 4. Colab (the one GPU module)

Only M1 Arm B needs a GPU, and it fits comfortably in a free T4 session.

```python
# In a Colab cell
!git clone https://github.com/ORG/REPO.git
%cd REPO
!pip install -e ".[dl,dev]" -q

from google.colab import drive
drive.mount('/content/drive')
```

**Checkpoint to Drive every epoch.** Colab cuts sessions without warning, and
losing a training run to a disconnect is the kind of avoidable problem that
eats a day.

Runtime → Change runtime type → T4 GPU. Confirm with:

```python
import tensorflow as tf
print(tf.config.list_physical_devices('GPU'))
```

The trained artefact comes back as a file, not a running process:

- M1 Arm B → `artifacts/models/m1_churn_lstm/` (SavedModel)

Do **not** commit it. It is gitignored. Share it through Drive or a GitHub
release.

---

## 5. Free accounts to create

All free. Create them on Day 1 so nobody is blocked on a signup mid-sprint.

| Service | For | Link |
|---|---|---|
| Kaggle | Datasets B and C | <https://kaggle.com> → Settings → Create New Token |
| Groq | *Optional* — Arabic offer copy in the channel simulator | <https://console.groq.com> |
| Hugging Face | Optional — Spaces demo host, Criteo uplift mirror | <https://huggingface.co> |
| Oracle Cloud Always Free | Demo host — 4 ARM cores, 24 GB RAM | <https://www.oracle.com/cloud/free/> |
| GitHub Student Developer Pack | Possible extra credits | <https://education.github.com/pack> |

Before spending anything, ask the SIC coordinators directly whether the
programme provides compute. The budget line in the proposal is $20–40 total,
and most of that is optional.

---

## 6. Troubleshooting

**`ModuleNotFoundError: cvm`** — the package is not installed in the active
env. Run `pip install -e .` from the repo root, and check `conda activate cvm`.

**LightGBM fails to load on Linux/Docker** — missing `libgomp1`. Already in
the Dockerfiles; if you hit it locally, `sudo apt install libgomp1`.

**TensorFlow reports no GPU on Windows** — expected. Native Windows TF has been
CPU-only since 2.11. Serving is CPU-only anyway; train on Colab.

**Pip resolves for a long time on `[all]`** — normal, it is a wide dependency
set. Install the narrow slice for your track instead.

**`GuardrailBreach` in a test you did not touch** — read the message before
changing the threshold. It names the constraint and the numbers. Guardrails are
the ethical core; if a demo needs one relaxed, change the demo.

### Slimming down

If disk space is tight (under ~10 GB free):

- Install CPU torch explicitly, as above. Saves ~1.5 GB.
- Skip the `dl` extra until you start M1 Arm B, and train it on Colab.
  Saves ~600 MB.
- Run `docker system prune` between rebuilds.
