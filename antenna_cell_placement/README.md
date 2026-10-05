# Integrated telecom planning for engineering review

Team Loop Gain — Samsung Innovation Campus capstone.

The public planner combines **Mahalm’s corrected GIS and inventory provenance** with **Ahmed’s explainable score, strict eligibility and verified source context**. Machine learning is a separate research comparison and is excluded from the default ranking.

## Open the combined demo

Open [integrated_release_v3/index.html](integrated_release_v3/index.html) locally in Chrome or Edge. Maps, assets, CSVs and screenshots work offline. GitHub’s HTML source view does not execute a map.

The earlier [submission demo](submission/index.html) is preserved as a historical release. Its experimental ML multiplier and old shortlist are not the integrated planner’s outputs.

## Run the planner

From `antenna_cell_placement/`, using Python 3.12 and `uv`:

```powershell
uv sync --locked
uv run python tools/download_worldcover.py
uv run python tools/download_osm_buildings.py
uv run antenna-placement doctor
uv run antenna-placement recommend --scope Tripoli --output-dir eval_reports/my_integrated_run
uv run antenna-placement assess --lat 32.88 --lon 13.18
uv run antenna-placement map --run-dir eval_reports/my_integrated_run
```

Download scripts use portable exclusive locks, temporary files and the reviewed SHA256 hashes. WorldCover is required for water screening; OSM buildings/POIs are optional review context. The source lock also identifies the required inventory, WorldPop, terrain and OCHA files. `doctor` explains absent or changed inputs before processing. New run directories are required; an existing run is never silently overwritten.

`recommend` and `all` now run the same integrated workflow, including maps, comparisons, footprint review, operator/technology measurement layers, the chronological pilot and the official-statistics audit. `predict` is an alias for explainable coordinate assessment. Add `--operator almadar` or `--operator libyana` for a scope-specific known-site gap; the default is all networks. The new inventory uses explicit network identity and the source-scoped owner confirmation; remaining unknown identities are not inferred from nearby sites.

`--scope national` generates geodesic settlement rings and sampled road locations. It is a proposal search, not an exhaustive national H3 search or a claim of nationwide deployment readiness. The release demonstration is Tripoli.

## What the score means

The score is a **provisional planning heuristic**: 40% population, 30% distance to known sites, 20% road access and 10% terrain. It is neither a coverage probability nor an installation approval.

Strict defaults require a location inside Libya, finite corrected measurements, at least 99% valid population catchment area, complete terrain evidence, observed non-water land cover, population within 5 km of at least 300, a known-site gap of at least 3 km, and a road within 4 km. Selected locations are separated by at least 2.5 km. An empty shortlist is a valid result; constraints are never relaxed to fill it.

Every candidate retains its rejection reasons, component scores, H3 IDs, operator scope, feature version and source-lock hash. Population is calculated from density × intersected area. “Population within 5 km” is not “population served”; overlapping catchments must not be summed as unique beneficiaries.

Footprints are preliminary review candidates inside the H3 areas containing shortlisted points. A point’s score does not establish suitability for every roof in its area. Building height is unavailable in the Microsoft sources used here; elevation is ground elevation. Usable roof area, structural capacity, permission, power and backhaul require investigation.

## ML: a separate, reproducible experiment

On the same 2,033 previously inspected hard-negative examples:

| Features, same training recipe | Experimental model AUC | Population-only AUC |
|---|---:|---:|
| Legacy GIS | 0.876141 | 0.594538 |
| Corrected GIS v2 | 0.885208 | 0.571961 |

The labels distinguish observed sites from generated non-site samples. **These numbers measure recognition of existing-site patterns, not RF coverage improvement.** No model has been promoted into the primary ranking.

The default install contains no LightGBM or scikit-learn. To reproduce research or compare the GIS-v2 model against the same integrated candidates:

```powershell
uv sync --locked --extra research
uv run --extra research antenna-placement experimental compare --run-dir integrated_release_v3 --model eval_reports/phase2_v2_run2/suitability_gis_v2.joblib --output-dir eval_reports/my_ml_comparison
uv run --extra research antenna-placement experimental train-experiment --output-dir eval_reports/new_experiment
uv run --extra research antenna-placement experimental phase2 --output-dir eval_reports/new_phase2
uv run --extra research python -m unittest discover -s tests -v
```

Comparison writes a separate artifact; it cannot change the primary shortlist. The current model supports all-network GIS-v2 features only. Source and model version mismatches fail explicitly. Historical commands and old feature/model behavior are retained under `experimental` for reproducibility.

## September 29 evidence and inventory update

The current release adds 4,874 eligible handset observations and a reconciled inventory of 2,670 radio-location groups / 2,344 physical references. All 645 owner-confirmed Al-Madar records remain traceable; 643 pass the boundary check and two remain in the review ledger. Six conflicting identities remain unresolved.

The full rerun keeps 162 eligible candidates and the same 20 selected points. No supplied eligible handset observations lie within 5 km of those points, so measured-service evidence does not validate this shortlist. The later-day signal baseline scores 74/258 blocks with 7.676 dB MAE; it is not an RF propagation model.

The historical [September 25 integration](integrated_release/index.html) remains available for comparison. See [the new implementation and reproduction guide](document/SEPT29_INTEGRATION.md).

## Documentation

- [September 29 measurements, inventory and verification](document/SEPT29_INTEGRATION.md)
- [Original integration result, architecture and validation](document/INTEGRATED_PLANNING.md)
- [Model targets, baselines and limitations](document/ML_MODELS_AND_DATA.md)
- [GIS corrections and footprint review](document/PHASE2_GIS_AND_ROOFTOPS.md)
- [Data inventory and provenance](document/DATASETS_OVERVIEW.md)
- [Original comparison and integration handoff](../document/team_notes/gis_BRANCH_INTEGRATION_HANDOFF.md)
- [Historical submission guide](../document/team_notes/gis_SUBMISSION_READINESS.md)

The source-scoped attribution of 645 records to Al-Madar is preserved, including the original raw observations. RF/KPI measurements and engineering feasibility evidence are still needed before deployment decisions.
