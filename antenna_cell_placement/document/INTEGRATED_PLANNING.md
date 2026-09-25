# Integrated antenna planning: implementation and verification

Implemented 23 September 2026; final validation 25 September 2026. Integration branch: `integration/antenna-planning-v2`.

## 1. What was combined

This is a selective integration from Mahalm’s submitted commit `8a2be6c928945ce8c52dba93e975e72aea0123d2` and Ahmed’s audited commit `15dc13a021f12f259319d611dc291ab6de9e4bbe`. It preserves the existing submission in `submission/` and produces a separate integrated result in `integrated_release/`.

| Responsibility | Integrated implementation |
|---|---|
| Population, terrain, road and site distances | Mahalm `gis_v2.py`: explicit units/nodata, density × intersection area, geodesic catchments and site distances, actual road lines in local zones |
| Inventory provenance | Fingerprinted 645-record owner attribution and network-scoped inventory/cluster audit; raw operator text is preserved |
| Primary score | Ahmed’s fixed four components and 40/30/20/10 weights, ported in `planning_score.py` |
| Eligibility and selection | Strict finite-evidence checks, explicit rejection reasons, stable candidate IDs and geodesic separation |
| Land cover | Ahmed’s WorldCover point screening and area summaries; required verified 2021 source, no RF clutter claim |
| OSM context | Ahmed’s clipped building footprints and selected hospital/education/aviation/industrial POIs; reviewed snapshot, optional and excluded from score |
| Roof review | Mahalm’s geometry-validated footprint shortlist, mapped explicitly from selected points to their H3 cells |
| ML research | Existing frozen benchmarks and GIS-v2 artifact retained; explicit separate matched-candidate comparison |

The audited problems fixed during integration include national single-zone selection distances, sampled-point road distance, partial population treated as complete, optional OSM `pd.NA` conversion, Unix-only download locks and unversioned runtime input use. Legacy implementations remain only where historical experiments depend on them.

## 2. Public workflow

```text
Reviewed source lock + metadata manifests
    -> doctor and runtime integrity checks
    -> GIS-v2 features on explicit candidate coordinates
    -> strict eligibility, with rejected rows retained
    -> explainable score and geodesic shortlist
    -> optional context and footprint review
    -> offline maps, CSV/GeoJSON, comparison and run manifest

Separate research command:
same frozen candidate artifact -> version-compatible ML -> comparison only
```

Public commands are `doctor`, `recommend`, `all`, `assess`, `predict` and `map`. `recommend` and `all` share the complete planning pipeline. `predict` now aliases explainable assessment. Former `train`, `features`, `phase2`, H3 and evaluation commands use the `experimental` namespace. The README lists exact commands.

The default install does not require model artifacts, LightGBM or scikit-learn. Research dependencies are an explicit `research` extra. The primary planner never calls a model, even if research dependencies happen to be installed.

## 3. Feature and source contract

Feature version: `gis_v2_density_circles_geodesic_20260922`.
Score version: `explainable-gis-v2-20260923`.

Each candidate includes stable ID, generation source, WGS84 coordinates, H3 identity/resolution, municipality, feature version, source-lock hash and operator scope. Catchment population includes strict total, observed subtotal, valid-area fraction, source units (people/km²), output units (people) and radius (5,000 m). Terrain elevation is ground elevation, not building height.

`sources/planning_sources.lock.json` pins reviewed input bytes. Runtime rehashes required inventory, population, DEM components, roads, places, boundaries and WorldCover. Required changes or absence stop the run. Optional OSM/footprint failure disables that context and records the unavailable state. Source metadata checks retain dataset versions, acquisition dates, licenses and original manifests. Git attributes preserve the expected bytes across Windows/Linux checkouts.

WorldPop density units are an explicit interpretation of the local product; its exact UN-adjustment provenance is still unresolved. Hash verification establishes which input was used, not that the source is complete or correct.

The source archive and full WorldCover tiles are excluded from Git. Downloaders use portable exclusive locks and atomic temporary files, validate against the reviewed hash before replacement, and reuse a verified local cache without network access. A different upstream snapshot requires deliberate review and a revised lock; silently accepting a file merely because its size matches is disallowed.

