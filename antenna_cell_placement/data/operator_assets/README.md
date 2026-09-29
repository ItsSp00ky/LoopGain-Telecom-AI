# Authorized operator asset review

Put an authorized export in a directory such as `data/operator_assets/my_export/`. Export directories and their aggregate reports are ignored by Git. The header-only files in `templates/` describe the expected fields; unknown values stay blank.

Required files are `sites.csv`, `sectors.csv` and `source_manifest.json`. The antenna catalog, backhaul table, independent survey checkpoints and engineering quality thresholds provide additional checks. Coordinates use WGS84; column names state measurement units.

The source manifest must declare:

```json
{
  "source_organization": "Name of the authorized source",
  "authorization_reference": "Actual authorization reference",
  "snapshot_utc": "2026-09-29T00:00:00Z",
  "field_sources": {
    "sites.latitude": "Actual source or survey reference",
    "sites.longitude": "Actual source or survey reference"
  }
}
```

These are schema examples, not evidence of authorization or a survey. Populate them from the supplied export and its documented provenance.

Run from the module directory:

```powershell
uv run python tools/audit_operator_assets.py data/operator_assets/my_export
```

The tool writes aggregate counts and hashes to `audit.json` inside the ignored private export folder. It does not publish operator rows, modify the planning inventory, or enable RF simulation. Review authorization, provenance and engineering thresholds before using the export.

The current pilot request is `integrated_release_v3/measurements/pilot_data_request.json`. It identifies the training-area cell identities and missing fields. The programmatic `pilot._pilot_asset_review` helper can compare an authorized export with those identities; there is no public asset-to-planning promotion command.
