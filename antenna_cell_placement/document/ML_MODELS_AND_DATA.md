# ML models and data: what the system learns and how to evaluate it

> Current update (2026-09-29): see [measured service and reconciled inventory](SEPT29_INTEGRATION.md). The active demo is `integrated_release_v3/`; earlier metrics and source versions below remain historical evidence.

**Integration update (23 September 2026):** The public `recommend`, `all`, `assess`/`predict` and `map` workflow now uses GIS v2 and Ahmed’s explainable heuristic. ML is excluded from primary ranking; old model-based commands are under `experimental`. See [the current integration guide](INTEGRATED_PLANNING.md) for the shared contract, source checks, runnable commands and validation. Historical results and implementation descriptions below retain their original scope.

**Submission update (2026-09-23):** The public demo now describes planning priorities for engineering review and omits equipment, frequency-band and bandwidth advice. The coordinate response exposes an experimental site-pattern score, not an installation-suitability verdict. The controlled hard-negative comparison remains 0.876141 versus 0.885208; population-only baselines are 0.594538 and 0.571961 respectively. These are the same frozen examples and recipe, not demonstrated RF improvement. [Submission guide](SUBMISSION_READINESS.md) and [portable demo](../submission/index.html).

Historical equipment-model results below describe research experiments, not the current public outputs. The preserved submission Tripoli map uses separate phase-2 artifacts. Its historical behavior is distinct from the integrated public planner; no ML model has been promoted.

Updated: 2026-09-22. This is the primary model/data reference. Historical numbers below come from saved reports, not from a new blind field trial. The implementation plan is in [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).

## 1. Purpose and decision boundary

**Phase 2 update:** the separate GIS v2 pipeline, model comparison, inventory audit and preliminary rooftop shortlist are documented in [PHASE2_GIS_AND_ROOFTOPS.md](PHASE2_GIS_AND_ROOFTOPS.md). Feature definitions described below as current refer to the legacy serving pipeline unless explicitly marked v2. The research command is now `antenna-placement experimental phase2`; it does not automatically replace serving artifacts. The local Microsoft footprints provide no usable heights, so building outputs are survey candidates, not tallest-building recommendations.

The project screens locations for telecom planning review. Its main classifier estimates how similar a location is to observed cell-site locations under a particular sampling scheme. A score of 0.9 does **not** mean a 90% chance that a new tower is needed, that a permit will be granted, or that coverage will improve.

An observed site is evidence of an existing installation. A synthetic point without a recorded site is an **unlabeled location** assigned a negative label for an experiment. It can still be a good future candidate. This distinction limits every classification metric in this project.

The planning objective should eventually become additional service benefit under operator, technology, RF, feasibility and budget constraints. The present classifiers supply screening signals for that future decision system.

## 2. Components and their roles

| Component | Method | Target/output | Current role |
|---|---|---|---|
| Serving suitability model | LightGBM binary classifier | Observed site versus sampled non-site; score 0–1 | Historical experimental recommendations and H3 multiplier only; excluded from integrated public ranking |
| Suitability challenger | XGBoost binary classifier | Same sampled classification task | Compared during legacy training; not saved as the serving artifact |
| Equipment recommender | Random Forest, four classes | Reproduce rule-derived equipment tiers | Provisional tier suggestion; not independently validated equipment design |
| H3 expansion score | Weighted formula | Relative area priority | Tripoli planning screen; not a trained demand or coverage model |
| Training experiment | LightGBM with grouped development CV | Same proxy task, with added hard negatives | Separate artifact and reproducible diagnostic reports; no automatic promotion |

The historical benchmark gives XGBoost a slightly higher AUC than LightGBM. The old statement that it "lost in CV" was incorrect. The selection of LightGBM should be justified by recorded operational evidence; a speed advantage is not established by the current benchmark JSON.

## 3. Data lineage and observation units

```text
SQLite source observations
  -> scoped radio-record deduplication and operator attribution
  -> 50 m connected-component grouping into estimated physical sites
  -> raster/vector/network features
  -> observed positives + synthetic background/corridor/hard negatives
  -> development/test municipality assignments
  -> training, evaluation, saved model and predictions

Physical sites + GIS layers -> H3 features -> relative priority -> review map
```

