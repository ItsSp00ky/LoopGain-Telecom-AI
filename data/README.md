# Data

**Nothing in this directory is committed.** Everything here is either
downloaded from a public source or generated from one. `python
scripts/download_data.py` refills `raw/` and `external/`; `pwsh tasks.ps1
pipeline` produces the rest.

```
raw/         Untouched source downloads, exactly as fetched
interim/     Deduplicated, schema-validated, identifiers hashed
processed/   features_offline.parquet, sequences_offline.npz, features_online.duckdb
synthetic/   CTGAN output -- the generated Libyan subscriber population
```

---

## The strategy: real structure, generated locality

No public Libyan CDR dataset exists, and none should — subscriber data cannot
legally or ethically leave an operator. The corpus is hybrid:

- **Real public datasets** supply the statistical structure of telecom
  behaviour: usage distributions, churn base rates, feature correlations, and
  genuine labels for validation.
- **A CTGAN** adds the Libyan prepaid layer: LYD recharge denominations,
  scratch-card channels, dual-SIM leakage, outage exposure, advance repayment.
- **The operator's real catalogue and tariffs** (`conf/catalogue.yaml`,
  `conf/market.yaml`) fix the monetary scale: 57 real bundles, the confirmed
  3/5/10/20/40/100 LYD recharge ladder, and published pay-as-you-go rates.

**No geography.** All subscribers are modelled as geographically equivalent —
no districts, no cells, no coordinates. Network quality survives as a
subscriber-level feature drawn from real data (UCI `Call Failures`, Cell2Cell
`dropvce`), not as a map.

Synthetic metrics are **not** evidence of production performance. The
deliverable is a validated pipeline and decision logic with a deployment-ready
schema. The report says this plainly and so does the pitch.

**No real subscriber data from any operator is present in this repository, at
any stage.** Identifiers are SHA-256 with salt from the moment of ingestion.

---

## Sources

### A — Iranian Churn Dataset (UCI 563) · PRIMARY

| | |
|---|---|
| Source | <https://archive.ics.uci.edu/dataset/563/iranian+churn+dataset> |
| Access | `from ucimlrepo import fetch_ucirepo; d = fetch_ucirepo(id=563)` |
| Size | 3,150 rows × 13 features + churn label |
| Licence | **CC BY 4.0** — attribution required |
| Credentials | none |

Collected from an Iranian operator over 12 months. Attributes aggregate months
1–9; the label is customer state at month 12, with a 3-month planning gap.

Why it anchors the project: it is the closest public analogue on four axes at
once — **prepaid**, **MENA-region**, contains a **network-quality feature**
(call failures) that most churn datasets omit, and its **9-month observation /
3-month prediction gap** is exactly the operational framing a real campaign
needs.

**Two mandatory corrections before use:**

1. Roughly **300 duplicate rows (~9.5%)** — exact-match deduplication required.
2. The pre-computed **`Customer Value`** field partially encodes the outcome.
   It is excluded from the feature matrix (`conf/features.yaml`), which is why
   our reported metrics are lower than the published ~97% accuracy / ~0.99 AUC.

### B — Cell2Cell (Duke University / Teradata CRM Center) · SCALE & SEQUENCES

| | |
|---|---|
| Source | <https://kaggle.com/datasets/jpacse/datasets-for-churn-telecom> |
| Size | 71,047 rows × 58 features (51,048 labelled / 19,999 unlabelled holdout) |
| Class balance | ~29% churn in the labelled split |
| Licence | public research terms |
| Credentials | Kaggle (`KAGGLE_USERNAME` + `KAGGLE_KEY`) |

Supplies volume and, critically, **trend and degradation features**:
`changem` (percent change in minutes of use), `changer` (percent change in
revenue), `dropvce`, `blckvce`, `unansvce`, care-call counts, handset
attributes. These are the direct ancestors of our
`revenue_decay_ratio_7d_30d`.

Also what makes the **M1 LSTM benchmark meaningful** — an LSTM on 3,000 rows
would prove nothing. The unlabelled holdout doubles as the inference load test
for the p95 latency evidence.

### C — IBM Telco Customer Churn (extended) · BENCHMARK & CLV

