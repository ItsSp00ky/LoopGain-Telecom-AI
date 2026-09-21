"""Download four official Ookla mobile quarters and create the Libya subset."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd

from antenna_cell_placement.config import (
    ADMIN0_GEOJSON_PATH,
    OOKLA_DIR,
    OOKLA_MANIFEST,
    OOKLA_TILES_GPKG,
)


LICENSE = "CC-BY-NC-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
DOCUMENTATION_URL = "https://github.com/teamookla/ookla-open-data"
ATTRIBUTION = (
    "Speedtest by Ookla Global Fixed and Mobile Network Performance Maps, "
    "accessed 21 September 2026 from AWS; based on project analysis for "
    "2025 Q2 through 2026 Q1. Ookla trademarks used under license."
)
PERIODS = (
    ("2025Q2", "2025-04-01", 2025, 2),
    ("2025Q3", "2025-07-01", 2025, 3),
    ("2025Q4", "2025-10-01", 2025, 4),
    ("2026Q1", "2026-01-01", 2026, 1),
)


def source_url(date: str, year: int, quarter: int) -> str:
    filename = f"{date}_performance_mobile_tiles.zip"
    return (
        "https://ookla-open-data.s3.amazonaws.com/shapefiles/performance/"
        f"type=mobile/year={year}/quarter={quarter}/{filename}"
    )


def download_ookla_mobile() -> dict[str, object]:
    """Download, spatially subset, validate, and record source provenance."""
    OOKLA_DIR.mkdir(parents=True, exist_ok=True)
    with (OOKLA_DIR / ".download.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        return _download_locked()


def _download_locked() -> dict[str, object]:
    records = []
    subsets = []
    boundary = gpd.read_file(ADMIN0_GEOJSON_PATH).to_crs("EPSG:4326")
    boundary_geometry = boundary.geometry.union_all()

    def fetch(period_spec):
        period, date, year, quarter = period_spec
        url = source_url(date, year, quarter)
        archive = OOKLA_DIR / f"{date}_performance_mobile_tiles.zip"
        headers = _download(url, archive)
        return period, date, url, archive, headers

    with ThreadPoolExecutor(max_workers=len(PERIODS)) as executor:
        downloads = list(executor.map(fetch, PERIODS))
    for period, date, url, archive, headers in downloads:
        subset = _read_libya_subset(archive, boundary_geometry)
        subset["quarter"] = period
        subset["quarter_start"] = date
        subsets.append(subset)
        records.append(
            {
                **_file_record(archive),
                "url": url,
                "period": period,
                "last_modified": headers.get("Last-Modified"),
                "etag": headers.get("ETag", "").strip('"'),
                "libya_rows": len(subset),
            }
        )
    combined = gpd.GeoDataFrame(
        pd.concat(subsets, ignore_index=True), geometry="geometry", crs="EPSG:4326"
    )
    combined.to_file(OOKLA_TILES_GPKG, layer="mobile_performance", driver="GPKG")
    subset_record = _file_record(OOKLA_TILES_GPKG)
    manifest = {
        "dataset": "Speedtest by Ookla Global Mobile Network Performance Map Tiles",
        "service_type": "mobile",
        "periods": [period for period, *_ in PERIODS],
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "documentation_url": DOCUMENTATION_URL,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": ATTRIBUTION,
        "source_files": records,
        "libya_subset": {
            **subset_record,
            "rows": len(combined),
            "crs": "EPSG:4326",
        },
        "schema": {
            "avg_d_kbps": "average download speed in kilobits per second",
            "avg_u_kbps": "average upload speed in kilobits per second",
            "avg_lat_ms": "average latency in milliseconds",
            "tests": "tests contributing to the tile-quarter",
            "devices": "unique devices within the tile-quarter only",
            "quadkey": "zoom-level 16 tile identifier",
        },
        "aggregation_warning": (
            "Device counts are not unique across tiles or quarters and must not be "
            "summed as people or national unique devices."
        ),
    }
    OOKLA_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(combined):,} Libya tile-quarter rows to {OOKLA_TILES_GPKG}")
    return manifest


def _read_libya_subset(archive: Path, boundary_geometry) -> gpd.GeoDataFrame:
    with ZipFile(archive) as zipped:
        shapefiles = [name for name in zipped.namelist() if name.endswith(".shp")]
    if len(shapefiles) != 1:
        raise ValueError(f"Expected one shapefile in {archive}, found {shapefiles}")
    frame = gpd.read_file(
        f"zip://{archive}!{shapefiles[0]}", bbox=boundary_geometry.bounds
    ).to_crs("EPSG:4326")
    representative_points = (
        frame.to_crs("EPSG:3857").geometry.centroid.to_crs("EPSG:4326")
    )
    return frame.loc[representative_points.within(boundary_geometry)].copy().reset_index(drop=True)


def _download(url: str, destination: Path) -> dict[str, str]:
    head = Request(url, method="HEAD")
    with urlopen(head, timeout=60) as response:
        expected_size = int(response.headers["Content-Length"])
        headers = dict(response.headers.items())
    if destination.exists() and destination.stat().st_size == expected_size:
        return headers
    temporary = destination.with_suffix(destination.suffix + ".part")
    if destination.exists() and not temporary.exists():
        destination.replace(temporary)
    downloaded = temporary.stat().st_size if temporary.exists() else 0
    request_headers = {"User-Agent": "antenna-placement/0.1"}
    if downloaded:
        request_headers["Range"] = f"bytes={downloaded}-"
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=180) as response:
        append = downloaded > 0 and response.status == 206
        mode = "ab" if append else "wb"
        with temporary.open(mode) as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if temporary.stat().st_size != expected_size:
        raise ValueError(
            f"Incomplete download: expected {expected_size}, got {temporary.stat().st_size}"
        )
    temporary.replace(destination)
    return headers


def _file_record(path: Path) -> dict[str, str | int]:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


if __name__ == "__main__":
    download_ookla_mobile()
