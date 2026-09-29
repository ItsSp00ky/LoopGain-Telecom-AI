"""Step 15: audit authorized operator assets without publishing sensitive rows."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
from pyproj import Geod
from shapely.geometry import Point

from antenna_cell_placement.config import OPENCELLID_RAW_PATH


SCHEMA = {
    "sites": ("site_id", "latitude", "longitude", "coordinate_accuracy_m", "surveyed_at_utc", "status"),
    "sectors": ("sector_id", "site_id", "antenna_id", "radio", "mcc", "mnc", "area", "cell",
                "frequency_mhz", "bandwidth_mhz", "azimuth_deg", "mechanical_tilt_deg",
                "electrical_tilt_deg", "height_m", "tx_power_dbm", "feeder_loss_db"),
    "antenna_catalog": ("antenna_id", "model", "gain_dbi", "pattern_reference"),
    "backhaul": ("link_id", "site_id", "endpoint_site_id", "endpoint_latitude",
                 "endpoint_longitude", "capacity_mbps", "status"),
}
REQUIRED_FILES = ("sites", "sectors")
PROVENANCE_FIELDS = (
    "sites.latitude", "sites.longitude", "sites.coordinate_accuracy_m", "sites.surveyed_at_utc",
    "sectors.radio", "sectors.frequency_mhz", "sectors.bandwidth_mhz", "sectors.azimuth_deg",
    "sectors.mechanical_tilt_deg", "sectors.electrical_tilt_deg", "sectors.height_m",
    "sectors.tx_power_dbm", "sectors.feeder_loss_db", "antenna_catalog.model",
    "antenna_catalog.gain_dbi", "antenna_catalog.pattern_reference",
)
RADIOS = {"GSM", "UMTS", "LTE", "NR", "CDMA"}
GEOD = Geod(ellps="WGS84")


def _filled(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    return frame[list(columns)].notna().all(axis=1) & frame[list(columns)].ne("").all(axis=1)


def _number(frame: pd.DataFrame, column: str, low: float, high: float) -> pd.Series:
    value = pd.to_numeric(frame[column], errors="coerce")
    return value.notna() & value.between(low, high)


def _read_table(directory: Path, name: str) -> pd.DataFrame:
    path = directory / f"{name}.csv"
    if not path.exists():
        if name in REQUIRED_FILES:
            raise FileNotFoundError(f"Required Step 15 input missing: {path}")
        return pd.DataFrame(columns=SCHEMA[name], dtype=str)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False).apply(lambda col: col.str.strip())
    missing = set(SCHEMA[name]) - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} lacks columns: {', '.join(sorted(missing))}")
    return frame


def _source_record(directory: Path, name: str) -> dict | None:
    path = directory / f"{name}.csv"
    if not path.exists():
        return None
    return {"file": path.name, "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest()}


def _observed_match(sectors: pd.DataFrame, observed_path: Path) -> dict:
    """Exact radio identity is supporting evidence, never mast confirmation."""
    from antenna_cell_placement.opencellid import load_cells

    identity = ("radio", "mcc", "mnc", "area", "cell")
    identified = sectors.loc[_filled(sectors, identity)].copy()
    if identified.empty:
        return {"identified_sectors": 0, "matched_sectors": 0, "match_rate_pct": None,
                "interpretation": "No complete radio identities supplied."}
    for column in identity[1:]:
        numeric = pd.to_numeric(identified[column], errors="coerce")
        identified = identified.loc[numeric.notna() & numeric.ge(0) & numeric.mod(1).eq(0)].copy()
        identified[column] = numeric.loc[identified.index].astype("int64")
    if identified.empty:
        return {"identified_sectors": 0, "matched_sectors": 0, "match_rate_pct": None,
                "interpretation": "No valid radio identities supplied."}
    observed, _, _ = load_cells(observed_path)
    eligible = observed.loc[observed.review_eligible].copy()
    known = set(zip(eligible.radio, eligible.mcc, eligible.net, eligible.area, eligible.cell))
    matches = sum(tuple(row) in known for row in identified[list(identity)].itertuples(index=False, name=None))
    return {"identified_sectors": len(identified), "matched_sectors": matches,
            "match_rate_pct": 100 * matches / len(identified),
            "interpretation": "Exact cell identity in review-eligible OpenCellID observations; no physical-site confirmation."}


def evaluate_operator_assets(directory: Path, *, output_path: Path | None = None,
                             observed_path: Path | None = OPENCELLID_RAW_PATH,
                             return_validated: bool = False) -> dict:
    """Validate an export in memory and write aggregate evidence only."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Operator asset directory missing: {directory}")
    source_manifest = directory / "source_manifest.json"
    if not source_manifest.exists():
        raise FileNotFoundError(f"Operator source manifest missing: {source_manifest}")
    source = json.loads(source_manifest.read_text())
    if not source.get("authorization_reference") or not source.get("snapshot_utc") or not source.get("source_organization"):
        raise ValueError("Source manifest needs authorization_reference, source_organization, and snapshot_utc")
    snapshot = pd.to_datetime(source["snapshot_utc"], utc=True, errors="coerce")
    if pd.isna(snapshot):
        raise ValueError("Invalid source snapshot_utc")
    if snapshot > pd.Timestamp.now(tz="UTC"):
        raise ValueError("Source snapshot_utc is in the future")
    field_sources = source.get("field_sources", {})
    if not isinstance(field_sources, dict):
        raise ValueError("field_sources must map field names to source references")
    provenance_count = sum(isinstance(field_sources.get(field), str) and
                           bool(field_sources[field].strip()) for field in PROVENANCE_FIELDS)
    tables = {name: _read_table(directory, name) for name in SCHEMA}
    sites, sectors, antennas, backhaul = (tables[name] for name in SCHEMA)
    if sites.empty or sectors.empty:
        raise ValueError("Step 15 requires at least one site and one sector")

    site_id_ok = _filled(sites, ("site_id",)) & ~sites.site_id.duplicated(keep=False)
    sector_id_ok = _filled(sectors, ("sector_id",)) & ~sectors.sector_id.duplicated(keep=False)
    antenna_id_ok = _filled(antennas, ("antenna_id",)) & ~antennas.antenna_id.duplicated(keep=False)
    location_ok = (_number(sites, "latitude", -90, 90) & _number(sites, "longitude", -180, 180)
                   & _number(sites, "coordinate_accuracy_m", 0, 100000))
    from antenna_cell_placement.opencellid import _libya_boundary
    boundary = _libya_boundary()
    inside_libya = pd.Series(False, index=sites.index)
    for index in sites.index[location_ok]:
        inside_libya.at[index] = boundary.covers(Point(float(sites.at[index, "longitude"]),
                                                      float(sites.at[index, "latitude"])))
    location_ok &= inside_libya
    date = pd.to_datetime(sites.surveyed_at_utc, utc=True, errors="coerce")
    date_ok = date.notna() & date.le(snapshot)
    site_age_days = (snapshot - date).dt.total_seconds() / 86400
    site_valid = site_id_ok & location_ok & date_ok & sites.status.isin(("active", "planned", "inactive"))
    site_lookup = set(sites.loc[site_valid, "site_id"])
    sector_numeric = {
        "frequency_mhz": (1, 100000), "bandwidth_mhz": (0.01, 10000),
        "azimuth_deg": (0, 360), "mechanical_tilt_deg": (-90, 90),
        "electrical_tilt_deg": (-90, 90), "height_m": (0.1, 1000),
        "tx_power_dbm": (-100, 100), "feeder_loss_db": (0, 100),
    }
    required_engineering = tuple(sector_numeric)
    engineering_complete = _filled(sectors, required_engineering)
    engineering_valid = pd.Series(True, index=sectors.index)
    for column, (low, high) in sector_numeric.items():
        engineering_valid &= sectors[column].eq("") | _number(sectors, column, low, high)
    sector_links_ok = sectors.site_id.isin(site_lookup)
    antenna_valid = (antenna_id_ok & _filled(antennas, ("model", "pattern_reference"))
                     & _number(antennas, "gain_dbi", -20, 60))
    valid_antennas = set(antennas.loc[antenna_valid, "antenna_id"])
    antenna_links_ok = sectors.antenna_id.eq("") | sectors.antenna_id.isin(valid_antennas)
    engineering_complete &= sectors.antenna_id.isin(valid_antennas)
    sector_valid = (sector_id_ok & sector_links_ok & antenna_links_ok & engineering_valid
                    & sectors.radio.isin(RADIOS))
    backhaul_valid = (_filled(backhaul, ("link_id", "site_id"))
                      & ~backhaul.link_id.duplicated(keep=False)
                      & backhaul.site_id.isin(site_lookup)
                      & (backhaul.endpoint_site_id.isin(site_lookup) |
                         (_number(backhaul, "endpoint_latitude", -90, 90)
                          & _number(backhaul, "endpoint_longitude", -180, 180)))
                      & _number(backhaul, "capacity_mbps", 0, 1000000)
                      & backhaul.status.isin(("active", "planned", "inactive")))

    # Optional independent surveyed coordinates provide a real accuracy check.
    checkpoints = directory / "survey_checkpoints.csv"
    location_error = {"count": 0, "median_m": None, "p90_m": None}
    if checkpoints.exists():
        checks = pd.read_csv(checkpoints, dtype=str, keep_default_na=False)
        need = {"site_id", "latitude", "longitude"}
        if not need.issubset(checks.columns):
            raise ValueError("survey_checkpoints.csv needs site_id, latitude, longitude")
        paired = sites.loc[site_valid].merge(checks, on="site_id", suffixes=("_asset", "_survey"))
        if not paired.empty:
            for column in ("latitude_asset", "longitude_asset", "latitude_survey", "longitude_survey"):
                paired[column] = pd.to_numeric(paired[column], errors="coerce")
            paired = paired.dropna(subset=("latitude_asset", "longitude_asset", "latitude_survey", "longitude_survey"))
            if not paired.empty:
                _, _, distance = GEOD.inv(paired.longitude_asset.to_numpy(), paired.latitude_asset.to_numpy(),
                                          paired.longitude_survey.to_numpy(), paired.latitude_survey.to_numpy())
                location_error = {"count": len(distance), "median_m": float(pd.Series(distance).median()),
                                  "p90_m": float(pd.Series(distance).quantile(0.9))}

    match = None
    if observed_path is not None:
        match = _observed_match(sectors.loc[sector_valid], Path(observed_path))
    metrics = {
        "sites": {"rows": len(sites), "valid_rows": int(site_valid.sum()),
                  "invalid_rows": int((~site_valid).sum()),
                  "outside_libya_rows": int((~inside_libya).sum()),
                  "coordinate_accuracy_declared_pct": 100 * int(sites.coordinate_accuracy_m.ne("").sum()) / len(sites),
                  "oldest_survey_age_days": float(site_age_days.loc[site_valid].max()) if site_valid.any() else None},
        "sectors": {"rows": len(sectors), "valid_rows": int(sector_valid.sum()),
                    "invalid_rows": int((~sector_valid).sum()),
                    "engineering_complete_pct": 100 * int((sector_valid & engineering_complete).sum()) / len(sectors),
                    "broken_site_links": int((~sector_links_ok).sum()),
                    "broken_antenna_links": int((~antenna_links_ok).sum())},
        "antenna_catalog": {"rows": len(antennas), "valid_rows": int(antenna_valid.sum())},
        "backhaul": {"rows": len(backhaul), "valid_rows": int(backhaul_valid.sum())},
        "survey_checkpoints": location_error,
        "observed_cell_match": match,
        "field_provenance": {"declared_fields": provenance_count,
                             "required_fields": len(PROVENANCE_FIELDS),
                             "completeness_pct": 100 * provenance_count / len(PROVENANCE_FIELDS)},
    }
    policy_path = directory / "quality_thresholds.json"
    checks = {}
    if policy_path.exists():
        policy = json.loads(policy_path.read_text())
        expected = {"minimum_valid_site_pct", "minimum_valid_sector_pct",
                    "minimum_engineering_complete_pct", "maximum_survey_median_error_m",
                    "minimum_observed_cell_match_pct", "maximum_site_age_days"}
        if set(policy) != expected or any(not isinstance(value, (int, float)) or isinstance(value, bool)
                                          or value < 0 for value in policy.values()):
            raise ValueError("quality_thresholds.json needs the five nonnegative numeric thresholds")
        if any(policy[key] > 100 for key in expected if key.endswith("_pct")):
            raise ValueError("Percentage thresholds must be at most 100")
        checks = {
            "valid_site_pct": 100 * int(site_valid.sum()) / len(sites) >= policy["minimum_valid_site_pct"],
            "valid_sector_pct": 100 * int(sector_valid.sum()) / len(sectors) >= policy["minimum_valid_sector_pct"],
            "engineering_complete_pct": metrics["sectors"]["engineering_complete_pct"] >= policy["minimum_engineering_complete_pct"],
            "survey_median_error_m": None if location_error["median_m"] is None else
                location_error["median_m"] <= policy["maximum_survey_median_error_m"],
            "observed_cell_match_pct": None if match is None or match["match_rate_pct"] is None else
                match["match_rate_pct"] >= policy["minimum_observed_cell_match_pct"],
            "site_freshness": None if metrics["sites"]["oldest_survey_age_days"] is None else
                metrics["sites"]["oldest_survey_age_days"] <= policy["maximum_site_age_days"],
        }
    report = {
        "step": 15, "status": "review",
        "decision": "Engineer review required before assets can enter RF simulation.",
        "source": {"source_organization": source["source_organization"],
                   "snapshot_utc": snapshot.isoformat(),
                   "authorization_reference_present": True,
                   "files": [record for name in (*SCHEMA, "survey_checkpoints")
                             if (record := _source_record(directory, name))]},
        "metrics": metrics, "thresholds": policy if policy_path.exists() else None,
        "checks": checks,
        "limitations": ["Input authorization and thresholds require operator/RF engineer review.",
                        "OpenCellID identity matches do not verify physical site coordinates.",
                        "No accepted asset rows are added to public planning outputs."],
    }
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if return_validated:
        # Only the explicit pilot command receives rows in memory. Never serialize
        # site coordinates or engineering settings into the aggregate report.
        valid = sectors.loc[sector_valid].copy()
        valid["engineering_complete"] = engineering_complete.loc[sector_valid].to_numpy()
        return report, valid
    return report
