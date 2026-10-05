> **Status update — 2026-09-22:** This document records an earlier design/run. Current model/data definitions, metric corrections, implemented fixes and remaining work are maintained in [ML_MODELS_AND_DATA.md](ML_MODELS_AND_DATA.md) and [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md). Historical figures here are not evidence of measured coverage, independent equipment validation or a completed RF planner.

# Telecom GIS, RF, and AI Planning Roadmap

## Purpose

This document explains how to evolve the current antenna placement project into a production-ready, AI-assisted telecom GIS and RF planning platform for Libya.

The current project already has a strong base:

- Existing Libyan telecom cell/site data
- Cleaned physical site locations
- SRTM elevation / height files for Libya
- WorldPop population data
- Roads and administrative boundaries
- Machine learning models for site suitability and equipment tier recommendation
- GeoJSON, CSV, and HTML map outputs

The next step is to make the system more like real telecom planning software. The goal is not only to predict good tower locations, but to explain why a site is needed, validate it with RF physics, recommend antenna specifications, and produce engineering reports that telecom companies can trust.

## Main Principle

Machine learning should identify where investment is needed.

GIS, RF analysis, and optimization should determine where the exact site should be placed.

In other words:

```text
ML finds the priority area.
GIS and RF planning choose the deployable antenna site.
```

The final product should not only say:

```text
AI thinks this location is suitable.
```

It should say:

```text
This area has high demand, weak existing coverage, good road access,
terrain advantage, low overlap with existing sites, and acceptable LOS/backhaul.

Recommended configuration:
35 m tower, 3 sectors, B20 + B3, azimuths 40 / 160 / 280,
4 degree downtilt, expected strong coverage gain.
```

## Recommended Open-Source Stack

### 1. Current Project

Keep the current Python project as the AI and geospatial intelligence core.

Current role:

- Clean telecom site data
- Extract population, road, terrain, and site-density features
- Train suitability models
- Rank candidate locations
- Recommend high-level equipment tiers
- Generate maps and reports

Future role:

- Generate priority areas
- Generate candidate sites
- Call RF planning tools
- Rank candidates using AI + RF + business constraints
- Produce final planning reports

### 2. H3 Geographic Grid

Use H3 hexagons as the main planning unit.

Instead of evaluating only points, divide Libya into H3 cells. Each H3 hexagon becomes one sample in the planning dataset.

Each H3 zone can contain:

- Population
- Building count
- Building density
- Average building height
- Road density
- POI density
- Land cover percentages
- Terrain elevation
- Terrain slope
- Terrain roughness
- Nearest existing site distance
- Site density within 1 km, 3 km, 5 km, and 10 km
- Cloudflare regional activity
- Ookla speed / latency if available
- Network KPI indicators if operator data becomes available

H3 helps the project produce:

- Demand maps
- Underserved area maps
- Expansion priority maps
- Planning zones
- Aggregated reports per municipality or region

### 3. GRASS-RaPlaT

GRASS-RaPlaT should be the main open-source RF planning engine.

Use it for:

- Terrain-aware coverage simulation
- Sector coverage prediction
- Antenna height evaluation
- Azimuth evaluation
- Downtilt evaluation
- Path loss calculation
- Multi-site coverage aggregation
- Coverage overlap analysis
- Population-covered calculations

Why it fits:

- It is designed for radio planning.
- It works with GIS raster terrain data.
- It supports cellular-style sector planning.
- It is closer to traditional RF planning workflows used by telecom engineers.

It should be used as the main replacement for the mathematical RF layer found in commercial planning tools such as Pathloss, Atoll, Planet, or Mentum.

### 4. SPLAT!

SPLAT! should be used as a supporting tool, not the main planning engine.

Use it for:

- Point-to-point terrain profiles
- Line-of-sight checks
- Fresnel zone clearance
- Microwave backhaul feasibility
- HAAT calculations
- Longley-Rice / ITM terrain path loss checks

Good questions SPLAT! can answer:

```text
Can this candidate site see the nearest backhaul point?
Is the path blocked by terrain?
Is microwave backhaul realistic?
Does the candidate have good height above average terrain?
```

### 5. PostGIS

Use PostGIS as the production geospatial database.

Store:

