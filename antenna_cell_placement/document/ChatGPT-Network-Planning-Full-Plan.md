# GIS / Network Planning

## 1. Objective

The goal of this module is to use **GIS, telecom network data, public geographic datasets, and machine learning** to identify areas that may require network expansion and then recommend suitable areas for new telecom sites.

The system will answer two main questions:

> **Which areas need additional network infrastructure?**

and then:

> **Where inside that area is a suitable location for a new site?**

The system will work in two stages:

```text
Stage 1
Find and rank areas that need expansion
        ↓
Stage 2
Analyze the best candidate locations inside those areas
```

---

# 2. Data We Will Use

| Data                          | Source                               | Why We Need It                                                       |
| ----------------------------- | ------------------------------------ | -------------------------------------------------------------------- |
| **Existing Cells / Sites**    | Our collected telecom dataset        | Understand the current network and existing infrastructure           |
| **Population**                | WorldPop                             | Identify where people live and estimate potential demand             |
| **Building Footprints**       | Microsoft Global Building Footprints | Measure building count, built-up area and urban density              |
| **Building Height / Density** | Microsoft Building Density & Height  | Understand vertical urban density and possible RF obstructions       |
| **Terrain**                   | FABDEM                               | Ground elevation, slope and relative height                          |
| **Land Cover**                | ESA WorldCover                       | Distinguish urban, desert, vegetation, water and other terrain types |
| **Roads / POIs / Land Use**   | OpenStreetMap                        | Understand accessibility and important activity areas                |
| **Internet Activity**         | Cloudflare Radar                     | Add a regional internet-activity / demand indicator                  |

WorldPop provides a Libya-specific 2026 population raster at approximately **100 m resolution**. Microsoft provides worldwide building footprints and a global building-density/height layer at approximately 100 m resolution.

FABDEM provides approximately **30 m global bare-earth elevation**, while ESA WorldCover provides land-cover information at approximately **10 m resolution**. OpenStreetMap also has a downloadable Libya extract containing current OSM data.

Cloudflare Radar provides traffic information grouped by first-level administrative regions, so we will use it mainly as a **regional demand indicator**, not as precise neighborhood-level traffic data.

---

# 3. Prepare the Existing Network Data

Our telecom dataset will be the primary network layer.

We should prepare fields such as:

```text
Site_ID
Cell_ID
Latitude
Longitude
Technology
Operator
Band
EARFCN
PCI
```

Cells belonging to the same physical site should be grouped where possible.

From this data we calculate features such as:

```text
Number of sites in the area
Number of cells
LTE cell count
5G cell count
Distance to nearest site
Distance to nearest LTE site
Distance to nearest 5G site
Site density
Cell density
```

The purpose is to understand how well an area is already served before recommending additional infrastructure.

---

# 4. Create the Geographic Analysis Grid

We will divide the study area into **H3 geographic hexagons**.

H3 does not represent telecom cells.

It is only a common geographic grid that allows us to combine all datasets.

For example:

```text
               H3 Area
                  │
       ┌──────────┼──────────┐
       │          │          │
 Population   Buildings   Network
       │          │          │
       └──────────┼──────────┘
                  │
               One Row
```

For an initial city-level analysis, **H3 resolution 9** is a reasonable starting point. Its average hexagon area is approximately **0.105 km²**, with an average edge length of around 200 m. Resolution 8 is larger at approximately **0.737 km²** and may be useful for broader national/regional screening.

We can test both and select the resolution that works best.

---

# 5. Population Features

WorldPop will be mapped to the H3 grid.

For each area we calculate:

```text
Total population
Population density
Population within 500 m
Population within 1 km
Population per existing site
```

Example:

```text
Area A

Population = 18,500
Sites nearby = 1

Population per site = 18,500
```

compared with:

```text
Area B

Population = 18,000
Sites nearby = 5

Population per site = 3,600
```

Area A would be much more interesting from a network-planning perspective.

---

# 6. Building Features

We combine:

```text
Microsoft Building Footprints
+
Microsoft Building Density & Height
```

Building footprints tell us **where buildings exist**.

Building height tells us more about the **vertical structure of the area**.

For each H3 area we derive:

