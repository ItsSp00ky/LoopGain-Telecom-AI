> **Status update — 2026-09-22:** This document records an earlier design/run. Current model/data definitions, metric corrections, implemented fixes and remaining work are maintained in [ML_MODELS_AND_DATA.md](ML_MODELS_AND_DATA.md) and [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md). Historical figures here are not evidence of measured coverage, independent equipment validation or a completed RF planner.

**Integration update (23 September 2026):** The public `recommend`, `all`, `assess`/`predict` and `map` workflow now uses GIS v2 and Ahmed’s explainable heuristic. ML is excluded from primary ranking; old model-based commands are under `experimental`. See [the current integration guide](INTEGRATED_PLANNING.md) for the shared contract, source checks, runnable commands and validation. Historical results and implementation descriptions below retain their original scope.

# Tripoli Pilot — Plan, Validation and Known Weaknesses

This document covers the H3 expansion-need pilot for Tripoli: what has been built, the plan from here, how the work is tested and validated, and an honest list of weaknesses with their fixes and current status. Numbers below come from the run of 2026-09-20 (`uv run antenna-placement experimental h3-all --city Tripoli`).

---

## 1. Where we are

The nationwide pipeline (clean → features → train → recommend → map) scores individual candidate points. The pilot adds an **area-level screening stage in front of it**: Tripoli is tiled into H3 hexagons, each hexagon gets demand, urban-form, land-cover and network-gap features, and an auditable Expansion Need Score ranks which areas need a new site first. The trained suitability model is then applied to each hexagon so the two stages are connected.

| Item | Value |
|---|---|
| Study area | Tripoli bbox lon 12.95–13.65, lat 32.60–32.95 (covers the Tripoli admin2 polygon and the Janzour suburbs) |
| Grid | 2,987 H3 hexagons at resolution 8 (~0.74 km² each) |
| Masked before scoring | 771 hexagons that are ≥50 % open water (Mediterranean); 0 uninhabited-and-roadless |
| Scored hexagons | 2,216 |
| Existing physical sites inside the grid | 713 (of 2,115 nationwide) |
| Phase-2 inputs | 970,860 Microsoft building footprints (2 tiles), ESA WorldCover 10 m (2 tiles), Geofabrik Libya OSM extract (roads + POIs) |
| Outputs | `data/cleaned/h3/h3_features_Tripoli.parquet`, `eval_reports/h3_expansion_scores_Tripoli.{csv,geojson}`, `eval_reports/h3_validation_Tripoli.json`, `eval_reports/h3_expansion_map_Tripoli.html` |
| Tests | 32 unit tests, all passing (`uv run python -m unittest discover -s tests`) |

**How the score works.** Four sub-scores, each min-max normalized with 2nd/98th-percentile clipping, combined with weights 0.35 population demand (mean of 1 km density and 3 km sum), 0.25 building/urban demand (building density, built-up ratio, POI count), 0.25 network gap (distance to nearest site + inverse 3 km site density + bonus for hexes with no site), 0.15 land-use demand (built-up % minus bare/water %). If Phase-2 columns are missing the corresponding weights are dropped and the rest renormalized. The result (0–100) is multiplied by a bounded factor 0.75–1.25 from the trained suitability model to give `combined_priority_score`.

---

## 2. Plan

### Done
1. **Phase 1 – H3 grid and existing features per hex** (`h3_grid.py`, `h3-grid`). Reuses `GeospatialFeatureExtractor` on hex centroids; aggregates existing sites per hex; carries Phase-2 columns over when the grid is rebuilt.
2. **Phase 2 – new data layers** (`building_features.py`, `landcover_features.py`, `osm_features.py`, `enrich-h3`).
3. **Scoring** (`expansion_score.py`, `expansion-score`) with water/uninhabited masking, robust normalization, graceful degradation and the suitability hand-off.
4. **Validation** (`validation.py`, `validate-h3`): known-site recovery and weight sensitivity, written to JSON.
5. **Map** (`map_visualizer.generate_h3_expansion_map`, `h3-map`): choropleth by priority quintile, existing sites, top-20 call-outs, offline basemap.
6. `h3-all` runs the whole chain; README and dataset documentation updated.

