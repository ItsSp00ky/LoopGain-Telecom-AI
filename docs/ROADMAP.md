# Roadmap

**Every declared function is implemented — 342 of 342.** What remains is not
code stubs but the two things that turn a pipeline into a demo: the Streamlit
surfaces (phase 9) and shipping it (phase 10).

This document is the order, and after every step a command that tells you
whether you got it right. If a check fails, do not move on — every layer below
inherits the mistake, and the expensive failures here are the silent ones.

**Phases 1 to 9 are written and verified**, and the function burn-down is at
**100%**. The quality gate passes, uplift is validated on Criteo's real
randomised arms at **Qini 0.0771**, both the leakage suite and the guardrail
suite are green with **every xfail deleted**, the decision engine serves at a
**37 ms p95** against a 200 ms budget, and all six dashboard screens render
headlessly in CI.

**Phase 10 is done.** Both images build, the stack comes up, and a real
subscriber is scored through it end to end. Across all eleven phases:
**84 checks passed, 0 failed, 1 pending** — and the one pending is the git
remote, which is a push nobody has made rather than code nobody has written.

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

<a id="phase-0"></a>

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

<a id="phase-1"></a>

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

<a id="phase-2"></a>

## Phase 2 · Synthesis — **DONE, GATE PASSED**

`python -m cvm.synthesis.run` produces **100,000 subscribers × 46 columns** at
a 3.52% churn rate against a 3.5% target, and the gate passes.

| metric | value | threshold | floor | |
|---|---|---|---|---|
| KS-complement | 0.9923 | ≥ 0.850 | 0.977 | pass |
| correlation delta | 0.0231 | ≤ 0.100 | 0.020 | pass |
| detection AUC (logistic) | 0.5187 | ≤ 0.650 | 0.468 | pass |
| TSTR retention | **0.9432** | ≥ 0.900 | 1.000 | pass |
| detection AUC (boosted) | 0.8366 | *reported* | 0.498 | noted |

**FLOOR is two disjoint halves of real data scored against each other** — what a
perfect generator would achieve. Every threshold is set against it rather than
chosen on paper, which is the change that made this section honest.

### The gate was measuring the wrong things

Three metrics became five, and one stopped gating.

**TSTR is now the metric that matters.** Detection asks "can an adversary tell
these apart", which is a proxy. The question this project needs answered is
narrower: *if M1 trains on this population, does it work on real subscribers?*
Train downstream on synthetic, test on held-out real, express it as a fraction
of training on real. **94.3% of the learnable signal survives the round trip**
(0.754 against a 0.799 real-trained baseline, floor 0.51 for shuffled labels).
LightGBM, because M1 is LightGBM.

**Two detectors, two thresholds, and the pairing was the bug.** The original
0.65 was applied to a tuned gradient booster and nothing ever reached it — the
best was 0.77 against a 0.498 floor. But 0.65 comes from the literature, where
the standard detection metric uses **logistic regression**. Applying it to a
booster is a category error. Logistic keeps 0.65 and the population clears it
at 0.519.

**The boosted detector is now reported, not gated**, and that is a judgement
worth defending. It is the only one of the five with no defensible absolute
threshold: it rises without bound with sample size for *any* imperfect
generator — the same generator scores 0.770 / 0.837 / 0.860 at three sample
sizes while the floor stays at 0.498. A threshold with no stated *n* is
underspecified the way a p-value with no stated *n* is. It is printed on every
run beside its floor so a regression toward 1.00 stays visible, and flagged
above 0.90.

**Scored against held-out real rows**, never the generator's own training data.
Scoring against the rows it memorised asks "can you tell this from the training
set", which penalises memorisation twice and says nothing about realism.

### What made the population pass

**A mixture of copulas, one per behavioural cluster.** A single copula imposes
one dependence structure on a population that does not have one — averaging a
commuter and a dormant line produces rows between clusters where nobody lives,
and a detector finds them first. At k=32 (29 clusters fitted, 3 too small):
logistic detection 0.593 → 0.519, correlation delta 0.039 → 0.023.

**Empirical marginals instead of fitted ones.** A copula separates dependence
from marginals; SDV's dependence half was good and its parametric marginal half
truncated every tail — `incoming_outgoing_ratio` to 8.3 where the real maximum
is 24.0, and a Gamma fit piling 40% of its mass on zero where the real data has
3.5%. Taking each marginal from the data instead makes range, quantiles and
point masses match exactly. **KS 0.853 → 0.992, boosted detection 0.9998 →
0.837.**

**Two structural corrections a copula cannot express**, both logged:
point masses (symmetric — too many zeros is the case nobody expects and the
worse one) and hard orderings (`active_lines <= household_lines` holds for
100.00% of real rows).

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

<a id="phase-3"></a>

## Phase 3 · Features — **DONE**

`python -m cvm.features.run` produces **100,000 × 53 columns over 261 snapshot
dates**, split 60/20/20 by time, and `scripts/check_phase.py 3` passes 8 of 8.

| split | rows | share | snapshot range |
|---|---|---|---|
| train | 60,069 | 60.1% | 2026-01-01 → 2026-06-06 |
| validation | 20,032 | 20.0% | 2026-06-07 → 2026-07-28 |
| test | 19,899 | 19.9% | 2026-07-29 → 2026-09-18 |

Three label artefacts dropped (`hazard_score`, `churn_date`, `days_to_churn`);
the target kept.

**On reproducibility, precisely.** Rebuilding all three layers from source
reproduces every Parquet artefact byte for byte — the three interim files, the
population and the offline store. The **DuckDB online store is
content-reproducible but not byte-reproducible**: two writes of an identical
frame produce identical rows and different files, because the format embeds
write-time metadata. Compare that one on content, never on hash. Medians still on their Cell2Cell anchors: leakage ratio 0.280
against 0.280 measured, revenue decay 0.997 against 1.012, off-peak share 0.461
against 0.424.

### The distinction that cost the most time

**`silent_churn_30d` is a label artefact AND the training target.** It is in
`LABEL_ARTIFACT_FIELDS`, and it must be in the feature store, because a store
with no target is a store nothing can be trained on. "May not be an input" and
"must not exist" are different claims, and collapsing them breaks the pipeline
in one direction and leaks in the other.

`drop_excluded_columns` takes `keep_target` for exactly this, and the first
version of the Phase 3 check got it wrong in the opposite direction — it failed
a store that was correct. `snapshot_date` has the same shape of problem: it is
excluded because it would leak the split, and it is also the column the split
is made *on*, which is why `run.py` splits at step 3 and drops at step 4 and
says so in its docstring.

### Five bugs the checks caught

**A single-snapshot population cannot be split temporally.** The generator
originally stamped every subscriber with one observation date, so every split
was arbitrary — a random split wearing the right name. `temporal_split` now
raises below three distinct dates rather than returning something plausible.

**`Lost` silently never fired.** Every `Lost` subscriber also satisfies
`Hibernating`, and the looser rule was tested first, so it swallowed the
tighter one. Eight declared segments, seven reachable, and nothing said so. The
rules are now ordered most-specific first with the reason written at the line.

**`IntCastingNaNError` on the quintiles.** 3% injected missingness leaves those
rows unranked. A missing value now takes the **middle** quintile, not the worst:
dropping them shrinks every cohort, and putting them at 1 asserts that an
unknown recency is a bad recency, which the data does not support.