- Existing sites
- Cells
- Sectors
- Antenna configurations
- H3 planning zones
- Terrain-derived features
- Population features
- Land cover features
- Candidate sites
- RF simulation outputs
- Coverage rasters
- Coverage polygons
- Scenario results
- Network KPI history if available

PostGIS is important because telecom companies need persistent, queryable, auditable planning data.

### 6. QGIS

Use QGIS for engineering review and validation.

QGIS can help with:

- Inspecting data layers
- Checking terrain and coverage
- Reviewing candidate locations
- Exporting professional maps
- Comparing planning scenarios
- Manually validating suspicious recommendations

### 7. GeoServer or QGIS Server + MapLibre

Use these tools for a production web GIS interface.

Recommended setup:

```text
PostGIS
  -> GeoServer or QGIS Server
  -> MapLibre web map
  -> Planning dashboard
```

The dashboard should allow planners to:

- View existing sites
- View coverage gaps
- View demand heatmaps
- View underserved areas
- Toggle population, roads, terrain, land cover, and buildings
- Click a recommended candidate site
- See antenna specs and RF validation
- Export a planning report

## Tools To Avoid As First Production Core

### Sionna RT

Sionna RT is powerful, but it should not be the first production RF engine for this project.

It is better for:

- Advanced research
- 5G/6G digital twins
- GPU ray tracing
- Dense urban 3D simulation
- Differentiable wireless simulation
- Future AI optimization experiments

Reasons to delay it:

- It needs detailed 3D scenes.
- It needs building geometry and material assumptions.
- It is more complex to calibrate.
- It is GPU-heavy.
- It is not the easiest path for Libya-wide planning.

Keep it as a future advanced module, especially for dense areas like Tripoli, Benghazi, and Misrata.

### pycraf

pycraf is useful for ITU-R propagation calculations, especially point/path analysis, but it should not be the main cellular planning platform.

Use it later if needed for:

- ITU-R P.452 path calculations
- Interference studies
- Atmospheric attenuation
- Specialized regulatory-style calculations

Do not make it the main multi-sector planning engine.

## Datasets To Add

The current project already includes useful core datasets. The next production upgrade should add more real-world planning layers.

### 1. ESA WorldCover

Priority: very high.

Use it for RF clutter and land cover.

Features:

- Built-up percentage
- Bare land percentage
- Cropland percentage
- Vegetation percentage
- Water percentage
- Tree cover percentage

Why it matters:

- RF behaves differently in urban, desert, vegetation, and water areas.
- Coverage range and losses depend on clutter type.
- It improves both demand estimation and RF planning.

### 2. Microsoft Global Building Footprints

Priority: very high.

Use it for:

- Building count
- Built-up ratio
- Building density
- Average building area
- Urban footprint detection

Why it matters:

- Population data alone misses commercial and industrial demand.
- Building density helps identify real developed areas.
- It helps distinguish empty land from actual urban expansion.

### 3. Microsoft Building Density and Height

Priority: high.

Use it for:

- Average building height
- Building height variation
- Vertical density
- Urban canyon risk
- Capacity demand estimation

Why it matters:

- High-rise areas create more demand.
- Tall buildings affect RF propagation.
- Dense vertical urban areas may need small cells or capacity layers.

### 4. OpenStreetMap

Priority: high.

Use it for:

- Roads
- POIs
- Hospitals
- Universities
- Schools
- Airports
- Ports
- Commercial zones
- Industrial zones
- Residential areas
- Power/fiber/backhaul proxies where available

Why it matters:

- POIs identify demand that population data may miss.
- Roads help with buildability and drive coverage.
- Industrial/commercial areas often need capacity during working hours.

### 5. Ookla Open Data

Priority: highly desirable.

Use it for:

- Download speed
- Upload speed
- Latency
- Test count
- Device count
- Poor performance zones

Why it matters:

- It helps detect areas where users experience weak network quality.
- It can validate underserved-area predictions.

Important note:

Ookla coverage in Libya should be checked before making it a hard dependency.

### 6. VIIRS Night Lights

Priority: optional / experimental.

Use it for:

- Economic activity proxy
- Night activity
- Urban activity intensity

Why it matters:

- Some areas may have high activity but weak population estimates.
- It can help detect commercial and industrial activity.

