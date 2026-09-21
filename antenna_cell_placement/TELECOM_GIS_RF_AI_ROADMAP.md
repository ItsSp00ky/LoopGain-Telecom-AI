# Telecom GIS, RF, and AI Roadmap

## Purpose

This roadmap evolves the current Libya GIS screening pipeline into a telecom planning system through sequential evidence gates. A new dataset or model is retained only after a reproducible comparison shows what it improved.

The dataset-only refactor and Steps 0-7 established the current baseline. Steps 8-11 evaluated land cover and selected OpenStreetMap evidence. Step 12 rejected Ookla runtime integration because shortlist coverage failed. Step 13 rejected VIIRS runtime integration because independent incremental validation was unavailable. Later sources remain **proposed** until their own gate is run; downloading a source does not by itself make it accepted evidence.

**Current position (2026-09-21):** Step 7 is accepted. Steps 8, 9, and selected Step 11 families are reversible `review-only` layers. Step 10, the Step 11 port proxy, and Step 12 have `remove` decisions. Step 13 is next; Steps 14-20 remain pending in the order below.

## Non-Negotiable Rules

- Declared source datasets are the only evidence inputs; every externally acquired source must pass its roadmap gate before broader use.
- Generated coordinates are allowed only as clearly labeled candidate placements.
- Synthetic labels, fabricated measurements, guessed operators, assumed equipment, and rule-created training targets are prohibited.
- Missing data remains visible and cannot silently become zero or an asserted fact.
- A planning priority is not a probability, RF prediction, or deployment decision.
- Every source has provenance, license, snapshot date, checksum, schema, units, CRS, and quality report.
- Every integration is reversible. The baseline pipeline must still run without the experimental source.
- Dataset files are never considered useful merely because they were downloaded.

## Gate Protocol Used by Every Step

Each step creates an evaluation record under a versioned report directory. The record contains:

1. **Question:** the planning uncertainty the source or tool is expected to reduce.
2. **Before:** a frozen baseline run using the same candidates, boundaries, configuration, and existing sources.
3. **Download record:** source URL or provider, license, release/snapshot date, retrieval date, checksum, byte size, and raw path.
4. **Quality profile:** schema, CRS, resolution, geographic coverage, temporal coverage, duplicates, invalid geometry, nodata, and outliers.
5. **Integration:** deterministic transformations with units and missing-data flags.
6. **After:** the same evaluation run with only the proposed source or stage added.
7. **Improvement check:** named metric, baseline value, treatment value, delta, and confidence or sensitivity where appropriate.
8. **Acceptance criterion:** a threshold written before viewing the result.
9. **Decision:** `keep`, `review-only`, `revise`, or `remove`, with a reason.

An integration cannot be marked complete without both the baseline and treatment reports. A failed experiment is removed from scoring but its report can remain as evidence.

## Common Evaluation Set

Create one stable evaluation package before adding sources:

- a fixed Libya boundary and candidate grid or H3 index;
- stratified samples for dense urban, suburban, settlement, road-corridor, rural, desert, mountain, border, and coast contexts;
- known-coordinate fixtures for distance and raster sampling;
- source availability masks;
- a baseline recommendation file with score components and reason codes;
- expert-reviewed candidate cases when reviewers become available;
- geographic holdouts that prevent nearby locations from appearing in both calibration and evaluation.

Until independent labels exist, improvement means better source completeness, internal consistency, geographic discrimination, rank stability, or agreement with an independent supplied reference. It must not be reported as predictive accuracy.

## Step 0: Freeze the Dataset-Only Baseline

**Status:** current implementation target.

Remove synthetic training examples, rule-created equipment labels, unmarked bandwidth assumptions, guessed operator defaults, and stale model-dependent outputs. Establish the explainable `planning_priority_score` and export every component.

**Before:** the legacy model workflow and its generated-label artifacts.

**After check:**

| Metric | Acceptance criterion |
| --- | --- |
| Generated rows in observed-data exports | 0 |
| Generated records outside candidate outputs | 0 |
| Public probability/equipment claims without observed targets | 0 |
| Same inputs/configuration produce identical scores and ranks | 100% |
| Candidate rows with component values, availability flags, and reason codes | 100% |
| Unknown operator/bandwidth/tower type preserved as unknown | 100% in controlled fixtures |

**Decision:** required. Do not proceed while prohibited generated evidence remains active.

