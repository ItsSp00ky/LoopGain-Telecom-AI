# Roadmap

**90 functions left, in a chain that cannot be reordered.** This document is
the order, and after every step a command that tells you whether you got it
right. If a check fails, do not move on — every layer below inherits the
mistake, and the expensive failures here are the silent ones.

**Phases 1 and 2 are written.** Layer 1 is at 100%, layer 2 at 100%, the whole
project at **59%**. Phase 2's code is complete but its quality gate does not yet
pass — see that section before starting phase 3, because it decides whether the
population you build features on is usable.

## Two commands

Where you are:

```bash
python scripts/progress.py
```

Whether the last phase actually landed:

```bash
python scripts/check_phase.py 1
```

`progress.py` prints the burn-down by layer and names the next phase;
`--detail` lists every remaining function. `check_phase.py` runs that phase's
verification and prints PASS, FAIL or PEND per check. **PEND is not a
failure** — it means the layer being checked is not built yet, and it names the
phase that fixes it. Omit the number to run every phase.

Every checkpoint below is one of those two commands. That is deliberate: the
inline `python -c "..."` one-liners this document used to carry do not survive
the trip between shells. `cp` is not a command on Windows, quoting rules differ
three ways, and a multi-line `-c` string cannot be typed into `cmd.exe` at all.

> **Shell.** Commands are plain `python ...` invocations that work identically
> in `cmd.exe`, PowerShell and bash. Where a shell built-in is genuinely
> needed, both spellings are given. Activate the environment first with
> `conda activate cvm`.

**Environment.** The `cvm` conda env is built and working (Python 3.11.16, 39
of 40 packages). Either `conda activate cvm` first, or call it directly as
`D:\Anaconda\envs\cvm\python.exe`. Everything below assumes one of those.

---

## Phase 0 · Setup — three things, about 30 minutes

Almost everything is already done. This is what is left.

### 0.1 `.env` with a real salt — **DONE, do not redo**

⚠ **`.env` already exists with a working 64-char salt, and three Parquet files
in `data/interim` are hashed against it.** Re-copying `.env.example` over it
would restore the `CHANGE_ME` placeholder and break every landed hash.

If you ever do need a fresh one — a new machine, CI, the demo host — note that
a salt shared across environments only has to leak once, so generate a separate
value each time:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then copy the template and paste the value over the placeholder. The copy is
the one genuinely shell-specific step in this document:

```bash
copy .env.example .env
```

(`cmd.exe`; in PowerShell `Copy-Item .env.example .env`, in bash `cp`.)

### 0.2 Prove the skeleton runs

```bash
python scripts/check_phase.py 0
```

Expect 6 PASS and 1 PEND. The pending one is the git remote, which is step 0.3.
It checks Python 3.11, the 15 key packages, the salt, that `.env` is
gitignored, the full test suite, and ruff + black.

The 9 `xfail`s in the suite are not failures. Each marks something in this
roadmap that is not built yet, and you turn them green as you go.

### 0.3 Push to GitHub

Nine commits, no remote. Getting this in front of your team was the point.

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

## Phase 1 · Ingestion — **DONE** (13 functions + 3 new loaders)

**Built first because the privacy commitment is enforced here**, and because
every later layer reads what it writes. All six sources load; five land or
cache, and the results are below.

