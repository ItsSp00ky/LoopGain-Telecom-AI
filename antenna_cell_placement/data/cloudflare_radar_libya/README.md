# Cloudflare Radar — Libya Internet Traffic Dataset

This directory contains authentic, real-world internet traffic, regional infrastructure, autonomous system (ISP), and connectivity telemetry for **Libya (`LY`)** collected directly from [Cloudflare Radar](https://radar.cloudflare.com/traffic/ly) covering the **longest time horizon available on Cloudflare Radar: 52 weeks (1 full year)**, as well as 26 weeks, 12 weeks, 30 days, and 7 days.

The files are a source snapshot. Derived fields such as stability, growth, and the
composite scores are calculated from the collected Radar responses; they are not
independent ground-truth labels for cellular coverage.

---

## Directory & File Overview

| File Name | Records | Description |
|---|---|---|
| [`libya_best_places_features_dataset.csv`](libya_best_places_features_dataset.csv) | 22 places | Regional feature table used by this project as a bounded demand prior. |
| [`libya_regions_traffic_summary.csv`](libya_regions_traffic_summary.csv) | 22 places | Regional traffic breakdown across three metrics and five horizons. |
| [`libya_regions_timeseries.csv`](libya_regions_timeseries.csv) | 6,910 rows | Multi-horizon time series for Libyan regions. |
| [`libya_isps_and_asns.csv`](libya_isps_and_asns.csv) | 45 ASNs | Libyan autonomous systems ranked across five horizons. |
| [`libya_isps_timeseries.csv`](libya_isps_timeseries.csv) | 5,250 rows | Multi-horizon ISP traffic trends. |
| [`libya_national_traffic_timeseries.csv`](libya_national_traffic_timeseries.csv) | 1,050 rows | National NetFlow and normalized HTTP request trends. |
| [`libya_device_usage_timeseries.csv`](libya_device_usage_timeseries.csv) | 222 rows | Mobile, desktop, and other traffic distribution. |
| [`libya_human_vs_bot_timeseries.csv`](libya_human_vs_bot_timeseries.csv) | 221 rows | Human and automated traffic distribution. |
| [`libya_content_types_timeseries.csv`](libya_content_types_timeseries.csv) | 221 rows | MIME content-type distribution. |
| [`libya_api_traffic_timeseries.csv`](libya_api_traffic_timeseries.csv) | 221 rows | API and non-API traffic share. |
| [`libya_protocol_and_tech_breakdown.csv`](libya_protocol_and_tech_breakdown.csv) | 12 rows | HTTP/IP versions and device totals. |
| [`libya_bgp_routing_infrastructure.csv`](libya_bgp_routing_infrastructure.csv) | 63 rows | BGP, RPKI, prefix, and peer statistics. |
| [`libya_bgp_announced_ip_space_timeseries.csv`](libya_bgp_announced_ip_space_timeseries.csv) | 2,017 rows | Announced IPv4 and IPv6 address-space counts. |
| [`libya_internet_outages_and_anomalies.csv`](libya_internet_outages_and_anomalies.csv) | 1 row | Outage/anomaly summary over the 52-week window. |
| [`raw_cloudflare_radar_libya.json`](raw_cloudflare_radar_libya.json) | 2.5 MB | Raw collected responses used to derive the CSV files. |

---

## Regional feature guide

[`libya_best_places_features_dataset.csv`](libya_best_places_features_dataset.csv)
contains the regional inputs evaluated for placement prioritization:

- **`place_name`**: Administrative district / city name in Libya.
- **`geo_code`**: GeoNames administrative division code.
- **`latitude`**, **`longitude`**: Geographic coordinates.
- **`rank_annual_overall`**: 1-year annual ground truth traffic volume rank (1 = Tripoli, 2 = Benghazi, 3 = Misratah, 4 = Sabha, 5 = Az Zawiyah, etc.).
- **`ai_best_place_prediction_score`**: Composite index integrating multi-horizon volume, annual stability, and 1-year growth momentum.
- **`digital_connectivity_index`**: Weighted multi-metric connectivity score.
- **`annual_stability_score_52w`**: Macro stability over 52 weekly observations ($1 / (1 + \frac{\sigma_{52w}}{\mu_{52w}})$).
- **`hourly_stability_score_7d`**: Micro diurnal stability over 168 hourly observations.
- **`http_requests_share_52w_pct`**: 1-year annual average % of national HTTP requests.
- **`total_bytes_share_52w_pct`**: 1-year annual average % of national byte traffic.
- **`http_bytes_share_52w_pct`**: 1-year annual average % of national HTTP bytes.
- **`http_requests_share_26w_pct`**, **`http_requests_share_12w_pct`**, **`http_requests_share_30d_pct`**, **`http_requests_share_7d_pct`**: Multi-horizon traffic share evolution over time.
- **`annual_traffic_growth_52w_pct`**: Year-over-year digital traffic momentum ($((Share_{7d} - Share_{52w}) / Share_{52w}) \times 100$).
- **`short_term_traffic_growth_30d_pct`**: Month-over-month traffic momentum ($((Share_{7d} - Share_{30d}) / Share_{30d}) \times 100$).
- **`mean_annual_weekly_traffic_normalized`**: Mean weekly normalized traffic level over 52 weeks.
- **`std_annual_weekly_traffic_volatility`**: Standard deviation of weekly traffic across 1 year.
- **`peak_to_trough_ratio_7d`**: Ratio of daytime peak to night-time trough traffic.

---

## How this project uses the data

Only the 52-week regional HTTP request share affects placement ordering. It is
mapped to the project's 22 OCHA municipalities, percentile-scaled, and bounded to
a ±10% priority adjustment. National, protocol, BGP, and ISP-wide values do not
vary by candidate location and are retained for analysis rather than used as
spatial model features.

The suitability-model ablation and decision are recorded in
[`../../eval_reports/cloudflare_radar_assessment.json`](../../eval_reports/cloudflare_radar_assessment.json).
The collector used to create this snapshot is not included in this repository;
refreshes should preserve the same CSV schema and source attribution.