### Next (in order)
7. **Engineering review of the top 20 hexes** using the map: classify each as *good / possible / not suitable* and record the reasons (see §3.4). This is the validation step that no metric can replace.
8. **Point-level hand-off inside top hexes**: for each of the top-N hexes generate candidate points (centroid plus a small ring), score them with `CellSiteOptimizer`'s model and RF-band heuristics, and export `h3_top_candidates_Tripoli.csv`. Today the hand-off is centroid-only.
9. **Bring in the KPI data** (`kpi_prediction/data/Data.csv`: RRC/E-RAB/handover/throughput per day). Once KPIs can be attached to sites or areas, add a *capacity stress* sub-score (congestion, throughput degradation) — this is the missing demand signal that population and buildings cannot see.
10. **Re-validate** with the KPI signal (hexes with degraded KPIs should rank high) and, if operator build dates become available, run the temporal test in §3.5.
11. **Second city (Benghazi)** with the same commands — only a bbox entry in `config.PILOT_CITY_BBOXES` and the two building tiles are needed — to check the weights are not Tripoli-specific.
12. **Rebuild the training set and retrain** following §3.7 (frozen split file, enforced >5 km filter, hard negatives, grouped validation, one-shot test) and re-report the benchmark honestly.
13. **RF stage** for the final short-list (terrain profile / line-of-sight from the DEM, building obstruction from footprints), as in the team roadmap.

---

## 3. Testing and validation

### 3.1 Unit tests (32, run in a few seconds)
| File | What it guards |
|---|---|
| `test_h3_grid.py` | grid covers a known Tripoli point; point→hex assignment is deterministic; per-hex site counts are conserved; centroids stay inside the bbox |
| `test_expansion_score.py` | constant columns normalize to neutral; dense hexes get a low gap score; an underserved populated hex outranks a saturated one; Phase-1-only input still scores; weights sum to 1 |
| `test_building_features.py` | GeoJSON-Lines loader; only buildings inside the hex are counted; empty hex gives zeros |
| `test_landcover_features.py` | a synthetic half built-up / half water raster yields ~50/50 %; all-bare raster yields 100 % bare |
| `test_osm_features.py` | road length/density from a line crossing the hex; POI counts by category; no data gives zeros |
| `test_validation.py` | network features recomputed from a site subset; recovery and sensitivity return well-formed metrics |
| existing `test_opencellid.py`, `test_cloudflare_radar.py` | unchanged, still pass |

### 3.2 Pipeline invariants (checked on every `h3-all` run)
- Sum of `existing_sites_site_count` equals the number of sites whose hex is in the grid.
- Every scored hex has non-null Phase-2 columns (0 missing in the current run).
- Masked hexes are reported with their reason (`water_hexes`, `uninhabited_hexes`).
- Active weights are printed so a Phase-1-only run is visible as such.

### 3.3 Statistical validation (`validate-h3`)
**Known-site recovery.** 5 folds; in each, 20 % of the 713 sites inside the grid (134–160 sites) are hidden, the network-gap features are recomputed without them, the score is recomputed, and we measure whether the hexes that contained hidden sites rank high. A population-only baseline is reported alongside.

| Metric (mean of 5 folds) | Expansion score | Population-only baseline |
|---|---|---|
| ROC-AUC, all hexes | 0.716 | 0.767 |
| Recall in top 10 % of hexes | 0.350 (3.5× random) | 0.372 |
| Recall in top 25 % of hexes | 0.574 | – |
| ROC-AUC, unserved hexes only | 0.680 | 0.724 |
| Recall in top 10 %, unserved only | 0.313 | 0.326 |

*Interpretation.* The score is clearly anchored to reality (AUC well above 0.5, 3.5× lift), but population alone recovers **past** sites slightly better. That is expected: the historical network followed population, while the network-gap term deliberately pushes the ranking **away** from already-served clusters. Random-hide recovery therefore works as a sanity check, not as proof that the ranking finds the best *next* sites — that needs the KPI or expert validation below. We keep the gap term because a score that only reproduces population would just re-propose the existing network.

**Weight sensitivity.** Each weight scaled ×0.5 and ×1.5: Spearman rank correlation with the default ranking stays ≥ 0.966 and top-50 overlap ≥ 86 %. The ranking is not an artefact of the exact weights.

