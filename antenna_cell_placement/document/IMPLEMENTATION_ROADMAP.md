> **Status update — 2026-09-22:** This document records an earlier design/run. Current model/data definitions, metric corrections, implemented fixes and remaining work are maintained in [ML_MODELS_AND_DATA.md](ML_MODELS_AND_DATA.md) and [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md). Historical figures here are not evidence of measured coverage, independent equipment validation or a completed RF planner.

# Research-to-implementation assessment

Reviewed: 2026-09-13. Source: `deep-research-report (3).md`, compared with the existing Python package, data inventory, saved outputs, and dependency declaration. This is an implementation proposal; no source changes, model retraining, dependency installation, or new benchmarks were performed.

## Decision

Build a population-based, incremental maximum-coverage planner first. Reuse the current GIS and map pipeline. Introduce a separate demand grid and choose sets of sites based on additional coverage under explicit assumptions. Add traffic forecasting and calibrated radio simulation when suitable data becomes available.

The report's distinction between demand estimation, candidate generation, and final optimization is directly useful. Its full forecasting/digital-twin architecture exceeds the data currently present.

## What is already available

- Raw SQLite radio observations, cleaned radio records and physical-site inventory, including operator/technology attributes and observation dates.
- Saved enriched inventory with 2,115 sites and population, terrain, road, settlement, and network-distance attributes.
- WorldPop 2020 population raster, SRTM elevation raster, roads, settlements, and Libya administrative boundaries, including an admin0 boundary.
- Geographic feature extractor and candidate generation around settlements and roads.
- LightGBM site-similarity classifier, Random Forest equipment classifier, and saved benchmark artifacts.
- Recommendation exports and Folium/Leaflet HTML maps.
- GeoPandas, Rasterio, SciPy, scikit-learn, Pandas and Folium declared as dependencies. OR-Tools is not declared.
- `uv` and Python 3.12/3.14 are discoverable on this machine. This does not establish that project dependencies are installed or that the pipeline runs.

The inspected customer-churn Record/Client datasets contain customer aggregates, not timestamped Libyan cell-sector KPIs joined to the tower inventory. They cannot fill the forecasting requirement.

## Feasibility by research proposal

| Proposal | Status with current inputs | Implementation / prerequisite |
|---|---|---|
| Geographic demand grid | Implement now as a population proxy | Start near the native population-raster resolution; preserve units and population totals. |
| Weighted K-Means / DBSCAN | Implement now for population hotspots | Use projected distances; map centers to eligible candidates; compare with direct candidate selection. |
| Greedy maximum coverage | Implement now | Create candidate-to-demand coverage links, subtract assumed existing coverage, and update marginal gains after every selection. |
| OR-Tools maximum coverage | Implement after dependency setup | Binary site selection and covered-demand variables, site-count/budget constraints, solver status and bounds. |
| P-Median | Optional benchmark | Minimizes weighted distance; maximum coverage better matches the initial underserved-population objective. |
| Operator/technology scenarios | Implement now with inventory caveats | Separate existing-network layers and assumptions; retain inferred operator attribution confidence. |
| What-if scenarios and explanations | Implement now | Compare 0/1/3/5/10 additions; report additional population under coverage assumptions, overlap, and runtime. |
| Demand/coverage sensitivity analysis | Implement now as scenarios | Vary population weights and coverage assumptions; describe resulting variation as scenario sensitivity, not measured confidence. |
| Budget/cost optimization | Framework now; realistic results need inputs | Use site-count budgets until candidate construction/operating costs are provided. |
| Congestion and capacity optimization | Data-dependent | Need busy-hour traffic, usable sector capacity, configuration, and load/service assumptions. |
| Traffic forecasting | Data-dependent | Need timestamped site/sector KPIs, stable identifiers, and configuration history. |
| Propagation-based coverage | Prototype with explicit assumptions | Calibrated results need antenna configuration, terrain/clutter, and geolocated RF measurements. |
| Historical replay | Data-dependent | Need commissioning/configuration histories and pre/post KPIs. Observation first-seen dates are not commissioning dates. |
| LSTM / GNN / reinforcement learning | Defer | First establish temporal data, simple baselines, evaluation, and a validated simulation environment. |
| Detailed digital twin / ray tracing | Defer | Need suitable 3D geometry, material assumptions, radio configurations, runtime planning, and measurement validation. |

