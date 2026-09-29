# Measured service and pilot review

Eligible phone measurements: **4,874**. Operator/technology/area groups: **209**.

Training days: 2026-09-23, 2026-09-24. Held-out days: 2026-09-26, 2026-09-28. Snapshot version: 2.

## Location reconciliation

6 conflicting identities; 0 provisional preferences; 0 resolved by independent survey.

| Network / radio / area / site | Separation | Decision |
| --- | ---: | --- |
| 606/0 / LTE / 1610 / 1169 | 5.80 km | unresolved |
| 606/0 / LTE / 2120 / 1130 | 634.87 km | unresolved |
| 606/0 / LTE / 6390 / 1138 | 3.31 km | unresolved |
| 606/0 / LTE / 6390 / 1196 | 1.09 km | unresolved |
| 606/0 / LTE / 6410 / 2003 | 844.58 km | unresolved |
| 606/1 / GSM / 1114 / 1649 | 1.10 km | unresolved |

All alternatives and their timestamps, verification flags, and source paths are in `pilot_review.json`. Obtain surveyed or operator-provided coordinates to resolve these conflicts.

## Pilot area

Status: **measured_review_only**.
H3 area: `87384b2d0ffffff`; center: 32.874826, 13.334322.
Training: 375 samples across 19 spatial bins and 2 days. Held-out samples: 313.
Nearby matching-network/technology source-verified, nonconflicting references: 0 (within 5 km of area center).
Pilot-only temporal validation: evaluated; matched blocks: 26.

## Held-out measurement baseline

Status: evaluated. Matched 74 of 258 blocks (28.68%).
Mean absolute error: 7.675675675675675 dB; bias: -1.7432432432432432 dB. These describe a historical measured-area median baseline, not an RF simulation or a pass against an engineering acceptance threshold.

| Held-out day | Matched blocks | Coverage | MAE (dB) |
| --- | ---: | ---: | ---: |
| 2026-09-26 | 26/55 | 47.27% | 8.423076923076923 |
| 2026-09-28 | 48/203 | 23.65% | 7.270833333333333 |

## RF input readiness

Status: **not_ready**. Complete engineering sectors: 0. Exact measured cell/sector identity matches: 0.
Fields absent from all supplied sectors: frequency_mhz, mechanical_tilt_deg, electrical_tilt_deg, height_m, tx_power_dbm, feeder_loss_db, gain_dbi, pattern_reference.

## Operator asset comparison

No authorized operator export selected.

The pilot-specific identity and field request is in `pilot_data_request.json`.

Next field work: revisit the pilot on additional days; collect comparable observations for both operators; export sector identities and engineering parameters; independently survey the conflicting locations. Keep the held-out day separate from any calibration.

## Limitations

- Measurements describe the collected routes, days, devices, and networks only.
- Service summaries separate operators and technologies; generic dBm is not RSRP.
- The held-out-day median baseline measures temporal repeatability, not RF prediction accuracy.
- Pilot selection never uses held-out signal values or held-out sample support.
- Conflicted locations remain conservative screening references, not reliable pilot anchors.
- No measured-area summary changes national placement scores.
