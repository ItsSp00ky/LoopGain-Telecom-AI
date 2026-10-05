# Submission guide: one reliable Tripoli demonstration

Prepared 23 September 2026. Scope: wording/output corrections, portable artifacts and verification. Ahmed's full integration is not included.

## Open and present

Open [the entry page](../../antenna_cell_placement/submission/index.html) locally in Chrome or Edge. GitHub displays HTML source rather than running it. Alternatively, from `antenna_cell_placement/`:

```powershell
uv run python -m http.server 8765 --bind 127.0.0.1 --directory submission
```

Open `http://127.0.0.1:8765/`. Geographic context and scripts/styles are bundled; presentation does not require remote tiles or CDNs.

1. Say: **“This is a shortlist for engineering review in Tripoli.”**
2. Open the planning map. Show ranked areas, known-site references and population within 5 km. Inventory gaps are not measurements of weak signal.
3. Open the footprint map. Show a footprint and its interior review coordinate. Say: **“Building heights are unavailable; these are survey candidates.”** Footprint area is not usable roof area.
4. Show the same-example ML comparison and population-only baselines.
5. Show operator counts and provenance. The 645-record Al-Madar attribution is scoped to the owner-confirmed import, not inferred from location.
6. If needed, use PNG screenshots and CSV exports in `submission/` as backups.

## What changed

- Public predictions and exports omit equipment, RF-band, bandwidth and operator-deployment strategy advice.
- Maps say “planning priorities for engineering review,” “experimental site-pattern score,” and “population within 5 km.”
- Public coordinate responses no longer declare suitability from an arbitrary classifier threshold.
- Building height is explicitly “Unavailable.”
- No-candidate results preserve the stated constraints and export an empty result; constraints are not silently relaxed.
- The submission map reads corrected phase-2 GeoJSON. Other public point commands retain their legacy contract and are labelled accordingly.
- Existing ranking and its experimental ML multiplier are retained. No model was automatically promoted.

Historical reports remain research records. They are not current equipment or deployment recommendations.

## Explain the ML result

| Same frozen hard-negative examples | Legacy features | Corrected GIS features |
|---|---:|---:|
| Model ROC-AUC | 0.876141 | 0.885208 |
| Population-only ROC-AUC | 0.594538 | 0.571961 |

There are 2,033 examples: 533 observed sites and 1,500 synthetic hard negatives. Keeping rows and recipe fixed isolates the feature change. The baseline changes because corrected GIS also changes population measurement.

> Corrected population and distance calculations slightly improved separation of observed sites from our synthetic comparison locations. This supports the GIS correction within this experiment. It does not demonstrate better RF coverage or successful installations.

Keep these limits visible:

- Unrecorded locations are unlabelled in reality, not verified unsuitable land.
- This previously inspected geographic benchmark is not a blind final test.
- Network features use the known inventory, including held-out regions.
- AUC is not percentage accuracy, deployment probability or covered population.
- Tripoli hidden-site recovery was 0.716 versus 0.767 for population alone; richer scoring has not shown superiority for future expansion.
- The 0.708 standard stress result used a different recipe. Do not describe 0.708 to 0.885 as a controlled feature-only improvement.

## Artifacts and rebuilding

| File inside `submission/` | Purpose |
|---|---|
| `index.html` | Presentation entry and metrics |
| `tripoli_planning_map.html` | Corrected-GIS Tripoli map; existing rank retained |
| `tripoli_shortlist.csv` | Top 20 areas and population coverage fractions |
| `rooftop_candidates_map.html` | 100 footprints for review |
| `rooftop_candidates.csv`, `.geojson` | Footprints, review coordinates and height status |
| `operator_inventory_counts.csv`, `verification.json` | Operator counts and provenance checks |
| `model_comparison.json`, `phase2_source_manifest.json` | Experimental evidence and source provenance |
| `submission_manifest.json`, `vendor_manifest.json` | Build/output hashes and asset sources |
| `screenshots/`, `browser_verification.json` | Browser-rendered backups and checks |

```powershell
uv run python tools/build_submission.py --phase2-dir eval_reports/phase2_v2_run2 --output-dir submission
uv run python -m unittest discover -s tests -v
```

The builder checks the v2 feature version, top-20/100-footprint relationship, coordinates inside footprints, unavailable local heights and source-scoped Al-Madar attribution. It packages frozen results without retraining. Initial building needs existing data and network access to runtime assets; the resulting folder is portable. Regenerate screenshots through a browser check after rebuilding.

## Verification and next stage

Fresh release results are recorded with the generated artifacts. The original 62 tests are a historical baseline, not a claim that later changes were already tested.

The connected native browser tool was unavailable during preparation. Local browser automation uses an installed Chromium browser through Playwright. Offline checks block external HTTP requests and verify Leaflet features and controls; HTML generation alone does not count as rendering verification.

After this submission, follow [the integration handoff](gis_BRANCH_INTEGRATION_HANDOFF.md): preserve the working release, establish the shared GIS/provenance contract, then integrate Ahmed's explainable score and source checks. Keep ML experimental until matched baselines and independent planning/RF evidence support it.


### Verified release result

- **64 tests passed**, including public-export and no-eligible-candidate regressions.
- `recommend`, `predict`, `map`, `h3-map` and the submission builder completed successfully.
- Microsoft Edge rendered the entry page and both maps with **zero external HTTP requests, zero JavaScript errors and no missing local assets**. Layer toggles and actual feature tooltips were checked.
- Four real browser screenshots are included; the overview and footprint detail were visually inspected.
- 645 owner-confirmed Al-Madar raw records and radio groups were verified; all attributed groups remain Al-Madar.
- 2,216 scored hexes, 20 shortlisted areas and 100 footprint candidates were checked. All review coordinates are inside their footprints; usable local building heights: zero.
- Raw SQLite and both serving model artifacts match their pre-change Git blobs.

See [release evidence](../../antenna_cell_placement/submission/release_verification.json) and [browser evidence](../../antenna_cell_placement/submission/browser_verification.json).

To reproduce the browser checks with Microsoft Edge installed:

```powershell
npm ci --prefix tools/browser_check
node tools/browser_check/verify.mjs submission
```

This optional Node tool is separate from the Python runtime. Recheck screenshots after regenerating maps.
