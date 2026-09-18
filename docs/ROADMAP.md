# Roadmap

**121 functions left, in a chain that cannot be reordered.** This document is
the order, and after every step a command that tells you whether you got it
right. If a check fails, do not move on — every layer below inherits the
mistake, and the expensive failures here are the silent ones.

Where you are, at any moment:

```bash
python scripts/progress.py
```

It prints the burn-down by layer and names the next phase. `--detail` lists
every remaining function by file.

**Environment.** The `cvm` conda env is built and working (Python 3.11.16, 39
of 40 packages). Either `conda activate cvm` first, or call it directly as
`D:\Anaconda\envs\cvm\python.exe`. Everything below assumes one of those.

---

## Phase 0 · Setup — three things, about 30 minutes

Almost everything is already done. This is what is left.

### 0.1 Create `.env` with a real salt

The only hard blocker in the repository. The code refuses to hash without a
salt and refuses the `.env.example` placeholder, both deliberately: an unsalted
SHA-256 of a 9-digit number space is trivially reversible.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste that value over `CHANGE_ME_generate_a_64_char_hex_string` in `.env`.

**Check** — prints the first 8 characters of your salt and nothing else:

```bash
python -c "from cvm.config import settings; print('salt ok:', settings.require_salt()[:8])"
```

If it raises `RuntimeError`, the salt is empty. If it raises `ValueError`, you
left the placeholder in.

### 0.2 Prove the skeleton still runs

**Check** — expect `113 passed, 10 xfailed`, then `All checks passed!`:

```bash
pytest -q && ruff check src tests apps scripts && black --check src tests apps scripts
```

The 10 `xfail`s are not failures. Each one marks something in this roadmap that
is not built yet, and you will turn them green as you go. They are your
progress bar; `python scripts/progress.py` is the other one.

### 0.3 Push to GitHub

Eight commits, no remote. Getting this in front of your team was the point.

```bash
gh repo create ai-cvm-suite --private --source=. --remote=origin
git push -u origin ali_branch
```

**Check** — prints the URL, and the branch shows 8 commits:

```bash
gh repo view --json url,defaultBranchRef
```

Then replace the `ORG/REPO` badge placeholders in `README.md` and `@ali` in
`.github/CODEOWNERS`, and confirm CI goes green on the push — that is the first
time the pipeline has ever run end to end.

---

## Phase 1 · Ingestion — 13 functions, 2–3 days

**Build this first because the privacy commitment is enforced here**, and
because every later layer reads what it writes.

Order inside the phase:

| | File | Functions | Note |
|---|---|---|---|
| 1 | `ingest/hashing.py` | 2 | Everything else depends on it |
| 2 | `ingest/uci_iranian.py` | 3 | Primary dataset; the dedup audit is pitch material |
| 3 | `ingest/cell2cell.py` | 4 | Already on disk, two-file join |
| 4 | `ingest/ibm_telco.py` | 3 | Needs Kaggle credentials |
| 5 | **three new loaders** | ~9 | `criteo_uplift.py`, `hillstrom.py`, `online_retail.py` |
| 6 | `ingest/run.py` | 1 | Orchestration |

**Write the three validation loaders in this phase, not later.** They are
about 20 lines each — Criteo from HuggingFace, Hillstrom via
`sklift.datasets.fetch_hillstrom`, Online Retail II via
`ucimlrepo.fetch_ucirepo(id=502)`. They gate deliverable D4, and deferring them
is the single most likely way this project ends up with a claim it cannot
support.

**Check 1** — the UCI dedup audit. Delete the `xfail` marker on
`test_uci_duplicate_rows_are_dropped` first:

```bash
pytest tests/leakage/test_point_in_time.py::test_uci_duplicate_rows_are_dropped -q
```

Record the actual duplicate count. The proposal says ~300 of 3,150 (~9.5%); if
your number differs, the proposal is what changes.

**Check 2** — Cell2Cell joins cleanly and drops the protected columns:

```bash
python -c "
from cvm.ingest.cell2cell import load, FORBIDDEN_COLUMNS
df = load()
print('rows:', len(df))
print('forbidden present:', sorted(set(FORBIDDEN_COLUMNS) & set(df.columns)) or 'none')
print('nulls in the two signature features:',
      df[['recv_vce_Mean','plcd_vce_Mean']].isna().sum().to_dict())
"
```