## Step 1: Validate the Project-Provided Cellular Observations

**Dataset:** `Libyan_cells_dataset/cells.sqlite3` and `cells.json`.
**Status:** current; no download required.

Treat rows as observations. Document identity keys for each radio technology. Keep any spatial clustering as an inferred site reference, never a verified mast inventory.

**Before:** raw row and field profile.
**After:** validated observations, quarantine table, deduplicated radio identities, and optional inferred clusters.

**Improvement check:**

- invalid and quarantined rows have explicit reasons;
- duplicate identity count decreases without collapsing geographically incompatible records;
- within-identity coordinate spread is reported before and after;
- operator, bandwidth, and tower-type unknown rates are unchanged unless supplied evidence resolves them;
- manual review of a stratified identity sample finds no cross-region merges.

**Acceptance criterion:** 100% lineage from retained rows to raw rows, zero silent imputations, zero reviewed cross-region collisions, and all distance calculations pass known-pair tests.

**Keep/remove decision:** keep the cleaned observation layer if accepted. Remove any clustering rule that cannot meet the sample review.

## Step 2: Revalidate WorldPop

**Dataset:** supplied WorldPop population raster under `data/external/`.
**Status:** current.

**Question:** does the raster add a useful population proxy to candidate prioritization?

**Before:** run the fixed candidates with the population component disabled.
**After:** enable local and catchment population features.

**Improvement check:**

- valid-pixel coverage within inhabited boundary/settlement test areas;
- nodata and out-of-bounds counts remain separate from true zero;
- positive association between populated-place class or supplied settlement importance and catchment population;
- change in top-k geographic distribution and score-component coverage;
- expert review of candidates promoted only by population.

**Acceptance criterion:** at least 95% valid coverage at settlement fixtures, zero nodata-to-zero conversions, correct raster units/aggregation, and no regression in deterministic output.

**Decision:** keep as a demand proxy if accepted; revise preprocessing if coverage/units fail; remove from scoring if it cannot distinguish known settlement contexts.

## Step 3: Revalidate the Supplied Elevation Data

**Datasets:** active elevation raster under `data/external/dem/` and supplied HGT tiles under `data/Libya_SRTM/`.
**Status:** current; the active source must be declared.

**Question:** does terrain data provide complete, coherent screening evidence?

**Before:** fixed candidates without terrain components.
**After:** add elevation, slope, roughness, and local prominence only where valid.

**Improvement check:**

- Libya coverage and missing-tile map;
- agreement between overlapping active-raster and HGT samples;
- elevation ranges and discontinuities at tile edges;
- rank changes caused by terrain alone;
- known mountain/coastal/desert fixture behavior.

**Acceptance criterion:** at least 98% valid coverage of eligible candidates, no unexplained seam larger than a pre-registered elevation tolerance, and zero nodata-to-zero conversions.

**Decision:** select one documented active terrain source. Keep the second as an independent comparison or remove it from runtime to avoid duplicate complexity.

## Step 4: Revalidate Roads, Boundaries, and Settlements

**Datasets:** supplied vector layers under `data/external/roads/` and `data/external/admin_boundaries/`.
**Status:** current.

**Question:** do these layers add reliable access and reporting context?

**Before:** candidates without road-distance or place attribution.
**After:** add projected road distance, municipality, and nearest settlement.

**Improvement check:**

- valid-geometry rate, duplicate rate, CRS, and national coverage;
- known-point municipality and settlement attribution;
- road-distance error at hand-checked fixtures;
- number of candidates excluded or demoted by stated access limits;
- boundary-edge ambiguity count.

**Acceptance criterion:** 100% known-point attribution fixtures pass, at least 99% valid geometries after documented repair, and road-distance tolerance passes all fixtures.

**Decision:** keep road access and place labels when accepted. Do not treat road proximity as proof of legal access, power, fiber, or road condition.

## Step 5: Integrate OpenCellID `606.csv` as Review Evidence

**Dataset:** supplied `data/606.csv`.
**Status:** current.

The exact schema is:

```text
radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal
```

`unit` is PSC for UMTS or PCI for LTE and is empty for GSM/CDMA. `range` is an estimated range, not a coverage polygon or accuracy radius. `changeable` is deprecated and always 1. `averageSignal` is deprecated and always 0 and must never be interpreted as signal evidence.

**Question:** does OpenCellID add independent observations that improve candidate review?