| Layer | Unit of observation | Use | Important limitation |
|---|---|---|---|
| `source_records` in `cells.sqlite3` | Crowdsourced radio observation | Source identity, technology, coordinates and dates | Observation time is not commissioning time; coordinates are not field-surveyed mast truth |
| `cleaned_radio_towers.csv` | Deduplicated `(rat, region_id, site_id)` | Technology/operator inventory | Network identity still needs to become part of the dedup key where known; matching keys across operators need an explicit migration |
| `cleaned_physical_sites.csv` | Connected group of radio records within 50 m links | Site inventory and positive examples | Chained links can produce a group wider than 50 m; co-location is inferred |
| `cleaned_cells_combined.parquet` | One enriched site | Serving training input and experiment input | Must be rebuilt after source or feature changes |
| Synthetic examples | Generated coordinate with extracted features | Negative label for a defined benchmark | Not a confirmed bad location; class balance is artificial |
| H3 feature table | One resolution-8 hex | Area screening | Most legacy raster/network features are centroid samples |

The historical inventory has 4,258 observations, 2,338 deduplicated radio records and 2,115 estimated physical sites. Count radio records and physical sites separately: several technologies/operators may share one physical location.

### Historical Al-Madar correction

The dataset owner confirmed that 645 anonymous LTE source rows belong to Al-Madar. The loader now applies that correction only when all these conditions match:

- Import ID `1`, source name `cells.json`.
- Recorded source SHA-256 `a099aa826f11a80e7f4dc23405f70dff7bac9327fb82e129acb61fef0d1c2b2a`.
- Radio technology `LTE`, SQL MCC and MNC both null.
- The matched cohort contains exactly 645 records; a changed nonempty cohort fails validation.

The raw database and raw operator value are retained. Cleaned rows carry `owner_confirmed_almadar` and attribution method `owner_confirmed_import_1_a099aa826f11`. Other imports still use the existing attribution rules. Deduplication propagates the confirmation only if every source row in that group belongs to the confirmed cohort, preventing a mixed group from silently acquiring the label.

This is owner-supplied provenance, not an independently measured operator label. Future unknown LTE records are not automatically Al-Madar. Historical output counts predating this fix must be regenerated before use.

## 4. External data and feature meanings

| Input | Approximate vintage / scale | Role | What it cannot establish |
|---|---|---|---|
| WorldPop | 2020, about 1 km | Population proxy | Current traffic, subscribers, congestion, or fine building-level population |
| SRTM DEM | Terrain at about 250 m in this project | Elevation, local prominence, approximate slope | Rooftop height, urban obstruction or RF line of sight by itself |
| OCHA roads/settlements/admin boundaries | Local downloaded snapshots | Access/context/grouping | Site acquisition, reliable power, backhaul or legal eligibility |
| Microsoft buildings | Downloaded 2026 release | Footprint area and density | Building height where value is missing; occupancy; building age from release date |
| ESA WorldCover | 2021 | Land cover fractions | Calibrated radio clutter loss |
| OSM roads/POIs | 2026 snapshot | Access and activity proxies | Uniform mapping completeness |
| Cloudflare Radar | 52-week regional context | Bounded nationwide ranking prior | Local cell traffic; intra-city congestion |
| OpenCellID | Timestamped public cell estimates | Separate corroborating review layer | Verified mast inventory, measured coverage footprints or RF capacity |

Exact local paths and download references are in [DATASETS_OVERVIEW.md](DATASETS_OVERVIEW.md). Release/download dates must not be described as imagery acquisition dates unless the source supports that interpretation.

### Suitability feature contract