| Source | Result |
|---|---|
| A UCI Iranian | 2,850 rows after dropping **exactly 300** exact duplicates (9.52%) |
| B Cell2Cell | 100,000 rows joined 1:1, **22** protected/marketing columns dropped at the boundary |
| C IBM Telco | 7,043 rows, **12** protected/geographic columns dropped, 11 blank `Total Charges` kept as null |
| F Criteo | 311 MB archive cached, seeded 10% sample |
| G Hillstrom | 64,000 rows, naive lift **6.09 pp** (7.66 pp on the men's arm alone) |
| J Online Retail II | 805,549 of 1,067,371 lines kept, 5,878 customers, 71.3% repeat buyers |

**The proposal's two headline data claims are confirmed against the files.**
The UCI duplicate count is 300 on the nose, and Cell2Cell's measured medians
are 0.280 for `incoming_outgoing_ratio` and 0.424 for `offpeak_data_ratio` —
both exactly as quoted.

### One finding that changed a document

Cell2Cell's decay figure — median 1.012, 46.8% declining — was quoted against a
feature named `revenue_decay_ratio`, but it comes from `avg3mou / avg6mou`:
**minutes, not revenue.** Computed properly they disagree, and the disagreement
is the point:

| | median | declining |
|---|---|---|
| `usage_decay_ratio` (minutes) | 1.012 | **46.8%** |
| `revenue_decay_ratio` (spend) | 1.000 | 42.2% |

Usage turns down before spend does, which is the entire reason a decay ratio is
an early warning. Generating one and labelling it the other would have flattened
the signal the feature exists to carry. Both are now measured and named
separately in `conf/data.yaml`, the data dictionary and the proposal.

Also worth knowing for phase 2: the source *columns* are 0% null, but the
derived *ratios* are undefined for 3–8% of subscribers, because someone who
placed no calls has no incoming/outgoing ratio. Those rows are excluded from the
fitted quantiles rather than coerced to zero, which would drag the very
distribution the generator is trying to reproduce.

### Six traps this phase hit

Worth reading before you touch phase 2, because four of them will bite again.

**0. Criteo ships two post-treatment columns next to its features, and the
first version of the loader passed both straight into the feature matrix.**
`conversion` is strictly downstream of `visit` — a user who converted visited —
so it is the label in a thin disguise. `exposure` is whether a treated user was
actually shown the ad, decided *after* assignment, so conditioning on it breaks
the randomisation that makes the dataset worth using at all.

Both are now dropped and an assertion refuses to return a frame containing
either. This is the same driver/artefact distinction the synthesis layer makes,
met in real data rather than generated data — and it was caught by printing the
feature list rather than by any test, which is the argument for printing the
feature list.

**1. `sklift.datasets.fetch_criteo` is dead.** It points at a hardcoded S3
bucket that returns **403**, and Criteo's own `go.criteo.net` link returns
**404**. The library everyone reaches for cannot fetch the data this project's
strongest claim depends on. The dataset is still on HuggingFace, so
`cvm.ingest.criteo_uplift` downloads from there directly — no credential, no
`datasets` dependency, 311 MB cached once, then a seeded 10% Parquet sample
taken *during* a chunked read rather than after loading 14M rows.

**2. `ucimlrepo` cannot fetch dataset 502.** Online Retail II exists in the UCI
repository but is published as a two-sheet Excel workbook, so
`fetch_ucirepo(id=502)` raises `DatasetNotFoundError`. The loader pulls the
static archive and reads **both** sheets — one sheet is half the period, which
halves every observed inter-purchase time and biases BG/NBD toward short
lifetimes.

**3. The conda env is not writable by your user.** `pip install` silently falls
back to the user site (`%APPDATA%\Python\Python311\site-packages`), and a
cross-drive metadata rename then fails with `WinError 17` *after* the package
is already in place — so it looks broken but works. `scikit-uplift` and
`openpyxl` both live there now. Worth fixing properly before a teammate clones
this.

**4. `openpyxl` was undeclared.** Dataset C ships as `.xlsx`; `read_excel`
raised. Now in the core dependencies.

**5. The MSISDN scanner had two real gaps and one false positive.** It missed
the international spelling (`+218` drops the trunk zero) and grouped digits
(`091 234 5678`), and it matched *inside its own SHA-256 digests* — a 64-char
hex string frequently contains `094` followed by seven numeric characters, so
whether the scan passed depended on the salt. All three are fixed, the pattern
is now imported rather than re-spelled in the test, and 10,000 digests across
50 salts come back clean.

### How it was verified

```bash
python scripts/check_phase.py 1
```

Nine checks, all passing: the UCI duplicate audit against `conf/data.yaml`, the
leaky field absent from the honest path and present in the naive one, the
Cell2Cell 1:1 join with 22 protected columns gone, all four measured medians
against the documented figures, IBM's 12 protected columns gone, Criteo's arms
with no post-treatment leak, Hillstrom's arms, Online Retail II's cleaning, and
an MSISDN scan over every landed Parquet file.

To run the pipeline itself, or the leakage suite:

```bash
python -m cvm.ingest.run
python -m pytest tests/leakage -q
```

`cvm.ingest.run` prints a table of every source with its row and column counts
and exits non-zero if any source fails, so a broken loader cannot pass quietly.
Two previously-`xfail`ed tests are now green and marked `slow`:
`test_uci_duplicate_rows_are_dropped` asserts the count against
`conf/data.yaml` *and* that no duplicate survived `load()`, and
`test_uci_leaky_field_is_dropped_by_default` asserts `Customer Value` is absent
from the honest path and present in the naive one — the naive reproduction is a
deliberate feature, not a bug.

To re-measure Cell2Cell's grounding figures at any time:

```bash
python -c "
from cvm.ingest.cell2cell import measured_distributions
for k, v in measured_distributions().items():
    print(f'{k:<26} median {v[\"median\"]:.3f}  p10 {v[\"p10\"]:.3f}  p90 {v[\"p90\"]:.3f}')
"
```

---

## Phase 2 · Synthesis — **BUILT, GATE NOT YET CLEARED**

**Every function is written, the environment is fixed, and every generator
runs. None of them clears the 0.65 detection threshold.** Measured on 20,000
rows with empirical marginals applied:

| | KS >= 0.85 | corr <= 0.10 | AUC <= 0.65 | |
|---|---|---|---|---|
| **real vs real** (floor) | 0.977 | 0.020 | **0.498** | -- |
| Gaussian copula | 0.981 | 0.039 | **0.817** | fail |
| TVAE, 300 epochs | 0.998 | 0.075 | **0.906** | fail |
| copula at full 100k scale | 0.985 | 0.056 | **0.939** | fail |

**The floor is the important row.** Two disjoint halves of *real* data score
0.498 — chance. So the detector and the protocol are sound, and an 0.82 is a
genuine generator deficiency rather than a measurement artefact. It also means
KS and correlation are essentially solved: 0.98 and 0.04 against thresholds of
0.85 and 0.10.

What remains is **dependence structure only**. A Gaussian copula's dependence
is Gaussian by construction and real behavioural data's is not, and a tree
ensemble finds the difference. TVAE is worse, not better. More rows make it
worse still, because the detector has more to learn from.

**The threshold was set on paper before anything was measured.** Published
detection scores for good tabular generators commonly sit in 0.7–0.9, so 0.65
may not be reachable on twelve correlated behavioural columns. That is a
decision to take on evidence, and the evidence now sits in
`conf/data.yaml#quality_gate.measured` beside the number itself.

**It stays failing until someone decides otherwise.** `fail_build_on_breach` is
true and the pipeline exits non-zero, writing no population. Relaxing the
threshold so a generator squeaks through would make every downstream metric a
statement about data a discriminator already knows is fake — exactly what §3.3
of the proposal promises not to do. Changing it is legitimate; changing it
quietly is not.

### The environment problem, and the fix

CTGAN and TVAE would not run at all. The failure read as an OpenMP conflict and
was not one:

```
OSError: [WinError -1066598273] Windows Error 0xc06d007f   (from threadpoolctl)
OSError: [WinError 127] ... Error loading "torch\lib\shm.dll"
```

`KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1` both leave it failing. Two
things were actually wrong, and **both** had to be fixed:

1. **The env's `Library/bin` was not on the DLL search path.** Running
   `envs\cvm\python.exe` directly is not the same as `conda activate cvm` —
   activation prepends it, a direct invocation does not. Without it MKL cannot
   resolve and `threadpool_info()` raises 0xc06d007f, which names neither the
   DLL nor the caller.
2. **torch must be imported before anything calls `threadpool_info()`.** With
   the path fixed, calling it first leaves the OpenMP runtimes in a state where
   `import torch` then dies on `shm.dll`. sklearn calls `threadpool_limits`
   internally and CTGAN goes through sklearn, so any import order touching
   sklearn first is a live grenade.

Both are handled in `src/cvm/_dlls.py`, which runs from `cvm/__init__.py`
before anything else can load a native library. `os.add_dll_directory` alone is
*not* sufficient — MKL's transitive dependencies resolve via PATH — so it
prepends to PATH as well. **You would not have hit this yourself**: you work
inside an activated `(cvm)` prompt, which sets the path already. It was an
artefact of how the tooling invokes Python, and it is now fixed for both.

### What did land, and is verified

| File | What works |
|---|---|
| `quantile_map.py` | Rank-preserving map onto the real ladder (ρ = 0.93), plus the two structural corrections below |
| `hazard.py` | Logistic hazard on six weighted drivers, intercept **solved** so the realised rate pins to 3.5% exactly and tracks any target |
| `overlays.py` | Eight overlays, all with measured output; Ramadan removed, weekend added |
| `ctgan_engine.py` | Copula / TVAE / CTGAN behind one interface, plus `compare_generators` for D2 |
| `quality_gate.py` | Three metrics, `enforce()` raises, and the summary table prints |
| `run.py` | End-to-end orchestration, gate before overlays |

**Two structural corrections the generator cannot express**, both in
`quantile_map.py` and both logged rather than hidden:

* **Point masses.** A continuous generator produces values *near* zero and
  never exactly zero, while real ratio data is full of exact zeros. The
  correction is symmetric and it needed to be: a Beta marginal produced 0%
  zeros where the real data has 7.5%, and a **Gamma marginal produced 40%**
  where the real data has 3.5%. Too many zeros is the case nobody expects and
  it is the worse one. Every share now matches to the decimal.
* **Orderings.** `active_lines <= household_lines` holds for **100.00%** of
  real rows — you cannot have more active lines than lines. A copula models the
  correlation and nothing else, so it generates households with three lines of
  which four are active, and a detector finds every one.

### Three bugs found by running it

**1. The hazard solved the wrong equation.** `1.0 / (1.0 + np.exp(...)).mean()`
is `1 / mean(1 + exp)`, not `mean(1 / (1 + exp))` — the `.mean()` binds to the
parenthesised term. It converged happily to a **9.9% churn rate against a 3.5%
target**, and every calibration claim downstream would have been measured
against a prior nobody chose. One pair of brackets.

**2. Cell2Cell is voice-era.** Measured on the file: `recv_sms_Mean` is 99.1%
zeros, the data-failure ratio is 97.4% zeros, `mou_cdat_Mean` is 86.6% zeros.
It is a ~2001 US dataset from before mobile data. Those columns do not fit
badly — they assert that nobody uses data, which is the opposite of Libyan
prepaid in 2026. Dropped from the backbone, with data and SMS behaviour coming
from the overlays instead. **This source grounds voice behaviour, the leakage
ratio, the off-peak activity split and the decay ratios. That is what it has.**

**3. `offpeak_data_ratio` was grounded on voice.** The measured 0.424 comes from
`mou_opkv_Mean / (mou_peav_Mean + mou_opkv_Mean)` — off-peak share of *minutes*.
Renamed `offpeak_activity_ratio` at the source, with the data ratio *derived*
from it. The transferable claim is that a subscriber active in the off-peak
window stays that kind of subscriber, not that voice and data split the day
identically.

### Two libraries that abort at the C level

Both found by bisection, because there is nothing to read: exit 127, no
traceback, no output.

* `gaussian_kde` as a copula marginal — crashes, and is unusably slow when it
  does not.
* `truncnorm` as a copula marginal — crashes.

Timings on the backbone: beta 8.2s, norm 4.8s, gamma 6.1s, truncnorm crash,
gaussian_kde crash. The config now names beta for bounded columns and gamma for
unbounded ones, with the measurements recorded beside it.

### How to verify it

```bash
python -m cvm.synthesis.run
```

It prints the gate table and **exits non-zero** on a failure, writing no
population. That is the correct behaviour and it is what happens today.

When a generator does clear the gate, these are the checks that matter:

```bash
python scripts/check_phase.py 2
```

Three of them: the gate passes, the generated churn rate is near 3.5%, and no
recharge amount is a denomination Almadar does not print.

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 3
```

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 4
```

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 5
```

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 6
```

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

**First, the phase check:**

```bash
python scripts/check_phase.py 7
```

**Then** delete all five `xfail` markers in `tests/guardrails/test_advance_safety.py`
and run:

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 8
```

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

**First, the phase check** — it will report PEND until this phase lands, then
PASS:

```bash
python scripts/check_phase.py 9
```

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
git clone <your-repo-url> C:/Temp/clean
```

Then `cd C:/Temp/clean` and run `docker compose up` there.

```bash
docker compose ps
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
