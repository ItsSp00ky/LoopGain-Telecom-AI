# Antenna cell placement: completed work and integration handoff

**Integration update (23 September 2026):** The public `recommend`, `all`, `assess`/`predict` and `map` workflow now uses GIS v2 and Ahmed’s explainable heuristic. ML is excluded from primary ranking; old model-based commands are under `experimental`. See [the current integration guide](INTEGRATED_PLANNING.md) for the shared contract, source checks, runnable commands and validation. Historical results and implementation descriptions below retain their original scope.

Updated: 23 September 2026. Comparison and validation runs: 22 September 2026.

**Historical handoff:** The plan below records the pre-integration audit. Its implemented replacement is described in [INTEGRATED_PLANNING.md](INTEGRATED_PLANNING.md).

**Submission follow-up (23 September):** The public output/wording cleanup and portable demo have now been implemented and verified. See [submission readiness](SUBMISSION_READINESS.md). The findings below record the earlier audited state; see the integration update above for current behavior.


This document explains what has been built and checked, what the results mean, and how to combine `mahalm_antenna_cell_placement` with `ahmed_cell_placement`. It is a handoff for the team or the next implementation session. Proposed modules, commands and acceptance checks below are plans, not claims of completed work.

## 1. Decision and intended product

Build a combined system using:

- **Mahalm's corrected GIS calculations, source-scoped Al-Madar attribution, inventory audits, ML evaluation tools and rooftop-footprint review.**
- **Ahmed's explainable planning score, strict eligibility rules, source manifests and contextual data gates.**
- **ML as a separate experimental comparison, initially excluded from the primary planning rank.**

Use the current Mahalm revision as the integration base. Create a separate integration branch so the existing working version remains available. This is a selective integration of behavior and modules; accepting every conflicting file from one side would discard useful work and mix incompatible feature contracts.

The product should answer:

> Which areas and mapped locations should engineers review first, why were they prioritized, and what evidence is still missing?

It cannot currently answer:

> Which antenna installation will deliver a verified coverage or capacity improvement, or which roof is structurally suitable?

For the submission deadline originally given as 23:00 Tripoli time on 22 September, the recommendation was to present the working Tripoli pilot and accurate limitations first. If integration starts before submission, the existing demo should remain separately runnable and the integration should not replace it until its acceptance checks pass.

## 2. Revisions and what was actually done

| Component | Audited revision |
|---|---|
| Mahalm branch | `16f32ef731cce826d26e7cc93ac9b5c6dbc9c6ac` |
| Ahmed branch | `15dc13a021f12f259319d611dc291ab6de9e4bbe` |

A direct GitHub `git ls-remote` check during the audit confirmed that Mahalm's remote branch and local HEAD both pointed to `16f32ef731cce826d26e7cc93ac9b5c6dbc9c6ac`. The working tree was clean at that check. The earlier statement that this commit had not been pushed was incorrect and was corrected.

That verification describes the audited state. This handoff document is a subsequent documentation addition; it is not included in that historical commit merely because the earlier code was pushed.

### Completed review work

1. Fetched the branches and prepared isolated source checkouts/snapshots.
2. Read the actual cleaning, GIS, CLI, map, scoring/model and source-gate implementations and their documentation.
3. Installed separate locked environments using `uv sync --locked`.
4. Ran both test suites and the main evaluation commands.
5. Rebuilt Mahalm's standard features and evaluations, trained the experimental classifier, and reran phase 2 on the frozen examples.
6. Ran Ahmed's commands first with the locally available data, recording missing-data failures.
7. Restored the exact WorldCover and dated OSM sources needed by Ahmed's core planner, verifying the committed sizes and SHA256 hashes.
8. Reran Ahmed's core planner, source gates, coordinate assessment and map generation after restoration.
9. Applied weight-sensitivity analysis to Ahmed's real candidate pool using his unmodified selection logic.
10. Produced a comparison report with the integration recommendation and verification limits.

The audit did not merge branches, change production scoring, promote an ML model or push new changes. Successful HTML generation was checked; browser rendering and RF field performance were not verified.

## 3. Work already implemented on Mahalm's branch

### 3.1 Operator and inventory provenance

The dataset owner's confirmation that the historical group of 645 records belongs to Al-Madar is retained as a source-scoped attribution. The implementation ties it to the fingerprinted import and records its attribution method. It is not a blanket rule that every unknown operator is Al-Madar.