| Columns | Current computation | Interpretation and debt |
|---|---|---|
| `population_density_1km` | Sample of the raster at a coordinate | Legacy density label; verify source units and pixel area before interpreting as people/km² |
| `population_sum_3km`, `population_sum_5km` | Sums of 7×7 and 11×11 pixel windows | Square-window proxies, not verified circular population totals; density rasters require area conversion |
| `elevation_m` | DEM sample | Approximate terrain elevation |
| `elevation_prominence_3km` | Sample minus surrounding window mean | Terrain prominence proxy, not antenna HAAT or a viewshed calculation |
| `terrain_slope_deg` | Finite difference with assumed 250 m spacing | Audit actual transform/CRS and nodata before engineering use |
| `dist_to_nearest_road_m` | Distance to sampled road points | Approximate road distance; sample spacing affects error |
| `dist_to_nearest_settlement_m` | Distance to settlement points | Settlement proximity |
| `dist_to_nearest_site_m` | Nearest inventory site, excluding self for positive examples | Inventory-relative spacing, not measured coverage |
| `site_density_3km`, `site_density_5km`, `site_density_10km` | Inventory counts within projected radii | Deployment concentration, not capacity or service quality |

These are the 12 LightGBM/XGBoost inputs. The equipment model uses the same inputs except `site_density_10km` (11 columns). Operator distance, Cloudflare, buildings, land cover and POIs are **not** serving-classifier features.

Network-distance calculations currently use UTM 33N nationwide. A region-aware or geodesic replacement, nodata handling, population unit conversion and raster indexing require a versioned feature migration followed by regeneration and retraining. They are not silently declared fixed by this milestone.

The operator-neighbor helper now excludes self only if that operator's index contains a matching coordinate; absent operator evidence is NaN. This fixes the previous unconditional second-neighbor lookup. Coordinate-based self identification remains an approximation until stable site IDs are passed to the extractor.

## 5. Serving suitability training and historical evaluation

The legacy training path uses 2,115 positive sites plus 2,500 generated negatives. It samples road points, settlement rings and bounding-box background. Ratios are approximate, depend on availability and are not guaranteed strata quotas. Bounding-box samples can include water or locations outside the national boundary.

The road-negative check previously mixed longitude/latitude with a meter-coordinate KD-tree and did not apply its computed distance. It now transforms the jittered coordinate into the tree CRS and rejects road samples at or within 5 km of an inventory site. Settlement/background samples do not inherit that filter. Existing saved models and benchmark JSON describe the old sampling run until explicitly retrained.

Legacy CV uses random stratified folds. Neighboring examples may appear in different folds. The saved final LightGBM uses 350 estimators, learning rate 0.035, depth 6 and 31 leaves; the CV fits use a different configuration (300 estimators, learning rate 0.04). Therefore the legacy CV number is not an exact assessment of the final artifact's training recipe.

Historical reports:

| Measurement | Value | Meaning |
|---|---:|---|
| Original LightGBM random-CV ROC-AUC | 0.9862 | Easy sampled site/non-site discrimination |
| Diagnostic municipality-grouped ROC-AUC | 0.9828 | Refit evaluation models, municipality grouping |
| Diagnostic held-out-municipality ROC-AUC | 0.9844 | 1,449 examples including 533 positives |
| Population-only ROC-AUC on that test | 0.9589 | A strong simple baseline on the easy task |
| Historical hard-negative ROC-AUC | 0.7238 | 533 positives versus 1,500 populated nearby synthetic non-sites |
| Population-only hard-negative ROC-AUC | 0.5675 | Baseline on the harder sampled task |
| Hard negatives with score ≥0.5 | 92.6% | A default 0.5 threshold accepts most plausible non-sites |

Source: [honest_evaluation.json](../eval_reports/honest_evaluation.json). These are historical diagnostic results. The newer hard-negative generator explicitly enforces the destination municipality and maximum nearest-site distance; the historical report predates those fixes. Do not compare future numbers as if the test samples were identical.

AUC measures ranking: 0.724 AUC is **not 72.4% accuracy**. Municipality grouping reduces some spatial leakage but cannot prove leakage is absent. Network features are calculated from the full observed inventory, including sites in held-out regions. That is a conditional inventory experiment; it does not recreate an unseen or earlier network. Buffered geographic and time-aware evaluations remain future work.

## 6. Reproducible training experiment

Run from the module folder:

```powershell
uv run antenna-placement clean
uv run antenna-placement experimental features
uv run antenna-placement experimental train-experiment --output-dir eval_reports/experiment_v1
```

The output directory must be new. Existing experiments cannot be overwritten through this command. It writes:

