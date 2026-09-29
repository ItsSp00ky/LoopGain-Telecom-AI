# Telecom GIS Planning: Technical Report

**Project:** Libya antenna cell placement planning
**Team:** Loop Gain, Samsung Innovation Campus capstone
**Document status:** Dataset-only implementation specification
**Updated:** 2026-09-21

## Executive Summary

The project is a decision-support pipeline for screening possible new cellular locations in Libya. It validates supplied cell observations, derives geographic evidence from supplied GIS layers, generates candidate coordinates, and ranks those proposals for engineering review.

The current system is not a trained site-suitability classifier. The former classifier learned to separate observed sites from generated negative points, so its high cross-validation scores measured that constructed task rather than future deployment success. The former equipment model learned rule-created labels and then reproduced those rules. Those metrics and models are not valid evidence of real-world performance and are no longer part of the intended design.

The replacement output is an explainable `planning_priority_score`. Each component comes from supplied data and is exported for audit. The score is a relative priority within a run. It is not a probability, coverage prediction, capacity estimate, or permission to deploy.

Roadmap Step 8 downloaded and evaluated official ESA WorldCover 2021 v200. It is retained only for deterministic water screening and review context. The gate remains `review-only` because no independent labeled Libya land-cover sample or RF truth is available; it does not enter the priority score or support RF/buildability claims.

Roadmap Step 9 downloaded and evaluated contributor-mapped OpenStreetMap building outlines from a dated Geofabrik Libya extract. They are retained only as mapped-building review context. The gate remains `review-only` because settled-area coverage was below threshold and no independent built-up labels exist. Building context does not enter the score, and an absent outline is not evidence that a building is absent.

Roadmap Step 10 audited explicit building heights in the matching dated OpenStreetMap PBF. The source failed every coverage and validation threshold and is excluded from runtime outputs and scoring. Floor counts were not converted into heights, and generated height products were not used.

Roadmap Step 11 evaluated hospitals, higher education, aviation, industrial land use, and a ferry-terminal port proxy from the same checked GeoPackage. The first four are retained as review-only context; the port proxy failed regional completeness and is excluded. These observations do not affect the score or rank.

Roadmap Step 12 evaluated four quarters of official Ookla mobile-performance tiles. The source passed national municipality coverage but failed candidate coverage, so it is retained only as audit evidence and is excluded from runtime outputs and scoring.

Roadmap Step 13 evaluated four official monthly VIIRS night-light composites with cloud-free support and a 2024 gas-flare exclusion. Coverage and temporal stability passed, but no independent activity/KPI labels exist to demonstrate incremental holdout improvement. VIIRS is retained only as audit evidence and excluded from runtime outputs and scoring.

## Engineering Principles

1. Supplied observations remain distinguishable from derived fields and generated proposals.
2. Candidate locations are the only generated data records allowed.
3. Unknown values remain unknown. A default used for computation must carry an availability or imputation flag and must not be presented as measured.
4. Every score must expose its components, source availability, units, direction, and version.
5. A cell observation is not automatically a physical mast; a site-distance gap is not automatically an RF coverage gap.
6. Recommendations are screened candidates. RF design, equipment selection, acquisition, and construction require separate evidence.
7. Dataset additions are experiments until an explicit before/after gate accepts them.

## Data Inventory and Provenance