The v2 inventory audit adds network-scoped grouping and observed-bandwidth provenance. Reported bandwidth uses an observed snapshot rather than summing repeated observations into a capacity claim. Physical-site clusters are checked by their complete geodesic diameter, while stable site identifiers are retained pending review of flagged clusters.

The fresh audit found 4,258 observations, 2,338 network-scoped radio groups and 2,115 clustered physical-site references. Five clusters exceeded 50 m diameter; the maximum was 87.06 m. No cross-network legacy-key collisions or repeated-observation bandwidth inflation were detected in this particular input. These checks still matter for future inputs.

### 3.2 Corrected GIS features

Feature version: `gis_v2_density_circles_geodesic_20260922`.

The corrected path includes:

- Converting population density to people using intersected area.
- Population aggregation inside geodesic circles and H3 polygons.
- Explicit nodata, coverage fractions and strict totals instead of treating missing pixels as zero.
- Floor-based raster indexing and preservation of valid negative terrain elevations.
- Terrain derivatives using geographic distances rather than a fixed metre-per-pixel assumption.
- Geodesic site/settlement distances and identity-based exclusion of an existing site's own record.
- Distance to actual road geometry in a local projected coordinate system.
- Actual municipality polygon membership, with historical experiment groups retained separately for controlled comparisons.

The WorldPop file is treated as a population-density product; its exact local provenance still needs care because the shortened filename alone does not establish every upstream variant. Keep the recorded hash, units and metadata when reusing it.

See [Phase 2 GIS and rooftops](PHASE2_GIS_AND_ROOFTOPS.md) and [the v2 extractor](../src/antenna_cell_placement/gis_v2.py).

### 3.3 Separate ML experiment and honest evaluation

The experiment uses observed sites as positives and generated, experimentally labelled non-site examples as negatives. An unrecorded location is not verified unsuitable land. The classifier therefore measures separation within a constructed benchmark, not the probability that a new antenna should be built.

The tooling includes municipality-grouped development evaluation, hard-negative stress tests, simple baselines, frozen example identities and separate experiment artifacts. Phase 2 remeasures the same 6,615 frozen coordinates and compares legacy and corrected GIS features using the same training recipe. The model artifact checks its expected feature version.

The geographic test examples have already been inspected. They are a diagnostic benchmark, not a new blind final test. Full-inventory network features and negative-sampling rules also limit interpretation.

**Important operational boundary:** the corrected phase-2 model was not automatically promoted. Legacy `train`, `recommend`, `predict` and `h3-all` paths still require deliberate migration. Passing phase-2 tests does not mean every public command uses v2 features.

See [ML models and data](ML_MODELS_AND_DATA.md), [the evaluation module](../src/antenna_cell_placement/evaluation.py) and [the phase-2 runner](../src/antenna_cell_placement/phase2_pipeline.py).

### 3.4 Tripoli and building-footprint review

The rerun covered 2,987 Tripoli hexes: 2,216 scored and 771 water-masked. Phase 2 recalculates its GIS features but carries existing building, land-cover and OSM aggregates by H3 identity; it does not rebuild every carried aggregate from its raw source.

The rooftop workflow shortlisted 100 building footprints across 20 ranked areas. Selection uses area priority and footprint area, with review coordinates inside each footprint. It does not rank by height or approve a mounting position.

The two local Microsoft footprint files contained 970,860 records and zero usable heights; 25 geometries were flagged invalid in the new scan. Height `-1` means unavailable. Footprint area is not usable roof area, and ground elevation is not building height.

## 4. Fresh validation results and their interpretation

### Mahalm

| Check | Fresh result | Interpretation |
|---|---:|---|
| Unit tests | **62 passed** | Existing test suite passed at the audited revision |
| Standard classifier random CV AUC | 0.990637 | Easy sampled-label task |
| Standard classifier municipality CV AUC | 0.990431 | Grouping alone does not remove sampling shortcuts |
| Standard held-out municipality AUC | 0.989781 | Population-only baseline: 0.962281 |
| Standard classifier hard-negative AUC | **0.708010** | Population-only: 0.585176 |
| Experimental classifier hard-negative AUC | **0.876141** | Population-only on the same examples: 0.594538 |
| Corrected-GIS experimental hard-negative AUC | **0.885208** | Corrected population-only baseline: 0.571961 |
| Equipment municipality CV accuracy | 0.783924 | Feature-side rule baseline: **0.786761** |
| Tripoli hidden-site recovery AUC | **0.716** | Population-only: **0.767** |
| Hidden-site recovery in unserved hexes | 0.680 | Population-only: 0.724 |
| Tripoli weight sensitivity | Minimum correlation 0.966 | Top-50 overlap: 86-100% |

