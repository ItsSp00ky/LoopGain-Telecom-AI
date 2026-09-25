# Phase 2: GIS feature version 2 and preliminary rooftop review

**Integration update (23 September 2026):** The public `recommend`, `all`, `assess`/`predict` and `map` workflow now uses GIS v2 and Ahmed’s explainable heuristic. ML is excluded from primary ranking; old model-based commands are under `experimental`. See [the current integration guide](INTEGRATED_PLANNING.md) for the shared contract, source checks, runnable commands and validation. Historical results and implementation descriptions below retain their original scope.

Updated 2026-09-22. This implements Milestone 2 of the improvement plan plus a preliminary building-footprint shortlist. It is separate from the older command `enrich-h3`, which adds building, land-cover and OSM aggregates.

## What the system can decide

The system can prioritize areas, find mapped building footprints in those areas, and provide interior coordinates for a survey shortlist. It cannot currently identify the tallest suitable building or approve an antenna installation.

The two local Microsoft footprint tiles contain **970,860 records**, all with height `-1` in the earlier complete data audit. That sentinel means height is unavailable. The new pipeline scans both files again and records its height audit in the run manifest. This finding applies to these local files, not every possible building source in Libya. OSM height availability has not been verified.

The DEM measures approximate ground elevation, not building height. A high ground-elevation value does not imply a tall building. Neither the DEM nor footprint area establishes structural loading, usable flat roof space, ownership, power, backhaul, antenna clearance, obstruction, or RF coverage benefit. The highest building is not automatically the best installation site.

## Versioned GIS contract

Feature version: `gis_v2_density_circles_geodesic_20260922`.

| Measurement | Version 2 definition | Limits |
|---|---|---|
| Population density | Floor-indexed source pixel, declared people per square kilometre | Approximate 2020 population, not current demand |
| Population within 3/5 km | WGS84 geodesic circles, 96 vertices; density times intersected pixel area in EPSG:6933 | Uniform density within each raster pixel; circle polygon approximation |
| Population in H3 hex | Density times exact projected pixel/hex intersection area | No resampling to invent finer population detail |
| Missing population | Nodata and outside extent remain missing; observed subtotal and valid-area fraction are retained | Strict total requires at least 99% valid area; ocean/nodata is not silently zero |
| Terrain elevation | Floor-indexed DEM value, including valid negative elevations | About 250 m source resolution; no roof height |
| Terrain slope | Central differences divided by actual ellipsoidal horizontal distances | Requires valid neighbouring pixels |
| Terrain prominence | Elevation minus area-weighted mean of valid pixel centres within 3 km | Requires full raster extent and at least 99% valid selected centres |
| Site and settlement distance | WGS84 ellipsoidal distance | Inventory completeness limits inferred gaps |
| Site density | Counts within geodesic 1/3/5/10 km circles | Existing site excluded by identity, not coordinate coincidence |
| Road distance | Nearest actual line geometry in the query's local UTM zone | Projection approximation, not driving distance or verified access |
| Municipality | Polygon intersection; outside polygons remains missing | Historical experiment groups separately preserved for fair comparison |

### Population source units and provenance