## Corrections before optimization

1. Audit deduplication with operator/network identity where known. Unknown operators must remain explicit rather than silently defining identity from uncertain attribution. Add a regression case for matching region/site IDs across operators.
2. Avoid summing repeated observations of the same carrier's bandwidth. Aggregate unique carrier/configuration observations with explicit provenance and handle configuration changes separately.
3. Replace square pixel-window population totals with well-defined geographic catchments. Inspect raster units: counts can be summed; density requires cell-area conversion. Test population conservation and missing-data behavior.
4. Check actual raster CRS, transforms, and pixel indexing. Use distance calculations appropriate to each pilot region or geodesic distances instead of assuming one projection works equally well throughout Libya.
5. Intersect candidate generation with the Libya land boundary and selected planning region. Keep geographic eligibility separate from unverified buildability.
6. Compute nearest-operator distance correctly: excluding the point itself must depend on whether the point belongs to that operator. The current extractor requests the second neighbor for both operators at every existing site.
7. Make coverage/operator/technology assumptions explicit. An existing 2G site should not automatically count as meeting a 4G planning target.
8. Retain the current classifier as a comparison score. Do not use its probability as proof of new-site benefit or automatically exclude underserved candidates because they differ from existing sites.

## First deliverable

Pilot recommendation: Zwara administrative area, because current saved recommendations already include Aljmail and Al Ajaylat. Make the region configurable and expand later.

Pipeline:

`clean inventory -> population demand cells -> candidates -> assumed coverage links -> incremental site selection -> scenario comparison -> map and report`

Use native-resolution population cells initially. A 100 m or 250 m display grid does not create population information that is absent from a roughly 1 km source. Fine grids should wait for finer inputs or explicitly documented allocation assumptions.

Build a sparse candidate-demand relationship rather than a dense nationwide all-pairs matrix. Begin with declared radius scenarios per operator/technology. These estimate population within assumed coverage, not measured RSRP/SINR or actual subscribers served.

For each demand cell, count population only once in total coverage. Remove population already covered by the baseline network under the same assumptions. A greedy step chooses the candidate with greatest remaining marginal benefit; a cost-aware variant uses marginal benefit per cost when trustworthy costs exist.

The CP-SAT variant should maximize newly covered population subject to at most p selected sites, eligibility, optional spacing, and optional budget. Record integer scaling, solver status, time limit, objective, and best bound. A feasible solution is not necessarily proven optimal. Avoid implementing capacity constraints until demand and capacity use compatible units.

Compare against the current ranking, random feasible selection with repeated seeds, population-first selection, and weighted clustering with centers snapped to candidates. Use the same candidate set, coverage assumptions, region, and site budget for fair comparisons. Freeze evaluation scenarios before tuning.

Proposed outputs:

- `scenario_comparison.csv`: method, region, operator, technology, site count, baseline covered population, additional covered population, remaining uncovered population, runtime, and solver status where applicable.
- `selected_sites.geojson`: coordinates, selection order where defined, marginal/total benefit, assumptions, eligibility state, and optional cost.
- HTML map: population, assumed baseline coverage, new coverage, selected candidates, and per-site explanations.
- Machine-readable scenario configuration and input provenance, including data dates.

Acceptance checks:

- Synthetic overlap fixture proves that shared population is never counted twice.
- Zero-site scenario equals baseline; selected sites satisfy eligibility and budget constraints.
- Adding a site to the same selected set cannot reduce union coverage in the simple coverage model.
- Tiny optimization fixtures match exhaustive enumeration; distinguish time-limited feasible solutions from optima.
- Baseline and optimized results are reproducible under fixed seeds/configuration.
- Sensitivity report shows results under multiple coverage radii and population-weight scenarios.
- Report no Mbps improvement, congestion reduction, or financial returns without the models/data needed to calculate them.