**Before:** candidate report without OpenCellID proximity.
**After:** add validated, deduplicated cell proximity and review flags without changing observed-site counts or the core priority score.

**Improvement check:**

- exact 14-column schema acceptance and invalid-row quarantine;
- retained, duplicate, timestamp-valid, and review-eligible counts;
- distances between OpenCellID cells and project-provided site references;
- candidates newly flagged for review;
- operator-specific distance availability without forced attribution;
- manual review of near and far cases.

**Acceptance criterion:** 100% schema/identity fixtures pass, 100% rejected rows have reasons, no cell is counted as a physical mast, and candidate score/rank remains unchanged when the layer is configured as review-only.

**Decision:** keep as review-only evidence if quality is adequate. Revise recency/sample policies when the snapshot changes. Remove it from operational review if temporal or geographic coverage is too weak, while preserving the source report.

## Step 6: Reassess Cloudflare Regional Context

**Dataset:** supplied files under `data/cloudflare_radar_libya/`.
**Status:** current, optional.

**Question:** does coarse regional Internet activity add information beyond population and settlement context?

**Before:** baseline priority without Cloudflare.
**After:** add mapped regional fields and, only if justified, a bounded context adjustment.

**Improvement check:**

- one-to-one municipality mapping and temporal completeness;
- spatial uniqueness: national constants must not enter a location score;
- top-k rank displacement and municipality concentration;
- sensitivity across several small bounds, including zero influence;
- agreement with future independent KPI or reviewer labels.

**Acceptance criterion:** all region mappings resolve uniquely, missing regions remain flagged, maximum rank influence stays within the configured bound, and the source improves an independent review/KPI metric when one exists.

**Decision:** keep as descriptive context now. Add it to scoring only after independent improvement is demonstrated; missing context stays missing and has no scoring effect.

## Step 7: Establish H3 Planning Units

**Input:** no new evidence dataset; H3 is a spatial index.
**Status:** accepted on 2026-09-19 using H3 4.5.0.

Build reproducible hexagonal planning units and aggregate active evidence with area-aware methods.

**Before:** point/grid candidate workflow.
**After:** H3 demand, evidence availability, and priority layers.

**Improvement check:** national coverage, polygon-boundary leakage, conservation of population totals within tolerance, runtime, repeatability, and rank stability across adjacent H3 resolutions.

**Acceptance criterion:** no gaps/overlaps inside the planning boundary, aggregate population conservation within 1%, and documented resolution sensitivity.

**Measured result:** resolution 7 created 266,955 national planning units and assigned all 50 shortlisted candidates to distinct primary units. Its resolution 6 parent created 38,498 national units and consolidated the shortlist into 35 reporting units. Four-sample, area-weighted allocation of the supplied WorldPop density raster produced 100% sampled national coverage, effectively zero population conservation error, and an identical allocation digest on repeat. Candidate scores and ranks were unchanged. Direct point indexing at resolutions 7 and 6 agreed for 92% of shortlisted points; hierarchical resolution 6 parents are therefore used for reproducible rollups, and the 8% boundary sensitivity is retained in the report. The strengthened exact polygon check measured 0% internal gap, 0% overlap, and 1.4828% edge-cell leakage before clipping at resolution 6. It also detected and removed one duplicate cell returned across boundary parts rather than silently counting it twice.

**Decision:** keep H3 for indexing, aggregation, and reporting. It remains outside the priority formula. Evidence: `eval_reports/step_07_h3_evaluation.json`.

## Step 8: Download and Test ESA WorldCover

**Dataset:** ESA WorldCover.
**Status:** evaluated on 2026-09-19; retained as `review-only`.

**Question:** does land cover improve clutter and buildability screening?

**Before:** accepted Step 7 baseline without land cover.
**After:** add class proportions per planning unit and candidate.

**Improvement metric:** valid Libya coverage, class agreement on stratified visual/reference samples, candidates correctly screened from water or unsuitable surface, and later RF error reduction by clutter class.

**Acceptance criterion:** at least 98% eligible-area coverage, at least 90% agreement on the pre-labeled sample, zero water candidates after screening, and measurable RF validation improvement when RF truth exists.

