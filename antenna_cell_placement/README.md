# Libya Telecom GIS Planning

Samsung Innovation Campus capstone project by Team Loop Gain.

This project cleans supplied Libyan cellular observations, joins supplied geographic datasets, and ranks generated candidate locations for engineering review. It does not create synthetic training rows, infer missing measurements as facts, or present a score as a deployment probability.

The central output is an explainable `planning_priority_score`. It is a relative planning indicator assembled from available population, access, terrain, and existing-site gap evidence. Regional Internet activity is exported as review context but does not affect the current rank. The score is not RF coverage, service quality, model confidence, or proof that a new site is required.

## Data Policy

Only declared source datasets are used as evidence. Processing may clean, deduplicate, aggregate, project, or derive features from those datasets. The only generated geographic records are proposed candidate placements. Externally acquired roadmap sources remain experimental until their recorded gate justifies a narrow use.

| Data class | Examples | Policy |
| --- | --- | --- |
| Supplied observations | `cells.sqlite3`, `cells.json`, `data/606.csv`, WorldPop, elevation, roads, boundaries, settlements, Cloudflare exports | Preserve source fields and provenance; validate before use. |
| Deterministic derivatives | Deduplicated cells, clustered site references, distances, raster samples, catchment sums, percentiles | Reproducible from supplied data; keep missingness visible. |
| Generated proposals | Candidate coordinates and their rank | Allowed only as clearly labeled planning suggestions. |
| Gate-reviewed external source | ESA WorldCover; dated OpenStreetMap layers; Ookla mobile tiles; VIIRS night lights | Allowed only for their recorded gate decisions. Step 10 heights, the Step 11 port proxy, Step 12 Ookla, and Step 13 VIIRS remain excluded from runtime. |
| Fabricated evidence | Synthetic positive/negative labels, invented bandwidth, guessed operator, assumed tower type, rule-created equipment labels | Prohibited. |

Generated candidates must never be merged into observed site inventories. A high rank means "review first," not "build here."

## Declared Sources

- `Libyan_cells_dataset/cells.sqlite3` and `cells.json`: project-provided cellular observations.
- `data/606.csv`: OpenCellID cell observations for MCC 606.
- `data/external/lby_pd_2020_1km.tif`: WorldPop population raster.
- `data/external/dem/`: elevation raster used by the feature pipeline.
- `data/Libya_SRTM/`: supplied SRTM HGT tiles; retained as source data even if the active pipeline uses the prepared elevation raster.
- `data/external/roads/`: supplied road vectors.
- `data/external/admin_boundaries/`: administrative boundaries and populated places.
- `data/cloudflare_radar_libya/`: regional Internet-activity context. This is not mobile demand or radio coverage.
- `data/external/worldcover_2021/`: 27 official ESA WorldCover 2021 v200 tiles plus a checked provenance manifest. Raw TIFFs stay local; the manifest records hashes, license, DOI, URLs, and retrieval metadata.
- `data/external/osm_libya_2026_09_19/`: the dated Geofabrik Libya GeoPackage, archive, and raw PBF with checked provenance manifests. Building outlines plus hospital, higher-education, aviation, and industrial observations are integrated as review context. Explicit heights and the sparse ferry-terminal port proxy are excluded.
- `data/external/ookla_mobile_2025q2_2026q1/`: four official quarterly mobile-performance archives, a deterministic Libya subset, and checked provenance. Step 12 rejected runtime integration because shortlist coverage failed. The source is CC BY-NC-SA 4.0 and is restricted to non-commercial use.
- `data/external/viirs_nightlights_2024/`: bounded Libya windows from four official monthly VIIRS DNB composites, cloud-free observation counts, the official 2024 gas-flare catalog, and checked provenance. Step 13 rejected runtime integration because independent activity/KPI validation is unavailable.

WorldCover and the Step 9 and 11 OSM layers are integrated only as `review-only` evidence. None changes the score. Step 10 height evidence, Step 12 performance observations, and Step 13 night lights are excluded from outputs and scoring. Proposed additions and their evidence gates are documented in [TELECOM_GIS_RF_AI_ROADMAP.md](TELECOM_GIS_RF_AI_ROADMAP.md).

