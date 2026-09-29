# September 29 integration: measured service and reconciled inventory

This update selectively integrates Ahmed's `2c48a27` into the combined `2eca2dd` baseline. The current demonstration is **`integrated_release_v3/index.html`**. The original `integrated_release/` and `submission/` artifacts remain historical, unchanged comparisons.

## What changed

1. Added verified Libya handset, CellMapper and BeaconDB ingestion, with row rejection and duplicate counts.
2. Added measured-service summaries, operator/technology map layers, a frozen chronological pilot, and a concrete field-data request.
3. Built a separate source-traceable inventory with bounded geodesic location groups, conflict alternatives, actual observed coordinate representatives and a source-to-site crosswalk.
4. Switched the public planner to that explicitly versioned inventory and reran all Tripoli candidates.
5. Added the official regional-population and national technology audit, with valid raster support reported.
6. Retained the optional ML comparison and ported the foreign-RF benchmark as a separate experiment. No foreign observations enter Libya scoring.

The existing GIS-v2 population/terrain/road calculations and fixed 40/30/20/10 scoring formula remain in use. Handset signals do not change the primary planning score. No estimated building heights, equipment settings or RF improvement claims were added.

## Inventory and attribution

Inventory version: `reconciled-geodesic-20260929-v1`.

| Item | Result |
|---|---:|
| Historical raw observations | 4,258 |
| Valid collected CellMapper rows | 2,494 |
| Retained combined source records | 6,726 |
| Additional boundary exclusions from historical observations | 26 |
| Network-scoped radio-location groups | 2,670 |
| Physical-site reference groups | 2,344 |
| Conflicted identities | 6 |
| Physical references containing a conflict | 12 |
| Independently survey-resolved conflicts | 0 |
| Maximum physical-group diameter | 49.58 m |
| Physical groups exceeding 50 m | 0 |

### The 645 Al-Madar records

All **645** source-fingerprinted owner-confirmed records remain in `source_crosswalk.csv`, with their Al-Madar attribution preserved. **643** pass the boundary check and enter the active inventory. Two records (`sqlite:604`, `sqlite:690`) lie outside the supplied boundary and remain in `rejected_records.csv` for review. This is a polygon-based exclusion, not proof that those source locations are false.

The immutable rule is the preservation and attribution of the 645 source records. The resulting number of radio/site groups can change as records are deduplicated, grouped or excluded; it must not be forced to 645.

### How references are grouped

- Radio identity includes MCC, MNC, technology, region and site ID. Owner-confirmed attribution is derived without changing the raw SQLite bytes.
- Same-identity locations are grouped with complete linkage and a maximum pairwise geodesic distance of 1 km. This is a review threshold, not claimed coordinate accuracy.
- Each group's representative is an actual observed coordinate minimizing summed within-group distances. Contributor verification on the representative is distinguished from any verified contributor record elsewhere in the group.
- Nearby radio references form physical groups only when every pair is within 50 m. A chain of nearby points cannot produce an oversized group.
- IDs are deterministic hashes of member source identities. The crosswalk retains the previous physical-site association for historical records; new group IDs do not pretend to be unchanged mast identities.
- Conflicting alternatives remain conservative screening references. They are excluded from reliable pilot anchors, and a separate sensitivity run removes every affected physical reference and recomputes all network features.

## Measured-service evidence

The supplied logs contain 11,335 rows, including 3,622 duplicates. Of 7,713 retained observations, **4,874** satisfy the review rules: valid generic signal, declared accuracy up to 100 m, serving rather than neighbouring cell, valid identity/location/time.

Summaries keep network and radio technology separate. Day/device/H3-9 block medians reduce the influence of repeated stationary logging. Generic `dbm` is not relabelled as LTE RSRP; explicit valid LTE RSRP has its own field. Map tooltips show observation, day, device-label and spatial-block counts.

The eligible LTE sample is uneven: 1,938 Al-Madar observations and 28 Libyana observations. It cannot establish a fair national operator comparison.

### Frozen chronological pilot

- Training days: September 23-24, 2026; 2,975 observations.
- Held-out days: September 26 and 28; 1,899 observations.
- Matched held-out blocks: **74/258 (28.68%)**.
- Matched-block mean absolute error: **7.676 dB**.
- Exact observed measurement/collected sector matches: **0/449**.
- Complete engineering sectors: **0**.

