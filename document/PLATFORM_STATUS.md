# Platform status

What `run_platform.py` and `platform_app/` actually do, as of this pass. Read this
before demoing or claiming something works - it says which pages show real pipeline
output versus a link to a module's own already-working app, and what's still not
connected.

## What's fully wired (real data, no stub)

- **GIS Planning page** (`platform_app/views/1_GIS_Planning.py`) calls
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
- **Network KPI page** (`platform_app/views/2_Network_KPI.py`) covers every KPI the
  operator data holds - RRC setup, E-RAB establishment, E-RAB drop, intra-4G and
  overall handover, availability, DL/UL throughput, connected users, downtime - on
  all 6 bands, in four tabs:
  - *KPI health*: latest observed value of all 60 band x KPI readings against its
    SLA, straight from the carrier export (13 of 60 breach on 2026-09-17; downtime is
    divided by the band's cell count because its SLA is per cell).
  - *KPI forecasts*: any band x KPI from a completed `cellular_kpi_forecast` run
    (`run_cellular.py train`, ~80 s; outputs committed under
    `cellular_kpi_forecast/data/output/`), with history, a 5th-95th percentile band,
    the SLA line, and a trust badge.
  - *Forecast accuracy*: only 21 of the 60 forecasts beat a naive baseline on
    held-out data (MASE < 1); availability, connected users and downtime beat it on
    none. Forecasts that don't are still shown but labelled "trend sketch only".
  - *Traffic volume*: `traffic_volume_forecast` run live (~2 s) on traffic history
    only. Using every KPI as input (`run_traffic.py enriched`) was tried and did not
    improve held-out accuracy once a same-day leak in the old multivariate code was
    fixed (2.22% vs 2.34% test WAPE); the previously reported 1.74% relied on that leak.
- **Navigation and Overview**: `platform_app/Home.py` is the entry point and groups
  pages by team (Network operations, Planning, Customers) with `st.navigation`;
  pages live in `platform_app/views/` (not `pages/`, which Streamlit would also
  auto-register and then report "Page not found" on deep links). The Overview
  (`views/0_Overview.py`) shows five live headline figures - KPI SLA breaches,
  critically congested towers, next-day 4G traffic, candidate sites, revenue at risk
  - and a "Needs attention" briefing that takes the most urgent item from each
  module with a link to act on it, plus per-service status. Revenue at risk comes
  from churn's own `/portfolio/summary`, which needs `PREPAID_CHURN_COPILOT_KEY`
  (see below). Theme, colours and the hidden developer toolbar are set in
  `platform_app/.streamlit/config.toml`, so run the shell from `platform_app/` (as
  `run_platform.py` does) for them to apply.
- **Congestion & Steering page** (`platform_app/views/3_Congestion_Steering.py`),
  served by the network API's `/steering/*` and `/towers/*` routes from two modules
  Mohamed Khalaf built as a pair: `tower_kpi_forecast/` trains per-tower XGBoost
  next-day forecasts (connected users, DL throughput, availability, drop rate, 1,067
  towers; chronological 70/30 split, leak-free lags), and `traffic_steering_son/`
  turns them into congestion alerts and 3GPP CIO handover-offset proposals. Shows the
  latest day's alerts and recommendations, cluster capacity, and any tower's
  predicted-vs-actual. Everything is labelled as a backtest over 2026-06-03 to
  2026-09-19, not live orders. "Estimated speed gain" is labelled as arithmetic
  (equal sharing of fixed capacity), not a measurement.
- **Customer Churn page** and the **Assistants page** embed each module's own
  already-running Streamlit app live via `st.iframe` (not a link to a new tab, and
  not a re-implementation of their UI) - prepaid_churn's app, and the customer
  chatbot / employee copilot, each still their own process on their own port. The
  copilot (Taha's latest) reads GIS `integrated_release_v3` and its measured-service
  review, plus the network KPI files, as well as the churn service.

## Access this needs that isn't in git

- Churn's FastAPI (`prepaid_churn/src/prepaid_churn/api.py`) requires
  `PREPAID_CHURN_CHATBOT_KEY`/`PREPAID_CHURN_COPILOT_KEY` (each at least 24
  characters, distinct) to start at all - see `assistants/README.md`. Without them,
  `run_platform.py` skips churn's API/app and both assistants, and the Home
  dashboard's churn tile and the Customer Churn/Assistants pages show a clear
  "unreachable"/"not set" state, never a guessed number. This pass generated two
  local demo keys to verify the fully-wired dashboard end to end; they are not
  committed anywhere and are not shared secrets - anyone running this platform
  generates their own the same way `assistants/README.md` already describes.
- Churn's own pipeline (`churn build-dataset` -> `train` -> `evaluate` -> `bundle`
  -> `score` -> `fit-tiers` -> `tiers`) was run once in this environment to produce
  real artifacts under `prepaid_churn/artifacts/` (gitignored, not committed):
  30,000 scored subscribers, champion `lightgbm-2026-09-19-ef9430fb`, release gate
  passed. Without running that pipeline in a given checkout, churn's tile and app
  show their own honest "not built yet" state (this is churn's own module
  behavior, not something platform_app controls or changed).

## What's not connected at all

- `erbs_node_analytics` (per-tower ST-GNN, sleeping-cell detection, 1,067 towers) is
  the one `network_kpi_prediction` pipeline with no platform route yet.
- `tower_kpi_forecast/` and `traffic_steering_son/` have no tests. The forecaster's
  committed outputs came from an older version of its code; the current (seeded)
  code reproduces close numbers except network-level availability R² (0.13
  committed vs 0.31 rerun). Committed outputs are kept because steering's committed
  results are built on them - regenerating both together is Mohamed's call.
- Tower IDs are anonymised (TWR_0001...) and the tower data carries no coordinates,
  so steering can't yet be placed on the GIS map.
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
- `platform_app/test_smoke.py`: all 5 pages (Home, GIS, KPI, Churn, Assistants) run
  through Streamlit's `AppTest` harness without raising, with or without the
  backend APIs running.
- Manual end-to-end check, all 7 services via `run_platform.py` with demo churn
  keys set: GIS API :8001, KPI API :8002, churn API :8000, churn app :8501,
  chatbot :8503, copilot :8502 and the platform shell :8510 all came up and
  answered real requests. Home's three dashboard metrics rendered real numbers
  (GIS: 20 shortlisted sites; KPI: 1,061,667 GB next-day forecast; churn: 30,000
  subscribers monitored) with zero exceptions via `AppTest`. The Churn and
  Assistants pages' `st.iframe` embeds were exercised against the live, reachable
  apps (not just the offline-fallback path) with zero exceptions.