| Source | Role | Status | What it cannot establish |
| --- | --- | --- | --- |
| `Libyan_cells_dataset/cells.sqlite3` | Supplied cellular observations | Active input | A verified current asset register or coverage footprint |
| `Libyan_cells_dataset/cells.json` | Supplied cellular observations | Preserved source; not read by the current runtime | Missing operator, bandwidth, or tower type |
| `data/606.csv` | OpenCellID MCC 606 observations | Active, separate review layer | Physical mast identity, coverage, capacity, or signal quality |
| WorldPop density raster under `data/external/` | Population proxy in people/km² | Active input | Mobile subscriptions, busy-hour traffic, or current population |
| Elevation data under `data/external/` | Terrain evidence | Active input | RF propagation without clutter, antenna, frequency, and calibration inputs |
| SRTM HGT tiles under `data/Libya_SRTM/` | Supplied elevation source | Preserved; active use depends on pipeline configuration | Complete RF-ready terrain merely by being present |
| Roads under `data/external/` | Access and corridor proxy | Active input | Legal access, road condition, power, or fiber availability |
| Boundaries and settlements under `data/external/` | Administrative and place context | Active input | Demand or coverage |
| `data/cloudflare_radar_libya/` | Regional Internet-activity context | Optional bounded context | Mobile-only traffic, radio demand, operator KPI, or local coverage |
| ESA WorldCover 2021 v200 under `data/external/worldcover_2021/` | Water exclusion and land-cover review context | Active `review-only` input | Buildability, ownership, current surface condition, or calibrated RF clutter |
| OpenStreetMap buildings from Geofabrik snapshot `libya-260919-free.gpkg` | Mapped-building density and footprint review context | Active `review-only` input | Building absence, completeness, height, ownership, access, or constructability |
| Explicit OSM height tags from `libya-260919.osm.pbf` | Step 10 source audit | Rejected from runtime; audit evidence retained | Reliable national height, measurement accuracy, RF clutter, or capacity demand |
| Selected OSM POI, transport, and land-use families | H3 observations and nearest-feature review context | Active `review-only` input for four accepted families | Complete facility inventory, demand, access, capacity, or backhaul |
| Ookla mobile tiles, 2025 Q2-2026 Q1 | Step 12 measured-performance audit | Rejected from runtime; local audit snapshot retained | Representative coverage, operator KPI, RF cause, or underserved-area truth |
| VIIRS DNB monthly composites, 2024 | Step 13 night-activity proxy audit | Rejected from runtime; local bounded snapshot retained | Mobile demand, traffic, coverage, service quality, or independently validated incremental value |

Legacy files under `data/cleaned/`, `models/`, and historical evaluation reports are derived artifacts, not independent evidence. The dataset-only runtime performs cleaning and feature derivation in memory and retains only proposed-placement CSV/GeoJSON and their review map. Retained artifacts must remain reproducible from the supplied inputs and pipeline version.

## OpenCellID Contract for `606.csv`

The importer accepts exactly 14 columns, with either a header row or this headerless order:

| Column | Type | Meaning and treatment |
| --- | --- | --- |
| `radio` | string | Radio technology such as GSM, UMTS, LTE, or CDMA. |
| `mcc` | integer | Mobile Country Code. This project validates MCC 606. |
| `net` | integer | Mobile Network Code, or SID for CDMA. It must not be replaced by a guessed value. |
| `area` | integer | LAC, TAC for LTE, or NID for CDMA. |
| `cell` | integer | Cell ID; for UMTS this is the combined RNC and cell identifier, and for CDMA the BID. |
| `unit` | integer | PSC for UMTS or PCI for LTE; empty for GSM and CDMA. It is not a site ID. |
| `lon` | double | Estimated cell longitude in degrees, from -180 to 180. |
| `lat` | double | Estimated cell latitude in degrees, from -90 to 90. |
| `range` | integer | Estimated cell range in metres. Retained as source metadata only; it is not used as a coverage polygon or location-accuracy bound. |
| `samples` | integer | Number of measurements assigned to the cell. It supports review filtering but does not calibrate positional accuracy by itself. |
| `changeable` | integer | Deprecated; always 1. It carries no planning signal. |
| `created` | integer | Unix timestamp for first appearance in the database. |
| `updated` | integer | Unix timestamp for last update. |
| `averageSignal` | integer | Deprecated; always 0. It is not a signal-strength measurement. |