The controlled feature comparison is **0.876141 versus 0.885208**, using the same frozen examples and recipe. The 0.708010 standard stress result comes from a different training/sample recipe and must not be presented as the starting point of a feature-only improvement.

AUC measures ranking under the experiment's labels. It is not percentage accuracy, covered population, capacity gain or deployment success. The equipment model does not beat the simple feature-side rules in the grouped test. The Tripoli score also does not beat population alone on hidden-site recovery; that diagnostic itself measures historical-site resemblance, not optimal future expansion.

### Ahmed

| Check | Final observed result |
|---|---|
| Unit tests | **49 passed** |
| Candidate generation | 22,317 proposals |
| Eligibility with restored core data | 3,720 eligible; 50 selected |
| H3 gate | Accepted for indexing/aggregation; 100% sampled national coverage, repeatable population allocation |
| WorldCover gate | Review-only; 100% eligible-point coverage; five water candidates removed |
| Building gate | Review-only; 1,268,052 source features; mapped buildings in 43/50 shortlisted H3 cells |
| Selected OSM context gate | Review-only; 3,497 retained features; scores/ranks unchanged |
| Explicit-height gate | Excluded from runtime; 3,042 valid heights, zero in shortlisted H3 cells |
| Coordinate assessment | Succeeded with the core OSM data present |
| Map command | HTML generation succeeded |
| Weight sensitivity | Minimum correlation **0.943252**; separated shortlist overlap **86-100%** |

Ahmed's score uses fixed weights: 40% population, 30% known-site gap, 20% road access and 10% terrain. These are planning assumptions, not learned or independently validated coefficients.

The sensitivity audit changed each weight separately by factors 0.5 and 1.5 and renormalized them. It used the same 3,720 eligible candidates and Ahmed's spatial shortlist selector. Stability is useful evidence, but does not prove the chosen sites improve service. The correlation values from the two branches are not directly comparable quality scores because their candidate domains differ.

H3 IDs and context-only additions are designed not to change the base score. An unchanged rank after adding them is a regression check, not independent validation of the planning objective.

## 5. Data restoration and remaining gaps

The exact following sources were restored in the isolated audit directory, with their committed size/hash records verified:

| Restored source | Size |
|---|---:|
| 27 ESA WorldCover 2021 tiles | 237,710,490 bytes total |
| Dated OSM PBF for explicit heights | 76,584,743 bytes |
| Dated OSM GeoPackage archive | 187,184,805 bytes |
| Extracted dated GeoPackage | 401,502,208 bytes |

The final building scan independently reproduced the 1,268,052-reference-footprint count. The 3,042 explicit OSM heights therefore represent about **0.2399%** of that count, with 19/22 municipalities represented and no heights in Ahmed's 50 shortlisted hexes. These results apply to that dated source and shortlist; they do not imply that no other building heights exist anywhere in Libya.

The older phase-2 document's statement that OSM heights had not been checked describes its earlier state. This later audit establishes the limited OSM height availability above. Related documents should be reconciled during integration.

**Ookla and VIIRS raw inputs were not restored.** Their gate commands were attempted and stopped at source verification. Their saved report figures remain historical claims, not independently reproduced results. They are already excluded from Ahmed's normal runtime, so they do not prevent the current core planner from operating.

Restoration used a separate portable audit helper. Ahmed's five original download scripts still import `fcntl`, which fails on Windows. Installing the locked environment succeeded; source bootstrap is the portability problem.

The restored raw files remain under the audit workspace. They were not silently installed into the main project or added to Git. Integration must deliberately configure or stage those sources and retain their provenance.

## 6. Weaknesses the integration must address

### Mahalm's current public behavior

