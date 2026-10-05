# Project handoff — 2026-09-22

Read `document/ML_MODELS_AND_DATA.md` and `document/IMPROVEMENT_PLAN.md` first. They describe the verified implementation, current evidence and staged acceptance gates. Historical technical/pilot reports have status notices; their old claims are not current RF validation.

The user authorized planning, implementation and documentation improvements. The first milestone is complete: source-scoped attribution of 645 Al-Madar LTE records; idempotent H3 feature joins; meter-correct road-negative filtering; municipality/distance checks for hard negatives; operator-neighbor self exclusion; missing-feature scoring; and a separate reproducible grouped training experiment.

40 tests passed. `eval_reports/implementation_verification.json` records corrected totals, raw-database preservation and refreshed outputs. `eval_reports/experiment_20260922_v1/` contains the exact dataset, split/parameter manifest, model, predictions and metrics. Hard-negative AUC is 0.8761 versus population-only 0.5945 on identical rows. Do not claim this proves improvement over historical 0.7238: the sample set changed and test geography had already been inspected.

The serving model is unchanged; experiment artifacts are not automatically promoted. The nationwide and Tripoli maps were regenerated. Phase-2 source feature values were carried over; full raw enrichment and browser visual QA were not rerun.

Phase 2 now has a separate GIS feature version, area-weighted circular/hex population, nodata/indexing corrections, geodesic/regional distances, network identity/bandwidth/cluster audits, a controlled model comparison, and a preliminary rooftop footprint shortlist. Read `document/PHASE2_GIS_AND_ROOFTOPS.md` for current verification results and exact limits. All 970,860 local Microsoft building records lack usable heights; DEM elevation is ground elevation. Do not invent roof heights or describe footprint candidates as installation-approved.

Phase 2 verification: 62 tests passed; `eval_reports/phase2_v2_run2/` is complete and integration-verified. AUC is 0.8852 versus 0.8761 on the same hard-negative rows. Five retained physical clusters exceed 50 m full diameter. The shortlist contains 100 footprints in 20 areas. Raw DB and serving-model hashes are unchanged. Browser visual QA was unavailable. The earlier `phase2_v2/` directory is incomplete and must not be used as the final run. Review strict-population missingness in the guide before interpreting scores.

Next work: incremental coverage selection, stronger independent evaluation, RF/feasibility, and joinable KPIs. See the plan's acceptance gates. No new RF, KPI, blind-test or field evidence is claimed. Serving commands remain legacy; only the explicit `phase2` command uses the new feature/model contract.

The repository already had substantial uncommitted work before this milestone. Preserve it; no commit/push was made in this turn. Original edited files are backed up under `C:/Users/LED/Desktop/GIS/backups/antenna_20260922`. Large external datasets remain local and need a reproducible distribution policy.

Commands from this folder:
```powershell
uv run python -m unittest discover -s tests -v
uv run antenna-placement clean
uv run antenna-placement features
uv run antenna-placement train-experiment --output-dir eval_reports/a_new_run
uv run antenna-placement phase2 --output-dir eval_reports/a_new_phase2_run
uv run antenna-placement h3-all --city Tripoli
```
Use a new experiment directory; existing artifacts cannot be overwritten by that command. The local virtual-environment base runtime has been repaired to the project-local Python 3.12.13 installation.