| Artifact | Contents |
|---|---|
| `dataset.parquet` | Exact examples, coordinates, feature values, labels, sample kinds, row IDs and split membership |
| `manifest.json` | UTC time, feature list, fixed parameters, package versions, input/dataset hashes, split regions, realized counts and limitations |
| `metrics.json` | Grouped development CV, fold metrics, held-out mixed/hard metrics, baselines, Brier score and precision@20/@50 |
| `predictions.csv` | Row-linked out-of-fold development and held-out test scores |
| `suitability_experiment.joblib` | Separate model trained only on development municipalities |

The experiment requests 1,500 corrected background/corridor negatives and up to 1,500 hard negatives for each partition. Actual counts are recorded after filtering and coordinate deduplication; scarce negatives are not silently duplicated to reach a quota. Hard negatives require 500–3,000 m nearest-site distance, population-window value ≥300, and membership in the partition's municipalities.

Test municipalities are fixed to the previously inspected diagnostic set: Wadi Ashshati, Almarj, Derna, Ejdabia, Sebha, Nalut, Al Jabal Al Akhdar, Tobruk and Aljfara. The remaining municipalities supply development data. Five-fold GroupKFold operates **only on development municipalities**. Fixed LightGBM parameters are then fitted on development and evaluated once on the saved test rows in that run.

Because this geographic test set has already been examined, it is a development benchmark, not a new blind final test. Do not repeatedly tune against it and call the result untouched validation. A future independently collected or prospectively reserved dataset is needed for a final deployment claim.

No serving artifact is promoted automatically. Before promotion, evaluate old and new models on identical frozen examples, inspect failure cases, test inference compatibility, and validate the planning objective with independent evidence. Brier score here measures probability quality on an artificial class mix, not real deployment-need calibration. Precision@K measures recovery of observed sites within the sampled benchmark, not the fraction of recommended new towers that should be built.

### Verified run on 2026-09-22

The implementation run passed **40 tests** and refreshed the cleaned/enriched inventory, H3 features/scores/validation/map and nationwide recommendations/maps. Cleaning produced **645 Al-Madar LTE** and **673 Libyana LTE** records, **2,115 physical sites** and **65 inferred shared sites**. The raw SQLite SHA-256 was unchanged.

Experiment `experiment_20260922_v1` contains 4,008 development examples (1,582 observed sites, 926 background/corridor negatives, 1,500 hard negatives) and 2,607 test examples (533 observed sites, 574 background/corridor negatives, 1,500 hard negatives).

| New experiment measurement | Model ROC-AUC | Population-only ROC-AUC |
|---|---:|---:|
| Development grouped CV | 0.9028 | 0.7378 |
| Held-out mixed benchmark | 0.9033 | 0.6950 |
| Held-out hard-negative benchmark | 0.8761 | 0.5945 |

These rows compare the new model with population on the same examples. The old 0.7238 stress result used different samples and is not a controlled before/after comparison. The serving model remains the legacy artifact; the new one is experimental. Test geography was previously inspected and still does not establish prospective coverage benefit.

See [experiment metrics](../eval_reports/experiment_20260922_v1/metrics.json), [manifest](../eval_reports/experiment_20260922_v1/manifest.json), and [implementation verification](../eval_reports/implementation_verification.json). Tripoli scores were refreshed using carried-over building, land-cover and OSM aggregates; raw Phase-2 enrichment was not rerun. Function-level rerun behavior is covered by regression tests. Maps were regenerated; this milestone does not include browser visual inspection.

## 7. Equipment model: rule imitation

Random Forest uses 200 trees, depth 8 and seed 42. Labels use the first matching rule:

1. Micro: source tower type MICRO, or population proxy >2,500 and nearest-site distance <250 m.
2. Urban: population proxy ≥1,200, bandwidth ≥40 MHz, or carrier count ≥3.
3. Suburban: population proxy ≥150, bandwidth ≥20 MHz, or road distance <500 m.
4. Rural: otherwise.

These are project rules. Neither the labels nor predicted tiers prove optimal equipment. Source bandwidth can reflect repeated observations or fallback assumptions; it requires a carrier-level audit.