## 4. Score and strict eligibility

For population P, known-site distance D, road distance R, slope S and 3 km elevation prominence H:

- Demand = clip(log(1 + P) / log(100001), 0, 1).
- Site gap = clip((D − 3000) / 17000, 0, 1).
- Road access = 1 − clip(R / 4000, 0, 1).
- Terrain = 0.5 × (1 − clip(S / 15, 0, 1)) + 0.5 × clip((H + 50) / 100, 0, 1).
- Priority = 100 × (0.4 demand + 0.3 gap + 0.2 road + 0.1 terrain).

These fixed transformations reproduce Ahmed’s formula on identical valid feature fixtures. Corrected input measurements justify the new score version. Weights and cutoffs are provisional planning assumptions, not fitted or independently validated coefficients.

Defaults require: inside Libya; finite required measurements; at least 99% valid population catchment area; terrain availability; observed non-water WorldCover; population ≥300 within 5 km; nearest known site ≥3,000 m; road distance ≤4,000 m. Selected points must be ≥2,500 m apart by WGS84 ellipsoidal distance. Ties are ordered by stable candidate ID. Scores on rejected coordinates may be diagnostic, but rejected rows are never shortlisted. No fallback relaxes constraints.

Changing a constraint does not silently change the fixed score normalizers. Both the score version and run-specific constraints are exported so reviewers can distinguish them.

## 5. Candidate geography and operator scope

The Tripoli demo uses land-based H3 centres in the configured pilot bounding box. It differs from the old 2,987-hex phase-2 domain because points outside the actual Libya boundary are filtered before measurement. National mode uses geodesic settlement rings and actual road-line samples, retaining generation sources. It is not an exhaustive nationwide hex search.

The minimum 3 km known-site gap often excludes dense central Tripoli locations. This workflow screens expansion locations; it cannot diagnose capacity upgrades without traffic and network-performance evidence.

Default site distance uses all known networks. Operator-specific modes filter the physical-site inventory before all network-feature measurements. The 645 owner-confirmed Al-Madar observations and radio groups remain traceable to their fingerprinted source; other historical labels include inference. The current research model was trained on all-network features and is rejected for operator-specific comparison.

## 6. Roof review and data that remain excluded

Shortlisted point locations are mapped explicitly to H3 cells. Footprints in those cells are selected by the existing geometry/area policy, with a representative point inside each geometry. This does not mean a footprint inherits RF suitability from the cell’s planning point. No height or structural recommendation is generated.

Microsoft footprint heights remain unavailable. The separate audited OSM heights were sparse and absent from Ahmed’s historical shortlist; they are not used to claim heights for the new shortlist. Height, Ookla, VIIRS and port scores remain excluded. Cloudflare and legacy equipment models also do not affect the integrated rank. In particular, neither missing OSM context nor an absent mapped building is evidence that no real building exists.

## 7. ML and matched comparisons

The default report compares population-only, gap-only and the explainable heuristic on the **same candidates and eligibility rules**, using the same spatial selection. It records IDs, shortlist overlap and rank correlation. It also varies each weight and constraint by ×0.5 and ×1.5, and removes population/terrain/land-cover evidence for a repeatable subset to verify strict rejection.

`experimental compare` verifies the frozen candidate artifact, requires a GIS-v2 model, and writes separate ML-only/combination comparisons. The combination multiplier `0.75 + 0.5 × ML` is retained only as an explicitly unvalidated experiment. None of these commands changes the primary shortlist.

Earlier hard-negative AUC 0.876141 → 0.885208 uses the same frozen examples/training recipe. Corresponding population baselines are 0.594538 and 0.571961. These are historical-site pattern diagnostics with generated negatives and previously inspected test data. AUC and shortlist overlap are not evidence of RF coverage improvement.

The old Tripoli hidden-site recovery result (0.716 versus 0.767 population baseline) belongs to the old scoring workflow. It must not be relabelled as a validation of this integrated score. A new, independently reserved city/time period and engineering/RF/KPI labels remain future validation work; there is no new blind trial in this integration.

## 8. Verification evidence

