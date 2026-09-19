# Almadar Aljadid catalogue and market facts

Almadar Aljadid (MCC-MNC 606-01) is the operator this module targets (decision 16).
This page explains the files in `data/almadar/` (ticket T16).
They were ported from Ali Marghem's `Ali_Branch` (see [ali_branch_merge.md](ali_branch_merge.md)).

| File | What it is | Who uses it |
|---|---|---|
| `source/` | The operator material as Ali collected it on 2026-09-18, unchanged: the package list (`internet_offers_data_v4.csv`), pay-as-you-go tariffs and the two emergency credit services, translated from Arabic. | Only as evidence for the two files below. |
| `offers.csv` | One row per package the operator sells: 57 packages in 17 families. | Retention offers (T11), the Almadar view of customers (T18), and the team's customer chatbot. |
| `market.toml` | Every other fact a calculation needs, each with a status and a source. | T11, T18 and T19. |

`src/prepaid_churn/almadar.py` loads both files and checks their rules; `tests/test_almadar.py` runs those checks.

## `offers.csv`

| Column | Meaning |
|---|---|
| `offer_id` | Stable ID, taken from `Ali_Branch` where it had one (for example `MO_20`). |
| `operator` | `Almadar Aljadid`. |
| `family_ar`, `family_en` | Package family, in Arabic as the operator names it and in English. |
| `name_ar`, `name_en` | Package name. |
| `price_lyd` | Price in LYD, as the operator states it. |
| `validity_ar`, `validity_hours` | Validity as the operator writes it, and in hours (one month is read as 30 days). |
| `data_gb` | Data volume in GB; empty when unlimited or unknown. |
| `data_unlimited` | 1 when the data volume is unlimited. |
| `volume_source` | Where the data volume comes from, see below. |
| `voice_minutes`, `voice_unlimited` | Voice minutes included; empty when none or unlimited. |
| `members` | Lines sharing a family package. |
| `max_download_mbps`, `max_upload_mbps` | Speed caps the operator states. |
| `network` | `5G` for 5G packages. |
| `valid_from_hour`, `valid_to_hour` | Time window of use, for example 6 to 11 for the morning pass. |
| `source_file`, `source_row`, `collected` | Where the row comes from (row number in the source file) and when it was collected. |
| `notes` | Anything a reader must know about the row. |

`volume_source` values:
- `stated`: the operator file states the volume (or that it is unlimited); 31 packages.
- `name`: read from the package name, for example "نت 20" is 20 GB and "نت 1/4" is 0.25 GB.
  17 packages; the operator file does not state these volumes, so confirm them before quoting a price per GB.
- `reported`: the file does not say, and `Ali_Branch` reports the package as unlimited; 6 packages (the Silver family, which the file only caps at 8 Mbps, and the two hourly 5G packages).
- `none`: nothing is known (the three Social packages).

`check_against_source` proves that every family, name, price and every value the operator states still matches the source file, and that every source row appears exactly once.

### Differences from `Ali_Branch`'s catalogue

`Ali_Branch` kept 37 packages in 12 families.
This catalogue has all 57 packages of the operator file, because the chatbot must show what is on sale.
The difference is the five Mix families (Diamond, Platinum, Bronze, Silver and Gold, 20 packages with data and voice), which Ali removed on 2026-09-18 without recording why.
If Mix is no longer sold, remove those rows; if it is, it is the richest data-and-voice family for offers.

## `market.toml`

Every table has a `status` and a `source`:

| Status | Meaning |
|---|---|
| `confirmed` | Stated in an operator document in `source/`, or a public fact. |
| `reported` | Stated by a teammate, with no document in the repo yet. |
| `assumption` | A team estimate; replace it with operator data or defend it in the report. |
| `estimate` | A number a calculation needs that nobody outside the operator knows. |

| Table | Status | Content |
|---|---|---|
| `operator` | confirmed | Almadar Aljadid, MCC 606, MNC 01; the competitor is Libyana. |
| `recharge_cards` | reported | 5, 10, 20, 40 and 100 LYD. |
| `payg` | confirmed | On-net voice 0.090 LYD for the first 3 minutes, then 0.050 per minute; 0.090 per minute to Libyana; 0.040 to landlines; SMS 0.050 (0.250 abroad); data 0.025 LYD per MB. |
| `airtime_advance` | confirmed | "رصيد في وقته": 1, 3 or 5 LYD when the balance is 0.5 LYD or less, recovered at the next recharge. |
| `data_advance` | confirmed | "نت في وقته": 2 GB for 3 days at 5 LYD, when the balance is 1 LYD or less and less than 250 MB is left. |
| `arpu` | assumption | 40 LYD per month, set just above the base monthly bundle (Net 20 at 35 LYD). |
| `delivery_cost` | estimate | 25% of the price for metered data, 35% for unlimited. No margin built on it may be presented as audited. |

## Known gaps

- The source files have no links; ask Ali where each came from (website page, app screenshot or shop), then add it to `source` values.
- The recharge cards are `reported` until an operator document backs them.
- ARPU and delivery costs are not operator data.

## Refreshing the files

Prices change, so every row keeps its collection date.
To refresh: save the operator's new material in `source/` (keep the old file if rows still cite it), edit `offers.csv` and `market.toml` by hand, update `collected`, and run `uv run pytest tests/test_almadar.py`.
The tests fail on any row that no longer matches its source.

Libyana can be added later as rows with `operator` set to `Libyana`, after adding it to `OPERATORS` in `almadar.py`.