- The legacy optimizer relaxes constraints when no strict candidate survives; the fallback also omits the road constraint. The combined system must return an explicit no-eligible-candidate result instead.
- Legacy outputs recommend equipment, bands and bandwidth without the operator/RF evidence needed to justify them. The map also calls nearby population “Population Served.” Replace those claims in the public product.
- Corrected v2 features, legacy features and experimental models coexist. A single public feature contract and explicit model compatibility are necessary.
- The existing pilot multiplies priority by `0.75 + 0.5 * suitability`. A bounded multiplier is still an unvalidated assumption; it should not become the combined planner's default.

### Ahmed's current implementation

- Weights, normalization constants and eligibility cutoffs require sensitivity and objective validation.
- Road distance uses sampled points rather than the actual line. Its sampling expression represents a 1,000 m straight road using only the endpoints, causing a 500 m error for a query on the midpoint.
- One UTM zone is used nationally. An analytic 10 km eastward segment at latitude 30/longitude 24 was measured about 0.91% too long. Use the corrected distance approach rather than treating the whole country as one local projection.
- Population catchments can return a finite subtotal even when most pixels are missing. A fixture with only one known 100-person pixel returned 100; missingness must remain distinguishable from complete catchment population.
- `assess` crashes when optional OSM counts are missing because it converts `pd.NA` to `int`. It succeeds with the source present; both states need supported behavior.
- Manifest verification is in separate gate commands, not a complete runtime integrity barrier. Each exported result should be tied to verified input versions.
- The blanket policy against machine-detected footprints is too restrictive for a review layer. Compare attributed Microsoft and OSM observations using quality/completeness checks; neither source establishes a usable roof or surveyed ground truth by itself.

### Scope correction

Ahmed's national H3 support is primarily indexing and population aggregation. Candidate points come from settlement rings and road sampling; it is not an exhaustive search over every national hex. Mahalm already has a national legacy point pipeline; the newer enriched H3/rooftop workflow is the Tripoli pilot. Neither proves nationwide RF planning readiness.

## 7. Target architecture

```text
Verified source manifests + observed telecom inventory
                         |
            Corrected, versioned GIS features
                         |
            Strict eligibility and missing-data checks
                         |
       Explainable planning components and primary score
                         |
          Spatially separated engineering-review shortlist
                         |
            Map / CSV / GeoJSON / source explanations
                         |
           Optional building-footprint review candidates

Separate research path:
Frozen examples -> experimental ML -> matched-baseline evaluation
                                       |
                           explicit promotion decision only
```

### Shared data contract

Every candidate should retain a stable identifier, coordinates, generation source, H3 identity/resolution, municipality, feature version and source/run identifiers. Population must include units, catchment radius, observed subtotal and valid-area fraction. Unknown observations must not be silently converted into zero.

Every recommendation should expose:

- Eligibility status and specific rejection/review reasons.
- Population, site-gap, road and terrain components, plus weight/score version.
- Source availability, date and verification status.
- Operator scope: all-network or the selected operator, stated explicitly.
- Separate optional context fields for buildings/POIs.
- Experimental ML output only when explicitly requested and clearly labelled.

The initial primary score should exclude ML, Cloudflare, Ookla, VIIRS and height multipliers. Existing source context may remain visible where its use is supported. If a different score definition is evaluated, assign a new score version rather than silently changing old results.

## 8. Implementation sequence and acceptance criteria

### Step 1: preserve the baseline and create the integration branch

Inspect current Git status and branch heads; do not assume the audited SHAs are still current. Preserve unrelated changes. Create a new branch such as `integration/antenna-planning-v2` from the chosen Mahalm revision. Record both source SHAs, baseline metrics, data manifests and example outputs.

**Done when:** the old demo still runs separately, the intended integration base is explicit, and no raw data or serving artifact has been overwritten.

### Step 2: establish the common GIS and inventory contract

Keep `gis_v2.py`, `inventory_audit_v2.py` and the fingerprinted 645-record attribution. Add an adapter for Ahmed's expected columns and availability fields. Do not reuse a legacy model with corrected features under the same version label.

**Done when:** known units, nodata behavior, geodesic distances, municipality membership, operator attribution and model-version rejection are covered by meaningful tests.

### Step 3: integrate the explainable score and strict selection

Port Ahmed's score components, strict eligibility, reason codes, candidate IDs and stable tie ordering from `site_optimizer.py`. Separate pure scoring from source loading, selection and exports; a proposed `planning_score.py` can hold the pure functions. Initially reproduce the formula, then document any changes caused by corrected inputs as a new score version.

Remove silent constraint relaxation. Preserve failed-candidate reasons and return a usable empty result when required evidence is absent.

