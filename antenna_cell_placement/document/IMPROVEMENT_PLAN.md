# Implementation plan and acceptance gates

> Current update (2026-09-29): see [measured service and reconciled inventory](SEPT29_INTEGRATION.md). The active demo is `integrated_release_v3/`; earlier metrics and source versions below remain historical evidence.

**Integration update (23 September 2026):** The public `recommend`, `all`, `assess`/`predict` and `map` workflow now uses GIS v2 and Ahmed’s explainable heuristic. ML is excluded from primary ranking; old model-based commands are under `experimental`. See [the current integration guide](INTEGRATED_PLANNING.md) for the shared contract, source checks, runnable commands and validation. Historical results and implementation descriptions below retain their original scope.

Updated 2026-09-22. The user authorized planning, implementation and documentation improvements. This plan unifies the H3 pilot and population maximum-coverage roadmap. The current milestone fixes data/evaluation integrity and establishes a reproducible experiment; later stages need separate engineering validation and, in some cases, new operator data.

## Milestone 1: data and evaluation integrity — implemented and verified

- Scope the owner-confirmed 645 Al-Madar LTE rows to source import/fingerprint; preserve raw source data and record attribution provenance.
- Replace H3 enrichment columns on rerun; reject duplicate/null H3 keys; retain missing evidence as missing.
- Fix road-negative distance units and enforce the documented >5 km rule after jitter.
- Keep hard negatives inside requested municipality and nearest-distance bounds.
- Fix per-operator nearest-site self exclusion and reset operator trees when an inventory changes.
- Handle nonfinite normalization and unknown land-cover/population values conservatively.
- Add `train-experiment`: exact saved examples/splits, grouped development CV, frozen geographic benchmark, package versions/hashes, predictions and separate candidate model.
- Rewrite ML_MODELS_AND_DATA.md around targets, evidence, data contracts, historical metrics, operational commands and limitations. Mark the old technical report as historical.

Verified on 2026-09-22: 40 tests passed; separate training experiment and output regeneration completed (see the verification JSON and ML guide).

Acceptance: full test suite passes; cleaning yields 645 Al-Madar LTE and 673 Libyana LTE records; attribution does not affect another import; repeated feature joins are identical; experiment split groups are disjoint; each score is traceable to data/parameters. Record actual results in `eval_reports/implementation_verification.json`.

## Milestone 2: version the GIS feature definitions — implemented

Implementation and verification are documented in [PHASE2_GIS_AND_ROOFTOPS.md](PHASE2_GIS_AND_ROOFTOPS.md). The `phase2` command produces separate GIS v2 features/model outputs and a preliminary footprint shortlist. Final suitability still requires height and feasibility evidence. This milestone is distinct from the historical `enrich-h3` source-enrichment command.

Audit raster metadata and source units. Correct pixel indexing, density-to-count conversion, nodata handling and circle/hex population aggregation. Use region-appropriate or geodesic distances. Replace road-point approximation where needed. Audit network-scoped dedup keys, chained physical-site clusters, and repeated-observation bandwidth totals.

Acceptance: synthetic population conservation fixtures; known-distance checks across western/eastern Libya; missing raster coverage remains missing; known cross-operator identity collisions remain separate. Regenerate feature version v2 and train models against that same version. Serving models must not consume silently changed feature semantics.

## Milestone 3: objective-based site selection

Review top 20 Tripoli hexes and generate feasible point candidates inside approved areas. Build demand cells near native population resolution. Define separate operator/RAT scenarios, explicit assumed coverage radii and budgets. Implement greedy maximum additional population coverage, updating uncovered demand after each choice. Add OR-Tools only after the transparent baseline works.

Acceptance: overlap is counted once; adding a selected site cannot reduce modeled union coverage; site-count and eligibility constraints hold; compare 0/1/3/5/10 additions against random feasible, population-first and current ranking using identical demand/candidates. Report assumed coverage, not measured RSRP or revenue.

## Milestone 4: stronger validation and model selection

Use the new stored experiment artifacts for repeatable comparisons and failure review. Add buffered spatial tests and a fully isolated network-recovery protocol if the intended use is reconstructing an unseen network. Obtain a fresh prospective test or new-city dataset before calling a result blind. Build expert review labels independently of the score.

Acceptance: candidate selection beats simple baselines on the same predeclared planning objective, with uncertainty across regions/seeds. Compare classifiers on identical held-out examples. Probability calibration needs a realistic target prevalence; scores on synthetic samples alone do not calibrate deployment need. Promote a new serving model only after the evidence supports it.

## Milestone 5: RF and feasibility

Collect sector parameters, antenna patterns, heights, azimuth/tilt, power and band. Prototype propagation and backhaul terrain/Fresnel checks for the reviewed shortlist. Add power, land, exclusion-zone and budget constraints.

Acceptance: compare RF predictions with geolocated measurements, report error by terrain/clutter class, quantify incremental covered population and overlap, and label uncalibrated parameter scenarios explicitly. Building footprints without heights do not establish full 3D obstruction.

## Milestone 6: capacity, operations and delivery

Join KPIs using verified cell/site identities and effective dates. Compare new macro, small cell, additional sector/carrier, tilt changes and backhaul upgrades. Add second-city validation, reproducible data download/checksum manifests, CI smoke tests and local map assets before the planner-facing scenario dashboard.

Acceptance: no arbitrary KPI joins; units and intervals checked; upgrades assessed against measured outcomes; teammate can reproduce the pilot from documented sources; maps render in the target environment. Commit code/docs and small reports once reviewed; use a deliberate large-data distribution mechanism for raw assets.

## Current boundaries

Serving `train` retains its legacy random-CV workflow. The new experiment is an explicit alternative and does not automatically replace the serving artifact. Historical JSON reports remain historical and must be labeled when input or code changes. AUC/accuracy gains do not prove new coverage, capacity or ROI. No RF simulation, new external KPI labels or field validation is claimed complete by Milestone 1.