Expect 100,000 rows, **no** forbidden columns, and zero nulls.

**Check 3** — no raw identifier survived, and the pipeline runs:

```bash
cvm ingest && pytest tests/unit/test_privacy.py -q
```

**Check 4** — all six sources land:

```bash
python scripts/download_data.py --only A,B,C,F,G,J
```

---

## Phase 2 · Synthesis — 18 functions, 3–4 days

**Build the Gaussian copula first and treat CTGAN as an upgrade.** This is the
one change I would make to the plan as written. The quality gate is a *gate* —
KS ≥ 0.85 **and** correlation delta ≤ 0.10 **and** detection AUC ≤ 0.65,
simultaneously, over ~80 columns. If CTGAN misses, you iterate, and each
iteration is a training run. `GaussianCopulaSynthesizer` fits in seconds,
`ctgan_engine.py` already calls it *"fast, and sometimes wins"*, and the
three-way comparison was always a deliverable. Get the whole downstream
pipeline working on the copula population, then try CTGAN with time to spare.

Order inside the phase:

| | File | Functions | Note |
|---|---|---|---|
| 1 | `synthesis/quantile_map.py` | 1 | Map measured Cell2Cell marginals |
| 2 | `synthesis/hazard.py` | 2 | The label. Get this wrong and nothing downstream means anything |
| 3 | `synthesis/overlays.py` | 5 | The Libyan layer — recharge ladder, morning peak, salary week |
| 4 | `synthesis/ctgan_engine.py` | 4 | **Copula first**, then TVAE, then CTGAN |
| 5 | `synthesis/quality_gate.py` | 5 | Three metrics, all fatal on failure |
| 6 | `synthesis/run.py` | 1 | Orchestration |

**Check 1** — the label is plausible and the leakage split holds:

```bash
python -c "
from cvm.synthesis.hazard import LABEL_DRIVER_FIELDS, LABEL_ARTIFACT_FIELDS
assert not set(LABEL_DRIVER_FIELDS) & set(LABEL_ARTIFACT_FIELDS)
print('driver/artefact sets are disjoint')
"
pytest tests/leakage -q
```

**Check 2** — the generated churn rate matches the market assumption. Expect
close to 3.5%; a rate near 50% means you inherited the Cell2Cell prior, which
would destroy the calibration claim:

```bash
python -c "
import pandas as pd
from cvm.config import settings
df = pd.read_parquet(settings.paths['synthetic'] + '/population.parquet')
print('rows:', len(df), '| churn rate:', round(df['silent_churn_30d'].mean(), 4))
"
```

**Check 3** — the quality gate, which is the deliverable:

```bash
cvm synthesise
```

It must print all three metrics and pass all three. **A failing gate is not a
warning.** If detection AUC is above 0.65 the generator is distinguishable from
real data and the population is not usable; retrain or fall back to the copula.

**Check 4** — the recharge ladder was respected, not approximated:

```bash
python -c "
import pandas as pd
from cvm.config import load_conf, settings
df = pd.read_parquet(settings.paths['synthetic'] + '/population.parquet')
ladder = set(load_conf('market')['recharge']['denominations_lyd'])
got = set(df['recharge_amount_lyd'].dropna().unique())
print('invented denominations:', sorted(got - ladder) or 'none')
"
```

Anything other than `none` means the generator is selling cards Almadar does
not print.

---

## Phase 3 · Features — 25 functions, 3–4 days

**The highest-risk phase for correctness, and the failures are silent.** If
point-in-time correctness is wrong, every metric from here to the end of the
project is invalid and nothing tells you. Build `splits.py` before anything
else in this phase, and do not start Phase 4 until the leakage suite is green
with every `xfail` marker deleted.

| | File | Functions | Note |
|---|---|---|---|
| 1 | `features/splits.py` | 4 | Temporal only. There is deliberately no `random_split` |
| 2 | `features/velocity.py` | 3 | `mean_7d / mean_30d` decay ratios |
| 3 | `features/distress.py` | 2 | Zero-balance hours, recharge gap volatility |
| 4 | `features/wallet_leakage.py` | 4 | The dual-SIM signature feature |
| 5 | `features/rfm_le.py` | 7 | Prepaid-redefined R/F/M plus L and E |
| 6 | `features/store.py` | 4 | `get_features(as_of=)` must never read the future |
| 7 | `features/run.py` | 1 | Orchestration |

