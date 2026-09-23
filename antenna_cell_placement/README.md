# Telecom GIS planning for engineering review

Team Loop Gain — Samsung Innovation Campus capstone.

This prototype prioritizes areas and building footprints for engineering review in Tripoli. Population, roads, terrain and the observed site inventory provide planning proxies. An experimental classifier recognizes patterns associated with existing sites. Neither the score nor the shortlist establishes RF coverage, capacity improvement or installation suitability.

## Submission demo

**Start with [submission/index.html](submission/index.html)** after downloading the files. GitHub's source view does not execute HTML; open the local file in Chrome or Edge, or serve the folder locally.

The package includes a Tripoli map with 20 priority areas, 100 footprint candidates with CSV/GeoJSON backups, explicit **building height: unavailable** labels, model comparisons, operator-provenance checks and screenshots. Map scripts/styles and geographic context are bundled for offline use.

No equipment, frequency-band or bandwidth recommendation is issued by the public planning workflow. Known-site distances are inventory gaps, not measured coverage gaps. Population within 5 km is a catchment estimate, not population served.

See [the submission guide](document/SUBMISSION_READINESS.md) for the demonstration sequence, rebuild commands and verification evidence.

## Experimental model evidence

On the same 2,033 frozen hard-negative test examples:

| Experiment | Model ROC-AUC | Population-only ROC-AUC |
|---|---:|---:|
| Legacy features, experimental recipe | 0.876141 | 0.594538 |
| Corrected GIS v2, same recipe | 0.885208 | 0.571961 |

The examples include 533 observed sites and 1,500 synthetic hard negatives. This is **existing-site pattern recognition, not coverage improvement**. The geographic benchmark was previously inspected; synthetic negatives are not verified unsuitable locations. Network features use the known inventory. AUC is not percentage accuracy or a deployment probability.

The separate Tripoli hidden-site recovery diagnostic gave 0.716 AUC for the planning score versus 0.767 for population alone. The richer score has not established superiority for future expansion. This demonstration retains the existing experimental ML multiplier; changing the primary score belongs to the later integration.

## Run locally

From `antenna_cell_placement/` with Python 3.12 and `uv`:

```powershell
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python tools/build_submission.py --phase2-dir eval_reports/phase2_v2_run2 --output-dir submission
uv run python -m http.server 8765 --bind 127.0.0.1 --directory submission
```

Open `http://127.0.0.1:8765/`. Building initially downloads the runtime assets and requires the existing phase-2 artifacts and cleaned data. The generated package is portable. `vendor_manifest.json` records asset sources and hashes.

Useful public commands:

```powershell
uv run antenna-placement clean
uv run antenna-placement features
uv run antenna-placement recommend
uv run antenna-placement predict --lat 32.88 --lon 13.18
uv run antenna-placement map
```

These point-planning commands now omit equipment advice but retain their legacy feature/model contract. The submission's Tripoli map uses the separately versioned phase-2 artifacts. No model has been automatically promoted.

Research commands remain available:

```powershell
uv run antenna-placement evaluate
uv run antenna-placement validate-h3 --city Tripoli
uv run antenna-placement train-experiment --output-dir eval_reports/new_experiment
uv run antenna-placement phase2 --output-dir eval_reports/new_phase2_run
```

Historical equipment-model experiments remain in research code. Grouped equipment accuracy of 0.783924 did not beat the feature-side rules at 0.786761.

## Data and provenance

The historical import of 645 records is attributed to Al-Madar through dataset-owner confirmation scoped to its source fingerprint. Unknown records outside that import require their own evidence. The raw SQLite database is read without rewriting its observations.

Local Microsoft building files contain 970,860 records with no usable heights. A separate audit of dated OSM data found 3,042 explicit heights nationally but none in Ahmed's 50 shortlisted hexes. Neither finding establishes suitable roofs for this demo. Ground elevation and footprint area are not building height.

Large raw inputs are not necessarily included in a clean clone. See the manifests and [dataset overview](document/DATASETS_OVERVIEW.md); the submission folder is the portable presentation artifact.

## Documentation and next stage

- [Submission guide](document/SUBMISSION_READINESS.md)
- [Models, targets, baselines and limitations](document/ML_MODELS_AND_DATA.md)
- [Corrected GIS and rooftop review](document/PHASE2_GIS_AND_ROOFTOPS.md)
- [Pilot validation](document/PILOT_PLAN_AND_VALIDATION.md)
- [Audit and planned branch integration](document/BRANCH_INTEGRATION_HANDOFF.md)

The next architectural step combines Ahmed's explainable score and strict source checks with the corrected GIS and evaluation tools. It is separate from this submission release.