The integrated run was executed in a fresh planning-only environment without LightGBM or scikit-learn. Its required sources and both metadata manifests passed verification. Both Windows downloaders verified their restored local caches successfully; this check did not repeat a fresh network download.

| Check | Result |
|---|---:|
| Reconciled unit/regression suite | **96 tests passed** |
| Tripoli candidates measured | **2,223** |
| Passed every strict eligibility check | **162** |
| Spatially separated priorities | **20** |
| Footprints shortlisted | **100**, all review coordinates inside geometry |
| Usable footprint heights | **0** |
| Owner-confirmed Al-Madar observations / radio groups | **645 / 645** |
| Public coordinate score versus same batch coordinate | Matched |
| Real assessment with optional OSM disabled | Passed; nullable counts serialize as null |
| Offline Edge browser | No external requests, JavaScript errors or missing assets |
| Planning-only environment | No LightGBM or scikit-learn installed |

The initial integration export stopped because a new check incorrectly expected the raw operator text to be rewritten. The correction verifies cleaned owner attribution while retaining original raw text; the completed release rerun passed. No raw observations or serving models were changed.

On the same 162 eligible candidates and 20-location spatial selection:

| Ranking | Shortlist overlap with the primary heuristic |
|---|---:|
| Population-only | 40% (8/20) |
| Known-site gap only | 10% (2/20) |
| ML-only experiment | 15% (3/20) |
| Experimental heuristic × ML multiplier | 35% (7/20) |

This is a comparison of rankings, not a competition with a known correct answer. The model did not change the primary scores or shortlist.

**Sensitivity is a remaining weakness:** weight changes produced a minimum rank correlation of 0.9268 but shortlist overlap as low as 60%. Increasing minimum known-site gap from 3 km to 4.5 km left only 25 eligible candidates and 6 separated selections. Halving the maximum road distance left 63 eligible and 15 selected. The planner correctly returned fewer results instead of relaxing constraints. These results show why the engineering team must justify cutoff choices before deployment use.

The repeatable missing-evidence stress affected 223 candidates per scenario and selected zero affected candidates for population, terrain and land cover. Source-version changes are blocked by the integrity lock until review. The coarser H3-resolution check is now complete: resolution 7 generated 316 candidates, with 22 eligible and 20 selected, versus 2,223 / 162 / 20 at resolution 8. Of the coarse selections, 15 were within 2.5 km of a baseline selection; median distance to the nearest baseline selection was 995 m. These are proximity comparisons between different grids, not matching candidate IDs or deployment evidence.

The new five-fold inventory-hidden recovery diagnostic gave mean planning-score AUC **0.689951**, compared with **0.734893** for population alone on the same scorable candidates. All network distances, site-density counts and operator-specific distances were rebuilt after hiding sites. The full list of hidden physical-site IDs is recorded for each fold. This is a previously inspected Tripoli domain and a historical-placement proxy, not a blind trial or future-expansion ground truth. The heuristic has not established superiority for coverage planning. See [grid and hidden-site diagnostics](../integrated_release/sensitivity/diagnostics.json).

A newly reserved external city/time-period outcome evaluation and RF/KPI evidence remain future validation work.

Evidence links: [run manifest](../integrated_release/manifest.json), [default comparison](../integrated_release/comparison.json), [ML research comparison](../integrated_release/research_comparison/comparison.json), [data/output verification](../integrated_release/integration_verification.json), [browser verification](../integrated_release/browser_verification.json), and [screenshots](../integrated_release/screenshots/).

Reproduce browser and artifact checks:

```powershell
uv run python tools/verify_integrated_run.py integrated_release
# Run on a newly generated planning run; creates a new sensitivity directory:
uv run python tools/validate_planning_sensitivity.py eval_reports/my_integrated_run
npm ci --prefix tools/browser_check
node tools/browser_check/verify_integration.mjs integrated_release
```

## 9. What “integrated” does and does not establish

The software integration delivers one public contract, one strict primary ranking, verified source state and consistent outputs. A stable ranking is still a provisional heuristic. Deployment work requires calibrated RF modelling, independently checked operator inventory/KPIs, incremental coverage/capacity and budget evaluation, and site access/structural/power/backhaul reviews. Those are evidence milestones beyond combining the software.