**Check 1** — the whole point of the phase. Delete all four `xfail` markers in
`tests/leakage/test_point_in_time.py`, then:

```bash
pytest tests/leakage -q
```

Expect every test to pass with no `xfail`. **This is the gate for Phase 4.**

**Check 2** — the generated distributions match what Cell2Cell measured. The
targets are in `docs/data_dictionary.md`:

```bash
python -c "
import pandas as pd
from cvm.config import settings
df = pd.read_parquet(settings.feature_store_offline)
for col, want in [('incoming_outgoing_ratio', 0.280),
                  ('offpeak_data_ratio', 0.424),
                  ('revenue_decay_ratio', 1.012)]:
    got = df[col].median()
    flag = 'OK' if abs(got - want) < 0.05 else 'DRIFTED'
    print(f'{col:<26} median {got:.3f} vs measured {want:.3f}  {flag}')
"
```

**Check 3** — point-in-time serving actually holds. Ask for features as of a
past date and confirm nothing later than that date contributed:

```bash
python -c "
from cvm.features.store import get_features
df = get_features(subscriber_ids=None, as_of='2026-06-30')
print('snapshot max date:', df['snapshot_date'].max())
assert str(df['snapshot_date'].max()) <= '2026-06-30'
print('no future leakage')
"
```

---

## Phase 4 · M1 churn — 17 functions, 2–3 days

Eight algorithms, one temporal split, calibration curves for all of them. The
benchmark table *is* the deliverable (D3), not the winner.

| | File | Functions |
|---|---|---|
| 1 | `models/m1_churn/gradient_boosting.py` | 3 |
| 2 | `models/m1_churn/calibration.py` | 3 |
| 3 | `models/m1_churn/benchmark.py` | 3 |
| 4 | `models/m1_churn/explain.py` | 4 |
| 5 | `models/m1_churn/survival.py` | 3 |
| 6 | `models/m1_churn/predict.py` | 1 |

**Check 1** — the benchmark has all eight rows and PR-AUC is the headline:

```bash
python -c "
import pandas as pd
from cvm.config import settings
t = pd.read_csv(settings.paths['reports'] + '/m1_benchmark.csv')
print(t.to_string(index=False))
assert len(t) >= 8, f'only {len(t)} models in the table'
assert 'accuracy' not in [c.lower() for c in t.columns[:2]], 'accuracy must not lead'
"
```

**Check 2** — calibration actually improved something. Brier must fall after
isotonic; if it does not, the calibration step is decoration and the phrase
*"a 0.31 means 31%"* is unsupported:

```bash
python -c "
import json
from cvm.config import settings
m = json.load(open(settings.paths['reports'] + '/m1_calibration.json'))
print('Brier raw:', m['brier_raw'], '-> calibrated:', m['brier_calibrated'])
assert m['brier_calibrated'] <= m['brier_raw']
"
```

**Check 3** — no single feature reconstructs the label. Delete the `xfail`
first:

```bash
pytest tests/leakage/test_point_in_time.py::test_a_single_feature_cannot_reconstruct_the_label -q
```

**Check 4** — the honest-metrics disclosure, which is pitch material. Published
work on UCI 563 reaches ~97% accuracy and ~0.99 AUC; reproduce it, then show
the corrected figure:

```bash
python -c "
from cvm.models.m1_churn.benchmark import naive_vs_honest
print(naive_vs_honest('uci_iranian').to_string(index=False))
"
```

---

## Phase 5 · M2 value — 9 functions, 2 days

**Check 1** — BG/NBD validated on real repeat purchases *before* it touches
recharges. This is the same move Criteo is for uplift:

```bash
python -c "
from cvm.models.m2_value.clv import fit_bg_nbd, fit_gamma_gamma, predict_clv
from cvm.ingest.online_retail import load
s = load()
bgf, ggf = fit_bg_nbd(s), fit_gamma_gamma(s)
print('holdout MAE:', predict_clv(bgf, ggf, s).pipe(lambda p: abs(p - s['actual']).mean()))
"
```