**Implementation:** downloaded the 27 official ESA WorldCover 2021 v200 Cloud Optimized GeoTIFF tiles intersecting Libya (237,710,490 bytes total). `data/external/worldcover_2021/manifest.json` records every URL, byte size, SHA-256 digest, ETag, retrieval date, license, DOI, CRS, resolution, and class legend. Raw TIFFs remain local and ignored by Git. Candidate point classes are sampled in WGS84, confirmed class 80 water points are ineligible, and area-weighted class proportions are computed only for shortlisted H3 resolution 7 cells. Mixed or coastal cells are flagged for review rather than rejected. WorldCover does not affect `planning_priority_score`.

**Measured result:** all 27 manifest files passed size and SHA-256 verification. Tile footprints covered 100% of the supplied Libya boundary, all 3,725 otherwise eligible candidates had a valid class, and the minimum valid classified area across shortlisted H3 cells was 99.8057%. The screen removed five water points from the eligible pool (3,725 to 3,720) and left zero point-class water candidates. The top 50 stayed identical with zero rank displacement and unchanged scores. Five shortlisted land points in mixed/coastal H3 contexts were explicitly flagged for review. Incremental WorldCover point sampling took 3.88 seconds for 22,317 generated candidates in the final measured run; shortlist selection plus H3 land-cover context took 0.19 seconds versus 0.07 seconds for baseline selection.

**Tests completed:** 28 automated tests passed, including tile naming, water/land/missing-state separation, deterministic area-weighted H3 proportions, source-manifest tamper detection, strict water exclusion, exact H3 topology, population conservation, OpenCellID schema behavior, missing-data preservation, and deterministic scoring. The live gate also regenerated the placement CSV/GeoJSON and was followed by map regeneration.

**Decision:** keep WorldCover for deterministic water screening and review context only. The 90% independent class-agreement criterion cannot be tested because no pre-labeled Libya reference sample is provided, and RF improvement cannot be tested because no RF truth is available. Therefore Step 8 is not accepted for suitability scoring, buildability claims, or RF clutter modeling. Evidence: `eval_reports/step_08_worldcover_evaluation.json`.

## Step 9: Download and Test Building Footprints

**Dataset:** contributor-mapped OpenStreetMap building outlines from the Geofabrik Libya snapshot `libya-260919-free.gpkg.zip`, licensed under ODbL 1.0.
**Status:** implemented as `review-only`; source downloaded, verified, profiled, and integrated without changing scores or ranks.

**Question:** do observed building footprints improve built-up demand and constructability context?

**Before:** Step 8 baseline with review-only WorldCover screening and no building data.
**After:** building count, footprint area, density, and built-up ratio.

**Improvement metric:** coverage by municipality, geometry validity, precision/recall on stratified imagery/reference samples, correlation with settled areas, and expert preference for top-k candidate ordering.

**Acceptance criterion:** at least 95% coverage of the target inhabited area, at least 90% valid geometry after documented repair, and at least a 5 percentage-point improvement over population-only classification of the pre-labeled built-up sample.

**Implementation:** the exact dated archive and extracted GeoPackage are stored locally under `data/external/osm_libya_2026_09_19/`; `manifest.json` records source URL, snapshot date, retrieval date, hashes, byte sizes, CRS, layer, license, and attribution. The runtime reads only the building geometries near shortlisted H3 cells through the GeoPackage spatial index. It exports mapped building count, footprint area, coverage ratio, density, observation state, source availability, and review state. A missing mapped outline remains “not observed,” never “no building.” Microsoft and Google footprint products were excluded because their published methods describe machine-generated footprints, which conflict with this project's no-generated-evidence rule.

**Measured result:** the source contains 1,268,052 input features. Geometry validation retained 1,267,982 polygon rows after removing 84 exact duplicate geometries; all retained geometry was valid after repair. Every municipality had at least one mapped building, but only 70 of 78 supplied populated places (89.74%) had a mapped building within 1 km, below the 95% gate. Of the top 50 candidates, 43 H3 units contained mapped footprints and seven did not. The treatment preserved every score and rank exactly (Spearman rank correlation 1.0). National profiling took 12.18 seconds, shortlist spatial loading 3.85 seconds, and H3 context aggregation 0.10 seconds in the final recorded run.

**Tests completed:** 33 automated tests passed after integration. Building-specific tests cover deterministic equal-area aggregation, missing-outline semantics, single-coordinate assessment without a precomputed H3 land-cover summary, invalid-geometry repair, exact duplicate removal, and manifest size/hash tamper detection. The live gate verified the archive and GeoPackage hashes, regenerated CSV/GeoJSON outputs, recorded seven no-outline review cases, and confirmed that prohibited model/equipment fields were absent.