Keep it only if testing shows that it improves the model.

### 7. FABDEM

Priority: useful upgrade.

Use it for:

- Bare-earth elevation
- Slope
- Terrain roughness
- Relative elevation

Why it matters:

- It can improve terrain calculations compared with noisy elevation data.
- It is useful for RF line-of-sight and candidate siting.

Because the project already has Libya SRTM files, FABDEM is an enhancement, not an immediate blocker.

## Main Outputs To Build

The production platform should generate five major outputs.

### 1. Unified Network GIS Map

This map should show:

- Existing sites
- Cells/sectors
- Operators
- Technologies
- Bands
- Population
- Roads
- Terrain
- Buildings
- Land cover
- H3 planning zones
- Candidate sites

### 2. Telecom Demand Map

This map estimates where telecom demand is high.

Demand can come from:

- Population
- Buildings
- POIs
- Cloudflare activity
- Ookla activity
- Night lights
- Land use
- Operator traffic KPIs if available

### 3. Underserved Area Map

This map identifies places where demand is high but service is weak.

Signals:

- High demand
- Few nearby sites
- Long distance to nearest site
- Poor Ookla speed or latency
- High predicted congestion
- Poor KPI performance if available
- Low coverage probability from RF simulation

### 4. Expansion Priority Map

This map ranks areas from low to critical priority.

Example labels:

```text
Critical
High
Medium
Low
```

The score should be explainable, not just a black-box model output.

### 5. RF-Validated New Site Recommendation

This is the final engineering output.

Each recommended site should include:

- Latitude and longitude
- Municipality
- Nearest settlement
- Demand score
- Underserved score
- RF validation score
- Final priority score
- Recommended tower height
- Recommended number of sectors
- Recommended azimuths
- Recommended downtilt
- Recommended bands
- Recommended bandwidth
- Recommended antenna gain
- Estimated coverage gain
- Estimated population newly covered
- Backhaul / LOS feasibility
- Road access distance
- Overlap with existing sites
- Main reason codes

## Planning Workflow

The improved workflow should be:

```text
1. Load raw telecom sites and cells
2. Clean and consolidate physical sites
3. Load public GIS layers
4. Convert Libya into H3 planning zones
5. Aggregate features per H3 zone
6. Train or apply demand model
7. Train or apply underserved model
8. Produce expansion priority map
9. Select high-priority H3 zones
10. Generate candidate points inside those zones
11. Evaluate candidates with GIS constraints
12. Simulate RF coverage with GRASS-RaPlaT
13. Validate LOS/backhaul with SPLAT!
14. Optimize antenna configuration
15. Rank final sites
16. Export map, CSV, GeoJSON, and planning report
```

## Scoring Models

### Demand Score

Demand score estimates where user demand is high.

Example formula:

```text
Demand Score =
  0.30 * population_score
+ 0.20 * building_density_score
+ 0.15 * POI_score
+ 0.15 * Cloudflare_activity_score
+ 0.10 * night_lights_score
+ 0.10 * Ookla_activity_score
```

If real operator traffic data becomes available, replace or improve the proxy score with actual traffic:

```text
DL_GB
UL_GB
RRC users
PRB utilization
Active users
```

### Underserved Score

Underserved score identifies areas where demand is high but service is weak.

Example formula:

```text
Underserved Score =
  0.35 * demand_score
+ 0.20 * nearest_site_gap_score
+ 0.15 * low_site_density_score
+ 0.15 * poor_speed_or_KPI_score
+ 0.15 * population_per_site_score
```

### RF Score

RF score validates whether a candidate site performs well physically.

Example formula:

```text
RF Score =
  coverage_gain
+ population_newly_covered
+ elevation_advantage
+ LOS_backhaul_feasibility
- coverage_overlap
- terrain_obstruction
- interference_risk
- bad_land_cover_or_buildability
```

### Final Site Score

The final score should combine AI, GIS, RF, and business factors.

Example formula:

```text
Final Site Score =
  0.30 * AI_suitability
+ 0.25 * newly_covered_population_score
+ 0.20 * RF_coverage_quality
+ 0.10 * low_interference_score
+ 0.10 * buildability_score
+ 0.05 * backhaul_feasibility
```