## Workflow

```text
supplied telecom observations --> validate and clean --> observed-site reference
supplied GIS layers -----------> derive features ------> auditable planning evidence
candidate generator -----------> score and filter ----> proposed placements
                                                        |
OpenCellID observations -------> proximity review ------+
ESA WorldCover ---------------> water screen/context ---+
OSM building outlines --------> mapped context ---------+
selected OSM families --------> local review context ---+
```

The planner favors locations with documented demand proxies, a gap from observed sites, and practical access. It emits the component values and missing-data flags alongside the final rank so a reviewer can see why a location was prioritized.

H3 resolution 7 provides stable planning-unit identifiers for candidates and area-weighted WorldPop aggregation. Resolution 6 is the documented parent sensitivity level. H3 improves aggregation and reporting but does not alter the placement score.

WorldCover removes candidate points classified as permanent water and adds area-weighted H3 land-cover context. Mixed/coastal units are flagged for review. It does not alter the score and is not treated as validated RF clutter or proof of buildability.

The building layer adds H3 mapped-outline count, footprint area, density, and coverage ratio. Missing outlines mean “not observed,” not “no buildings.” This context does not alter ranking or prove land availability, access, ownership, or constructability.

The selected Step 11 layer adds H3 observation counts and nearest-feature distances for mapped hospitals, higher education, aviation, and industrial land use. These are contextual observations, not complete inventories or demand measurements. The sparse ferry-terminal class is excluded from runtime as an inadequate national port proxy.

The current output is a GIS screening product. It does not calculate RSRP, RSRQ, SINR, interference, sector azimuth, downtilt, antenna height, bandwidth, traffic capacity, or backhaul feasibility. Those require RF inputs and validation described in the roadmap.

## Installation

Python 3.12 or newer and `uv` are required.

```bash
uv sync
uv run antenna-placement --help
```

Rebuild the local WorldCover source snapshot and its provenance manifest from the official ESA bucket with:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python tools/download_worldcover.py
```

The source is [ESA WorldCover 2021 v200](https://esa-worldcover.org/en/data-access), licensed CC BY 4.0 and identified by [DOI 10.5281/zenodo.7254221](https://doi.org/10.5281/zenodo.7254221).

Rebuild the exact Step 9 OpenStreetMap building snapshot and provenance manifest with:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python tools/download_osm_buildings.py
```