**Decision:** retain the source only as mapped-building review context. The inhabited-area threshold failed and no independent labeled built-up sample exists, so classification improvement cannot be measured. Do not use missing footprints as negative evidence, do not alter the priority score, and do not infer buildability. Evidence: `eval_reports/step_09_buildings_evaluation.json`.

## Step 10: Download and Test Building Height

**Dataset:** explicit `height=*` tags in the dated Geofabrik Libya OpenStreetMap PBF snapshot `libya-260919.osm.pbf`.
**Status:** evaluated and removed from runtime use.

**Question:** does vertical form improve capacity-demand or clutter screening beyond footprints?

**Before:** Step 9 review-only footprint baseline.
**After:** audit-only parsed height values, units, distribution, source metadata, and geographic coverage. No height fields were added to recommendations.

**Improvement metric:** spatial coverage, comparison with independent known-height samples, reduction in RF residual by urban morphology, and incremental reviewer/KPI value beyond footprint density.

**Acceptance criterion:** at least 50% national footprint coverage, at least 95% municipality coverage, median absolute error at most 3 m on an independent reference, and demonstrated RF/KPI improvement beyond the footprint baseline.

**Implementation:** downloaded the exact 76,584,743-byte dated PBF and recorded its SHA-256 digest, HTTP metadata, snapshot, license, attribution, and source policy in `height_manifest.json`. Only explicit `height=*` values are parsed. Metres and explicitly declared imperial units are supported, values outside 1-500 m are rejected, and `building:levels=*` is counted only for coverage auditing. Floor counts are never converted into height. Machine-learned and remotely inferred height products remain excluded under the generated-evidence rule.

**Measured result:** 3,050 building objects carried an explicit height tag; 3,042 parsed into plausible values, for 0.2399% coverage of the 1,268,052 mapped footprints. Valid heights appeared in 19 of 22 municipalities (86.36%) and in zero of the 50 shortlisted H3 cells. The median was 4 m and the 90th percentile 12 m. None of the valid values declared `source:height`. The raw snapshot contained 104,841 `building:levels` tags, but none was converted into metres. No independent height sample or RF/KPI truth was available. Source verification and profiling took 8.14 seconds in the final recorded gate.

**Tests completed:** 37 automated tests passed. Height-specific tests cover exact tag extraction, metre and imperial-unit parsing, plausible-range rejection, preservation of missing provenance, and manifest metadata/size/hash tamper detection. The live gate confirmed the recommendation file remained unchanged.

**Decision:** `remove` building height from runtime outputs and scoring. Every coverage and validation criterion failed. Retain only the provenance manifest and `eval_reports/step_10_building_height_evaluation.json` as audit evidence.

## Step 11: Download and Test OpenStreetMap

**Dataset:** a dated Libya OpenStreetMap extract with attribution and license metadata.
**Status:** evaluated on 2026-09-21; selected families retained as `review-only`.

**Question:** do POIs, land use, and infrastructure tags add useful local context beyond supplied roads and settlements?

**Before:** Step 9 footprint baseline with Step 10 height excluded.
**After:** selected, documented OSM feature families such as hospitals, universities, airports, ports, industrial areas, power, and backhaul proxies.

**Improvement metric:** tag completeness by region, duplication against existing roads, known-POI recall, candidate rank impact, and manual review of candidates promoted by sparse tags.

**Acceptance criterion:** each enabled feature family passes its own completeness test, improves a pre-labeled planning case set, and does not penalize regions merely because mapping activity is low.

**Implementation:** the gate reuses the checksum-verified Step 9 GeoPackage. It validates and deduplicates selected objects, converts polygon features to representative points, and adds per-family H3 resolution 7 counts, observation flags, and spherical nearest-feature distances. Each family has a pre-registered minimum feature count and municipality-coverage threshold. None affects eligibility, score, or rank.

**Measured result:** all 3,497 retained geometries were valid after removing 10 duplicate family/object rows. Hospitals retained 893 features with 100% municipality coverage; higher education retained 799 with 100%; aviation retained 87 with 90.91%; and industrial land use retained 1,706 with 100%. The port candidate contained only 12 ferry-terminal records in one municipality (4.55% coverage). All 50 candidates received source context, and score and rank values were identical before and after integration (Spearman 1.0). No independent labeled planning case set is available, so predictive improvement remains unmeasured.