**`smallest_denomination_lyd: 3` was stale** in `conf/advance.yaml` after the
ladder moved to 5 LYD, so the zero-residual flag was measuring the wrong floor.

**The mutation check found nothing, which is the point of running it.** Both
the recency inversion and the filter-before-dedup ordering in the as-of read
were removed deliberately and the suite caught each one. A test that cannot
fail is not evidence.

### Verify it yourself

```bash
python scripts/check_phase.py 3
```

Expect 8 passed, 0 failed. The two that matter most:

**The leakage suite is the gate for Phase 4.**

```bash
pytest tests/leakage -q
```

Expect `12 passed, 1 xfailed`. The single remaining `xfail` —
`test_a_single_feature_cannot_reconstruct_the_label` — needs a trained M1 and
is Phase 4's to delete. Every other marker is gone.

**Point-in-time serving, on the real store:**

```bash
python -c "from cvm.features.store import get_features; d = get_features(as_of='2026-06-30'); print(len(d), 'rows, latest', d['snapshot_date'].max())"
```

An as-of read goes to the **offline** store, filters, and only then takes each
subscriber's latest row. The other order drops a subscriber entirely whenever
their newest snapshot post-dates the cut-off, which shrinks a backtest cohort
silently instead of answering it.

### Unit coverage

`tests/unit/test_features.py` — 26 tests. Ten cover `splits.py` alone, because
it is the one module here whose failure is invisible: a leaked split produces a
model that scores beautifully, ships, and is worthless, and the only symptom is
that the numbers are *better* than they should be.

---

<a id="phase-4"></a>

## Phase 4 · M1 churn — **DONE**

`python -m cvm.models.m1_churn.run` trains eight models on one temporal split,
calibrates every one of them, fits M1b, and writes six reports.
`scripts/check_phase.py 4` passes 8 of 8.

| model | PR-AUC | lift@1 | recall@1 | Brier | ECE | ROC-AUC |
|---|---|---|---|---|---|---|
| **logistic_regression** | **0.4721** | 6.30 | 63.0% | 0.0248 | 0.0036 | 0.8651 |
| lightgbm | 0.4417 | 6.26 | 62.6% | 0.0257 | 0.0039 | 0.8570 |
| catboost | 0.4195 | 6.34 | 63.4% | 0.0261 | 0.0039 | 0.8628 |
| xgboost | 0.4177 | 6.03 | 60.3% | 0.0263 | 0.0037 | 0.8576 |
| decision_tree | 0.4032 | 5.84 | 58.4% | 0.0265 | 0.0038 | 0.8353 |
| knn | 0.3770 | 5.57 | 55.7% | 0.0268 | 0.0039 | 0.7734 |
| naive_bayes | 0.2672 | 5.98 | 59.8% | 0.0295 | 0.0046 | 0.8241 |
| svm | 0.2314 | 5.14 | 51.4% | 0.0311 | 0.0041 | 0.7952 |

Base rate 3.68%. Accuracy is the last column in the written CSV and the phase
check fails if it ever leads.

### Logistic regression wins, and the reason is the finding

**Read the ranking with care, because the generator is linear.** The synthetic
label comes from a logistic hazard — a weighted sum of standardised drivers
through a sigmoid — so logistic regression is *correctly specified* on this
data. The tree models are being asked to rediscover with step functions a
smooth linear-in-log-odds surface the linear model was handed for free.

This benchmark therefore measures **the generator's functional form** as much
as it measures the models. It is a working pipeline and a fair comparison on
this data. It is **not** evidence about which model wins on real Almadar
subscribers, whose churn is under no obligation to be linear in log-odds. The
verdict paragraph says so on every run, and emits that caveat only when a
linear model actually places in the top two — a warning printed unconditionally
is wallpaper.

The practical consequence: `explain.py` grew a `LinearExplainer`. (Smoke-testing
the serving path also caught the quintile columns rendering as `E is 2` and
`recency raw is 2.95` — the column name with a number after it, which is not a
sentence a marketing analyst can act on.) For a linear
model the SHAP value *is* `coef × (x − E[x])`, exact and unsampled. A serving
path that could only explain the tree arms would have silently dropped every
explanation the day the benchmark changed its mind — which is exactly what
happened on the first run.

### Calibration is the step that does the most work

| | raw | calibrated |
|---|---|---|
| Brier | 0.11859 | **0.02480** |
| ECE | 0.25502 | **0.00363** |
| mean predicted | 0.2919 | 0.0337 |

Observed rate 0.0368. `scale_pos_weight ≈ 27` is correct for ranking at a 3.5%
base rate and deliberately destroys the absolute scale — the raw scores average
0.29 against a 3.7% reality. Isotonic puts them back. Without this step every
`E[gain] = uplift × CLV − offer_cost` in the decision engine is wrong by 8x,
and because the *ranking* is right, every ranking metric says it is fine.

One claim corrected: isotonic is monotone **non-decreasing**, so it cannot
reorder anyone, but it can map distinct scores onto shared values, and those
ties move PR-AUC by about 0.0014. "The AUCs are identical" was the easier
sentence and it was false. The test asserts the real property — sort by raw
score and the calibrated scores never go down.

### The honest-metrics disclosure

| setup | rows | leaky field | split | accuracy | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| naive (as published) | 3,150 | kept | random | 0.9524 | 0.9874 | 0.9301 |
| + duplicates removed | 2,850 | kept | random | 0.9614 | 0.9823 | 0.9087 |
| + leaky field dropped | 2,850 | dropped | random | 0.9661 | 0.9853 | 0.9250 |
| **honest (ours)** | 2,850 | dropped | temporal | 0.9263 | 0.9692 | **0.8033** |

The ~0.99 published ROC-AUC reproduces at 0.9874. **PR-AUC is where the damage
shows: 0.9301 → 0.8033.** Accuracy and ROC-AUC barely move, which is itself the
argument — the two metrics most often quoted are the two least sensitive to the
three things that were wrong. And note the middle rows: removing duplicates
*raises* accuracy. The effects are not additive and the report should not
pretend they are.

### M1b: holding out reversed the result

| | in-sample | **held-out** |
|---|---|---|
| Cox | 0.8492 | **0.8493** |
| Random Survival Forest | 0.8930 | **0.8293** |

**The forest's win was entirely memorisation.** lifelines'
`concordance_index_` and scikit-survival's `.score()` both report the fit on
the rows they were fitted to, and the first run duly reported RSF 0.8962
against Cox 0.8540 — a 4-point win for the forest, and the wrong conclusion.
Scored on rows neither model has seen, the forest drops 6.4 points and **Cox
wins**. The penalised linear model barely moves, which is what a model with no
capacity to memorise looks like.

That matters beyond the leaderboard: the module docstring says a large RSF
margin would mean the proportional-hazards assumption is not holding. On the
held-out numbers there is no such margin, so the assumption stands and Cox's
coefficients can be read as the effects they claim to be.

Two related bugs were found in the same pass: `_design` re-ranked features by
correlation **on the test set** and then zero-filled whatever training had
chosen and test had not, and it imputed with test-set medians.

### No ladder boundaries, and that is the correct answer

The generator places churn dates uniformly across the 30-day outcome window, so
the survival curve falls at a near-constant rate and the three "largest drops"
are the three largest random fluctuations. The first run emitted `[115, 122,
128]`.