```text
Building count
Building footprint area
Building density
Built-up ratio
Average building size
Average building height
Building height variation
```

This allows us to distinguish between areas such as:

```text
Dense apartment area
Low-rise residential area
Commercial area
Sparse suburb
Empty land
```

Building information contributes both to **demand estimation** and later to **radio/site-location analysis**.

---

# 7. Terrain Features

FABDEM will provide terrain elevation.

For every area or site candidate we calculate:

```text
Elevation
Average surrounding elevation
Maximum elevation
Minimum elevation
Slope
Terrain roughness
Relative elevation
```

Relative elevation is particularly useful.

Example:

```text
Candidate elevation = 78 m

Average surrounding elevation = 46 m

Relative elevation = +32 m
```

A candidate located higher than its surroundings may have better coverage potential, although actual RF performance still depends on antenna parameters, frequency, clutter and other factors.

---

# 8. Land-Cover Features

ESA WorldCover will identify the type of environment.

Examples include:

```text
Built-up
Bare / desert
Vegetation
Cropland
Trees
Water
```

For each H3 area we calculate percentages such as:

```text
Built-up % = 71%
Bare land % = 10%
Vegetation % = 14%
Water % = 0%
```

This allows the model to distinguish between urban and rural/desert environments.

It will also be useful later as an RF-clutter indicator.

---

# 9. OpenStreetMap Features

OpenStreetMap will provide roads, land use and important Points of Interest.

Examples:

```text
Major roads
Minor roads
Hospitals
Universities
Schools
Shopping areas
Commercial areas
Industrial areas
Government facilities
Airports
Stadiums
```

From this we generate features such as:

```text
Road density
Distance to nearest main road
POI density
Commercial POI count
Hospital count
University count
Commercial land-use %
Industrial land-use %
Residential land-use %
```

This is important because **population alone does not represent network demand**.

For example, a university or commercial district may have relatively few permanent residents but thousands of daytime users.

Road information is also important when evaluating whether a proposed site is reasonably accessible.

---

# 10. Cloudflare Regional Activity

Cloudflare Radar will provide another demand indicator.

Because it is regional rather than precise H3-level mobile traffic, we will use it as contextual information.

For example:

```text
Region
   ↓
Cloudflare Internet Activity
   ↓
Regional Demand Factor
```

It should **not** be treated as actual operator GB traffic.

If actual operator traffic becomes available later, it will replace or strongly improve this part of the model.

---

# 11. Final ML Feature Table

After combining all datasets, each H3 area becomes one row.

Example:

| Feature                      | Example |
| ---------------------------- | ------: |
| H3 ID                        |  893... |
| Population                   |  18,500 |
| Population Density           |    High |
| Sites within 1 km            |       1 |
| Cells within 1 km            |       3 |
| Distance to nearest site     |  1.3 km |
| LTE cells                    |       3 |
| 5G cells                     |       0 |
| Building count               |   1,520 |
| Building density             |    High |
| Average building height      |    11 m |
| Built-up percentage          |     73% |
| Elevation                    |    58 m |
| Relative elevation           |   +12 m |
| Slope                        |    2.1° |
| Road density                 |    High |
| Distance to major road       |    90 m |
| POIs                         |      76 |
| Commercial area              |  Medium |
| Cloudflare regional activity |    High |

This becomes the input to the ML/planning system.

---

# 12. Machine Learning – Area Analysis

We do not need to start with complicated AI.

## Unsupervised Learning

We can first use:

**K-Means**

to group areas with similar characteristics.

Possible groups could become:

```text
Dense urban / well served

Dense urban / poorly served

Growing suburban

Commercial / high activity

Low-density rural

High population / low network density
```

This will help us understand the structure of the network geographically.

---

# 13. K-Nearest Neighbors

KNN can be used mainly for **similar-area comparison**.

For example:

```text
New candidate area
        ↓
Find geographically / statistically
similar existing areas
        ↓
Compare infrastructure requirements
```

If an area has characteristics similar to areas that normally require three or four sites but currently has only one, that provides another indication of possible expansion need.

KNN should therefore be treated as a supporting method rather than the complete site-planning algorithm.

---

# 14. Network Expansion Need Score

