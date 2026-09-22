# Datasets Used — Antenna Cell Placement Project

This document lists every dataset used in the project, split into what already powers the current nationwide model and what is being added for the new Tripoli pilot (H3 expansion-need analysis).

---

## 1. Already in use (nationwide pipeline)

| Dataset | Source | Resolution / Scale | What it's used for |
|---|---|---|---|
| **Telecom cell/site data** | Crowdsourced telemetry (proprietary, `cells.sqlite3`/`cells.json`) + OpenCellID | Point-level | Core network layer: 2,338 deduplicated radio antennas collapsed into 2,115 physical mast sites (via 50m collocation clustering). Ground truth for "where the network already exists." |
| **WorldPop 2020 Population Density** | WorldPop (UN-adjusted gridded population) | 1 km resolution | Estimates population density/sum around each site or candidate location — the core demand signal. |
| **SRTM Digital Elevation Model (DEM)** | NASA/USGS SRTM | 250 m resolution | Elevation, slope, and 3km viewshed prominence — used to judge coverage potential of a location. |
| **UN OCHA Transportation Network** | UN OCHA Libya | 4,141 road segments | Road accessibility: distance to nearest road, access tier. |
| **UN OCHA Populated Places & Admin Boundaries** | UN OCHA Libya | Vector (points/polygons), all 22 municipalities | Distance to nearest settlement, municipality/region assignment. |
| **Cloudflare Radar (Libya)** | Cloudflare Radar API | Regional (22 municipalities), 52-week window | Regional internet-activity indicator, used only as a bounded (±10%) ranking prior — deliberately excluded from the trained ML model after leakage testing. |

**Result on this data:** LightGBM suitability classifier (0.9862 ROC-AUC) + Random Forest equipment-tier recommender, evaluated 22,605 candidate locations nationwide, ranked a Top-50 priority list.

---

## 2. New datasets added for the Tripoli pilot (Phase 1 + Phase 2 GIS expansion analysis)

| Dataset | Source | Resolution / Scale | What it adds |
|---|---|---|---|
| **Microsoft Global ML Building Footprints** | Microsoft Bing Maps AI (`GlobalMLBuildingFootprints`) | Building-level vector polygons, Tripoli-area tiles (~88 MB) | Building count, density, footprint area, built-up ratio per area — a proxy for urban density that population data alone doesn't capture. |
| **ESA WorldCover 2021 (v200)** | European Space Agency | 10 m resolution raster, 2 tiles covering Tripoli (~43 MB) | Land-cover classification (built-up, bare/desert, cropland, vegetation, water, tree cover) — distinguishes urban vs. rural/desert environment and acts as an RF-clutter indicator. |
| **OpenStreetMap (Libya extract)** | Geofabrik | Vector (roads, POIs, land use), full country (~77 MB) | Road density, distance to main roads, POI density (hospitals, universities, schools, commercial/industrial zones) — captures "daytime demand" that residential population doesn't show. |

**Why a pilot city:** these three datasets are being validated on Tripoli first before deciding whether to scale nationwide — building footprints and OSM are heavier to process at country scale, so Tripoli is used to prove the approach.

---

## 3. What the new data enables

Combining the existing pipeline (population, elevation, roads, existing-site density) with these three new datasets, tiled onto an **H3 hexagon grid**, produces a new **Expansion Need Score** per hexagon — flagging *which areas* of Tripoli most need a new site, before the existing point-by-point suitability model decides the *exact* best location within that area. This is a new area-level screening stage sitting in front of the existing site-level model, not a replacement for it.

---

## 4. Column-level detail (per dataset)

### 4.1 Telecom cell/site data
`data/cleaned/cleaned_physical_sites.csv` (2,115 rows):
```
physical_site_id, canonical_latitude, canonical_longitude, radio_tower_count,
technologies, rat_subtypes, has_gsm, has_umts, has_lte, tech_count, max_generation,
operators, has_libyana, has_almadar, operator_count, is_multi_operator, is_multi_tech,
total_bandwidth_mhz, total_carrier_count, bands_deployed, band_count, primary_tower_type,
is_visible, first_seen_ms, last_seen_ms, has_timing_advance, has_signal_strength
```
`data/cleaned/opencellid_cells.csv` (supplementary, 1,406 rows):
```
radio, mcc, net, area, cell, unit, lon, lat, range, samples, changeable, created,
updated, averageSignal, created_utc, updated_utc, timestamp_valid, age_days,
review_eligible, operator, source, nearest_existing_site_m
```