**A chi-square against uniformity was the first guard and it was the wrong
test.** With 3,523 events it rejects exact uniformity on trivial overdispersion
(chi2 = 45.7, p = 0.025) and then blesses boundaries that are still noise.
Significance and stability are different properties, and the one that matters
for a ladder cut-point is stability.

The guard is now a bootstrap: resample the events 40 times, recompute the
boundaries, and take the mean per-rank standard deviation. Measured —

| event days | spread | returned |
|---|---|---|
| the real population | 4.0 days | **none** |
| uniform, 3,523 events | 4.2 days | none |
| three planted cliffs at 110/120/130 | 0.0 days | `[110, 120, 130]` |

Tolerance is 3 days: a stage that moves by less than that is the same stage,
one that moves by a week is different advice to a campaign manager. Two halves
of the real events return `[115, 125, 134]` and `[115, 122, 130]` — only day
115 recurs. On real Libyan data the check passes and the cut-points mean
something.

### Seven bugs, one of which was nearly invisible

**LightGBM early-stopped after one tree.** It tracks `binary_logloss` alongside
whatever `eval_metric` asks for, and early stopping watches *every* tracked
metric. `scale_pos_weight ≈ 27` makes logloss degrade from iteration 1, so
stopping fired immediately: **1 tree instead of 97, PR-AUC 0.3076 instead of
0.4556.** The model did not crash and did not look broken — it looked mediocre,
sitting below the decision tree, which is a result you could rationalise. Fixed
by setting `metric` on the constructor; guarded by a hard failure under three
trees and a regression test.

**`_positive_class` mishandled SHAP's list form.** LightGBM's TreeExplainer
returns a *list* of two arrays rather than a 3-D one. Indexing the wrong element
explains the negative class and flips every sign — it raises nothing and reads
as a plausible explanation.

**The survival merge collided on the target,** which is on both the feature and
population sides; pandas suffixed both to `_x`/`_y`.

**The verdict compared the winner to itself** and printed "+0.0%". It now
compares against the best non-linear arm, which is the number a reader wants.

**SHAP ran once per row in the serving path** — 2,188 ms for 500 subscribers
against a 200 ms budget. The explainer is stateless across rows, so one call
over the batch returns identical numbers: **438 ms, 0.88 ms each.**

**Four feature columns were redundant — two exactly, two affinely.**
`recency_raw` *is* `days_since_last_topup`, and `at_recharge_floor` *is*
`data_advance_leaves_nothing` because the data advance and the smallest card
are both 5 LYD — the M4 finding surfacing as two names for one condition.

Fixing those by equality left two more, found only by re-checking the serving
output afterwards: `offnet_share_30d == 1 − onnet_ratio` and
`balance_zero_share_30d == balance_zero_hours_30d / 720`. Both carry |r| = 1.0
and neither is an exact copy.

**That matters more here than it usually would, because the model that wins is
logistic regression.** Perfectly collinear columns leave a linear model's
coefficients unidentifiable — the split between the pair is pinned only by the
L2 penalty, so it is an artefact of regularisation strength rather than a fact
about subscribers. It also put "spent 91 hours at zero balance" and "spent 13%
of the month unable to transact" into the same five-item waterfall, which is
one fact and two sentences.

The matrix goes 56 → 52 columns. Dropped at the model boundary rather than in
the feature layer, so the store keeps its semantics, and logged so that if the
ladder ever changes and the advance stops matching the smallest card, the log
line disappearing is itself information. A correlated-but-distinct column is
deliberately left alone, and there is a test for that too — a guard that eats
real features is worse than the redundancy it removes.

### Verify it yourself

```bash
python scripts/check_phase.py 4
```

Expect 8 passed, 0 failed. The gate for Phase 5:

```bash
pytest tests/leakage -q
```

**Expect `13 passed` with no xfail.** The last marker is gone —
`test_a_single_feature_cannot_reconstruct_the_label` now runs against the real
store. Top univariate AUC is 0.7471 (`days_since_last_topup`, the strongest
hazard driver) against a 0.95 threshold.

That test has a measured limit worth knowing: it catches *deterministic*
reconstruction (`days_to_churn` scores 1.0000) but **not** `hazard_score`, which
reaches only 0.8799 — the label is a Bernoulli draw from that hazard, so the
probability cannot perfectly separate outcomes it governs only in expectation.
Lowering the threshold to catch it would leave no margin over the strongest
honest driver. It is the second line of defence; the named-artefact test is the
first, and neither covers the other.

### Unit coverage

`tests/unit/test_m1_churn.py` — 26 tests. Most guard failures that are silent:
a model that stops after one tree still returns probabilities, an uncalibrated
score still ranks, and an explanation still renders if it says `shap = +0.14`.

---

<a id="phase-5"></a>

## Phase 5 · M2 value — **DONE**

`python -m cvm.models.m2_value.run` validates BG/NBD on real purchases, fits
CLV on the recharge base, and discovers segments three ways.
`scripts/check_phase.py 5` passes 8 of 8.

| | value |
|---|---|
| median CLV (12m, discounted) | 234.17 LYD |
| mean CLV | 495.58 LYD |
| p90 CLV | 1,078.02 LYD |
| **median retention ceiling** | **35.13 LYD** |

At the 40 LYD ARPU reference the annual value is 480 and 15% of it is exactly
**72.00 LYD**, which is the figure the proposal quotes and the consistency test
pins.

### The technique is validated before it is used

BG/NBD on **Online Retail II**, fitted to 2011-06-01 and scored on the 191 days
after it: 4,933 customers, **MAE 1.085** against a mean actual of 1.649,
**Spearman 0.629**, mean predicted 1.605 against 1.649 observed.

This is the same move Criteo is for uplift. Every CLV number for Almadar is
computed on generated recharges from a reconstructed summary, so it cannot
validate itself — a good fit there would only mean the generator and the model
agree with each other. Online Retail II has real repeat purchases with real
timestamps, so fitting one period and scoring the next measures whether the
technique works at all.

**What the reconstruction costs.** BG/NBD wants a transaction log; the
population carries 90-day aggregates, so frequency is `recharge_count_90d − 1`,
T is `min(90, tenure_days)` and recency is `T − days_since_last_topup`. That
loses the WITHIN-window timing: two subscribers who each recharged six times
look identical whether one spread them evenly and the other front-loaded all
six into week one. It is directionally right and it is not a substitute for
transaction data.

T is the observation window and **not** tenure. Pairing a 90-day count with a
five-year T tells the model a weekly recharger transacts ten times a decade,
and every predicted value collapses.

### The segments are not a shape in the data

This is the finding, and it is an uncomfortable one.

| | |
|---|---|
| k by silhouette | **3** |
| k by elbow | 6 |
| silhouette at k=3 | 0.2466 |
| dendrogram's natural cut | **3** |
| declared business segments | 8 |
| rule/cluster disagreement | 63.2% (51.8% at matched k) |
| adjusted Rand | 0.085 (0.137 at matched k) |
| PCA variance in 2 components | 58.0% |

Two independent methods say **three** groups; the business taxonomy says eight.
Adjusted Rand between the rules and the clusters is 0.137 even after forcing
k=8 to remove the granularity confound — the two labellings are close to
independent.