**Tests completed:** 40 automated tests passed. Step 11 tests cover deterministic output, input non-mutation, rank preservation, representative-point handling for polygons, observation-only zero semantics, and required candidate fields. The live gate verified the source manifest and regenerated recommendation artifacts.

**Decision:** retain hospitals, higher education, aviation, and industrial land use as review-only context. Remove the ferry-terminal port proxy from runtime because regional completeness failed. Do not combine the families into a generic POI score, interpret missing mapping as absence, or add any family to ranking without independent planning/KPI validation. Evidence: `eval_reports/step_11_osm_context_evaluation.json`.

## Step 12: Download and Test Ookla Open Data

**Dataset:** Ookla open performance tiles, subject to availability and license.
**Status:** evaluated on 2026-09-21; removed from runtime.

**Question:** can measured speed, latency, and test density provide independent service-quality evidence?

**Before:** priority without performance observations.
**After:** spatially and temporally aggregated metrics with test-count support and uncertainty.

**Improvement metric:** Libya tile coverage, tests/devices per unit, temporal stability, agreement with independent drive tests/KPIs, and improvement in identifying reviewed underserved areas.

**Acceptance criterion:** pre-register minimum sample density, require coverage across target regions, and require improvement on a geographic holdout of independent service-quality labels. Units below support thresholds remain missing.

**Implementation:** downloaded the official 2025 Q2, Q3, Q4, and 2026 Q1 mobile shapefile archives and recorded URL, size, SHA-256, ETag, last-modified timestamp, license, attribution, and retrieval time. A reproducible downloader extracts tile centroids inside the supplied Libya boundary into a compact GeoPackage. The gate requires at least five tests and three devices per tile-quarter, at least two supported quarters per H3 resolution 7 unit, at least 50% municipality coverage, and at least 25% shortlist coverage. Test counts may be summed; device counts are never summed as unique people or national devices.

**Measured result:** the Libya subset contains 24,979 tile-quarter rows with 100% valid geometry, no duplicate quarter/quadkey rows, and one invalid metric row. Only 4,426 rows met the support threshold; 20,552 valid rows were below it. Supported observations reached 490 H3 units in any quarter, while 294 units met the two-quarter requirement and covered 20 of 22 municipalities (90.91%). Only 3 of 50 shortlisted candidate units (6%) met that requirement. Adjacent-quarter municipality download-speed Spearman correlations were 0.5702, 0.3113, and 0.4792, with a 0.4792 median. The treatment preserved every score and rank exactly. No independent drive-test or operator KPI labels were available.

**Tests completed:** 44 automated tests passed. Step 12 tests cover support thresholds, test-weighted speed and latency aggregation, non-mutation, explicit missingness for unsupported units, prohibition on device-count aggregation, required schema, and manifest tamper detection. The live gate verified all four global archives and the derived subset.

**Decision:** `remove` Ookla fields from recommendations, assessment, maps, and scoring. Municipality coverage passed, but candidate coverage failed decisively and temporal stability was modest. Retain the downloader, local snapshot, and `eval_reports/step_12_ookla_evaluation.json` as reproducible audit evidence. Reassess only with a newer supported snapshot or independent drive-test/KPI labels.

## Step 13: Download and Test VIIRS Night Lights

**Dataset:** monthly or annual VIIRS night-time lights composite.
**Status:** evaluated on 2026-09-21; removed from runtime.

**Question:** does night activity identify demand missed by population/buildings?

**Before:** accepted demand-proxy baseline.
**After:** radiance statistics after removing water, fires, and known artifacts where supported.

**Improvement metric:** incremental agreement with independent activity/KPI labels, collinearity with population/buildings, temporal stability, and false promotion of gas flares or industrial light sources.

**Acceptance criterion:** adds statistically and operationally meaningful holdout improvement, keeps artifact false-positive rate below a pre-registered threshold, and remains stable across selected months.

**Implementation:** the reproducible downloader uses range requests against official Cloud Optimized GeoTIFFs to retain only Libya bounding-box windows for January, April, July, and October 2024. Each radiance window is paired with its cloud-free observation-count raster. A pixel is supported only with at least three cloud-free observations in a month, and a candidate needs three supported months. Confirmed WorldCover water is ineligible. The median of selected months reduces transient influence. The official EOG 2024 flare catalog provides a 5 km gas-flare exclusion. The manifest records URLs, periods, units, bounds, license, sizes, and SHA-256 digests for 128,340,693 local bytes.