**Suitability cross-check.** The nationwide LightGBM model applied to hex centroids: median 0.943, 75th percentile 0.987, minimum 0.03. Its influence on the hex ranking is bounded to ±25 %; §3.6 measures how well it really discriminates.

### 3.4 Expert (engineering) review — to do
Open `eval_reports/h3_expansion_map_Tripoli.html`, walk the top-20 hexes and record for each: population and buildings visible, existing sites in and around the hex, road access, obvious blockers (industrial/military/airport, coastline), verdict *good / possible / not suitable*. Target: ≥ 70 % good-or-possible before moving to point-level design. Also check the two negatives: a downtown hex full of existing sites should have a low `network_gap_score`; a peripheral populated hex with no site should score high.

### 3.5 What we cannot validate yet, and what unlocks it
| Missing evidence | Why it matters | Unlocks |
|---|---|---|
| Real build dates of sites | `first_seen_ms` in the crowdsourced data mostly reflects when a tower was *observed* (597 of 732 Tripoli sites are "first seen" in 2025–26), so a hide-the-newest temporal test would be misleading | Temporal recovery test: score the 2020 network, check where operators actually built next |
| Per-site / per-area KPIs (PRB load, drops, throughput) | Population and buildings are demand proxies; congestion is demand evidence | Capacity-stress sub-score and a direct validation target |
| Operator traffic or Cloudflare below municipality level | Cloudflare is constant inside a city (2 distinct values across the whole Tripoli grid) | Intra-city demand weighting |
| Expert labels (good / not suitable) | Only way to test the *planning* judgment rather than historical correlation | Supervised calibration of the weights |

### 3.6 Train / validate / test protocol for the ML models (`antenna-placement experimental evaluate`)
The hex score is a rule, so its hold-out is "hide real sites" (§3.3). The two trained models are evaluated like this, with a fixed seed and the shipped hyper-parameters:

| Stage | Suitability model (LightGBM) | Equipment recommender (Random Forest) |
|---|---|---|
| Train | sites plus 2,500 synthetic negatives | all sites, rule-derived tier labels |
| Validation | random stratified 5-fold CV (the shipped scheme), then municipality-grouped 5-fold CV | random 5-fold CV, then municipality-grouped 5-fold CV |
| Final test | 9 whole municipalities held out (Wadi Ashshati, Almarj, Derna, Ejdabia, Sebha, Nalut, Al Jabal Al Akhdar, Tobruk, Aljfara; 533 sites) | (same grouped CV; no separate test set because the labels are rules) |
| Stress test | real held-out sites vs 1500 populated non-sites 0.5-3 km from a site | - |

| Result | Suitability ROC-AUC | Equipment accuracy |
|---|---|---|
| As shipped (random CV / in-sample) | 0.9859 | 0.8955 |
| Municipality-grouped CV | 0.9828 | 0.7839 |
| Held-out municipalities (final test) | 0.9844 | - |
| Population-only baseline, same test | 0.9589 | rules only 0.7868; majority tier 0.5414 |
| Hard-negative stress test | 0.7238 (population-only 0.5675) | - |

*Reading it.* Splitting by municipality barely moves the suitability score (0.986 to 0.983), so the model is not memorizing regions, and the technical report's 0.983 municipality-held-out figure is reproduced independently. But the benchmark task is easy: population alone reaches 0.959. On the harder question that matches deployment, separating real sites from populated non-sites, the model reaches 0.72, clearly above population alone (0.57) but far from 0.98. The equipment recommender drops from 89.6 % to about 78 % on unseen regions and equals its own labeling rules, so it is a rule engine in effect. The stress test parameters (0.5-3 km, at least 300 people within 5 km) are my choice and the held-out split is a single seeded draw. Full numbers: `eval_reports/honest_evaluation.json`.

### 3.7 Plan: training set, validation set and test set (for the retrain)
§3.6 measures the models as they are today. This is the plan for the retrained version, so the numbers we report afterwards can be defended.