The exact weights should be calibrated using real operator feedback.

## RF Calculations To Implement

### Free Space Path Loss

```text
FSPL(dB) = 32.44 + 20log10(f_MHz) + 20log10(d_km)
```

Use this as a simple baseline check.

### Received Power

```text
Received Power =
  EIRP
+ receiver_gain
- path_loss
- cable_loss
- clutter_loss
- penetration_loss
- body_loss
```

For cellular planning, this can approximate RSRP or signal strength depending on the model.

### Noise Floor

```text
Noise(dBm) =
  -174
+ 10log10(bandwidth_Hz)
+ noise_figure
```

### SINR

```text
SINR =
  signal_power
- 10log10(interference_power + noise_power)
```

### Fresnel Zone

Use for microwave/backhaul and LOS checks.

The first Fresnel zone radius should be checked along the terrain path. If terrain enters the Fresnel zone too much, the microwave link may be unreliable even if basic line-of-sight exists.

### Height Above Average Terrain

```text
HAAT =
  antenna_ground_elevation
+ antenna_height
- average_surrounding_terrain_elevation
```

This is important because a site on a hill can cover much more area than a site in a valley.

## Propagation Models

Use different propagation models depending on the planning scenario.

### Free Space

Use for:

- Baseline calculations
- Open desert
- Initial sanity checks

### Hata / Okumura-Hata

Use for:

- Macro cellular planning
- Urban/suburban/rural LTE-style coverage
- Fast wide-area estimation

### COST231-Hata

Use for:

- Higher-frequency urban and suburban macro coverage
- 1800 MHz / 2100 MHz style cellular planning

### Walfisch-Ikegami

Use for:

- Dense urban areas
- Building-aware planning where building height/density is available

### Longley-Rice / ITM

Use for:

- Terrain-aware rural and long-distance propagation
- SPLAT! validation
- Mountain/desert terrain checks

### ITU-R P.452

Use for:

- Interference and point-path studies
- Specialized microwave/regulatory-style analysis
- Optional future pycraf integration

## Antenna Specification Optimizer

The platform should recommend practical antenna specifications.

For each candidate site, evaluate combinations like:

- Tower height: 20 m, 25 m, 30 m, 35 m, 40 m, 50 m
- Sectors: 1, 2, 3, or 4 sectors
- Azimuths: demand-facing directions
- Mechanical downtilt: 0 to 8 degrees
- Electrical downtilt: 0 to 8 degrees
- Bands: B20, B8, B3, B1, and future NR bands if known
- Bandwidth: 5, 10, 15, 20 MHz or carrier aggregation sets
- Antenna gain: 15 to 18 dBi for macro panels
- Transmit power / EIRP

Example strategy:

```text
Urban high-capacity:
3 sectors
B3 + B1 + B20
30 to 40 m height
4 to 8 degree downtilt
capacity-focused

Suburban standard macro:
3 sectors
B3 + B20
30 to 45 m height
3 to 6 degree downtilt
coverage and capacity balance

Rural coverage macro:
1 to 3 sectors
B20 + B8
40 to 60 m height
0 to 4 degree downtilt
long-range coverage

Hotspot / small cell:
1 sector or omni
B3 / B1 / NR depending on spectrum
low height
high-demand POI area
capacity-focused
```

## Network ML Integration

If telecom companies provide internal KPI data, add a Network ML module.

Initial KPI fields:

- Cell ID
- Site ID
- Timestamp
- DL traffic
- UL traffic
- DL PRB utilization
- UL PRB utilization
- Connected users / RRC users
- DL throughput
- UL throughput
- Cell availability
- RRC setup success rate
- ERAB setup success rate
- Drop rate
- Handover success rate
- RSRP
- RSRQ
- SINR
- CQI
- Interference
- RAT
- Band
- EARFCN
- Latitude
- Longitude

Network ML should produce:

- 24-hour traffic forecast
- 24-hour PRB forecast
- Congestion prediction
- Anomaly detection
- Performance / QoE score
- Geographic congestion heatmap
- Suggested action

Suggested actions:

- Load balancing
- Mobility parameter optimization
- Downtilt or azimuth adjustment
- Carrier activation
- Add capacity to existing site
- Add sector
- Add small cell
- Build new macro site

