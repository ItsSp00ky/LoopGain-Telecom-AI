# Step 15 operator asset export

Place an authorized export in a directory under `data/operator_assets/`. The directory is ignored by Git. Copy the header-only CSV files from `templates/` and fill them from authoritative operator systems. Keep the original export and its access restrictions outside the public repository.

Required files: `sites.csv`, `sectors.csv`, and `source_manifest.json`. `antenna_catalog.csv`, `backhaul.csv`, and `survey_checkpoints.csv` are optional but needed for their respective quality checks. All coordinates use WGS84 decimal degrees; heights, losses, gains, power, and frequencies use the units in the headers. Use blank cells for unknown values. Never infer bands, power, antenna settings, or backhaul from nearby observations.

`source_manifest.json` example:

```json
{
  "source_organization": "authorized operator name",
  "authorization_reference": "internal access or release reference",
  "snapshot_utc": "2026-09-22T00:00:00Z",
  "field_sources": {
    "sites.latitude": "survey database, coordinate field",
    "sectors.azimuth_deg": "radio configuration database, azimuth field"
  }
}
```

Add a `field_sources` entry for each engineering and location field. The validator reports declaration coverage without publishing source references. Undeclared provenance remains visible for engineer review.

For `sectors.csv`, `radio`, `mcc`, `mnc`, `area`, and `cell` are the optional OpenCellID identity tuple. `area` means LAC/TAC as appropriate for the radio technology; `cell` means cell identity, not a physical site ID. The identity comparison is evidence for manual review, not a mast match.

If RF engineers agree on quantitative gates, add `quality_thresholds.json` with six numeric fields: `minimum_valid_site_pct`, `minimum_valid_sector_pct`, `minimum_engineering_complete_pct`, `maximum_survey_median_error_m`, `minimum_observed_cell_match_pct`, and `maximum_site_age_days`. No defaults are applied. The report shows `null` for checks that lack survey or observed-cell evidence.

Run:

```bash
uv run antenna-placement operator-assets-evaluate --directory data/operator_assets/my_export
```

The command checks source metadata, file hashes, row IDs, coordinates, dates, field ranges, foreign keys, and aggregate quality. It writes only an aggregate report to `eval_reports/step_15_operator_assets_evaluation.json`. The report is also ignored by Git until the operator reviews it for disclosure. The status remains `review` until an RF engineer accepts the export and thresholds. This stage does not feed operator assets into recommendations or maps.

For the measured pilot, consult `eval_reports/pilot_data_request.json` for the exact training-area cell identities and missing engineering fields. Run `uv run antenna-placement pilot-review --assets data/operator_assets/my_export` to compare the valid export with those identities. The comparison report is written under ignored `eval_reports/private_pilot_review/`; it contains counts and hashes only. Sector settings and site coordinates remain in the private export. Preserve the frozen holdout and create a new pilot snapshot when input files or evaluation dates change.