**Done when:** fixed feature fixtures reproduce the expected score, the same input produces the same order, constraints hold for every selected candidate, and empty/missing inputs behave explicitly.

### Step 4: integrate source checks and portable bootstrap

Adapt Ahmed's H3, WorldCover, building and selected OSM modules to the shared contract. Replace Unix-only locks in downloaders, keep atomic downloads and hash verification, and bind gate/source state to exported runs. A proposed `doctor` command should list missing or incompatible inputs before expensive processing.

Allow optional context to be absent without crashing. Keep rejected height/Ookla/VIIRS integrations disabled. Do not treat a passing source-integrity check as independent RF validation.

**Done when:** Windows bootstrap works, an altered required source is rejected, missing optional OSM data is handled by the real `assess` path, and each export identifies its verified inputs.

### Step 5: reconcile public CLI, maps and rooftop review

Make the new public planning commands use the common GIS and primary score. Label nearby population as “population within 5 km,” score as “planning priority,” and buildings as “footprints for review.” Remove unsupported deployment equipment/bandwidth outputs.

Keep `rooftop_candidates.py`; adapt it to the new ranked-area/candidate contract explicitly. National point recommendations must not be passed into a Tripoli hex workflow without a defined mapping. Do not infer height from DEM or footprint area.

**Done when:** a representative Tripoli run produces consistent CSV/GeoJSON/map values; coordinate assessment matches batch scoring; zero-candidate and missing-context maps work; the exact demo is checked in Chrome or Edge.

### Step 6: retain and isolate experimental ML

Retain `placement_model.py`, `evaluation.py`, `training_experiment.py`, `phase2_pipeline.py` and their frozen benchmarks. Put research commands in an explicit experimental namespace and move ML-only dependencies to an optional group where practical. Preserve legacy feature extraction only where controlled historical comparisons still need it.

**Done when:** primary planning needs no model loading, research experiments remain reproducible, feature mismatch fails explicitly, and there is no automatic model promotion.

### Step 7: validate the integrated planning objective

Freeze a common candidate set and compare population-only, gap-only, the explainable score and an optional ML combination. Measure score/shortlist sensitivity to weights, cutoffs, missing data, source versions and H3 resolution.

For hidden-site recovery, remove hidden sites from every relevant network feature and rebuild those features. Interpret this as a historical-placement diagnostic. Reserve a second city or future period before tuning and seek independent engineering/RF/KPI labels for the actual planning objective.

**Done when:** baseline comparisons and failure cases are published, no inspected test is called blind, and the default score is justified as either a provisional heuristic or supported by independent evidence.

### Step 8: document, review and release the integrated version

Update the linked model/data, pilot and phase-2 guides, the dataset overview, README and roadmap so all describe the same public behavior. Keep old benchmark values labelled with their historical inputs. Record operational, experimental, review-only and unavailable features in one status table.

**Done when:** the reconciled tests and CLI checks pass, browser demonstration is verified, artifacts carry source/feature/score versions, and the integrated changes are reviewed before replacing the submission branch.

## 9. File ownership and retirement map

All implementation paths below are relative to `src/antenna_cell_placement/` unless stated otherwise.

| File or group | Integration action |
|---|---|
| `gis_v2.py`, `inventory_audit_v2.py` | Keep Mahalm's corrected foundation |
| `data_cleaning.py` | Reconcile source-preserving behavior; retain Al-Madar provenance and scoped inventory audit |
| `config.py` | Build one explicit source/output/version contract; do not overwrite with either branch's file wholesale |
| `feature_engineering.py` | Migrate public callers to corrected features; retain a clearly isolated legacy path only for required benchmarks |
| `site_optimizer.py` | Adopt Ahmed's strict scoring/selection behavior through the corrected feature adapter |
| `h3_grid.py`, `h3_planning.py` | Reconcile grid construction, identifiers, resolution and population aggregation without duplicate conflicting logic |
| `worldcover.py`, `buildings.py`, `osm_context.py` | Adapt Ahmed's source checks and review context; reconcile existing Mahalm enrichers |
| `building_heights.py`, `ookla.py`, `nightlights.py` | Retain as source-audit/experimental modules; keep unsupported runtime use disabled |
| `rooftop_candidates.py` | Keep footprint-review capability with explicit new ranking inputs |
| `placement.py`, `cli.py`, `map_visualizer.py` | Use one public planning contract and accurate output language |
| `placement_model.py`, `evaluation.py`, `training_experiment.py`, `phase2_pipeline.py` | Keep under research/experimental use; preserve compatibility guards |
| `expansion_score.py` | Preserve historical comparison behavior; retire its ML-weighted path as the public default after migration |
| `tools/download_*.py` | Make cross-platform and provenance-preserving |
| `pyproject.toml`, `uv.lock` | Reconcile dependencies; isolate research extras; regenerate and verify the lock |
| `document/*.md`, README | Reconcile status, metrics, provenance, limitations and runnable instructions |

