"""Download the dated Geofabrik Libya snapshot used by Step 9."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pyogrio
from pyproj import CRS

from antenna_cell_placement.buildings import (
    LICENSE,
    LICENSE_URL,
    SNAPSHOT_DATE,
    SOURCE_URL,
    discover_building_layer,
)
from antenna_cell_placement.config import OSM_BUILDINGS_DIR, OSM_BUILDINGS_GPKG


ARCHIVE_NAME = "libya-260919-free.gpkg.zip"


def download_osm_buildings() -> dict:
    """Download, extract, validate, and record source provenance."""
    OSM_BUILDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with (OSM_BUILDINGS_DIR / ".download.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        return _download_locked()


def _download_locked() -> dict:
    archive = OSM_BUILDINGS_DIR / ARCHIVE_NAME
    headers = _download(SOURCE_URL, archive)
    _extract_geopackage(archive, OSM_BUILDINGS_GPKG)
    layer = discover_building_layer(OSM_BUILDINGS_GPKG)
    info = pyogrio.read_info(OSM_BUILDINGS_GPKG, layer=layer)
    if not CRS.from_user_input(info["crs"]).equals(
        CRS.from_epsg(4326), ignore_axis_order=True
    ):
        raise ValueError(f"Unexpected building CRS: {info['crs']}")
    records = [_file_record(archive), _file_record(OSM_BUILDINGS_GPKG)]
    manifest = {
        "dataset": "OpenStreetMap Libya building outlines via Geofabrik",
        "source_url": SOURCE_URL,
        "snapshot_date": SNAPSHOT_DATE,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": "OpenStreetMap contributors",
        "format_documentation": (
            "https://download.geofabrik.de/osm-data-in-gis-formats-free.pdf"
        ),
        "http": {
            "etag": headers.get("ETag", "").strip('"'),
            "last_modified": headers.get("Last-Modified"),
        },
        "building_layer": layer,
        "building_feature_count": int(info["features"]),
        "crs": str(info["crs"]),
        "files": records,
    }
    manifest_path = OSM_BUILDINGS_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Saved {manifest['building_feature_count']:,} OSM building outlines "
        f"and provenance to {manifest_path}"
    )
    return manifest


def _download(url: str, destination: Path) -> dict[str, str]:
    head = Request(url, method="HEAD")
    with urlopen(head, timeout=60) as response:
        expected_size = int(response.headers["Content-Length"])
        headers = dict(response.headers.items())
    if destination.exists() and destination.stat().st_size == expected_size:
        return headers
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "antenna-placement/0.1"})
    with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if temporary.stat().st_size != expected_size:
        raise ValueError(
            f"Incomplete download: expected {expected_size}, got {temporary.stat().st_size}"
        )
    temporary.replace(destination)
    return headers


def _extract_geopackage(archive: Path, destination: Path) -> None:
    with ZipFile(archive) as zipped:
        members = [name for name in zipped.namelist() if name.endswith(".gpkg")]
        if len(members) != 1:
            raise ValueError(f"Expected one GeoPackage in {archive}, found {members}")
        member = members[0]
        if destination.exists() and destination.stat().st_size == zipped.getinfo(member).file_size:
            return
        temporary = destination.with_suffix(destination.suffix + ".part")
        with zipped.open(member) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        temporary.replace(destination)


def _file_record(path: Path) -> dict[str, str | int]:
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    download_osm_buildings()