**Measured result:** all 50 shortlist candidates had at least three supported months; one fell within 5 km of a catalogued flare, leaving 49 (98%) after artifact exclusion. Adjacent selected-month Spearman correlations were 0.9653, 0.9660, and 0.9817 (median 0.9660), above the 0.75 threshold. Log-radiance correlated 0.3653 with 5 km population and 0.5037 with mapped-building density. A pre-registered hypothetical 10% radiance weight promoted five candidates into the top 10; none was within 5 km of a known flare. The four-month median is not an active-fire mask, the flare catalog cannot label every industrial source, and no independent activity/KPI labels are available for a geographic holdout.

**Tests completed:** all 49 automated tests passed. Step 13 tests cover true zero versus unsupported pixels, water exclusion, geodesic flare distance, candidate schema, non-mutation, and manifest tamper detection.

**Decision:** `remove` VIIRS from recommendations, assessment, maps, and scoring. Coverage, temporal stability, and the known-flare proxy pass, but the decisive incremental holdout-improvement criterion is untestable without independent labels. Retain the downloader, local snapshot, and `eval_reports/step_13_viirs_evaluation.json` as reproducible audit evidence. Redundancy or plausible correlation is not improvement.

## Step 14: Download and Test FABDEM

**Dataset:** FABDEM.
**Status:** proposed; not downloaded.

**Question:** does a bare-earth DEM improve terrain and RF results over the accepted elevation source?

**Before:** RF/terrain run using the selected current DEM.
**After:** identical run with FABDEM.

**Improvement metric:** coverage, voids, tile seams, agreement with independent elevation checkpoints, line-of-sight changes, and geographic-holdout RF error.

**Acceptance criterion:** better checkpoint error and RF error without worse coverage or artifacts. Define the minimum error reduction before the test.

**Decision:** replace the active DEM only if it wins the controlled comparison. Otherwise remove from runtime and retain the report.

## Step 15: Acquire Operator Asset and Configuration Data

**Datasets:** verified site/sector inventory, antenna catalogue, azimuth, tilt, height, bands, bandwidth, power, feeder loss, and backhaul endpoints.
**Status:** proposed; requires operator authorization.

**Question:** can the system progress from site-gap screening to engineering simulation?

**Before:** inferred site references and GIS priority only.
**After:** versioned, access-controlled asset and sector layers with field-level provenance.

**Improvement metric:** match rate to observed cells, required-field completeness, coordinate accuracy against surveyed samples, sector consistency, and age.

**Acceptance criterion:** thresholds are agreed with RF engineers before ingestion; records below completeness/confidence thresholds remain excluded or explicitly uncertain.

**Decision:** keep secured authoritative fields. Never fill missing antenna or spectrum values with generic assumptions in production outputs.

## Step 16: Integrate RF Simulation

**Tools:** GRASS-RaPlaT for area coverage; SPLAT! or an accepted equivalent for terrain profile, LOS, and backhaul checks.
**Status:** proposed.

Start with a reproducible link budget and propagation configuration based on supplied operator parameters. Record frequency, EIRP, antenna pattern, height, receiver assumptions, clutter, DEM, resolution, and software version.

**Before:** explainable GIS priority only.
**After:** calibrated predictions such as RSRP/received power, best server, overlap, newly covered population, and LOS evidence.

**Improvement metric:** median and 90th-percentile prediction error against geographically held-out drive-test points; coverage-threshold precision/recall; error by terrain/clutter/region; runtime.

**Acceptance criterion:** RF engineers pre-register tolerances. A reasonable starting target for review is median absolute RSRP error at or below 8 dB and 90th percentile at or below 15 dB, with no region consistently outside tolerance. These are acceptance proposals, not current results.

**Decision:** calibrate and revise until accepted. Do not publish RF-validated recommendations from an uncalibrated model.

## Step 17: Integrate Operator KPI and Drive-Test Evidence

**Datasets:** temporally aligned, privacy-safe RSRP, RSRQ, SINR, throughput, drops, accessibility, retainability, PRB utilization, active users, and traffic.
**Status:** proposed; requires operator authorization and governance.

**Question:** do candidates target observed service or capacity problems?

**Before:** GIS plus calibrated RF ranking.
**After:** KPI-supported underserved and capacity-priority components.