Important:

The system should not always recommend a new tower. Sometimes the best answer is cheaper:

```text
Change tilt
Change azimuth
Activate another carrier
Improve backhaul
Rebalance traffic
Add a small cell
Add a sector
```

## Combined Architecture

```text
TELECOM AI PLATFORM

Data Layer:
  PostGIS
  Raster store
  H3 planning zones
  Site/cell database
  KPI database

GIS Feature Layer:
  Population
  Buildings
  Terrain
  Land cover
  Roads
  POIs
  Cloudflare
  Ookla
  Night lights

Network ML Layer:
  Traffic forecast
  PRB forecast
  Anomaly detection
  QoE score
  Congestion prediction

GIS ML Layer:
  Demand map
  Underserved map
  Expansion priority map
  Candidate area generation

RF Planning Layer:
  GRASS-RaPlaT coverage
  SPLAT! LOS/backhaul
  Path loss models
  Terrain profiles

Optimization Layer:
  Site selection
  Tower height
  Azimuth
  Downtilt
  Band selection
  Sector configuration

Product Layer:
  Web GIS dashboard
  Scenario comparison
  Planning reports
  Employee copilot
```

## Production Dashboard Features

The production app should include:

- Interactive Libya map
- Layer toggles
- Existing sites and cells
- Operator filters
- RAT filters
- Band filters
- H3 demand map
- H3 underserved map
- H3 expansion priority map
- Recommended candidate sites
- RF coverage overlays
- Terrain profile viewer
- Backhaul LOS viewer
- Scenario comparison
- Candidate site detail panel
- Export to CSV, GeoJSON, PDF, and engineering report

Candidate detail panel should show:

- Coordinates
- Municipality
- Nearest settlement
- Demand score
- Underserved score
- AI suitability
- RF score
- Final priority
- Population newly covered
- Existing nearest sites
- Overlap risk
- Road access
- Terrain elevation
- Recommended antenna specs
- Reason codes

## Employee Copilot

Later, add an internal employee copilot.

It should answer questions like:

```text
Which areas in Benghazi need expansion?
Why is this site recommended?
Which cells are predicted to be congested tomorrow?
Should we build a new site or add capacity to an existing site?
Show me candidate sites near Misrata with good road access and low overlap.
```

The copilot should use controlled APIs, not direct unrestricted database access.

It can combine:

- GIS scores
- RF results
- Network KPIs
- Forecasts
- Anomaly scores
- Planning documents
- SOPs

## Implementation Phases

### Phase 1: H3 Planning Grid

Goal:

Convert Libya into H3 planning zones and aggregate current features per zone.

Tasks:

- Choose H3 resolution.
- Assign existing sites to H3 cells.
- Aggregate population per H3.
- Aggregate road access per H3.
- Aggregate terrain features per H3.
- Calculate nearest site and site density per H3.

Outputs:

- H3 feature table
- H3 GeoJSON
- Initial demand and gap maps

### Phase 2: Add Better GIS Data

Goal:

Add the missing high-value public datasets.

Tasks:

- Add ESA WorldCover.
- Add Microsoft Building Footprints.
- Add OpenStreetMap POIs and land use.
- Test Ookla Open Data coverage for Libya.
- Optionally test VIIRS Night Lights.
- Optionally upgrade terrain with FABDEM.

Outputs:

- Enriched H3 feature table
- Land cover / clutter features
- Building and POI features

### Phase 3: Demand and Underserved Models

Goal:

Train or calculate explainable scores for demand and underserved areas.

Tasks:

- Build demand score.
- Build underserved score.
- Compare rule-based scoring vs LightGBM/XGBoost.
- Validate against known existing site distribution.
- Validate against Ookla/KPI data if available.

Outputs:

- Demand map
- Underserved map
- Expansion priority map

### Phase 4: Candidate Generation

Goal:

Generate candidate sites inside high-priority H3 zones.

Tasks:

- Sample candidate points near roads.
- Avoid water and unsuitable land cover.
- Prefer accessible terrain.
- Avoid excessive closeness to existing sites.
- Include candidate points around settlements, POIs, and road corridors.

Outputs:

- Candidate site list
- Candidate site GeoJSON