## Code integration

Extend the existing package instead of creating a second repository or replacing all modules.

| File | Proposed responsibility |
|---|---|
| `data_cleaning.py` | Correct identity/bandwidth aggregation and preserve attribution provenance. |
| `feature_engineering.py` | Correct population extraction, spatial units, and operator-neighbor calculations. |
| New `demand_grid.py` | Region-clipped population cells, weights, and provenance. |
| New `coverage_model.py` | Interchangeable assumed-radius and later propagation coverage backends. |
| `site_optimizer.py` | Reuse candidate generation; add marginal-gain greedy selection and separate coverage objectives from similarity scores. |
| New `facility_optimizer.py` | OR-Tools maximum-coverage formulation with solver metadata. |
| New `scenario_evaluation.py` | Baselines, site-count scenarios, sensitivity analysis, and comparable metrics. |
| `map_visualizer.py` | Before/after layers and recommendation explanations. |
| `cli.py`, `config.py` | Region/operator/technology/site-count/coverage-assumption controls. |
| `placement_model.py` | Geographic holdouts and valid equipment evaluation if retaining these classifiers. |
| `pyproject.toml`, `uv.lock` | Add/pin tested solver dependency and keep the environment reproducible. |

## Data request for the next stage

| Dataset | Minimum useful fields | Purpose |
|---|---|---|
| Cell/sector inventory | operator, site_id, cell_id, sector_id, lat/lon, technology, band, bandwidth, antenna height, azimuth, tilt, transmit power, effective dates | Join KPIs and simulate the network configuration. |
| Time-series KPIs | timestamp/timezone, interval length, cell_id, DL/UL volume with units, active users, PRB utilization, throughput, availability and missing-data flags | Estimate demand, congestion, and forecast performance. |
| RF measurements | timestamp, lat/lon, serving cell/operator/technology, RSRP, RSRQ, SINR, measurement method | Calibrate and independently check coverage predictions. |
| Candidate feasibility | candidate_id, coordinates, site type, land/rooftop availability, power, fiber/microwave backhaul, exclusions, build and operating cost with currency/date | Recommend executable plans and compare costs. |
| Deployment history | commissioning and configuration-change dates, pre/post KPIs, recorded upgrades | Historical replay and outcome validation. |

Prefer 6-12 months of hourly or 15-minute KPI history for an initial forecasting study, with longer history for annual seasonality and long horizons. Shorter series can support limited pilots; they cannot establish reliable six-month forecasts by themselves. Cell aggregates are sufficient to start; individual subscriber records are unnecessary.

Cell-level KPIs do not identify exactly where users are within a cell. Fine-grid demand requires geolocated aggregates or an explicit allocation model; retain the resulting uncertainty.

If operator data is unavailable, keep the Libyan planner population-based. Public foreign traffic datasets may demonstrate the forecasting software separately; they cannot validate Libyan traffic forecasts. Synthetic growth can support what-if scenarios only.

## Tools and scope

The existing file-based Python/GIS stack is enough for a regional pilot. Add OR-Tools for constrained optimization after the greedy baseline. No GPU requirement is introduced by this proposed first stage. Benchmark actual runtime/memory before scaling nationwide. PostGIS, additional dashboards, and deep-learning frameworks are later options driven by scale and demonstrated need.

## Research qualifications

- Many report references are exported citation tokens without resolvable URLs. Restore a proper bibliography before citing its numerical research claims in competition material; this review did not verify every paper.
- The report's short-horizon traffic studies do not by themselves demonstrate reliable forecasts months ahead.
- Its sample before/after results are illustrations, not measurements from this repository.
- Additional population inside a coverage model is not automatically additional subscribers, measured traffic served, or incremental revenue.

Official implementation references checked during this assessment:

- [OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver): integer model requirements and OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN status handling.
- [NVIDIA Sionna](https://nvlabs.github.io/sionna/): reference for the later radio-simulation stage, not a prerequisite for the first deliverable.
