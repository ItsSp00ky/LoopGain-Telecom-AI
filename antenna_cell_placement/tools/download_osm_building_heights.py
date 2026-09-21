"""Download and record the dated raw OSM source used by Step 10."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import shutil
from urllib.request import Request, urlopen

import pyogrio

from antenna_cell_placement.building_heights import HEIGHT_SOURCE_URL, OSM_LAYER
from antenna_cell_placement.buildings import LICENSE, LICENSE_URL, SNAPSHOT_DATE
from antenna_cell_placement.config import (
    OSM_BUILDINGS_DIR,
    OSM_BUILDINGS_GPKG,
    OSM_HEIGHT_MANIFEST,
    OSM_HEIGHT_PBF,
)


def download_osm_building_heights() -> dict[str, object]:
    """Download, validate, and record the raw source without deriving heights."""
    OSM_BUILDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with (OSM_BUILDINGS_DIR / ".height-download.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        headers = _download(HEIGHT_SOURCE_URL)
        layers = {name for name, _ in pyogrio.list_layers(OSM_HEIGHT_PBF)}
        if OSM_LAYER not in layers:
            raise ValueError(f"Missing expected OSM layer {OSM_LAYER}: {sorted(layers)}")
        building_info = pyogrio.read_info(
            OSM_BUILDINGS_GPKG, layer="gis_osm_buildings_a_free"
        )
        manifest = {
            "dataset": "Explicit OpenStreetMap building height tags via Geofabrik",
            "source_url": HEIGHT_SOURCE_URL,
            "snapshot_date": SNAPSHOT_DATE,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "attribution": "OpenStreetMap contributors",
            "tag_documentation": "https://wiki.openstreetmap.org/wiki/Key:height",
            "http": {
                "etag": headers.get("ETag", "").strip('"'),
                "last_modified": headers.get("Last-Modified"),
            },
            "osm_layer": OSM_LAYER,
            "reference_building_feature_count": int(building_info["features"]),
            "file": {
                "filename": OSM_HEIGHT_PBF.name,
                "bytes": OSM_HEIGHT_PBF.stat().st_size,
                "sha256": _file_sha256(OSM_HEIGHT_PBF),
            },
            "policy": {
                "accepted": "explicit height tags",
                "profile_only": "building:levels tags",
                "prohibited": [
                    "floor-count-to-height conversion",
                    "machine-learned height",
                    "remotely inferred height",
                ],
            },
        }
        OSM_HEIGHT_MANIFEST.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Saved Step 10 provenance to {OSM_HEIGHT_MANIFEST}")
        return manifest


def _download(url: str) -> dict[str, str]:
    head = Request(url, method="HEAD")
    with urlopen(head, timeout=60) as response:
        expected_size = int(response.headers["Content-Length"])
        headers = dict(response.headers.items())
    if OSM_HEIGHT_PBF.exists() and OSM_HEIGHT_PBF.stat().st_size == expected_size:
        return headers
    temporary = OSM_HEIGHT_PBF.with_suffix(OSM_HEIGHT_PBF.suffix + ".part")
    request = Request(url, headers={"User-Agent": "antenna-placement/0.1"})
    with urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if temporary.stat().st_size != expected_size:
        raise ValueError(
            f"Incomplete download: expected {expected_size}, got {temporary.stat().st_size}"
        )
    temporary.replace(OSM_HEIGHT_PBF)
    return headers


def _file_sha256(path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    download_osm_building_heights()