**Splits (by municipality, never by random row).** Sites and negatives from the same municipality always stay on the same side.
| Set | Contents | Used for | Rule |
|---|---|---|---|
| Test | the 9 held-out municipalities from §3.6 (533 of 2,115 sites, about 25 %) | one final measurement | Frozen. Saved to `data/splits/municipality_split.json` (today it is only reproducible from seed 42). Nothing is tuned on it; it is scored once, after every design decision is made |
| Train + validation | the other 13 municipalities (about 1,582 sites) | fitting, feature choices, hyper-parameters | Municipality-grouped 5-fold CV. Each fold's held-out municipalities act as the validation set |

**Training set construction (suitability model).**
- Positives: all real sites, with features computed excluding the site itself (already how `extract_features(is_existing_site=True)` works).
- Negatives, three kinds with fixed shares: about 20 % easy (random points, desert), about 30 % corridor points (roads and rings around towns) that really are more than 5 km from any tower (enforce the filter that is documented but never applied), about 50 % hard (populated, 0.5-3 km from an existing site, built with `generate_hard_negatives`).
- Ratio about 1 : 1.5 sites to negatives; class weights instead of resampling; the same fixed seed for every run.
- Features stay the 12 nationwide ones. Buildings, land cover and OSM exist only for the Tripoli tiles, so they cannot be model inputs nationwide until the tiles for the rest of Libya are downloaded.
- What the label means: "site-like location", a proxy. Hard negatives near existing sites are places that were *already covered*, not places where a mast would be wrong. There is no ground truth for "a new site is needed here"; the KPI data and the expert review (§3.4) are what test that.

**Rules to keep the test honest.**
1. Choose features, negative shares and hyper-parameters on the validation folds only.
2. The primary metric is the hard-negative AUC (it matches deployment); ROC-AUC on the mixed set is secondary because population alone already reaches 0.96.
3. Score the frozen test set once, report it whatever it is, and do not retrain afterwards to improve it.
4. Every result table shows the population-only baseline beside the model.

**Targets (proposed, to agree with the instructor).**
| Metric | Today | Target |
|---|---|---|
| Mixed-set ROC-AUC on the held-out municipalities | 0.984 | stay above 0.95 |
| Hard-negative AUC on the held-out municipalities | 0.72 | at least 0.80 |
| Gain over the population-only baseline on hard negatives | +0.16 | at least +0.20 |

If retraining does not reach the targets we still report the measured numbers; the targets only decide whether the model is described as improved.

**Equipment recommender.** Do not present it as a learned model while its labels are the rules: either report it as a rule engine, or relabel from real per-site capacity data (bandwidth actually deployed, utilization) and evaluate on the same frozen split. Its target is to beat the rules-only accuracy (78.7 %) on held-out municipalities.

**Expansion score (not trained).** Weights are frozen at 0.35 / 0.25 / 0.25 / 0.15. Tripoli was used to design and diagnose it, so it counts as *seen*. The held-out city is Benghazi: run `h3-all --city Benghazi` unchanged and compare the known-site recovery numbers with Tripoli's (§3.3).

---

## 4. Weaknesses and fixes