| | |
|---|---|
| Source | IBM Cognos community sample; mirrored on Kaggle |
| Size | 7,043 customers × ~19–33 features |
| Churn rate | ~27% |
| Licence | IBM public sample |
| Credentials | Kaggle |

The extended release carries **Churn Reason** (a labelled categorical
explanation), **CLTV** (a benchmark lifetime-value target), and **Churn Score**.

Three roles: an independent CLTV benchmark for M2, a sanity check that our
churn drivers resemble real ones, and a small fast dataset so the first
baseline is never blocked on pipeline work.

### D — OpenCelliD · **removed**

Geography is out of scope, so there are no cells to join to. Dropping it also
sheds an API key and a CC BY-SA attribution obligation on every slide.

Network quality is kept as a **subscriber-level** feature instead, sourced from
the real datasets above (UCI `Call Failures`, Cell2Cell `dropvce` / `blckvce` /
`unansvce`) rather than from a tower map.

---

## Recommended additions

Not in the original proposal. Each closes a specific hole, and each is free.
Ordered by how much they improve the project.

### F — Criteo Uplift Prediction · **fills the biggest gap**

| | |
|---|---|
| Source | <https://ailab.criteo.com/criteo-uplift-prediction-dataset/> |
| Mirror | <https://huggingface.co/datasets/criteo/criteo-uplift> (13.98M rows, ~297 MB compressed) |
| Size | 25M rows × 11 features + `treatment`, `conversion`, `visit`, `exposure` |
| Licence | free for academic and research use |
| Credentials | none |

**Why this matters more than anything else on this list.** The uplift model in
M3 decides who gets budget, and right now it can only be validated against
response data we generated ourselves — which means we cannot honestly claim the
two-model difference works. Criteo is a *real* incrementality test with genuine
treatment and control arms. Train and validate the uplift method here, then
apply the validated method to the synthetic population.

That converts "our uplift model scores well on data we made up" into "our
uplift method is validated on 25M real randomised rows, then applied to a
Libyan population". It is a direct answer to the evaluator question *"your data
is generated — how do we know it works?"*

Note: the data is deliberately sub-sampled non-uniformly so the original
incrementality level cannot be recovered. Use it to validate *method*, not to
quote an effect size.

### G — Hillstrom MineThatData E-Mail Challenge · small uplift warm-up

| | |
|---|---|
| Source | <http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv> |
| Easiest access | `pip install scikit-uplift` then `from sklift.datasets import fetch_hillstrom` |
| Size | 64,000 customers; three arms (Mens email / Womens email / no email) |

The classic teaching set for uplift. Get the two-model difference working here
in an afternoon — it is small enough to iterate on — then move to Criteo for
the real validation. Also a clean place to demonstrate the four quadrants
(persuadable, sure thing, lost cause, **sleeping dog**), which matters because
the sleeping-dogs guard is a stated commitment.

### H — KKBox WSDM Churn Challenge · real daily sequences

| | |
|---|---|
| Source | <https://www.kaggle.com/c/kkbox-churn-prediction-challenge/data> |
| Size | ~1M members; `transactions`, `user_logs` (daily), `members` |
| Credentials | Kaggle (accept the competition rules to download) |

**The closest public analogue to prepaid silent churn.** Churn is defined as
*no renewal within 30 days of expiry* — an absence, not a cancellation, which
is exactly our target definition. And `user_logs` is genuinely daily
per-user activity, which is what the M1 Arm B LSTM needs. Cell2Cell gives
scale; KKBox gives real **sequences** and a real **no-renewal** label.

It is also large (the raw logs are several GB), so subsample before use — you
have limited disk.

### I — Telecom Italia / Milan CDR · **no longer needed**

| | |
|---|---|
| Source | <https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/EGZHFV> |
| Kaggle mirror | <https://www.kaggle.com/datasets/marcodena/mobile-phone-activity> |
| Size | 62 daily files, Nov 2013 – Jan 2014; 100×100 grid, 10-minute intervals |
| Contents | SMS in/out, call in/out, internet traffic per cell per interval |
| Licence | **ODbL** (Open Database License) — share-alike, attribution required |

Its only purpose was real per-cell load curves for off-peak trough detection,
and that went with geography. **M3 now uses Almadar's own published
06:00–11:00 window** (عروض الصبح), which is stronger evidence than any trough
we could detect ourselves — the operator has told us when its spare capacity
is.