### Phase 5: RF Simulation With GRASS-RaPlaT

Goal:

Validate candidate sites with real RF planning models.

Tasks:

- Convert DEM and land cover to GRASS-compatible rasters.
- Create antenna configuration templates.
- Run coverage simulation per candidate and sector.
- Produce predicted signal raster.
- Aggregate sector/site coverage.
- Calculate newly covered population.
- Calculate overlap with existing coverage.

Outputs:

- Coverage rasters
- Coverage polygons
- RF score per candidate
- Population covered per candidate

### Phase 6: LOS and Backhaul Validation With SPLAT!

Goal:

Check whether candidate sites are practical for backhaul and terrain visibility.

Tasks:

- Generate terrain profiles to nearby existing sites, fiber routes, or hub candidates.
- Check line-of-sight.
- Check Fresnel clearance.
- Calculate terrain obstruction.
- Calculate HAAT.

Outputs:

- LOS result
- Backhaul feasibility score
- Terrain profile report

### Phase 7: Antenna Specification Optimizer

Goal:

Recommend practical antenna parameters.

Tasks:

- Test multiple tower heights.
- Test multiple azimuth sets.
- Test multiple downtilt values.
- Test bands and bandwidth options.
- Choose the configuration with best final score.

Outputs:

- Recommended tower height
- Recommended sectors
- Recommended azimuths
- Recommended downtilt
- Recommended bands
- Recommended bandwidth
- Recommended antenna gain / EIRP

### Phase 8: Production Storage and API

Goal:

Move from local files to production-style storage.

Tasks:

- Add PostGIS schema.
- Store H3 zones.
- Store sites, cells, sectors, candidates, and RF outputs.
- Build API endpoints for map and recommendation access.
- Add scenario IDs for planning experiments.

Outputs:

- Production geospatial database
- Planning API
- Scenario management

### Phase 9: Web GIS Dashboard

Goal:

Build the planner-facing product.

Tasks:

- Build map interface.
- Add layer controls.
- Add candidate detail panel.
- Add scenario comparison.
- Add report export.
- Add filters by operator, RAT, band, municipality, priority, and score.

Outputs:

- Telecom planning dashboard
- Interactive RF/GIS maps
- Exportable planning reports

### Phase 10: Network ML Integration

Goal:

Integrate real operator KPIs when available.

Tasks:

- Ingest historical KPI data.
- Forecast traffic and PRB.
- Detect anomalies.
- Calculate performance/QoE score.
- Feed persistent problem areas into GIS planning.

Outputs:

- Congestion forecast
- Anomaly map
- Performance heatmap
- Suggested planning action

## Example Final Recommendation Report

```text
Recommended Site: South Benghazi Growth Area

Coordinates:
32.xxxx, 20.xxxx

Reason:
High population and building density, weak nearby site density,
poor predicted service, good road access, and positive terrain prominence.

Recommended Configuration:
Tower height: 35 m
Sectors: 3
Azimuths: 40 / 160 / 280 degrees
Bands: B20 800 MHz + B3 1800 MHz
Bandwidth: 20 to 30 MHz
Downtilt: 4 degrees
Antenna gain: 17 dBi macro panel

RF Validation:
Good predicted B20 coverage
Acceptable B3 capacity footprint
Low terrain obstruction
Medium overlap with existing cells
Backhaul LOS available to nearest hub

Expected Benefit:
New population covered: 18,200
Coverage gap reduced: 7.4 km
Priority: Critical
```

## Business Value For Telecom Companies

The system should help operators:

- Reduce manual planning time
- Find underserved areas faster
- Prioritize investment objectively
- Avoid building unnecessary towers
- Improve CAPEX planning
- Compare new site vs capacity expansion
- Explain decisions to engineering and management
- Produce auditable planning reports
- Combine GIS, AI, RF, and network KPI data in one platform

## Final Product Positioning

Do not present the system as only:

```text
AI antenna placement model
```

Present it as:

```text
AI-assisted telecom GIS and RF planning platform for Libya.
It detects demand, identifies underserved areas, validates candidate sites
with RF physics, recommends antenna configurations, and generates
engineering-ready planning reports.
```

This positioning is stronger because telecom companies need explainable, auditable, RF-backed planning decisions, not only ML predictions.