**Check 2** — *k* is chosen by silhouette, not by eye, and the rule-based
quintiles disagree with the clusters somewhere. Where they disagree is a
dashboard insight; perfect agreement means one of them is redundant:

```bash
python -c "
import json
from cvm.config import settings
r = json.load(open(settings.paths['reports'] + '/m2_segmentation.json'))
print('k:', r['k_chosen'], '| silhouette:', round(r['silhouette'], 3))
print('rule/cluster disagreement:', f\"{r['disagreement_share']:.1%}\")
"
```

**Check 3** — the CLV ceiling is live. At 40 LYD ARPU it must be 72 LYD:

```bash
pytest tests/unit/test_proposal_consistency.py::test_clv_ceiling_matches_the_guardrail -q
```

---

## Phase 6 · M3 uplift — 9 functions, 2–3 days

**Validate on Criteo before you write anything that touches the generated
population.** The order matters: it is the difference between a measurement and
an assertion, and it is the strongest claim in the proposal.

**Check 1** — Qini on real randomised arms. This is deliverable D4:

```bash
python -c "
from cvm.models.m3_uplift.evaluate import validate_on_criteo
r = validate_on_criteo()
print('Qini:', round(r['qini'], 4), '| uplift@30%:', round(r['uplift_at_k'], 4))
assert r['qini'] > 0, 'no measurable uplift -- the model is not working'
"
```

**Check 2** — the four quadrants are populated and sleeping dogs are excluded.
A run with zero sleeping dogs usually means the threshold is wrong, not that
none exist:

```bash
python -c "
from cvm.models.m3_uplift.evaluate import quadrant_counts
q = quadrant_counts()
for k, v in q.items(): print(f'  {k:<14} {v:>7,}')
assert q['sleeping_dog'] > 0, 'check sleeping_dog_threshold in conf/models/m3_uplift.yaml'
"
```

**Check 3** — the break-even the whole business case rests on. Expected value
must turn positive at 1.04 pp of uplift and not before:

```bash
python -c "
from cvm.models.m3_uplift.evaluate import expected_value_of_treatment as ev
print('at 1.00 pp:', round(ev(0.0100, 480, 5), 3))
print('at 1.04 pp:', round(ev(0.0104, 480, 5), 3))
assert ev(0.0100, 480, 5) < 0 < ev(0.0110, 480, 5)
print('break-even sits where the proposal says it does')
"
```

---

## Phase 7 · M4 advance — 5 functions, 1–2 days

Cheap, because the PD heads share M1's feature pipeline. The most
differentiated idea in the project for the least remaining work.

**Check** — delete all five `xfail` markers in `tests/guardrails/
test_advance_safety.py`, then:

```bash
pytest -m guardrail -q
```

Every test must pass with no `xfail`. The headline case is
`test_habitual_minimum_recharger_is_declined_the_data_advance`: a subscriber
whose modal top-up is the 5 LYD card is declined the 5 LYD data advance and
offered `DAY_50MB` instead. They would probably repay — that is the trap, and
why affordability declines what PD would approve.

---

## Phase 8 · Decision engine — 23 functions, 2–3 days

The guardrails are already built and tested. This phase is the pieces around
them: the pricing function, the LP, the ladder, the off-peak simulation, the
decision log, and the model registry.

| | File | Functions |
|---|---|---|
| 1 | `models/registry.py` | 2 |
| 2 | `decision/pricing.py` | 4 |
| 3 | `decision/offpeak.py` | 3 |
| 4 | `decision/budget_lp.py` | 2 |
| 5 | `decision/ladder.py` | 3 |
| 6 | `decision/advance_limit.py` | 6 |
| 7 | `decision/decision_log.py` | 3 |

**Check 1** — the endpoints stop returning 501:

```bash
python -c "
from fastapi.testclient import TestClient
from cvm.api.main import app
c = TestClient(app)
for path, payload in [('/v1/offer/next-best', {'subscriber_id':'a'*64,'channel':'api'}),
                      ('/v1/advance/limit', {'subscriber_id':'a'*64,'product':'rasid_fi_waqtuh'})]:
    r = c.post(path, json=payload)
    print(f'{path:<24} {r.status_code}')
    assert r.status_code == 200, r.text
"
```