The main GIS result will be a score for every geographic area.

Conceptually:

```text
Expansion Need
=
Population Demand
+
Building / Urban Demand
+
Activity Demand
+
Distance From Existing Network
+
Low Site Density
+
Land-Use Demand
```

All variables should first be normalized.

Example:

```text
Area A

Population Score       = 0.94
Building Score         = 0.88
Activity Score         = 0.82
Site Deficiency        = 0.91
Distance Score         = 0.86

Expansion Need Score   = 0.90
```

Areas can then be ranked:

```text
Area A    0.90
Area B    0.84
Area C    0.73
Area D    0.31
```

Initially this score can combine engineering rules and ML-derived features.

---

# 15. Supervised Learning

If we have historical information showing where operators previously added new sites, we can improve the system significantly.

For example:

```text
Area features
+
Historical expansion decision
        ↓
Random Forest / XGBoost
        ↓
Probability of expansion need
```

Possible models:

```text
Random Forest
XGBoost
LightGBM
```

The model could learn what geographic and network conditions historically resulted in new sites being deployed.

If we **do not have historical labels**, we should not pretend this is supervised prediction. In that case, Version 1 remains:

```text
Clustering
+
Engineering scoring
+
Area ranking
```

That is still a valid planning system.

---

# 16. Integration with Network ML

Later, the Network ML module will improve the GIS model.

Network ML can provide:

```text
Traffic trend
Congestion forecast
PRB forecast
Repeated anomalies
Performance degradation
```

Then Expansion Need becomes much stronger.

For example:

```text
Area A

Population              High
Building Density        High
Existing Sites          Low
Internet Activity       High

Network ML:
Traffic Growth          High
Predicted Congestion    94% PRB
Repeated Congestion     Yes

        ↓

Very High Expansion Priority
```

This is where the two modules connect.

---

# 17. Candidate-Area Ranking

After calculating the Expansion Need Score, we select the highest-priority areas.

Example:

```text
1. Area A → 0.94
2. Area B → 0.91
3. Area C → 0.86
4. Area D → 0.79
```

Only the highest-priority areas move to the detailed site-location stage.

This prevents us from running detailed RF/geographic calculations across the entire country unnecessarily.

---

# 18. Exact Candidate-Site Search

H3 is no longer enough at this stage.

Inside the selected area, we generate more precise candidate coordinates or candidate parcels/locations.

Each candidate can be evaluated using:

```text
Terrain elevation
Relative elevation
Slope
Nearby building height
Building density
Distance to main road
Distance to existing sites
Population around candidate
Land cover
Expected coverage area
Site accessibility
```

---

# 19. Candidate-Site Suitability Score

Each candidate receives another score.

Conceptually:

```text
Site Suitability
=
Elevation Advantage
+
Population Served
+
Demand Served
+
Road Accessibility
-
Terrain Difficulty
-
Building Obstruction
-
Excessive Existing-Site Overlap
```

Example:

| Candidate   |    Score |
| ----------- | -------: |
| Candidate 1 | **0.91** |
| Candidate 2 |     0.82 |
| Candidate 3 |     0.76 |
| Candidate 4 |     0.58 |

The highest-scoring locations become recommended **candidate locations**, not automatic final construction decisions.

---

# 20. RF Analysis

For the top candidate locations, we can perform more detailed RF analysis.

Using terrain, buildings and network configuration we can investigate:

```text
Terrain profile
Line of sight
Possible obstructions
Existing-site overlap
Approximate coverage
```

If operator information becomes available, we can also include:

```text
Frequency
Antenna height
Azimuth
Tilt
Transmit power
Technology
```

and use an appropriate propagation model.

This makes the final recommendation much more realistic.

---

# 21. Validation

We should validate the system in several ways.

### Geographic Validation

Select areas where we already know existing sites were necessary.

Remove or hide some existing sites and ask:

> Would the model identify these areas as having high expansion need?

If yes, that is a useful validation.

### Engineering Review

Network-planning engineers can review the highest-ranked areas and classify recommendations as:

```text
Good candidate
Possible candidate
Not suitable
```

### Model Evaluation

If labelled historical expansion data exists, standard supervised-learning metrics can be used.