| # | Weakness | Impact | Status | Fix |
|---|---|---|---|---|
| 1 | Pilot bbox cut off eastern Tripoli (stopped at lon 13.45; the admin polygon reaches 13.60) and included a band of open sea to lat 33.05 | Missing suburbs; sea hexes distorted the normalization | **Fixed** | bbox now 12.95–13.65 / 32.60–32.95, verified against the admin2 bounds; existing building tiles still cover it |
| 2 | Water and uninhabited hexes were scored like any other; far-out sea hexes stretched the distance scale so land hexes were compressed | Wrong ranking scale | **Fixed** | `mask_unscorable_hexes` (≥50 % water, or zero population and >3 km from a road) plus 2/98-percentile clipping in the normalization |
| 3 | Re-running `h3-grid` silently wiped the Phase-2 columns | Fragile pipeline order | **Fixed** | Phase-2 columns are carried over by `h3_index` on rebuild, with a warning if any hex lacks them |
| 4 | 5 km population sum saturates inside the city (every central hex sees ~400 k people) | No discrimination between neighbouring hexes | **Fixed** | Population demand now uses 1 km density + 3 km sum |
| 5 | Stage 1 (area) was not connected to Stage 2 (point model) | Score was standalone | **Fixed (centroid level)** | Suitability model scores every hex centroid; bounded factor gives `combined_priority_score`. Point-level ring candidates are step 8 of the plan |
| 6 | No quantitative validation of the score | Nothing to defend the ranking with | **Fixed** | Known-site recovery (all / unserved-only, with baseline) and weight sensitivity, JSON + CLI table |
| 7 | CLI status lines use "✓", which crashes `rich` on Windows consoles with a non-UTF-8 code page (reproduced on this machine; would also hit `clean`, `features`, `all` during a demo) | Demo crash | **Fixed** | stdout forced to UTF-8 at CLI start |
| 8 | The nationwide suitability model is trained against **synthetic negatives** (40 % road points, 30 % rings around towns, 30 % random points across Libya); the documented ">5 km from any tower" filter for road negatives is computed at `placement_model.py` but never applied | Headline 0.986 ROC-AUC could overstate placement skill | **Measured (§3.6)** | Municipality-held-out AUC is 0.984, so geographic leakage is small and the model generalizes to unseen regions. But population alone scores 0.959 on the same test, and on hard negatives (populated non-sites 0.5-3 km from a site) the model scores 0.72. Report both numbers; still open: enforce the distance filter and train with hard negatives |
| 9 | Weights (0.35/0.25/0.25/0.15) are engineering judgment, not learned | Ranking could reflect our priors | **Mitigated** | Sensitivity shows the ranking is stable to ±50 % changes; calibrate against expert labels or KPIs when available (plan steps 7–10) |
| 10 | Cloudflare Radar is municipality-level: constant inside the city | Adds nothing intra-city | **Accepted** | Not used in the hex score; keep as nationwide prior only |
| 11 | Timestamps in the site data reflect observation, not construction | No temporal validation | **Open** | Needs operator build dates (§3.5) |
| 12 | Microsoft building height is unavailable for Libya (`height = -1`) | No vertical density / obstruction feature | **Accepted** | Use footprint area and density only; revisit if a height product appears |
| 13 | Hex features are sampled at the centroid (population, terrain, roads, site distance); buildings, land cover and OSM are true zonal statistics | Small edge effects at ~0.7 km² | **Accepted at res 8** | Move to zonal statistics for population if resolution 9 is adopted |
| 14 | OSM completeness in Libya is uneven; POI counts may under-represent some districts | Building sub-score noisier in poorly mapped areas | **Accepted** | Building footprints (satellite-derived, complete) carry most of the urban signal; POIs are one of three inputs |
| 15 | Data vintages differ: WorldPop 2020, WorldCover 2021, buildings 2026-08 release, OSM 2026-09 | Minor inconsistencies | **Accepted** | Documented in `DATASETS_OVERVIEW.md` |
| 16 | Resolution 8 chosen a priori; resolution 9 (~0.1 km²) not compared | Possible over-smoothing downtown | **Open** | `h3-grid --resolution 9` works out of the box; compare top-20 stability |
| 17 | Uncommitted work: all pilot code, outputs and ~208 MB of raw Phase-2 data are only on this machine | Risk of loss; teammates cannot run it | **Open** | Commit code + small outputs; decide with the team whether raw tiles go in git (repo already stores rasters) or a shared drive, and document the download URLs (they are in `DATASETS_OVERVIEW.md`) |
| 18 | The equipment recommender is scored on its own training data (README/technical report quote 89.55 %, and the report calls it "cross-validated"); its labels are hard-coded rules | Overstated accuracy; the model adds nothing over the rules | **Measured (§3.6)** | Held-out accuracy is 78.4% (municipality CV), against 78.7% for the feature-side rules alone and 54.1 % for always guessing the majority tier. Correct the quoted number; either present it as a rule engine, or relabel with real per-site capacity/utilization data |

---

## 5. Reproduce

```bash
cd antenna_cell_placement
uv sync
uv run antenna-placement experimental h3-all --city Tripoli        # ~5 min; grid, enrich, score, validate, map
uv run python -m unittest discover -s tests            # 32 tests
uv run antenna-placement experimental evaluate                      # municipality-held-out model evaluation (~2 min)
```
Individual steps: `h3-grid`, `enrich-h3`, `expansion-score`, `validate-h3`, `h3-map` (all accept `--city`). Raw inputs must exist in `data/external/{buildings,landcover,osm}/` (paths in `config.py`).