Source definition: [OpenCellID database format](https://docs.opencellid.org/docs/downloads/database-format#Columns_present_in_database).

Validation checks column count, data types, identity fields, MCC, coordinate bounds, and timestamp consistency. Invalid rows are quarantined with a reason. Deduplication uses the cell identity `(radio, mcc, net, area, cell)` and retains the best documented recent record. Quality thresholds such as minimum samples or recency are review policies, not statistical confidence.

OpenCellID stays separate from the project-provided site reference. Candidate annotations record distance to relevant observations and whether human review is warranted. They do not alter an observation into a mast, create training labels, or prove that an area is served or unserved.

## Processing Method

### 1. Validation and cleaning

The pipeline validates source schemas, coordinates, identifiers, and timestamps before analysis. Duplicate radio observations may be consolidated only with a documented identity key. Spatially close observations may be grouped into a site reference for planning, but the result must be described as an inferred cluster rather than a verified physical mast.

Operator identity is retained only when present in a supplied source or supported by an explicit, separately reported mapping. Unresolved values remain `Unknown`. Missing tower type, radio bandwidth, antenna configuration, and capacity remain missing.

### 2. Geographic features

The feature stage joins candidates and observed-site references to supplied layers. Typical fields include:

- local population density and geodesic 5 km population catchment from WorldPop;
- elevation and local terrain context from the active elevation raster;
- distance to the supplied road network;
- municipality and nearest settlement;
- distance to observed-site references;
- optional regional Cloudflare context;
- explicit availability flags for each source family.

All distances require a suitable projected coordinate reference system and unit tests at known point pairs. Raster nodata, coordinates outside a raster, and failed samples remain missing. A true source value of zero must be distinguishable from unavailable data.

The supplied WorldPop file is a density raster in people/km². Density is multiplied by each geographic pixel's ellipsoidal area before population counts are summed. Candidate catchments use a geodesic 5 km radius rather than a square pixel window.

### 3. H3 planning units

Accepted Step 7 uses H3 resolution 7 for primary reporting and its resolution 6 parent for sensitivity and rollups. Candidate rows carry both identifiers. WorldPop density is converted to population counts and divided across four quadrant samples per source pixel, which gives boundary pixels an area-aware weight. The national allocation and H3 unit tables remain in memory; only the compact acceptance report is retained.

The accepted evaluation recorded 266,955 national resolution 7 units, 38,498 resolution 6 units, 100% candidate ID coverage, 100% sampled national coverage, effectively zero population conservation error, and unchanged candidate scores and ranks. Direct point indexing at the adjacent resolutions agreed for 92% of shortlisted candidates, so resolution 6 identifiers are derived from the resolution 7 parent hierarchy. This boundary sensitivity is recorded rather than hidden. An exact equal-area polygon check additionally measured 0% internal gap, 0% overlap, and 1.4828% edge-cell leakage before boundary clipping at resolution 6.

### 4. WorldCover screening

Step 8 uses 27 official ESA WorldCover 2021 v200 tiles at approximately 10 m resolution. The provenance manifest stores source URLs, retrieval metadata, byte sizes, SHA-256 hashes, license, DOI, CRS, and class legend; the gate verifies file contents before evaluation.

Every generated candidate receives a point class, availability flag, and explicit water flag. A candidate whose observed point class is permanent water is ineligible. After shortlist selection, raster pixels inside each H3 resolution 7 polygon are weighted by ellipsoidal pixel area to derive classified-area coverage, dominant class, and water, built-up, and bare/sparse proportions. Cells with less than 98% valid coverage or more than 20% water are flagged for human review. A mixed coastal cell is not automatically rejected when the candidate point itself is on land.

The measured run covered 100% of the supplied national boundary by tile footprint and 100% of 3,725 otherwise eligible candidate points. It removed five water points, leaving 3,720 eligible candidates and zero water points after screening. The same 50 candidates retained the same scores and ranks; five mixed/coastal shortlist cells were flagged. Minimum shortlist H3 classified-area coverage was 99.8057%. Point sampling added 3.88 seconds across 22,317 proposals, while treatment selection and H3 context took 0.19 seconds compared with 0.07 seconds for baseline selection.

The layer improves a concrete geographic safety check, but predictive accuracy has not been established. Without an independently labeled reference sample, the 90% agreement criterion is pending. Without RF measurements, no clutter-error improvement can be claimed. WorldCover therefore remains outside the score and RF logic.

### 5. Mapped-building context

Step 9 uses the `gis_osm_buildings_a_free` layer from the dated Geofabrik Libya OpenStreetMap extract. The manifest records the exact archive URL, snapshot and retrieval dates, archive and GeoPackage hashes and byte sizes, layer, CRS, ODbL license, and required attribution. The runtime uses the GeoPackage spatial index to load only geometry near shortlisted H3 resolution 7 cells.

Building polygons are validated, repaired when necessary, and deduplicated by exact geometry. Area is calculated in equal-area EPSG:6933. Each shortlist row exposes mapped building count, footprint area, H3 coverage ratio, density per square kilometre, whether at least one footprint was observed, source availability, and a review flag. These are descriptive fields only.

The recorded gate profiled 1,268,052 input features and retained 1,267,982 polygon rows after removing 84 exact duplicates; all retained geometry was valid. All 22 municipalities had mapped outlines, while 70 of 78 supplied populated places (89.74%) had an outline within 1 km, below the 95% acceptance threshold. Forty-three of the top 50 H3 units contained mapped outlines. Scores and ranks were unchanged, with Spearman rank correlation 1.0. Because mapping completeness varies and no independent labeled sample was supplied, no classification-accuracy or buildability improvement is claimed.

### 6. Building-height audit

Step 10 uses the raw PBF matching the Step 9 snapshot because the simplified GeoPackage does not expose height tags. Only explicit OSM `height=*` values are parsed. Values may use metres or explicitly declared imperial units and must fall within 1-500 m. The audit retains raw values and optional `source:height` and `height:accuracy` metadata. It does not derive height from `building:levels`, and it excludes machine-learned or remotely inferred height products.

The gate found 3,050 explicit height tags and accepted 3,042 plausible values. That is 0.2399% of the 1,268,052 mapped footprints. Valid values occurred in 19 of 22 municipalities and zero of the 50 shortlisted H3 units; none declared `source:height`. The source therefore failed the pre-registered 50% national coverage, 95% municipality coverage, independent median-error, and RF/KPI-improvement criteria. No height field was added to candidate outputs, and the recommendation file remained unchanged.

### 7. Candidate generation

Candidate coordinates are generated from documented planning geometry: supplied settlement rings and sampled supplied road geometry. Every retained proposal carries a generation source, score version, and deterministic candidate identifier.

Candidate generation does not create labels. It must respect national and source coverage boundaries, exclude invalid locations, and apply stated minimum spacing without silently weakening constraints to reach a target count.

### 8. Explainable priority ranking

The current ranking engine combines four normalized evidence components:

- population catchment or demand-proxy score;
- observed-site gap score;
- road-access score;
- terrain screening score based on slope and local prominence.

As of score version `dataset-priority-v2-metric-terrain`, slope uses geodesic east/west and north/south pixel spacing in metres, and prominence uses a circular 3 km physical-distance window. The earlier sampler divided height differences by a fixed 500 m even though the supplied geographic raster's ground spacing varies with latitude; it also used a fixed 12-pixel square. The corrected sampler is shared with the Step 14 comparison. The active elevation source remains the supplied SRTM raster.

The priority index is:

```text
100 * (
  0.40 * demand_component
+ 0.30 * known_site_gap_component
+ 0.20 * road_access_component
+ 0.10 * terrain_component
)
```

The exported `planning_priority_score` is bounded to `[0, 100]` and must be deterministic for the same inputs and configuration. These transformations and weights are planning assumptions, not learned parameters. If a required local component is unavailable, the location is not eligible for the ranked shortlist.

Cloudflare data is exported as regional review context and is never described as cellular demand. It does not affect the current score because it has not passed the independent improvement gate in the roadmap. OpenCellID proximity is also review evidence and must not be interpreted as measured coverage.

No ROC-AUC, PR-AUC, classifier accuracy, feature importance, or equipment-model accuracy applies to this score. Appropriate checks are reproducibility, monotonic behavior, missingness, spatial sanity, rank stability, and agreement with later independent RF/KPI evidence.

### 9. Recommendation review

The output is a shortlist. Non-maximum suppression or a documented separation rule prevents nearly identical proposals from filling the list. Each row should explain its rank through component values and reason codes.

No output may claim recommended bands, bandwidth, tower height, antenna count, azimuth, downtilt, equipment tier, coverage gain, or capacity unless those values come from supplied engineering constraints and an accepted RF workflow. At the current stage these are decisions for an RF engineer.

## Missing-Data Behavior

| Condition | Required behavior |
| --- | --- |
| Missing source bandwidth | Keep null; do not insert a technology default. |
| Unknown operator | Keep `Unknown`; do not infer a default operator or overwrite MNC. |
| Missing tower type | Keep null/unknown. |
| Raster nodata or out-of-bounds sample | Keep null and set availability false; do not use zero. |
| Missing municipality context | Keep null and avoid municipality-specific adjustment. |
| Missing Cloudflare row | Keep context fields null and availability false; ranking is unaffected. |
| Missing OpenCellID evidence | Keep proximity fields null; do not call the location uncovered. |
| Missing WorldCover tile or invalid class | Keep class null, set availability false, and make the candidate ineligible; never convert missing to land. |
| No mapped OSM building outline | Export zero mapped count with `osm_building_observed_h3=false`; do not assert that no building exists or penalize the score. |
| Missing OSM building source | Keep building context unavailable and ranking unchanged. |
| Missing or unsupported building height | Keep height absent. Never infer metres from floor count or an unverified model. |
| Too few candidates after constraints | Return fewer candidates and report the constraint counts. |

Where a computational fallback is unavoidable, the raw value, effective value, fallback reason, and availability flag must all be exportable.

## Output Contract

The current recommendation CSV and GeoJSON contain:

| Field family | Examples |
| --- | --- |
| Identity | deterministic candidate ID, H3 resolution 7 unit and resolution 6 parent, recommendation rank, generation source, score version |
| Location | latitude, longitude, municipality, nearest settlement |
| Priority | `planning_priority_score` and component scores |
| Evidence | population fields, terrain fields, road distance, nearest observed-site distance |
| Availability | WorldCover and Cloudflare availability; required local sources are enforced by eligibility |
| OpenCellID review | nearest observation distances, eligibility/proximity flag |
| Land-cover review | point class/water flag, H3 dominant class, coverage and class proportions, mixed/coastal review flag |
| Mapped-building review | H3 mapped count, footprint area, density, coverage ratio, observation, availability, and review flags |
| Step 12 performance evidence | Excluded after its coverage gate; no Ookla fields appear in retained recommendations |
| Step 13 night-light evidence | Excluded after its incremental-value gate; no VIIRS fields appear in retained recommendations |
| Explanation | reason codes derived from exported component evidence |

A future provenance gate will add source snapshot hashes and a full pipeline/configuration version to each retained artifact.

The map must visually distinguish observed records, inferred site clusters, OpenCellID cells, and generated candidates. Popup language should use “candidate,” “priority,” and “review,” avoiding “optimal,” “coverage gap,” or “recommended equipment” unless later stages establish those claims.

## Invalidated Historical Artifacts

Any serialized suitability or equipment model trained from generated labels is incompatible with the dataset-only policy. Historical model metrics, ROC plots, confusion matrices, feature-importance plots, and recommendations derived from those models must not be treated as current outputs. Regeneration after removing the generator does not make those old artifacts valid.

The same applies to tables containing invented equipment tiers, assumed bandwidth, guessed operators, or scores labeled as probabilities. Preserve raw supplied datasets; derived artifacts can be retired or rebuilt.

## Verification

Automated tests should cover:

- exact OpenCellID 14-column ingestion, including named and headerless files;
- invalid-row quarantine and cell-identity deduplication;
- preservation of unknown operator, bandwidth, and tower type;
- distinction between raster zero and raster nodata;
- projected-distance checks against known coordinates;
- deterministic score and rank output;
- monotonic component behavior at controlled fixtures;
- no prohibited model/equipment fields in public outputs;
- no generated rows in observed-data exports;
- strict behavior when candidate constraints cannot fill the requested count.
- WorldCover tile naming, point sampling, water exclusion, missingness, area-weighted H3 summaries, and manifest hash verification;
- exact H3 polygon gap, overlap, leakage, and duplicate-cell checks.
- OSM building equal-area aggregation, missing-outline semantics, invalid-geometry repair, exact duplicate removal, and manifest size/hash tamper detection.
- explicit OSM height tag extraction, unit conversion, plausible-range rejection, missing provenance, and manifest integrity.
- Ookla schema, support thresholds, weighted aggregation, missingness, device-count safeguards, and manifest integrity.
- VIIRS zero-versus-nodata behavior, water exclusion, flare distance, required coordinates, and manifest integrity.

Run the repository tests with:

```bash
uv run python -m unittest discover -s tests -v
```

Automated checks establish implementation behavior, not telecom validity. The next validation layer is an independent spatial holdout against accepted RF or operator evidence, as specified in the roadmap.

On 2026-09-20, the complete automated suite passed 37 tests. The Step 10 gate verified the 76,584,743-byte PBF and its SHA-256 digest, profiled explicit height and floor-count tags, and confirmed that recommendations remained unchanged. The result is recorded in `eval_reports/step_10_building_height_evaluation.json`; runtime integration was rejected because height coverage was 0.2399%, municipality coverage was 86.36%, shortlist coverage was zero, and independent validation was unavailable.

On 2026-09-21, the complete suite passed 40 tests. The Step 11 gate verified the existing GeoPackage, retained 3,497 selected features after deduplication, enabled four families with 90.91-100% municipality coverage, rejected the port proxy at 4.55% coverage, and confirmed unchanged scores and ranks. The result is recorded in `eval_reports/step_11_osm_context_evaluation.json`.

On 2026-09-21, the complete suite passed 44 tests. The Step 12 gate verified four official Ookla archives and 24,979 Libya tile-quarter rows. Although supported observations reached 20 of 22 municipalities, only 3 of 50 shortlisted H3 units had evidence in at least two quarters. The 6% shortlist coverage failed the 25% threshold, and the source was excluded from runtime. The result is recorded in `eval_reports/step_12_ookla_evaluation.json`.

On 2026-09-21, the complete suite passed 49 tests. Step 13 verified four radiance windows, four cloud-free-count windows, the official global flare KML, and a 183-site Libya flare subset. After the declared cloud-free and flare filters, 49 of 50 candidates were supported. Adjacent selected-month Spearman correlations were 0.9653, 0.9660, and 0.9817. Log-radiance correlations were 0.3653 with 5 km population and 0.5037 with mapped-building density. Five candidates entered a hypothetical top 10 with a 10% radiance weight; none was within 5 km of a known flare. Because independent labels were unavailable, geographic holdout improvement remained unmeasured and the source was excluded from runtime. The result is recorded in `eval_reports/step_13_viirs_evaluation.json`.

## Limitations and Decision Boundaries

1. Crowdsourced cell locations are estimates and may not coincide with physical assets.
2. Dataset timestamps and coverage differ; comparisons need snapshot metadata.
3. Population and activity proxies do not represent busy-hour traffic or subscriber distribution.
4. Nearest-site distance cannot account for frequency, antenna pattern, terrain obstruction, clutter, interference, or outages.
5. Terrain alone is insufficient for propagation modeling.
6. Road proximity does not establish ownership, access rights, power, security, or backhaul.
7. A deterministic score reflects chosen planning policy. Weight sensitivity must be reported before operational use.
8. National-scale ranking is unsuitable for construction decisions without field and RF review.
9. WorldCover is a 2021 categorical observation. It cannot establish present-day land availability, legal access, constructability, or RF attenuation without independent validation.
10. OpenStreetMap building coverage reflects contributor mapping. Missing outlines cannot be treated as empty land, and footprints do not establish height, use, ownership, access, structural suitability, or permission to build.
11. Explicit OSM height tags are extremely sparse in this snapshot and lack declared measurement provenance. They cannot support national vertical-form or RF-clutter analysis.
12. Ookla observations are self-selected and sparse at shortlisted candidates. Their non-commercial share-alike license also constrains reuse. Device counts are unique only inside one tile-quarter.
13. VIIRS radiance measures emitted light, not mobile demand. Median aggregation and a known-flare exclusion reduce specific artifacts but do not remove every fire or industrial source.

## Path to Telecom-Grade Validation

The [Telecom GIS, RF, and AI roadmap](TELECOM_GIS_RF_AI_ROADMAP.md) turns future work into sequential gates. Step 14 compared 13 verified FABDEM tiles with the active SRTM source and retained SRTM because shortlist coverage was 92%, municipality coverage was 90.91%, and independent elevation and RF validation was unavailable. The measured pilot now has a versioned source and evaluation snapshot, plus a request for 41 training-area cell identities. Step 15 still requires authorized operator assets, independent survey evidence, and engineer-approved thresholds. Steps 16-20 then cover calibrated RF, KPI evidence, scenario optimization, outcome-labeled AI, and production infrastructure. Every proposed download keeps its own baseline, quality check, measured before/after comparison, acceptance threshold, and explicit keep/review/revise/remove decision.

The [public-data source review](PUBLIC_DATA_RESEARCH.md) documents two official Libya CSVs downloaded while Step 15 is pending. The 2022 regional population table matches 19 of the project's 22 supplied municipality names without speculative crosswalks; across these matched areas, the 2020 WorldPop total is 97.37% of the official 2022 total. Different reference years prevent interpreting this as a population-model accuracy score. The 2019–2025 technology table gives national context only. Neither table changes placement scores, RF readiness, or the data policy.

## External RF Method Benchmark With Real Measurements

This benchmark uses **real observations from Chongqing, China, not Libya**. The source is [Xu et al., *A Real-time 5G Macro-cells Signal Dataset for Signal Model Simulation and Prediction within Complex Terrain Area*, Zenodo release 1.0](https://zenodo.org/records/20564635), licensed [CC BY 4.0](https://zenodo.org/records/20564635/files/LICENSE.txt?download=1). Its raw records contain smartphone and UAV GNSS positions, timestamps, cell identities, and measured 5G SS-RSRP. A separate anonymized operator base-station table contains processed coordinates and radio settings. The release also includes an interpolated grid; this benchmark excludes that grid and uses only the raw measured rows. The local [manifest](data/external/chongqing_5g_2026/manifest.json) pins URLs, sizes, SHA-256 hashes, publisher, release, license, and country. The 14.9 MB raw CSV and other source files stay local and can be re-fetched with `tools/download_chongqing_5g.py`.

**Question:** can the pipeline join actual measurements to real supplied cell records, enforce measurement quality, and evaluate an empirical signal baseline against unseen geographic areas? This is a method test for future RF work. It does not estimate Libya signal levels.

**Before:** for each cell, predict its training-area median SS-RSRP. **After:** fit that cell's measured SS-RSRP against the logarithm of geodesic distance to its supplied base-station coordinate, using the same training observations. Neither method invents measurements or missing transmitter settings. Both are evaluated on the same held-out data.

**Preparation:** verify all source file hashes and schemas; retain outdoor standalone 5G observations with GNSS accuracy at most 50 m, plausible SS-RSRP, valid timestamp and coordinate, an exact NCI-to-ECI match, and a 50 m–30 km observed-to-base distance. Aggregate repeated logs to one median per cell/day/H3-10 block. Assign complete H3-8 areas to the holdout by a fixed SHA-256 rule; the remaining areas train the baselines. Fit a cell only with at least 20 training blocks, two training H3-8 areas, and at least 100 m of distance spread. This keeps neighboring samples within one held-out area together and avoids reusing held-out signal values for fitting.

**Measured result:** of 81,419 raw rows, 80,136 passed the measurement filters and 79,795 also had an exact cell match and usable distance. They formed 4,786 day/cell/H3-10 blocks. Ten of 29 H3-8 areas were held out; 436 of 1,126 holdout blocks belonged to 27 supported cells and could be scored. On those identical blocks, the measured-cell median baseline had 7.101 dB mean absolute error and 14.500 dB 90th-percentile absolute error. The simple distance model had 7.793 dB and 16.335 dB respectively: **9.75% worse mean absolute error**. The distance model's prediction bias was 5.000 dB. The complete [benchmark report](eval_reports/foreign_rf_benchmark.json) records source quality, support, metrics, and limits.

**Decision:** keep the real foreign dataset as a reproducible method fixture; do **not** use this distance model for planning. It failed to improve even its foreign geographic holdout baseline. The benchmark does not validate RF simulation, transmitter coordinates, signal levels, frequencies, or placement choices in Libya. Operator assets, independent surveys, and engineer-set thresholds remain on hold until available. No foreign observation or configuration enters the Libya site inventory, national ranking, map, or proposed placements.

AI can be reconsidered only after real outcome labels exist, such as accepted/rejected acquisition decisions, calibrated coverage measurements, or independent KPI improvement following deployment. Any future model must be compared with the explainable baseline on geographic holdouts and must add measurable value without hiding source limitations.