Otherwise, validation should focus on:

```text
Cluster quality
Ranking stability
Sensitivity analysis
Known-site recovery
Expert assessment
```

---

# 22. Suggested Technology

```text
Python

Pandas
GeoPandas
Rasterio
Shapely

H3

Scikit-learn

XGBoost / LightGBM

PostgreSQL
PostGIS

QGIS for inspection

Frontend Map
MapLibre / Leaflet
```

A PostGIS database is useful because most of our analysis involves geographic queries such as:

```text
Sites within 1 km
Population around point
Buildings inside area
Distance to road
POIs around site
```

---

# 23. System Architecture

```text
                    DATA SOURCES
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
    NETWORK          POPULATION         GEOGRAPHY
      │                  │                  │
Our Cells            WorldPop             FABDEM
Our Sites                               WorldCover
                                           OSM
                                       Buildings
      │                  │                  │
      └──────────────────┼──────────────────┘
                         │
                   Cloudflare Radar
                         │
                         ▼
                  DATA PREPARATION
                         │
                         ▼
                       H3
                         │
                         ▼
                FEATURE ENGINEERING
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
        CLUSTERING             EXPANSION SCORE
        K-Means                  RF / XGBoost
             │                       │
             └───────────┬───────────┘
                         ▼
                  AREA RANKING
                         │
                         ▼
               HIGH-PRIORITY AREA
                         │
                         ▼
             CANDIDATE LOCATIONS
                         │
                         ▼
              TERRAIN + BUILDINGS
                  + ACCESSIBILITY
                         │
                         ▼
                 SITE RANKING
                         │
                         ▼
                   RF ANALYSIS
                         │
                         ▼
              RECOMMENDED CANDIDATES
```

---

# 24. Development Order

### Phase 1 – Data

Download and prepare:

```text
Our Telecom Data
WorldPop
Microsoft Buildings
Microsoft Building Height
FABDEM
ESA WorldCover
OpenStreetMap
Cloudflare Radar
```

### Phase 2 – GIS Integration

Create:

```text
PostGIS database
H3 grid
Spatial joins
Feature tables
```

### Phase 3 – Area Intelligence

Develop:

```text
K-Means clustering
KNN similarity analysis
Expansion Need Score
Area ranking
```

### Phase 4 – Site Planning

Develop:

```text
Candidate generation
Terrain analysis
Building analysis
Road accessibility
Site suitability ranking
```

### Phase 5 – Integration

Connect the system with:

```text
Network ML
Employee Copilot
Interactive GIS Map
```

---

# 25. Three-Week GIS Work Plan

| Week       | Work                                                                                                                                  |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Week 1** | Download datasets, clean telecom data, build PostGIS database, create H3 grid, and combine population/building/terrain/OSM layers.    |
| **Week 2** | Feature engineering, clustering, Expansion Need Score, candidate-area ranking, and initial GIS visualization.                         |
| **Week 3** | Candidate-site ranking, terrain/building analysis, integration with Network ML results, testing, validation, and final visualization. |

---

# 26. Team Responsibility

### Mahmoud Almabrouk

**Team Leader & GIS / Network Planning**

Main focus:

```text
GIS architecture
Feature/model design
Expansion Need Score
ML experiments
Candidate ranking
Evaluation
Integration
```

### Ahmed Gali

**GIS / Data Engineering**

Main focus:

```text
Dataset collection
GIS preprocessing
PostGIS
H3 preparation
Spatial joins
Building / terrain / OSM processing
Data pipelines
```

Both members will work together on the final model and GIS application.

---

# Final GIS Concept

The complete logic is:

```text
Where are people?
        ↓
Where are buildings and activities?
        ↓
What does the terrain look like?
        ↓
Where is the existing network?
        ↓
Which areas appear underserved?
        ↓
Rank expansion need
        ↓
Select high-priority areas
        ↓
Find suitable candidate locations
        ↓
Analyze terrain, buildings and access
        ↓
Combine later with Network ML
        ↓
Recommend candidate site locations
```

The main principle is:

> **Machine learning and GIS identify where expansion is needed, while geographic, engineering, and RF analysis determine which candidate location is most suitable.**