Listed here only so nobody re-discovers it and wonders why it was skipped. If
you ever need real cell-level load shapes, this is where they are, and note
ODbL is share-alike.

### J — UCI Online Retail II · CLV validation

| | |
|---|---|
| Source | <https://archive.ics.uci.edu/dataset/502/online+retail+ii> |
| Access | `from ucimlrepo import fetch_ucirepo; d = fetch_ucirepo(id=502)` |
| Size | 1,067,371 transactions, Dec 2009 – Dec 2011 |
| Licence | **CC BY 4.0** |
| Credentials | none |

The canonical validation set for BG/NBD and Gamma-Gamma — it is what the
`lifetimes` documentation is written around. Non-contractual, transaction-level,
with enough history for a real holdout.

M2 currently benchmarks CLV only against IBM's `CLTV` field, which is itself a
model output, not ground truth. Fitting BG/NBD here first proves the
implementation is correct before you point it at recharges.

### Worth knowing about, lower priority

| Dataset | Link | Why you might want it |
|---|---|---|
| KDD Cup 2009 (Orange) | <https://kdd.org/kdd-cup/view/kdd-cup-2009> | Real telco, 50k customers × 230 anonymised features, with churn/appetency/up-selling labels. Brutally noisy — good for a robustness check, bad for interpretation. |
| IBM Telco base version | <https://www.kaggle.com/datasets/blastchar/telco-customer-churn> | The widely-mirrored 7,043-row version, if the extended release with `CLTV` and `Churn Reason` is hard to locate. |
| Cell2Cell "new" variant | <https://www.kaggle.com/datasets/jpacse/telecom-churn-new-cell2cell-dataset> | Same source, different preprocessing. Compare row counts before assuming they are interchangeable. |

### Suggested order of work

1. **IBM Telco** — small and fast, unblocks the Week-1 baseline immediately.
2. **UCI Iranian** — the primary set; do the dedup and leakage audit here.
3. **Hillstrom** → **Criteo** — get uplift validated early, since it gates M3.
4. **Cell2Cell** — scale, and the trend features.
5. **KKBox** — only if the LSTM arm needs more sequence signal than Cell2Cell gives.
6. **Online Retail II** — when you start M2's CLV.

### Disk budget

You have roughly 20 GB free. Do not download everything at once.

| Dataset | Approx. size |
|---|---|
| UCI Iranian, IBM Telco, Hillstrom | < 30 MB total |
| Online Retail II | ~45 MB |
| Cell2Cell | ~100 MB |
| Criteo Uplift | ~300 MB compressed, ~3 GB expanded |
| KKBox | ~30 GB raw — **subsample on download or skip** |

For KKBox, `user_logs` is the huge file; sample members first, then filter the
logs to that member set while streaming.

---

## Synthetic output (`synthetic/`)

Generated by `cvm.synthesis` — CTGAN (primary), TVAE (challenger), Gaussian
copula (classical baseline), then quantile mapping onto the LYD scratch-card
ladder, then business-rule overlays (outage exposure, Ramadan seasonality,
salary-week spikes, advance repayment behaviour).

**Quality gate.** Output is rejected and the generator retrained unless:

| Gate | Threshold |
|---|---|
| KS-complement on continuous marginals | ≥ 0.85 |
| Pairwise correlation delta | ≤ 0.10 |
| **Discriminator detection AUC** | **≤ 0.65** |

The third is the one worth a slide: a LightGBM classifier trained to separate
real rows from synthetic ones should not manage better than 0.65 AUC. **We
evaluate our GAN with an adversarial test — the same principle that trains it.**

Every generated field, its type, and its generation logic are documented in
[../docs/data_dictionary.md](../docs/data_dictionary.md). Adding a generated
field without a dictionary entry will get the PR rejected.

---

## Attribution block

Reproduce this wherever the datasets are used — report, slides, README of any
derived artefact:

> Iranian Churn Dataset, UCI Machine Learning Repository (ID 563), CC BY 4.0.
> Cell2Cell dataset, Duke University Teradata Center for CRM.
> IBM Telco Customer Churn sample, IBM.

Add Criteo, Hillstrom, KKBox or Online Retail II to this block if you enable
them — each carries its own terms.