**So the eight RFM-LE segments are a reporting convention, not a discovered
structure**, and the dashboard should say so rather than imply the data
produced them. That is exactly the question hierarchical clustering was put in
the design to answer, and it answered it the inconvenient way. The segments
remain useful — they are legible to a marketing analyst in a way that "cluster
2" is not — but they should be presented as a chosen vocabulary.

PCA is the counterweight: 58.0% in two components means the five dimensions are
carrying genuinely different information, so RFM-LE is not five names for two
things. The taxonomy is redundant; the underlying measurements are not.

### Five bugs, two of them in my own metrics

**A feature was missing from the store, and CLV is what found it.**
`recharge_count_90d` never reached the feature store — velocity carried the
derived ratios and RFM-LE emitted only `frequency_raw`, which is that count
divided by (1 + cv). BG/NBD takes repeat transactions and cannot use a
penalised score. A feature store that can train a churn model and cannot fit a
purchase-frequency model is missing a feature, not expressing a preference.
Added, and the store went 53 → 54 columns; M1 was retrained against it.

**The penalizer chosen to stabilise the fit was what broke it.** 0.01 shrinks
`a` and `b` toward zero, and once b < 1 the dropout Beta is U-shaped and
lifetimes' conditional expectation takes the log of a negative number. Measured
on Online Retail II:

| penalizer | a | b | NaN predictions | MAE |
|---|---|---|---|---|
| **0.0** | 0.157 | **3.317** | **0** | **1.085** |
| 0.001 | 0.086 | 1.274 | 0 | 1.087 |
| 0.01 | 0.047 | 0.570 | **844** | 1.139 |
| 0.1 | 0.017 | 0.203 | 220 | 1.089 |

844 of 4,933, every one a customer with no repeat purchase — the group a
prepaid base has most of. It returned NaN rather than raising. The default is
now 0.0 and the fit is probed for NaN before it is returned.

**A Spearman over quantiles is always exactly 1.000.** The IBM benchmark
correlated two independently sorted quantile vectors, which are monotonic by
construction, so it returned 1.000 for any two distributions whatsoever. A
metric that cannot fail is not evidence, and printing it beside the word
"Spearman" reads as a perfect result. Removed. What survives is the scaled
quantile MAE and the spread ratio, which found something real: our CLV spread
(p90/p10 = 9.84) is **4.4× wider** than IBM's (2.25) — a prepaid base runs from
5 LYD floor-rechargers to heavy users, where a postpaid contract base is
compressed by its own tariff structure.

**Adjusted Rand between 3 clusters and 8 segments is bounded by arithmetic,**
not by disagreement — three groups cannot reproduce eight. The comparison now
runs at matched k as well, and only that one is evidence.

**3% missingness made lifetimes fail to converge** on the first likelihood
evaluation with `NaN result encountered`, which reads like a modelling problem
and is a data problem. Inputs are imputed explicitly, the affected 11.5% are
flagged, and the fit excludes them while scoring keeps them — a subscriber with
no ceiling has no constraint, which is worse than an estimated one.