| Historical measurement | Result |
|---|---:|
| In-sample accuracy | 89.55% |
| Random-CV accuracy / macro-F1 | 79.57% / 0.7443 |
| Municipality-grouped accuracy / macro-F1 | **78.39% / 0.7297** |
| Feature-side rules baseline | 78.68% |
| Majority-class baseline | 54.14% |

The old 77.8% figure was a documentation error. The 78.68% baseline uses only rules whose inputs are available to the model, with unavailable tower/bandwidth/carrier inputs set to defaults. Applying the complete original labeling rule would reproduce its own targets exactly; describing the feature-side baseline as the entire rule was misleading.

Historical classes: urban 1,145; suburban 719; micro 188; rural 63. Macro-F1 weights each class equally and helps expose poor results on scarce rural examples. A useful future learner needs real configuration, utilization, constraints and outcome labels. Until then, retain an explicit rules baseline and describe suggestions as provisional.

## 8. H3 scoring and validation

The Tripoli formula combines population (35%), buildings/POIs (25%), inventory spacing (25%) and land use (15%). Missing Phase-2 blocks drop out and remaining weights renormalize. Missing per-row land-cover values are neutral; unknown population/road values are no longer treated as proven empty remote land. Normalization treats infinities as missing.

The score is multiplied by `0.75 + 0.5 * suitability`, so `combined_priority_score` can exceed 100. It is a relative score, not a probability. Normalization depends on the pilot dataset; scores are not directly comparable across cities or resolutions.

Historical Tripoli run: 2,987 hexes, 771 water-masked, 2,216 scored. Hidden-site recovery AUC is 0.716 versus 0.767 for population alone; top-10% recall is 0.350 versus 0.372. Stability under weight perturbation does not establish correctness. Recovery of past sites is a sanity check, not evidence of future coverage or congestion improvement. The suitability multiplier itself is not validated by the base-score recovery result.

Phase-2 joins now replace existing columns by unique H3 identity. Reruns do not create `_x`/`_y` duplicate feature columns, duplicate/null keys raise an error, and unmatched features remain missing. Carry-over still needs input-version tracking; changing source tiles requires explicit enrichment regeneration.

Some high-scoring hexes already contain sites. Label these as demand/densification review candidates; an empty hex is not proof of no RF coverage. The next engineering step is point generation and feasible set selection inside reviewed areas.

## 9. Data needed for the next stage

| Dataset | Required fields | Enables |
|---|---|---|
| Operator inventory | operator, site/cell/sector ID, coordinates, RAT, band, bandwidth, height, azimuth, tilt, power, effective dates | Stable joins and RF configuration |
| KPIs | timestamp/timezone, cell ID, interval, traffic with units, PRB load, users, throughput, availability, quality flags | Congestion evidence and upgrade-versus-new-site decisions |
| RF observations | time, coordinates, serving cell, operator/RAT, RSRP, RSRQ, SINR, measurement method | Calibration and independent RF validation |
| Feasibility/cost | land access, exclusions, power, backhaul, permitted heights, acquisition/construction cost | Buildable, budget-constrained alternatives |
| Deployment history | commissioning/configuration dates and pre/post outcomes | Historical replay and benefit evaluation |

`kpi_prediction/data/Data.csv` currently lacks a usable site/location key according to the project handoff. Do not attach its rows to arbitrary sites or treat unrelated public KPIs as Libyan ground truth.

## 10. Reproduction and acceptance

```powershell
uv sync
uv run python -m unittest discover -s tests -v
uv run antenna-placement clean
uv run antenna-placement experimental features
uv run antenna-placement experimental train-experiment --output-dir eval_reports/my_new_experiment
uv run antenna-placement experimental h3-all --city Tripoli
```

The local pre-existing `.venv` may refer to a deleted interpreter. Recreate/sync it using a working Python 3.12 runtime before using these commands. Avoid claiming tests passed based only on the presence of this guide; use the implementation verification report for the actual run.

Regression tests cover historical import boundaries, duplicate/missing H3 joins, hard-negative geography, missing-data scores, operator-neighbor self exclusion and split membership. They do not validate RF physics or demonstrate deployment outcomes. Current results, source changes and remaining acceptance gates belong in [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md).