**Improvement metric:** spatial/temporal coverage, sample support, agreement between predicted and measured weak-service areas, top-k precision against RF-engineer labels, and stability across time windows.

**Acceptance criterion:** minimum sample support and time alignment are defined before use; geographic holdout performance must beat the GIS+RF baseline; privacy and access controls pass review.

**Decision:** keep KPI components only where supported. Do not turn missing KPI regions into low-demand or good-service regions.

After the evidence layer passes, test traffic/PRB forecasts and anomaly detection as separate models. Traffic forecasts must beat seasonal-naive and recent-value baselines on temporal and geographic holdouts. Anomaly alerts must be evaluated against independently recorded incidents or engineer labels with a pre-registered false-alert limit. Suggested actions such as load balancing, tilt review, carrier activation, backhaul improvement, or new-site study remain recommendations for an engineer; they are not automatic consequences of a forecast.

## Step 18: Optimize Candidate and Sector Scenarios

**Input:** accepted GIS, RF, asset, and KPI stages.
**Status:** proposed.

Generate candidate coordinates within high-priority planning units and test documented scenarios. Optimize measurable objectives such as newly covered population, weak-service reduction, overlap, interference, access, power/backhaul feasibility, and cost.

**Before:** independently ranked points.
**After:** scenario portfolios with constraints, trade-off frontiers, and marginal benefit per site.

**Improvement metric:** gain over the greedy baseline on held-out scenarios, constraint violations, sensitivity to uncertain inputs, and reviewer acceptance.

**Acceptance criterion:** zero hard-constraint violations, measurable objective gain over baseline, and stable choices under pre-registered perturbations.

**Decision:** keep the simplest optimizer that passes. Equipment and sector settings remain engineering outputs from supplied constraints, not learned guesses.

## Step 19: Consider AI Only with Real Outcomes

**Eligible labels:** RF-engineer acceptance, acquisition success/failure, commissioned-site KPI improvement, calibrated measured coverage, or another independently observed outcome.
**Status:** future.

**Before:** explainable weighted baseline using the same evidence.
**After:** candidate model trained without generated labels and evaluated on geographic and temporal holdouts.

**Improvement metric:** task-appropriate calibration and ranking metrics, performance by region, error analysis, stability, explanation quality, and operational reviewer benefit.

**Acceptance criterion:** pre-register a minimum improvement over the explainable baseline, pass calibration and fairness/geographic checks, and demonstrate value on untouched outcomes.

**Decision:** deploy only if it adds reproducible value. Otherwise retain the explainable baseline. Never train on generated negatives or rule-created equipment labels.

## Step 20: Production Data and Review Platform

**Components:** PostGIS for versioned geospatial data, QGIS for engineering review, and GeoServer/QGIS Server plus MapLibre if a web interface is needed.
**Status:** proposed.

**Before:** file-based local workflow.
**After:** access-controlled, auditable scenario and review system.

**Improvement metric:** query/runtime targets, reproducible scenario rebuilds, lineage completeness, concurrent review, export integrity, recovery tests, and user-task completion time.

**Acceptance criterion:** 100% source-to-output lineage, role-based access for restricted data, successful backup/restore exercise, deterministic rebuild of an accepted scenario, and no loss of units or missingness during export.

**Decision:** adopt components only when scale or collaboration requires them. QGIS remains the engineering inspection surface regardless of web deployment.

## Score Evolution

The score name communicates the evidence stage:

| Stage | Output | Meaning |
| --- | --- | --- |
| Current | `planning_priority_score` | Relative GIS screening priority |
| After accepted RF gate | `rf_scenario_score` plus physical metrics | Comparison within a declared RF scenario |
| After accepted KPI gate | `service_improvement_priority` | Priority supported by measured network evidence |
| After accepted outcome model | model-specific calibrated output | Only the outcome defined by its real labels |

Keep the component values even after later stages are added. A single opaque “AI suitability” field is not an acceptable final output.

## Required Deliverables at Every Gate

- raw-source provenance manifest;
- quality and missingness report;
- baseline and treatment configuration;
- before/after metric table;
- geographic difference map;
- rank-change and sensitivity report;
- failed-case sample;
- keep/review-only/revise/remove decision;
- updated limitations and attribution;
- tests for schema, units, missingness, and determinism.

The project advances one accepted gate at a time. This keeps improvements measurable and makes it possible to remove a weak dataset without destabilizing the rest of the planning pipeline.