Two smaller ones: lifetimes' fitters carry a lambda from `fit()` and cannot be
joblib-pickled, which raised at the *end* of the run after every number had
been computed (they now use lifetimes' own serialiser); and the first test
fixture drew frequency and recency independently, which is not a purchase
process at all — the fixture is now generated from a real BG/NBD process with
the parameters fitted on the live base.

### Verify it yourself

```bash
python scripts/check_phase.py 5
```

Expect 8 passed, 0 failed.

```bash
pytest tests/unit/test_m2_value.py -q
```

23 tests. And the guardrail the whole module exists to serve:

```bash
pytest tests/unit/test_proposal_consistency.py::test_clv_ceiling_matches_the_guardrail -q
```

---

<a id="phase-6"></a>

## Phase 6 · M3 uplift — **DONE**

`python -m cvm.models.m3_uplift.run` validates the method on Criteo's real
randomised arms, then applies it to the population and writes the
expected-value table the decision engine consumes.
`scripts/check_phase.py 6` passes 8 of 8.

### Criteo — this is the evidence

| | |
|---|---|
| rows scored (held out) | 419,388 |
| treated share | 85.1% |
| naive lift | +1.050 pp |
| **Qini coefficient** | **+0.0771** |
| **uplift@30%** | **+2.986 pp** |

Targeting the top 30% by predicted uplift returns **2.8× the incremental
retention** of treating everyone. That is deliverable D4, and it is the single
strongest answer to "your data is generated, so how do we know any of this
works?" — real randomised arms, a real counterfactual, a real number.

All four quadrants populate on Criteo: persuadable 20.6%, sure thing 23.6%,
lost cause 49.2%, **sleeping dog 6.6%**. That last one is why the module cannot
be skipped. A system without an uplift model does not merely waste budget on
the 73% who were never movable; it actively causes churn among the 6.6% who
leave *because* they were contacted.

### The generated population is a pipeline test, and it is labelled as one

| | held out |
|---|---|
| rows scored | 30,000 |
| Qini | +0.0091 |
| uplift@30% | +4.911 pp |

The treatment effect here was injected by us, so recovering it shows the
pipeline is wired correctly end to end and says **nothing** about whether
uplift modelling works on Libyan prepaid subscribers. Criteo is the evidence;
this is the wiring diagram. The two are written to separate files with separate
names so a reader cannot mistake one for the other.

### The break-even is tighter than the headline suggests

| | uplift needed |
|---|---|
| at the headline 480 LYD annual ARPU | **1.0417 pp** |
| at M2's median fitted CLV of 234 LYD | **2.1352 pp** |

The proposal quotes `5 / 480 = 1.04 pp` and that is correct for the headline
figure. But M2's fitted median CLV is roughly half the annual ARPU, so on a
*typical* subscriber the offer has to clear **2.14 pp** before it pays for
itself — twice as hard, and above what the Criteo model achieves at depth. Both
numbers are now reported on every run rather than only the flattering one.

This does not break the business case: expected value is computed per
subscriber against *their own* CLV, so the high-value tail carries the
campaign. It does mean the headline break-even is the best case rather than the
typical one, and the report should say which it is quoting.

### Three bugs, and one of them I had already written the warning for

**The population path trained and scored on the same rows.** `validate_on_criteo`
has a docstring explaining that a two-model difference memorises readily —
both arms overfit independently and the difference of two overfits looks like
signal — and then two functions later I did exactly that. It reported **Qini
0.2745 and uplift@30% of +50.8 pp from an injected effect of at most 6 pp.**
Held out properly: **0.0091 and +4.9 pp**, a 30× drop. Numbers that good on
data you generated yourself are the symptom, not the result. A phase check now
fails if the generated population outscores Criteo by more than 3×.

**M2's outputs were features of M3.** `clv_12m` went into the uplift model's
design matrix and then got multiplied by that model's output two steps later,
making the expected value partly a function of itself. `retention_ceiling_lyd`
is 0.15 × CLV and the collinearity guard from Phase 4 was already dropping it —
which is how the first one got noticed.

**The Qini normalisation was non-standard.** The first version divided the area
between the model curve and the random line by the total incremental response.
Right sign, right ordering, magnitude about 3× too large. Radcliffe's
normalisation divides by the *perfect* curve's area, which is what
`sklift.metrics.qini_auc_score` computes and what every published Qini means.
It now agrees with scikit-uplift to **3.1e-05** at 50/50, 85/15 and 15/85 arm
splits — the residual is a discretisation difference, not an error.

Also: the blended incentive, a number the entire business case turns on, lived
only as a hardcoded constant in a test fixture. It is now in
`conf/market.yaml#base.blended_incentive_lyd`, and the proposal-consistency
test reads it from there.

### Verify it yourself

```bash
python scripts/check_phase.py 6
```

Expect 8 passed, 0 failed.

```bash
pytest tests/unit/test_m3_uplift.py -q
```

25 tests. The one that matters most asserts our Qini against scikit-uplift's at
three arm splits, because Criteo's 85/15 is exactly where a wrong rescaling
term hides.

---

<a id="phase-7"></a>

## Phase 7 · M4 advance — **DONE**

`python -m cvm.models.m4_advance.run` trains the two PD heads, measures the
selection bias, corrects it, and scores the base through
`min(f(PD), g(tier), h(CLV), affordability)` with every mandatory guard
applied. `scripts/check_phase.py 7` passes 7 of 7, and **the guardrail suite is
66 passed with every behavioural xfail deleted**.

### The headline case, running

Same subscriber, modal recharge **5 LYD** — the smallest card — repayment
probability **0.92**:

| product | decision | binding term |
|---|---|---|
| نت في وقته (data, 5 LYD flat) | **declined**, `DAY_50MB` offered | affordability_ceiling |
| رصيد في وقته (airtime) | **granted 3 LYD** | affordability_ceiling |

`limit_from_pd(0.92, "data")` returns 5.0 — **PD alone would approve it**. That
is the trap: they probably *would* repay, and the repayment would consume their
entire next top-up and return them to zero. The objective is solvency, not
recovery yield, so affordability declines what PD approves.

And the asymmetry is what makes the argument precise rather than blanket. The
same subscriber is granted **3 LYD of airtime**, leaving 2 LYD of usable
balance after settlement. Clearing that debt still buys them service. Only the
5 LYD rung reproduces the zero-residual problem.

The declined subscriber is told why, in Arabic, and offered the 0.5 LYD bundle
they can afford:

> لا يمكن منح هذه السلفة لأن سدادها سيستهلك رصيد التعبئة بالكامل. يمكنك
> الاستفادة من باقة 50 ميجابايت بنصف دينار.

### Selection bias, measured before it is corrected

| head | observed outcomes | repayment rate | worst covariate imbalance |
|---|---|---|---|
| airtime | 29,054 | 0.9669 | `E` at SMD 5.35, 8 features above 0.25 |
| data | 15,414 | 0.9166 | `data_advance_count_90d` at 3.46, 11 above 0.25 |

Only 38% of the base ever took an advance, so 62% have no settlement outcome —
they never had a debt to settle. The gate is `balance <= 0.5 LYD`, which
**selects on being broke**. That is the inverse of a bank's risk filter, so the
textbook direction of the bias cannot be assumed and is measured rather than
asserted. After fuzzy augmentation the mean PD moves by **−0.019** (airtime)
and **−0.026** (data): a real correction, and a modest one.

### Three bugs, two of which made a broken correction look like a strong one

**`sample_weight` was reaching the constructor, where LightGBM discards it.**
It accepts arbitrary keywords and silently drops the ones it does not know, so
a weighted fit quietly became an unweighted one. Measured on identical data and
weights: **mean p = 0.504 through the constructor, 0.950 through `fit()`**. The
whole reject-inference correction was doing nothing except halving the signal —
each never-borrowed subscriber counted as one positive *and* one negative at
equal weight. `gradient_boosting.train` now takes `sample_weight` explicitly
and **raises** on any other fit-only parameter left in `**params`.

**The calibrator was fitted on the inferred labels.** Fuzzy augmentation gives
each reject two rows, one repaid and one defaulted, so the augmented set is near
50/50 by construction *however the weights fall*. Fitting is fine — the weights
carry the information. Calibrating is not: the isotonic map learns to send every
score toward 0.5. It moved mean PD from 0.97 to **0.61** and that 36-point drop
was being reported as a bias correction. It was the calibrator learning the
shape of the augmentation. Calibration now uses a slice of the **observed**
outcomes, held out before augmentation, because those are the only rows with a
real outcome.

Both bugs pointed the same way, and both looked like success. A correction that
moves an estimate by a third is not a strong correction, it is a broken one —
the phase check now fails above 0.15.

**The module docstring still carried the retired 3 LYD argument**, claiming the
debt *exceeded* the smallest card and locked subscribers out entirely. That was
true when the card was 3 LYD and it is not now. The file says so explicitly
rather than quietly swapping the number, because a reader who remembers the
stronger claim needs to see it was withdrawn.

### What binds, at scale

200,000 decisions over the full base — 100,000 subscribers × 2 products:

| product | approved | mean limit | declined by tier | by affordability | by PD |
|---|---|---|---|---|---|
| airtime | 91,612 (91.6%) | 2.21 LYD | 4,538 | 3,108 | 677 |
| data | 13,294 (13.3%) | 5.00 LYD | 80,417 | 5,531 | 690 |

**The credit model is almost never what binds.** PD declines 677 airtime and
690 data requests; the tier ceiling and affordability decline eighty times as
many. That is the intended shape: PD says who *can* repay, and the safety terms
decide who *should be asked to*.

**52,121 subscribers — 52% of the base — top up at the 5 LYD floor.** That is
the population the zero-residual finding is about, and it is half the base
rather than a tail. They are largely *approved* for small airtime advances
(1 or 3 LYD, which leave change) and largely *declined* the flat 5 LYD data
advance. The asymmetry is doing exactly the work it was designed for.

### Verify it yourself

```bash
python scripts/check_phase.py 7
```

Expect 7 passed, 0 failed. The gate for phase 8:

```bash
pytest -m guardrail -q
```

**Expect 66 passed with no xfail.** Two of those checks sweep rather than
spot-check: 48 combinations of starting limit, modal recharge, lockout risk and
distress all confirm the guards only ever reduce, and 205 cases across the PD
range confirm no invented denomination ever reaches a subscriber.

```bash
pytest tests/unit/test_m4_advance.py -q
```

20 tests, including regressions for both silent bugs above.

---

<a id="phase-8"></a>

## Phase 8 · Decision engine — **DONE**

The four models become one recommendation. `scripts/check_phase.py 8` passes
8 of 8, `/health` reports **ok** with 5 of 5 models loaded, and the three
decision endpoints return 200 instead of 501.

### What the engine decides

Over 40 subscribers:

| outcome | count |
|---|---|
| **NO_ACTION** | **18** |
| MO_20 via off-peak data | 16 |
| MO_20 via on-net minutes | 5 |
| MO_20 via price discount | 1 |

**45% get no offer at all**, and that is the system working rather than
failing. Most of the value here is in the offers it does not make: sleeping
dogs are excluded outright, and anyone whose `uplift × CLV − cost` is negative
is declined before a price is even computed. A run where every subscriber got
an offer would mean the uplift filter and the guardrails were doing nothing.

Only one subscriber in forty got a headline price cut. The rest of the treated
population got capacity — off-peak data or on-net minutes — which costs almost
nothing on an idle sector and leaves the published price sheet intact.

### Serving latency

**p95 37 ms**, median 35 ms, against a 200 ms budget.

The first version read the offline Parquet per request and measured **292 ms
for a single subscriber** — a full 100,000-row scan to answer one lookup, and
linear in the base. The online DuckDB store is one row per subscriber with a
unique index on the id, which is exactly what it exists for.

### Two bugs, one of which corrupted live config

**`replay` was emptying the pricing weights for the whole process.** It swapped
the recorded weights into `load_conf("pricing")` and restored them in a
`finally` — but `load_conf` is cached, so the saved reference and the dict
being cleared were **the same object**. The restore put back what the clear had
just emptied, and every later caller priced with no weights at all. An audit
function that corrupts live pricing config is worse than one that does not
exist. Replay now passes weights through the features dict; nothing global
moves, and there is a regression test.

**PuLP emitted one deprecation warning per decision variable** — 2,358 of them
in a single test run, which is how a real warning gets missed. Switched to
`problem.add_variable`, which is the PuLP 4.0 API. Down to 8.

### A finding that needs a decision, not a fix

**The tier ceiling dominates the discount formula.** The three positive weights
sum to 0.90, so `d(i,b)` spans roughly [−0.20, 0.90] — but the tier ceilings
are 0.05 to 0.20. Measured over uniform random inputs:

| tier | clips at `d_max` | lands strictly inside |
|---|---|---|
| bronze | **96.8%** | 1.9% |
| platinum | **80.9%** | 17.7% |

So for most subscribers the formula reduces to `d(i,b) = d_max(tier(i))` and
the four weighted terms express nothing. The personalisation is real in the
code and almost never visible in the output.

This is **not** a bug — `conf/pricing.yaml` specifies `clip(..., 0, d_max)` and
the code does that. The weights and the ceilings were evidently chosen on
different scales. Scaling the formula **by** `d_max` instead of clipping **at**
it would let all four terms express themselves inside each tier's allowance,
and would change what every subscriber is charged. That is a pricing-policy
decision rather than a refactor, so it is flagged here and documented in
`compute_discount` rather than changed quietly.

### Auditability, which is a commitment rather than a feature

Every decision — including every NO_ACTION — writes its inputs, the weights as
they were at the time, every constraint **considered** (not only those that
bound), the reason codes and the outcome. `replay` re-runs a logged decision
twice, once under the recorded weights and once under today's, and reports
which of the three cases it is: nothing changed, the config moved, or the code
moved. Reporting only "differs" would leave an auditor to work that out by hand.

Storing the weights separately from the inputs is what makes "why did we decide
that **then**" answerable, as opposed to "what would we decide now".

### Verify it yourself

```bash
python scripts/check_phase.py 8
```

Expect 8 passed, 0 failed.

```bash
pytest tests/unit/test_decision.py -q
```

42 tests. Three sweep rather than spot-check: the margin floor across the full
churn range, the budget at four budgets including zero, and the same-budget
blanket comparison at four budgets, where a negative result would mean the LP
objective had a sign error.

---

### The blanket comparison was measuring the campaign against itself

Found by reading the Campaign Builder rather than testing it: **"Saved against
a blanket campaign: 0 LYD"**, directly beneath a chart reporting that 227 of
497 subscribers had been removed by guardrails. The 227 *were* the saving.

Four faults, in one metric.

**The baseline was the wrong population.** `campaign_summary` computed blanket
cost from the allocation frame — whatever the caller passed in. The Campaign
Builder removes sleeping dogs, negative expected value and sub-ceiling CLV
*before* calling, so "blanket" meant "everyone the guardrails already
approved". Whenever the budget did not bind, the two populations were
identical and the saving was necessarily zero. It now takes an explicit
`cohort`, and reports `blanket_baseline` so the answer can never again look
the same whether or not anyone thought about it.

**The campaign was charged twice.** M3's `expected_value_lyd` is
`uplift × CLV − cost` — already net. The screen passed it as
`expected_margin_lyd`, and `campaign_summary` subtracts the cost itself. Net
margin on the default cohort read **20,115 LYD** against a true
**21,335 LYD**: understated by 1,220, which is exactly the campaign cost. The
margin column is gross, the contract now says so, and the screen passes
`uplift × CLV`.

**Viability was gross.** `viable = margin > 0` admits a subscriber returning
3 LYD of retained value for a 5 LYD offer. It is now `margin > cost`, which is
the same break-even the rest of the system is built on, and the LP maximises
net rather than gross — identical while every incentive is the blended 5 LYD,
and not identical the first time a segment gets its own offer.

**Negative margins were clipped away at the call site.** `.clip(lower=0)` on
expected value made a blanket campaign look merely wasteful rather than
value-destroying, which is the one thing the comparison exists to show. (There
was also a `.clip(lower=None)` inside `campaign_summary` — a no-op that reads
like a safeguard. Gone.)

#### And then the fixed metric exposed a flaw in its own framing

With the baseline corrected, the phase-8 check reported that targeting beat a
blanket campaign by **−2,075 LYD**. Arithmetically right, and a bad headline:
the targeted arm is capped by the budget and the blanket arm is not, so the
number was measuring the size of the budget, not the quality of the targeting.

So there are two comparisons now, and the screen leads with the fair one:

| | |
|---|---|
| **Same budget, untargeted** | the same money spread across the cohort without targeting. With a uniform incentive, a random selection of *k* returns *k* × the cohort mean **in expectation, exactly** — no sampling, no seed, no ordering to argue about. This is the one that answers "is the targeting worth anything". |
| **All of them, unconstrained** | what treating the whole cohort would cost and return. This is the one the business case quotes, and it is reported as cost avoided rather than as a margin difference. |

A test sweeps four budgets and asserts the same-budget figure is never
negative: the LP picks the best net margin per LYD available, so it cannot do
worse than the cohort average on equal money. If that ever fails, the
objective has a sign error.

#### What the screen says now

On the default cohort — At-Risk Valuable, risk ≥ 0.05, CLV ≥ 100 LYD:

| | before | after |
|---|---|---|
| Expected net margin | 20,115 LYD | **21,335 LYD** |
| Headline comparison | "saved 0 LYD" | **+14,837 LYD** vs the same money untargeted |
| Discount not spent | — | 1,005 LYD — *all* of it from guardrails, none from the budget |
| Value not destroyed | — | 8,478 LYD |

The saving is split by cause because "a guardrail declined them" and "the
budget ran out" are different events, and summing them into one figure
measured against the wrong baseline is how it came to read 0.

---

<a id="phase-9"></a>

## Phase 9 · Surfaces — **DONE**

Six screens across two Streamlit apps, all rendering against real pipeline
output. `scripts/check_phase.py 9` passes 6 of 6, and every screen is tested
**headlessly in CI** rather than by clicking through before a demo.

| app | screens |
|---|---|
| Command Center | Home, Executive Overview, Segment Explorer, Subscriber 360, Campaign Builder |
| Channel Simulator | USSD menu, SMS preview |

### Three API endpoints had to land first

`/v1/score/churn` was **returning 0.0 for every subscriber** — `score_batch`
was built in phase 4 and never wired, so the endpoint served a stub that looked
like a working model. `/v1/cohort/query` and `/v1/subscriber/{id}` were 501s.
All three now answer, and M1 writes `m1_scores.parquet` for the whole base so
the dashboard is not re-scoring 100,000 subscribers on every filter change.

**Revenue at risk is CLV weighted by probability**, not the CLV of everyone in
the top deciles. 3,500 subscribers at 22% risk is not 3,500 lifetimes of
revenue, and quoting it that way would overstate the headline roughly fivefold
— in the flattering direction, which is when to be careful.

### The screens say what the analysis found, including the awkward parts

**Segment Explorer leads with the finding it would be easier to bury.** Two
independent methods say three groups; the taxonomy says eight; adjusted Rand at
matched k is 0.137. The screen states plainly that the eight RFM-LE segments
are a reporting convention rather than a discovered structure — and then shows
the cross-tab, where the least-pure cluster is the group the rules have no
single word for.

**Executive Overview is built around the do-nothing baseline**, because a model
metric only becomes an executive number when it is next to the alternative. The
uplift it applies is the **Criteo** figure measured on real randomised arms, not
one taken from the generated population, and the caption says so.

**Campaign Builder shows what the guardrails removed before showing what the
budget bought.** Sleeping dogs, negative expected value, subscribers whose CLV
ceiling cannot justify the offer — each with a count and a stated reason. The
mandatory control holdout is on screen, not in a footnote: without a
counterfactual there is no way to isolate net margin impact, which is pain
point P4.

**Subscriber 360 renders the SHAP waterfall as sentences** — "has not topped up
in 23 days", never `days_since_last_topup = 23, shap = +0.14` — and shows every
guardrail that was *considered*, not only those that bound.

### The SMS limit is 70, not 160

GSM-7 gives 160 characters per part. **Any Arabic character forces the whole
message into UCS-2, where one part is 70** — and 67 once a message spans parts,
because the concatenation header costs 6 bytes. Measured:

| message | encoding | parts |
|---|---|---|
| 160 Latin characters | GSM-7 | 1 |
| 161 Latin characters | GSM-7 | 2 |
| 60 Arabic characters | UCS-2 | 1 |
| 71 Arabic characters | UCS-2 | **2** |
| **100 Latin + 1 Arabic** | **UCS-2** | **2** |

That last row is the trap: one Arabic letter in an otherwise Latin message
costs 90 characters of capacity. A preview showing 160 would tell a campaign
manager a message fits in one SMS when it sends as three, and they are billed
per part. All four of the engine's Arabic templates fit one part — the longest
is 51 of 70.

### Privacy, enforced in the UI

The Subscriber 360 lookup accepts 64 hex characters and refuses anything that
looks like a phone number, **before** any lookup or log. A Streamlit widget
value reaches session state and the server log, so rejecting a raw MSISDN at
the backend is too late. There is a check for it.

### The honest state of two things

The retention ladder uses the **configured fallback** boundaries of 7 / 30 / 60,
and logs a warning saying so, because M1b returns no inflections on this
population — the generator places churn dates uniformly, so there is nothing to
derive. The derivation is built and validated; the data cannot feed it yet.

Every screen carries the same notice: these figures come from generated data.
The uplift model is validated separately on Criteo's real randomised arms, and
that is the only performance claim in the project that rests on real outcomes.

### Verify it yourself

```bash
python scripts/check_phase.py 9
```

Expect 6 passed, 0 failed.

```bash
pytest tests/unit/test_surfaces.py -q
```

15 tests, including all six screens rendered headlessly.

```bash
streamlit run apps/command_center/Home.py
streamlit run apps/channel_sim/Home.py
```

---

<a id="phase-10"></a>

## Phase 10 · Ship — **DONE**

`scripts/check_phase.py 10` passes **8 of 8**. The stack builds, comes up, and
reports `/health: ok` from inside a container.

The two Dockerfiles the compose file had always referenced **did not exist**.
`docker/api.Dockerfile` and `docker/ui.Dockerfile` were named by four services
and were never written — deliverable D1 was a compose file pointing at nothing,
which validates as YAML and fails only at build.

| image | before | after |
|---|---|---|
| `cvm-ali-branch-api` | 3.68 GB | **1.84 GB** |
| `cvm-ali-branch-ui` | 3.82 GB | **2.07 GB** |

### The images were installing the whole training stack to serve

The first API build measured 3.68 GB, of which **454 MB was NVIDIA CUDA
runtime**: `xgboost` declares `nvidia-nccl-cu12` unconditionally on Linux, and
nccl is multi-GPU collective communication that a CPU booster never calls.
Behind it, catboost at 269 MB, xgboost at 228 MB, llvmlite at 173 MB.

None of it answers a request. catboost, xgboost, scikit-survival, optuna,
statsmodels, imbalanced-learn and scikit-uplift **build** the benchmark;
nothing loads or calls them at serving time. There is now a `serve` extra —
sklearn and lightgbm to load the artefacts, shap for the Subscriber 360
waterfall, pulp for the campaign LP, lifelines and lifetimes because the
registry deserialises a Cox fit and two BG/NBD fits. **Both images halved.**

Two tests hold that boundary: one asserts `serve` pulls no training-only
package, the other asserts that `cvm/_dlls.py`'s Windows torch preload stays
behind its platform guard — the containers are Linux and do not ship torch, so
an unguarded preload would attempt a missing package on every request path.

### How it was found, which is the more useful story

**Exporting the 3.8 GB UI layer crashed the Docker engine — twice.** It did not
recover from `docker desktop restart`, from terminating the `docker-desktop`
WSL distro, or from a full process kill.

The cause was not Docker. **C: had 5.4 GB free on a 121 GB drive**, and
Docker's WSL data disk had grown to 20.2 GB — mostly build cache from those two
oversized images. The engine ran out of room mid-export and then could not
restart, because WSL2 needs headroom the disk did not have.

Clearing the data disk freed 20 GB and the engine came straight back. The image
was too big, and it was too big for a reason worth fixing — so the crash led to
the `serve` extra rather than being worked around.

### Three smaller things the build caught

**`libgomp1` is not in `python:3.11-slim`.** Without it `import lightgbm` fails
at load with a bare `libgomp.so.1: cannot open shared object file`, which reads
like a Python problem and is a missing system package.

**Streamlit blocks on stdin asking for an email** on first run. A container that
does that never serves and never says why. Fixed with a baked `config.toml`
rather than hoping an environment variable is set.

**The channel simulator mounted only `./conf`.** It calls the decision engine
with the subscriber's real features, so every lookup would have reported "not
in the feature store" — which looks like a data problem and was a compose
problem. It also had no healthcheck, and the shared one would have polled 8501
while it served on 8502.

### A claim of mine that was wrong

The first draft of `api.Dockerfile` said the CPU-only choice was "the
difference between a ~700 MB image and a ~3.5 GB one". The measured image was
**3.68 GB with no torch in it at all**. The docstring carries measured figures
now, not an estimate.

### What the checks verify

Not that files exist — that the system runs.

| check | result |
|---|---|
| docker daemon reachable | 29.8.0 |
| compose file is valid | 4 services, every Dockerfile present |
| images build | api 1.84 GB, ui 2.07 GB |
| **the stack comes up and scores a subscriber** | **api healthy on :8000, and a real subscriber scored through it** |
| containers run as non-root | both run as the unprivileged `cvm` user |
| no secret baked into an image | no salt, token or key in either image or Dockerfile |
| pipeline artefacts reproduce | 7 Parquet files, byte for byte |
| the demo path is runnable | 6 entry points |

`/health` is `ok` only when every model artefact is **usable** and the feature
store is readable. The word doing the work is *usable*, and it was earned late.

---

### The phase was signed off on a check that could not see three live bugs

This section previously said that a stack coming up healthy had proved its
volume mounts were right, and stopped there. That was true and it was not
enough. **Nothing in eleven phases had ever scored one real subscriber through
the running container, or opened a screen in a browser**, and five separate
faults were waiting on those two paths. All five are fixed; recording them
matters more than the fixes.

The first three share a single shape: **a statistic that belongs to training,
taken from the request instead**. All three need the same trigger — a batch of
**one row**, which is exactly what an evaluator does when they look up a
subscriber, and exactly what the test suite never did. The last two share a
different shape: **they are invisible unless you actually run the thing**, one
needing a browser and one needing a container.

#### 1 · The serving image outran its own pickles

`pyproject.toml` said `scikit-learn>=1.5`, so the image resolved **1.9.1**
against artefacts pickled by **1.7.2**. Every artefact deserialised,
`load_registry` logged "7 of 7 loaded", `/health` returned `ok`, Docker marked
the container healthy — and the first real request returned **500**:
`'SimpleImputer' object has no attribute '_fill_dtype'`, a private attribute
the newer `transform()` reads and the older `fit()` never wrote. It took
`/v1/score/churn`, `/v1/subscriber/{id}` and the Subscriber 360 SHAP waterfall
with it.

sklearn had said so, five times, in a warning whose own text is "might lead to
breaking code **or invalid results**" — to stderr, inside a container.

Pinned to `>=1.7,<1.8`; `registry.smoke_check()` now pushes one row through
every estimator at startup, because **loading is not working** and only the
second matters to a caller; version skew logs at `ERROR`, which is the one that
catches the silent case a smoke check cannot — a skewed pickle that still
predicts, just wrongly.

#### 2 · `time_to_churn_days: -9223372036854775808`

`fit_cox` computed the training design — columns *and* medians — and returned
neither, so the artefact never carried them. Serving improvised: it imputed
with `design.median()` over **the batch being scored**. A one-subscriber
request is a one-row batch, and the median of a single NaN is that same NaN.

Two columns are undefined for anyone with fewer than two recharges in 90 days
(`inter_recharge_gap_std`, `recharge_irregularity`). The NaN survived the
`fillna`, went through the Cox linear predictor, and came out of `.astype(int)`
as **INT64_MIN** in the response body — well-formed, schema-valid, and wrong by
nine quintillion days.

This is the same fault `_design(medians=)` was written in phase 4 to prevent.
The parameter existed. The statistic just never reached the artefact.

Fixed at both ends: `fit_cox` attaches `design_columns` and `design_medians`,
and a non-finite expectation now reports `null`, which the contract already
allowed. The artefact was rebuilt through the same seeded path and its held-out
concordance matches the recorded **0.8485359882** to 1e-9 — the same model,
now carrying its design.

#### 3 · Every SHAP bar was exactly zero

The worst of the three, because it did not fail. For a linear model the
attribution is `coef_j · (x_j − E[x_j])`, and both serving callers built the
explainer with **the rows they were about to explain** as the reference
population. For one row, `E[x] = x`, so every contribution is `coef_j · 0`.

Exactly zero, for every feature, for every subscriber — with the right shape,
the right dtype, and a plain-language sentence under each bar reading **"lowers
churn risk"**, because `0 > 0` is false. On a subscriber scored at **1.0000**.

Measured on `/v1/score/churn`. The Subscriber 360 screen never reached this
fault, because it had a worse one in front of it — see #4.

The bundle now carries a 500-row training background; `LinearExplainer`
**raises** on a background of fewer than two rows rather than returning zeros,
and the serving path turns that into no drivers at all. An empty panel gets
reported. Five zero bars get believed.

With it fixed, the same subscriber reads:

```
+4.9521  has not topped up in 117 days — raises churn risk
+1.9362  recharges are irregular (variation 2.33) — raises churn risk
```

Warm p95 for a one-row score is **54 ms** against the 200 ms budget, so the
background costs nothing that matters.

#### 4 · Transposing a Series throws away every dtype

Found by opening the screen in a browser, which is the only reason it was
found at all.

`3_Subscriber_360.py` looked its subscriber up as a one-row frame, squeezed it
to a Series, and rebuilt a frame with `row.to_frame().T`. **A Series holds one
dtype.** Transposing it returns every column as `object`, so `prepare_matrix`
refused all 54 — "not numeric and are not declared categorical".

So the explainability deliverable had never rendered. Not zero bars: no bars,
and a warning in their place, on every subscriber, since the screen was
written. The screen degraded politely and nobody read the warning.

Fixed by keeping the one-row frame instead of reconstructing one. That left
two genuinely non-numeric columns, `tier` and `quadrant`, which the screen
joins on for display — and those turn out to belong in `NOT_FEATURES` on their
own merits: `tier` is M2's output and `quadrant` is M3's, both computed from
scores M1 feeds, so either one entering the churn matrix would be circular.
The numeric check only caught them because they happen to be strings; a
numerically-encoded tier would have sailed through.

#### 5 · `[Errno 30] Read-only file system`

The offer panel died writing `decision_log.jsonl`. `ui` and `channel-sim`
mounted `./data` as `:ro`.

That mount looked right — a dashboard reads, it does not write — and it was
wrong, because these two surfaces call the decision engine **in-process**.
That is the deliberate trade recorded in `ui.Dockerfile`, so the dashboard
survives the API being down. The corollary nobody followed through on is that
a surface which makes decisions has to be able to record them, and this
project's own non-negotiable is that every pricing and advance decision is
logged with its inputs, weights, constraints and reason codes, replayably.

`./data` is now writable for both. `./artifacts` stays `:ro`, and a test
asserts both halves of that.

**Invisible outside a container.** A local `streamlit run` writes to the repo
and never fails, which is why nine phases of local testing never saw it.

#### What the checks do now

`check_the_stack_comes_up` no longer reads a readiness flag. It posts a
subscriber id drawn from the feature store and requires a calibrated
probability back, which exercises the volume mounts, the model load, the
sklearn pipeline, the store read and the response contract in one call.
`/health` gained an additive `model_errors` field, so "degraded" arrives with
the reason attached; `docs/INTEGRATION.md` is unchanged.

Nine tests were added. The pin test was mutation-checked by unbounding the pin, and the smoke check was verified against the actually-broken 1.9.1
container, where it flagged `m1_churn_lightgbm` and nothing else — correct, since only M1's pipeline contains the imputer.

**The honest lesson is not the pin.** Deserialisation was being read as
readiness, a batch was being read as a population, a dtype was being assumed to
survive a transpose, and a read-only mount was being assumed to suit a surface
that writes. Every check in the project agreed with all four.

A green suite and eleven green phases did not mean the thing worked. It meant
nobody had asked it a question the way a person would — typed an id into the
box, or read what came back.

### Still outstanding, and they are yours rather than the code's

- **`git remote`** — nothing has been pushed anywhere. Phase 0.3, and the only
  PENDING check left in the whole project.
- **A clean-clone build on another machine.** Verified here; the point of the
  check is a machine that is not this one.
- **The contract test** against a teammate's component, per `docs/INTEGRATION.md`.
- **Three timed dry-runs of the demo.** Not two.
- **Disk headroom.** C: sat at 5.4 GB free before this phase. It is at ~24 GB
  now, and that is only because Docker's cache was cleared.

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