The snapshot comes from [Geofabrik's Libya extract](https://download.geofabrik.de/africa/libya.html) and requires [OpenStreetMap attribution under ODbL](https://www.openstreetmap.org/copyright).

Rebuild the exact Step 10 raw OSM snapshot and height-audit manifest with:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python tools/download_osm_building_heights.py
```

The gate reads explicit [`height=*`](https://wiki.openstreetmap.org/wiki/Key:height) tags only. It does not convert `building:levels` into metres.

Rebuild the Step 12 Ookla snapshot, Libya subset, and provenance manifest with:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python tools/download_ookla_mobile.py
```

The source is [Speedtest by Ookla Global Mobile Network Performance Map Tiles](https://github.com/teamookla/ookla-open-data), licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Speedtest® by Ookla® data was accessed on 21 September 2026 from AWS for project analysis of 2025 Q2 through 2026 Q1. Ookla trademarks are used under license.

Rebuild the Step 13 bounded VIIRS snapshot and provenance manifest with:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run python tools/download_viirs_nightlights.py
```

The monthly composites come from the [World Bank Light Every Night public bucket](https://registry.opendata.aws/wb-light-every-night/) under ODbL. The upstream product is generated by the Earth Observation Group. The gate also uses EOG's official 2024 gas-flare catalog to exclude candidate points within 5 km of a known flare.

## CLI

Run the stages individually:

```bash
# Validate and clean the supplied telecom observations.
uv run antenna-placement clean

# Validate and summarize data/606.csv for candidate review.
uv run antenna-placement opencellid

# Derive GIS features from the supplied datasets.
uv run antenna-placement features

# Generate and rank proposed locations with the explainable planning score.
uv run antenna-placement recommend

# Validate H3 coverage, population conservation, hierarchy, and repeatability.
uv run antenna-placement h3-evaluate

# Verify and compare the WorldCover screening layer against the frozen baseline.
uv run antenna-placement worldcover-evaluate

# Verify and compare mapped-building context against the Step 8 baseline.
uv run antenna-placement buildings-evaluate

# Audit explicit building-height evidence against the Step 9 baseline.
uv run antenna-placement building-heights-evaluate

# Evaluate selected OSM feature families against the frozen ranking baseline.
uv run antenna-placement osm-evaluate

# Audit supported Ookla mobile observations against the Step 11 baseline.
uv run antenna-placement ookla-evaluate

# Evaluate VIIRS radiance without adding it to production recommendations.
uv run antenna-placement viirs-evaluate

# Assess one proposed coordinate with the same explainable score.
uv run antenna-placement assess --lat 32.88 --lon 13.18

# Build the review map.
uv run antenna-placement map

# Run the complete dataset-only pipeline.
uv run antenna-placement all
```

Use `uv run antenna-placement --help` as the authoritative command list. Coordinate assessment must report a planning score and evidence fields, never a probability or equipment recommendation.

## OpenCellID `606.csv`

The importer accepts a named or headerless file with exactly these 14 columns in this order:

```text
radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal
```

The fields follow the [OpenCellID database format](https://docs.opencellid.org/docs/downloads/database-format). `net` is the MNC (SID for CDMA), `area` is LAC/TAC (NID for CDMA), and `cell` is the cell identifier. `unit` is PSC for UMTS or PCI for LTE and is normally empty for GSM/CDMA. `lon` and `lat` are estimated cell coordinates. `range` is an estimated cell range in metres; it is retained as metadata and is not treated as a coverage radius or coordinate-accuracy bound. `samples` is the number of measurements assigned to the cell. `created` and `updated` are Unix timestamps. `changeable` is deprecated and always `1`; `averageSignal` is deprecated and always `0`, so neither provides planning evidence.

The importer keeps OpenCellID cells separate from physical-site references. A nearby cell can trigger review, but does not prove mast identity, coverage, capacity, operator ownership, or suitability. The absence of a nearby OpenCellID record does not prove a coverage gap.

## Missing Data

Missing source values stay missing or receive an explicit availability flag. In particular:

- absent bandwidth is not replaced with a technology-wide assumption;
- unresolved operator identity stays unknown;
- missing tower type stays unknown;
- unavailable raster samples are not converted to measured zero;
- absent Cloudflare regional data remains missing and flagged unavailable; Cloudflare does not affect ranking.
- absent mapped building outlines remain explicitly unobserved; they are not converted into evidence of empty land and do not affect ranking.

Rows that fail source validation are quarantined or excluded with a recorded reason. The pipeline must not silently relax planning constraints to force a requested number of recommendations.

## Outputs

Cleaning and feature transformations run in memory. The retained project artifacts are proposed-placement CSV/GeoJSON, the review map, and compact Step 7-13 evaluation reports under `eval_reports/`; they can be rebuilt from declared source inputs.

The recommendation output contains:

- deterministic candidate ID, H3 resolution 7 unit, resolution 6 parent, generation source, latitude, and longitude;
- `planning_priority_score` and component scores;
- distance to observed-site references and roads;
- population and terrain evidence when available;
- municipality and settlement context;
- OpenCellID proximity fields and review flag;
- WorldCover point class, water/availability flags, H3 class proportions, and mixed/coastal review flag;
- OSM mapped-building count, footprint area, density, coverage ratio, observation/availability flags, and review flag;
- H3 counts, observation flags, and nearest-feature distances for the accepted Step 11 OSM review families;
- a stable recommendation rank, score version, and reason codes.

Candidates missing required population, terrain, site-distance, road-distance, or WorldCover point evidence are ineligible rather than filled with invented values. Confirmed WorldCover permanent-water points are also ineligible. Cloudflare context carries its own availability field.

It must not contain invented radio bands, bandwidth, building height, equipment tier, coverage gain, or model probability.

## Verification

```bash
uv run python -m unittest discover -s tests -v
```

For each pipeline run, also inspect the CLI source-validation summaries, missingness counts, candidate audit, score-component ranges, and map. Exact source snapshots and row counts can change, so record the command output with the source snapshot used for an accepted review.

The 2026-09-20 Step 10 run passed all 37 automated tests and verified the raw PBF size and hash. Of 1,268,052 mapped footprints, only 3,042 had a plausible explicit height: 0.2399% coverage. Valid heights appeared in 19 of 22 municipalities and zero shortlisted H3 cells; none declared `source:height`. The recommendation output remained unchanged. Step 10 therefore has a `remove` decision, and no height field enters the runtime or score.

The 2026-09-21 Step 11 run passed all 40 automated tests and verified the existing GeoPackage snapshot. It retained 893 hospitals, 799 higher-education features, 87 aviation features, and 1,706 industrial features as review-only context. Those families covered 90.91-100% of municipalities. The 12-record ferry-terminal proxy covered only one municipality and was removed. Scores and ranks were identical before and after integration (Spearman 1.0).

The 2026-09-21 Step 12 run passed all 44 automated tests and verified four official Ookla archives plus the deterministic Libya subset. Of 24,979 tile-quarter rows, 4,426 met the support threshold of at least five tests and three devices. Supported evidence covered 20 of 22 municipalities, but only 3 of 50 shortlisted H3 cells had at least two supported quarters. The 6% shortlist coverage failed the pre-set 25% threshold, so no Ookla field enters recommendations, assessment, maps, or scoring. Scores and ranks remained unchanged.

The 2026-09-21 Step 13 run verified 128,340,693 bytes of local VIIRS and flare artifacts. Forty-nine of 50 candidates remained supported after a 5 km official gas-flare exclusion (98% coverage), and selected-month radiance was stable (median Spearman 0.9660). A hypothetical 10% radiance weight promoted five candidates into the top 10, none near a catalogued flare. However, no independent activity, traffic, KPI, or reviewed planning labels exist to show incremental holdout improvement. VIIRS is therefore excluded from recommendations, assessment, maps, and scoring; redundancy is not treated as improvement.

## Limitations

- Crowdsourced cell coordinates are estimates and may be stale, duplicated, or displaced from a physical mast.
- A cluster of radio observations is an inferred site reference, not a verified asset register.
- Population, roads, terrain, and Internet activity are planning proxies; none measures operator traffic or service quality.
- Site-distance gaps do not establish RF coverage gaps.
- Libya-wide work spans several UTM zones; distance and area calculations require projection checks.
- Candidate coordinates require field survey, land and permitting review, power and backhaul checks, spectrum planning, RF simulation, and operator approval.
- WorldCover describes 2021 surface class; it does not prove current buildability or calibrated RF attenuation.
- OpenStreetMap building outlines are contributor-mapped and incomplete; absence does not prove empty land, while a footprint does not prove height, ownership, access, or constructability.
- Explicit OSM height tags are too sparse and insufficiently sourced for national planning; floor counts are not converted into heights.
- Ookla Speedtest observations are self-selected, sparse at shortlisted cells, and licensed for non-commercial use under share-alike terms. Tile-quarter device counts are not unique across space or time.
- VIIRS radiance is an activity proxy, not mobile demand. A four-month median reduces transient influence but is not an active-fire mask, and the flare catalog cannot identify every industrial light source.

See [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) for the implemented methodology and [TELECOM_GIS_RF_AI_ROADMAP.md](TELECOM_GIS_RF_AI_ROADMAP.md) for the gated path to RF- and KPI-validated planning. Step 14, FABDEM comparison, is next; Steps 15-20 remain pending in roadmap order.