**Check 2** — every offer carries the constraint that bound it. An offer the
system cannot explain is one it should not have made:

```bash
python -c "
from fastapi.testclient import TestClient
from cvm.api.main import app
r = TestClient(app).post('/v1/offer/next-best', json={'subscriber_id':'a'*64,'channel':'api'})
b = r.json()
print('offer:', b['offer_id'], '| price:', b['price_lyd'])
print('binding:', [c['name'] for c in b['applied_constraints'] if c['binding']])
assert b['reason_codes'], 'no reason codes -- unexplainable offer'
"
```

**Check 3** — a cohort run respects the budget and the guard rejects
candidates. The rejection counts are the most persuasive thing in the demo:

```bash
python -c "
from cvm.decision.budget_lp import allocate
r = allocate(budget_lyd=144_000)
print('allocated:', round(r['cost_lyd'], 2), 'of 144000')
print('rejected by guardrail:', r['rejections'])
assert r['cost_lyd'] <= 144_000
"
```

---

## Phase 9 · Surfaces — 2 days

**Check 1** — `/health` reports `ok`, which it does only when every model is
loaded and the feature store is readable:

```bash
python -c "
from fastapi.testclient import TestClient
from cvm.api.main import app
b = TestClient(app).get('/health').json()
print(b['status'], b['models_loaded'])
assert b['status'] == 'ok', 'still degraded -- check models_loaded'
"
```

**Check 2** — latency. Delete the `xfail` on the p95 test:

```bash
pytest tests/integration/test_api.py::test_tabular_scoring_meets_the_p95_budget -q
```

**Check 3** — the dashboards render with no traceback:

```bash
streamlit run apps/command_center/Home.py
streamlit run apps/channel_sim/Home.py
```

Click every screen. Arabic copy must render right-to-left, and the SMS preview
must enforce the real 70-character UCS-2 limit rather than 160.

---

## Phase 10 · Ship — 2 days

**Check 1** — Docker, from a clean clone. Start Docker Desktop first; the
daemon has never run on this machine, so D1 is unverified:

```bash
docker compose up --build
```

**Check 2** — the definition of done, on a machine that is not yours. This is
the one that catches people:

```bash
git clone <your-repo-url> /tmp/clean && cd /tmp/clean && docker compose up
```

**Check 3** — the contract test with your teammate's component, against the six
frozen endpoints in `docs/INTEGRATION.md`.

**Check 4** — three timed dry-runs of the demo. Not two.

---

## If you fall behind

You have about 15 working days and this is roughly 25–32 days of work, so
assume you will. Cut in this order, and cut early — a narrow system that runs
end to end beats a broad one that does not.

| Cut | Saves | Costs you |
|---|---|---|
| CTGAN, ship the copula | 2–3 days | One deliverable row; the copula population is still gated and still defensible |
| Hierarchical clustering | half a day | A cross-check, not a result |
| Random Survival Forest challenger | half a day | Cox alone still answers *when* |
| Optuna tuning | 1 day | A few points of PR-AUC |
| Evidently drift monitoring | 1 day | A monitoring story you can describe instead of demo |
| Channel simulator | 1–2 days | Demo polish. Cut this before cutting anything above it |

**Never cut:** temporal splits and the leakage gate, isotonic calibration, the
Criteo validation, the six guardrails, the M4 safety guards, the control
holdout, or the honest-metrics disclosure. Those are the project's argument. A
system that ships without them is a different and much weaker project.

---

## The three things most likely to go wrong

**Point-in-time correctness, silently.** No library does it for you, nothing
warns you, and every number downstream is invalid. This is why Phase 3 gates
Phase 4 and why the leakage suite is a required CI job.

**The quality gate fighting back.** Three simultaneous constraints on a
generative model. Budget for iteration, and take the copula path if it bites.

**Validation data deferred until it is too late.** Criteo, Hillstrom and Online
Retail II are ~350 MB, need no credentials, and each converts a claim into a
measurement. Fetch them in Phase 1. Everything else in this roadmap can slip a
day; these are what make the results mean anything.