Delete unsupported deployment-facing equipment/bandwidth generation and obsolete public callers only after the replacement is tested. Do not delete source manifests, raw observations, frozen benchmarks or useful evaluation tests. No specific destructive Git operation is required to begin this integration.

## 10. Test reconciliation

The current 62 and 49 tests are separate suites; their sum is not an integrated test count.

Preserve Mahalm's `test_gis_v2.py`, `test_evaluation.py`, `test_validation.py` and `test_improvement_regressions.py`. Port Ahmed's `test_population.py`, `test_site_optimizer.py` and source-specific gate tests. Reconcile duplicate OpenCellID and Cloudflare tests by intended behavior.

Add integration coverage for:

- Missing optional OSM values through the actual coordinate-assessment command.
- Missing/changed mandatory source files and export provenance.
- Zero eligible candidates without constraint relaxation.
- Known raster units, partial coverage and actual road-geometry distance.
- Preservation of the 645-record attribution and unknown-operator handling elsewhere.
- Consistent feature versions between public scoring and optional model inference.
- Same-candidate, same-source baseline comparisons and deterministic tie handling.

Run focused tests during changes, then both reconciled suites and the complete demonstration path once integration is ready. Passing unit tests does not replace a browser check or independent RF validation.

## 11. Evidence locations and reproducibility limits

The detailed audit and execution evidence are local to the review workstation:

```text
C:\Users\LED\Desktop\GIS\branch_review\
  BRANCH_COMPARISON.md
  audit_runner.py
  audit_probes.py
  restore_sources.py
  ahmed_followup.py
  runs\mahalm\commands.json
  runs\mahalm\fresh_experiment\metrics.json
  runs\mahalm\fresh_phase2\model_comparison.json
  runs\mahalm\fresh_phase2\manifest.json
  runs\ahmed\commands.json
  runs\ahmed\restored\commands.json
  runs\ahmed\restored_osm\commands.json
  runs\ahmed\weight_sensitivity.json
  runs\ahmed\source_restoration_retry.json
```

Ahmed's freshly generated gate JSON files are under the isolated `ahmed/antenna_cell_placement/eval_reports/` directory. The standard Mahalm evaluation is under the corresponding `mahalm/antenna_cell_placement/eval_reports/` directory. Logs record executed commands, exit codes and timings. Initial failed attempts and successful restored-source attempts are kept separately.

These local paths are not a promise that another teammate's Git clone contains the raw data or audit artifacts. During integration, publish an appropriately sized evidence bundle and immutable manifests alongside reproducible commands; arrange access to large sources separately. The metric tables in this document remain readable without the local workspace.

Existing project references:

- [ML models and data](ML_MODELS_AND_DATA.md)
- [Pilot plan and validation](PILOT_PLAN_AND_VALIDATION.md)
- [Phase 2 GIS and rooftops](PHASE2_GIS_AND_ROOFTOPS.md)
- [Dataset overview](DATASETS_OVERVIEW.md)
- [Improvement plan](IMPROVEMENT_PLAN.md)

## 12. Immediate next action

**Begin Steps 1 and 2: create the integration branch and define/test the shared feature and provenance contract.** Then port the explainable score onto that foundation. Do not start by replacing whole conflicting files or enabling all available data sources.

The integration is complete only when the public workflow uses that contract, strict rules and honest labels; the regression/demo checks pass; experimental ML remains reproducible; and the documentation matches the delivered behavior.

Later deployment work still needs calibrated RF modelling, operator-confirmed inventory and KPIs, budget-aware incremental coverage/capacity evaluation, independently reviewed locations, and building access/structural/power/backhaul checks. Those are separate evidence milestones, not benefits already demonstrated by this merge plan.