The error measures repeatability of a historical measured-area median, not the accuracy of an RF simulation or the planning score. Those dates have now been inspected; reserve new dates before a new blind model evaluation.

The frozen input hashes now use canonical forward-slash paths on Windows and Linux. Changed source bytes or training/holdout dates fail validation. This fixes the original cross-platform false snapshot mismatch.

## What the rerun established

The same 2,223 Tripoli candidate points remain the comparison domain. There are **162 eligible candidates and 20 selected priorities**. The inventory update changes nearest-reference distance for 307 candidates, by up to approximately 1,665 m, while retaining all 20 selected IDs. Excluding the 12 conflict-affected physical references also retains those 20 selections.

There are **zero eligible supplied handset observations within 5 km of any selected point**. The measured-service layer therefore improves evidence review elsewhere in the surveyed area; it does not validate these deployment priorities.

See `inventory_comparison/comparison.json` and its per-candidate change table for the exact comparison. Population-only, gap-only and explainable methods use identical candidate eligibility and spatial selection. The optional historical GIS-v2 model runs separately on this newer inventory snapshot; its old AUC is not transferred to this run.

## Official and engineering evidence

The official-population audit matches 19 of 22 regions, with about 6.276 million WorldPop 2020 people versus 6.446 million reported 2022 people in matched regions. The ratio is 0.9737. Years differ, three regions lack a safe crosswalk, and regional totals do not establish local catchment accuracy. Per-region valid raster area is now exported. No automatic rescaling affects ranking.

Authorized operator-data templates and the aggregate asset audit are available in `data/operator_assets/` and `operator_assets.py`. No real authorized engineering export was supplied. Heights, transmitter settings, antenna patterns and independent surveys remain missing inputs.

The ported foreign RF experiment remains `method_review_only`; Ahmed's stored benchmark had worse error than its baseline. Its raw external files are not bundled or silently downloaded. FABDEM remains a deferred experimental terrain comparison; its previous gate did not justify replacing SRTM.

## Run and reproduce

From the `antenna_cell_placement` module:

```powershell
uv sync --locked
uv run antenna-placement doctor
uv run antenna-placement recommend --scope Tripoli --output-dir eval_reports/new_review
# recommend now includes service review, map layers and the official audit.

# Independent evidence workflows; choose output directories that do not exist:
uv run antenna-placement service-review --planning-run integrated_release_v3 --output-dir eval_reports/service_review_new
uv run antenna-placement evidence-review --output-dir eval_reports/official_review_new
uv run antenna-placement inventory-build --output-dir eval_reports/inventory_review_new

uv sync --locked --extra research
uv run --extra research python -m unittest discover -s tests -v
uv run --extra research antenna-placement experimental compare --run-dir integrated_release_v3 --model eval_reports/phase2_v2_run2/suitability_gis_v2.joblib --output-dir eval_reports/new_ml_comparison
uv run python tools/verify_integrated_run.py integrated_release_v3

npm ci --prefix tools/browser_check
node tools/browser_check/verify_integration.mjs integrated_release_v3
node tools/browser_check/verify_measurements.mjs integrated_release_v3
```

`inventory-build` writes a separate proposal. It does not silently activate or trust new input bytes. Activating another inventory requires reviewing its crosswalk/exclusions, revising the source lock and inventory version, and rebuilding candidate features and comparisons.

## Reproducibility and checks

Two locks pin the planning sources and collected evidence. Legacy raw/cleaned/model/release inputs remain unchanged. New inventory outputs are independently hashed. The planning manifest covers the included measured-service and official-evidence artifacts; later validation and experimental outputs are covered by `release_verification.json`.

**121 regression tests passed.** Both offline Edge checks passed with zero external requests, JavaScript errors or missing assets. The planning environment has no LightGBM or scikit-learn installed.

Validation evidence accompanies the release: regression log summary, coordinate/batch agreement, strict eligibility and separation checks, source and artifact hashes, no-ML planning runtime, unchanged primary ranks under experimental comparison, and offline browser checks with screenshots.

## Remaining work after this integration

The next scientific step is collecting comparable serving-cell measurements around the actual priorities across additional days and devices, for both operators. Obtain independently surveyed conflicting coordinates and authorized sector engineering inputs. Building-height and roof feasibility checks remain necessary before installation decisions.

The `tahaDev` branch and a unified web application remain separate work. This integration improves data handling, traceability and review capability; it does not establish RF coverage or capacity gains.