The [WorldPop Libya 2020 population-density product](https://hub.worldpop.org/geodata/summary?id=47207) defines density in people/km2. The local `lby_pd_2020_1km.tif` has no unit tag. Version 2 explicitly declares the density interpretation based on this product family; the precise UN-adjustment provenance of the local file is not established by its shortened filename. The manifest records its hash, CRS, transform, dimensions, nodata and metadata. A future source replacement must verify provenance and trigger a new feature version.

Multiplying density by intersected area converts it to people. For example, 100 people/km2 over 0.8 km2 contributes 80 people. Summing raw density pixels alone is not a population count.

### Inventory audits

`radio_inventory_scoped_v2.csv` separates `(RAT, region, site, network)` keys. Explicit network codes and the source-scoped owner confirmation are retained; unknown network identities remain unknown. The audit detects cross-network collisions in legacy keys.

Reported bandwidth is the latest nonempty observed bandwidth-list total per scoped group. Repeated observations are not summed into capacity. Missing carrier/sector identity means this is an observed snapshot, not verified aggregate RF capacity. The table also retains the naive sum for comparison.

Physical clusters are checked using their full geodesic diameter. Connected chains wider than 50 m are flagged for review. Stable legacy physical-site IDs are retained for this controlled feature experiment; flagged clusters are not silently reclustered. Legacy estimated bandwidth fields are not v2 suitability-model inputs.

## Model experiment and migration

The runner remeasures the same 6,615 frozen example coordinates used in the first experiment. It keeps row identity, labels, sample kind, development/test assignment and historical municipality groups unchanged. Actual v2 polygon membership is a separate field.

Both legacy and v2 features are trained with the same LightGBM settings and development-only median imputation with missingness indicators. Five-fold municipality-grouped development predictions and geographic test predictions are saved. Baseline population missing values use the development median. This is a controlled feature comparison; the previously inspected geographic test is not a new blind benchmark. Synthetic non-site labels are not known failed installation locations.

Neighbour features use the known full site inventory, excluding an observed positive's own site identity. They are not an isolated test of reconstructing a completely unseen network. Missingness, coast proximity and the negative-sampling scheme can themselves distinguish the classes; higher AUC does not resolve those target limitations.

The model artifact wraps prediction with a required feature-version check. Passing legacy or unversioned features fails. The pipeline writes a separate artifact and does not promote it into the serving model. Existing `train`, `recommend`, `predict` and `h3-all` remain on their legacy contract until a deliberate migration.

## Tripoli ranking and rooftop shortlist

1. Recompute circle features for all Tripoli hex centroids and population totals inside the hexes.
2. Carry existing building/land-cover/OSM aggregates and site-in-hex counts by validated H3 identity. These existing aggregates are not refreshed from raw sources in this run.
3. Apply the existing water mask and transparent area-demand formula. Unknown normalized inputs receive neutral values; valid-area fractions remain visible for review.
4. Apply the separate v2 classifier through the existing bounded priority multiplier, `need * (0.75 + 0.5 * suitability)`.
5. Scan building footprints in the top 20 ranked areas. Keep up to five footprints per area with at least 150 m2 footprint area, ordered by area priority then footprint area. Assign each building using an interior representative point.
6. Export survey coordinates, footprint geometry/area, source tile/line, height availability, nearby road/site distances, ground elevation and explicit unverified feasibility fields.

This footprint ranking is a configurable review heuristic. Footprint area is not usable roof area and is not a height estimate. Candidate points are for building review, not approved antenna mounting positions. The shortlist does not yet optimize additional population coverage, roof-specific RF propagation or interference.

Height-aware selection needs measured height or a validated height estimate with source, date and uncertainty; antenna mounting height; terrain and surrounding obstructions; sector parameters; and a site survey. Then roof-specific RF/feasibility checks can compare buildings. Use unknown values now instead of fabricated storeys or heights.

## Reproduction and outputs

From the antenna project folder, with its environment and existing local datasets:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m antenna_cell_placement.cli phase2 --output-dir eval_reports/phase2_v2
```

Choose a new output directory on each full run. The runner refuses to overwrite an existing directory. The default frozen dataset is `eval_reports/experiment_20260922_v1/dataset.parquet`.

The completed verified run is **`eval_reports/phase2_v2_run2/`**. The earlier `phase2_v2/` directory contains only an incomplete inventory audit from before directory-format DEM hashing was corrected; use the completed run for results. A completed run has `completed_utc` in its manifest.

| Output | Purpose |
|---|---|
| `manifest.json` | Version, input/code hashes, raster metadata, audits, missing-feature counts and completion status |
| `radio_inventory_scoped_v2.csv`, `inventory_audit.json` | Network identity and observed bandwidth audit |
| `physical_site_cluster_audit.csv` | Full cluster diameters and review flags |
| `physical_sites_features_v2.parquet/csv` | Remeasured physical-site features |
| `dataset_v2.parquet` | Frozen examples with corrected GIS features |
| `model_comparison.json`, `comparison_predictions.csv` | Controlled feature comparison and per-row predictions |
| `suitability_gis_v2.joblib` | Separate feature-version-checked candidate model |
| `h3_features_Tripoli_v2.parquet` | Versioned centroid and hex population features plus carried aggregates |
| `h3_scores_Tripoli_v2.csv/geojson` | Ranked pilot areas |
| `rooftop_candidates.csv/geojson`, `rooftop_candidates_map.html` | Preliminary building review shortlist |

The HTML map embeds the project's local basemap, but Folium/Leaflet browser libraries still require their configured CDN access. It is not a fully offline application.

## Verification results

The inventory audit has 4,258 raw observations, 2,338 network-scoped radio groups and 2,115 retained physical sites. It found zero cross-network legacy-key collisions and zero groups with repeated-observation bandwidth inflation in this source. There are 623 groups with an observed bandwidth list. Five physical clusters exceed a 50 m full diameter; the largest is 87.064 m. See the cluster CSV for review IDs and distances.

| Physical-site ID to review | Full diameter (m) |
|---|---:|
| 4 | 51.76 |
| 83 | 55.46 |
| 459 | 53.35 |
| 704 | 69.26 |
| 1000 | 87.06 |

**62 tests passed**, including synthetic density/count conservation, missing coverage, floor indexing, negative terrain elevation, metric slope, western/eastern geodesic distances, line-interior road distance, self exclusion, network scoping, chain detection, directory-raster hashing, version rejection and rooftop geometry/unknown-height behaviour. Passing tests verifies specified software behaviour, not roof feasibility or RF benefit.

Controlled comparison in `eval_reports/phase2_v2_run2/model_comparison.json`:

| Metric | Legacy features, same training recipe | GIS v2 |
|---|---:|---:|
| Grouped development ROC-AUC (4,008 rows) | 0.9028 | 0.9039 |
| Geographic diagnostic test ROC-AUC (2,607 rows) | 0.9033 | 0.9107 |
| Hard-negative test ROC-AUC (2,033 rows) | 0.8761 | 0.8852 |
| Hard-negative average precision | 0.8370 | 0.8453 |
| Hard-negative Brier score (lower is better) | 0.10455 | 0.10466 |
| Population-only hard-negative AUC | 0.5945 | 0.5720 |

The AUC improvement is modest (+0.0091 on hard negatives); hard-negative Brier score is slightly worse. No uncertainty interval or significance claim is provided. All comparisons use the same saved rows. Corrected population units/geometry change the population baseline too. These results do not establish RF coverage improvement or calibrated deployment probabilities.

The full run completed on 2026-09-22. It regenerated 2,115 physical-site rows, all 6,615 experiment rows and 2,987 Tripoli hexes. The existing water mask excluded 771 hexes, leaving 2,216 ranked areas. There are 761 hexes with less than 99% population raster coverage; this count covers the entire grid, including masked areas.

The building scan read all 970,860 records: **zero usable heights**, 970,860 missing heights, and 25 invalid geometries skipped. It exported **100 footprint candidates across the top 20 areas**, five per area, each at least 150 m2. Every output coordinate was verified to lie inside its footprint. The HTML map was generated; visual browser QA could not run because the browser tool reported no available browser.

`integration_verification.json` confirms preserved coordinates/rows/labels/splits, disjoint municipality groups, saved-model reload matching test predictions, rejection of legacy features, valid shortlist geometry and unchanged raw-database/serving-model hashes. The verification script is saved alongside the report and runs from the project root.

Missingness is material: strict 5 km population totals are unavailable for 1,707 of 6,615 examples (742 observed sites, 234 background/corridor negatives, 731 hard negatives). Source nodata and incomplete catchment coverage stay visible. The model imputes from development data; this does not recover measured population. The different missingness rates by sample type are a validation concern for a later independent experiment.

## Next gates

Milestone 3 remains incremental coverage selection on common demand cells with overlap counted once, operator/RAT scenarios, budgets and identical candidate baselines. Milestone 4 adds independent spatial/prospective evaluation. RF calibration and field feasibility remain later gates. No classification AUC should be presented as measured coverage improvement.