### 4.2 WorldPop 2020 Population Density
`data/external/lby_pd_2020_1km.tif` — single-band raster (no tabular columns); each pixel = estimated population count per ~1km² cell. Read via `rasterio`, values sampled at each site/candidate location.

### 4.3 SRTM Digital Elevation Model (DEM)
`data/external/dem/DEM/lyb_strm_250m` — single-band raster; each pixel = elevation in meters. Used to derive elevation, 3km prominence, and local slope.

### 4.4 UN OCHA Transportation Network
`data/external/roads/LYB_Roads.shp` (4,141 road segments):
```
NAME, ALT1_NAME, ETYPE, Road_Type, Shape_Leng, geometry
```

### 4.5 UN OCHA Admin Boundaries & Populated Places
`lby_admin1.geojson` (3 regions) / `lby_admin2.geojson` (22 municipalities):
```
adm1_name / adm2_name, adm*_name1-3 (alt. names), adm*_pcode, adm1_name (parent, admin2 only),
adm0_name, valid_on, valid_to, area_sqkm, version, lang, lang1-3,
adm*_ref_name, center_lat, center_lon, geometry
```
`lby_populatedplaces.geojson` (78 settlements):
```
featurename_en, featurename_ar, pcode, featurerefname, featurealtname1-2_en/ar,
popplaceclassnumber, popplaceclasstitle, adm2_en/ar/pcode, adm1_en/ar/pcode,
adm0_en/ar/pcode, date, validon, validto, version, geometry
```

### 4.6 Cloudflare Radar (Libya)
`data/cloudflare_radar_libya/libya_best_places_features_dataset.csv` (22 municipalities):
```
place_name, geo_code, latitude, longitude, rank_annual_overall,
ai_best_place_prediction_score, digital_connectivity_index, annual_stability_score_52w,
hourly_stability_score_7d, http_requests_share_52w_pct, total_bytes_share_52w_pct,
http_bytes_share_52w_pct, http_requests_share_26w_pct, http_requests_share_12w_pct,
http_requests_share_30d_pct, http_requests_share_7d_pct, total_bytes_share_7d_pct,
http_bytes_share_7d_pct, annual_traffic_growth_52w_pct, short_term_traffic_growth_30d_pct,
mean_annual_weekly_traffic_normalized, std_annual_weekly_traffic_volatility,
mean_hourly_traffic_normalized, peak_to_trough_ratio_7d
```

### 4.7 Microsoft Global ML Building Footprints (new — Tripoli pilot)
`data/external/buildings/libya_*.csv.gz` — GeoJSON-Lines format (one JSON feature per line), not flat CSV columns:
```
type, properties.height, properties.confidence, geometry.type, geometry.coordinates
```
Note: `height` and `confidence` are `-1.0` (unavailable) for Libya in this release — Microsoft's height data has sparse global coverage. We'll derive building count, footprint area, and density from the polygon geometry itself, not from these two fields.

### 4.8 ESA WorldCover 2021 (new — Tripoli pilot)
`data/external/landcover/ESA_WorldCover_10m_2021_v200_*.tif` — single-band categorical raster; each pixel holds a land-cover class code:
```
10 Tree cover · 20 Shrubland · 30 Grassland · 40 Cropland · 50 Built-up
60 Bare/sparse vegetation · 70 Snow/ice · 80 Water · 90 Herbaceous wetland
95 Mangroves · 100 Moss/lichen
```
We compute the % of each class per H3 hexagon (`rasterstats.zonal_stats`).

### 4.9 OpenStreetMap Libya extract (new — Tripoli pilot)
`data/external/osm/libya-latest.osm.pbf` — not tabular; a binary OSM file containing tagged geometries, read via `pyrosm`. Two layers get extracted:
- **Roads** (`get_network()`): geometry + `highway` tag (motorway/primary/secondary/residential/…), used for road density and distance-to-road.
- **POIs** (`get_pois()`): geometry + tags such as `amenity` (hospital, school, university, marketplace), `shop`, `office`, `landuse` — used for POI density and land-use-mix features.
