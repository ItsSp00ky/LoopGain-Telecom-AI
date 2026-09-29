# Platform status

What `run_platform.py` and `platform_app/` actually do, as of this pass. Read this
before demoing or claiming something works - it says which pages show real pipeline
output versus a link to a module's own already-working app, and what's still not
connected.

## What's fully wired (real data, no stub)

- **GIS Planning page** (`platform_app/pages/1_GIS_Planning.py`) calls
  `antenna_cell_placement`'s `api.py` directly: source-verification status from
  `verify_sources()`, the shortlist from `integrated_release_v3/` - the completed
  run behind the real collected-data/reconciled-inventory integration (CellMapper,
  BeaconDB, OpenCellID Libya exports, Chongqing 5G, Libya official statistics;
  `inventory_version: "reconciled-geodesic-20260929-v1"`), hash-checked against its
  manifest, same rule the CLI's `map` command already enforces - and an on-demand
  coordinate assessment via `assess_coordinate`. If required local source data isn't
  present/verified in a given checkout (the large gitignored DEM/WorldCover/OSM/cleaned
  files - true of this checkout right now), `/assess` returns a clean 503 and the page
  shows that instead of crashing; `/shortlist`, `/rooftops` and `/map` don't need that
  data, only the completed run, so they work regardless.
- **Network KPI page** (`platform_app/pages/2_Network_KPI.py`) calls
  `network_kpi_prediction`'s new `api.py`, which runs the real
  `traffic_volume_forecast` pipeline (clean, chronological split, four-model
  benchmark, champion retrain, recursive forecast) live and returns the actual held-out
  test metrics (WAPE/MAE/RMSE/R2) plus the forecast series with 80%/95% intervals.
- **Home page** service-status cards call each backend's real `/health` endpoint
  (GIS, KPI, churn) - "unreachable" means that process isn't running, not a bug in
  the shell.

## What's a link-out, not embedded

- **Customer Churn** and the **customer chatbot / employee copilot**: these already
  have their own tested Streamlit apps and a key-protected FastAPI service
  (`prepaid_churn/src/prepaid_churn/api.py` requires
  `PREPAID_CHURN_CHATBOT_KEY`/`PREPAID_CHURN_COPILOT_KEY`, each at least 24
  characters). `platform_app/Home.py` links to each one's own URL rather than
  re-importing their page code or calling their key-protected routes without a key
  provisioning story. This is a deliberate scope decision, not an oversight - see
  the commit that added `platform_app/`.

## What's not connected at all

- Of `network_kpi_prediction`'s three pipelines, only `traffic_volume_forecast` has
  an API route. `cellular_kpi_forecast` (multi-band 3GPP KPI forecasting) and
  `erbs_node_analytics` (ST-GNN sleeping-cell/topology intelligence) are real,
  tested pipelines in that module but have no platform API route yet.
- `traffic_steering_son/` (congestion detection, mobility load balancing) has no
  API route and is not reachable from the platform shell at all yet.
- GIS's KPI-as-congestion-signal idea from `antenna_cell_placement`'s own pilot
  planning docs is still future work, not part of this pass.
- No production deployment, reverse proxy, HTTPS or process manager - `run_platform.py`
  is a local development launcher (subprocess, no Docker), matching that no module in
  this project currently uses Docker.

## Superseded folders still in the repo

`customer_churn_prediction/`, `customer_support_chatbot/` and `kpi_prediction/` at the
repository root are earlier, unreviewed precursors to `prepaid_churn/`, `assistants/`
and `network_kpi_prediction/` respectively. Nothing in the platform imports them
(checked by grep before writing this file). They were left in place rather than
deleted in this pass - deleting them is a one-line follow-up once the team agrees,
not a step this pass took unilaterally.

## Verification behind this document

- `antenna_cell_placement`: 126 tests, all pass (1 skip: `/assess` needs locally
  regenerated cleaned CSVs and downloaded DEM/WorldCover/OSM data this checkout
  doesn't have - unrelated to code correctness). This module's GIS integration is
  `dc897a4` on `mahalm_antenna_cell_placement` (the user's own commit, cherry-picked
  here), not the author's own earlier from-source port - that port covered the same
  ground with copied code only and no real collected data, so it was reverted in
  favor of this commit once it existed (129 tests, 5 errors from exactly the missing
  data this version now ships).
- `network_kpi_prediction/test_api.py`: 3 tests, all passing against the real
  pipeline (no mocking).
- `platform_app/test_smoke.py`: every page runs through Streamlit's `AppTest`
  harness without raising, with or without the backend APIs running.
- Manual end-to-end check: all three always-on services (GIS API :8001, KPI API
  :8002, platform shell :8510) started via `run_platform.py`, answered real
  requests, and shut down cleanly with no orphaned ports.
- Not verified in this pass: the churn API/app/chatbot/copilot path end-to-end
  through `run_platform.py` (this environment has no
  `PREPAID_CHURN_CHATBOT_KEY`/`PREPAID_CHURN_COPILOT_KEY` set) - the skip path was
  verified, the enabled path was not.
