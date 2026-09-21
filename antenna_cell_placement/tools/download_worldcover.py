"""Download the official ESA WorldCover 2021 tiles intersecting Libya."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

import geopandas as gpd
import rasterio
from shapely.geometry import box

from antenna_cell_placement.config import ADMIN0_GEOJSON_PATH, WORLDCOVER_DIR
from antenna_cell_placement.worldcover import (
    CLASS_LEGEND,
    WORLDCOVER_BASE_URL,
    WORLDCOVER_DOI,
    WORLDCOVER_LICENSE,
    WORLDCOVER_VERSION,
    tile_name,
)


def tile_names_for_boundary() -> list[str]:
    boundary = (
        gpd.read_file(ADMIN0_GEOJSON_PATH)
        .to_crs("EPSG:4326")
        .geometry.union_all()
    )
    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    names = []
    for south in range(math.floor(min_lat / 3) * 3, math.floor(max_lat / 3) * 3 + 1, 3):
        for west in range(math.floor(min_lon / 3) * 3, math.floor(max_lon / 3) * 3 + 1, 3):
            if boundary.intersects(box(west, south, west + 3, south + 3)):
                names.append(tile_name(south, west))
    return sorted(names)


def download_worldcover() -> dict:
    WORLDCOVER_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = WORLDCOVER_DIR / ".download.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        return _download_worldcover_locked()


def _download_worldcover_locked() -> dict:
    records = []
    for name in tile_names_for_boundary():
        destination = WORLDCOVER_DIR / name
        url = f"{WORLDCOVER_BASE_URL}/{name}"
        print(f"WorldCover: {name}", flush=True)
        response_headers = _download(url, destination)
        _validate_tile(destination)
        records.append(
            {
                "filename": name,
                "url": url,
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "etag": response_headers.get("ETag", "").strip('"'),
                "last_modified": response_headers.get("Last-Modified"),
            }
        )

    manifest = {
        "dataset": WORLDCOVER_VERSION,
        "doi": WORLDCOVER_DOI,
        "license": WORLDCOVER_LICENSE,
        "attribution": (
            "© ESA WorldCover project 2021 / Contains modified Copernicus "
            "Sentinel data (2021) processed by ESA WorldCover consortium"
        ),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source_base_url": WORLDCOVER_BASE_URL,
        "crs": "EPSG:4326",
        "resolution_m": 10,
        "tile_size_degrees": 3,
        "class_legend": {str(code): label for code, label in CLASS_LEGEND.items()},
        "tile_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "tiles": records,
    }
    manifest_path = WORLDCOVER_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(records)} tiles and provenance to {manifest_path}", flush=True)
    return manifest


def _download(url: str, destination: Path) -> dict:
    if destination.exists():
        request = Request(url, method="HEAD")
        with urlopen(request, timeout=60) as response:
            expected_size = int(response.headers["Content-Length"])
            headers = dict(response.headers.items())
        if destination.stat().st_size == expected_size:
            return headers

    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "antenna-placement/0.1"})
    with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        headers = dict(response.headers.items())
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(destination)
    return headers


def _validate_tile(path: Path) -> None:
    with rasterio.open(path) as source:
        if str(source.crs) != "EPSG:4326":
            raise ValueError(f"Unexpected CRS for {path.name}: {source.crs}")
        if source.count != 1 or source.dtypes[0] != "uint8":
            raise ValueError(f"Unexpected WorldCover schema for {path.name}")
        if source.width != 36_000 or source.height != 36_000:
            raise ValueError(f"Unexpected WorldCover tile dimensions for {path.name}")


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    download_worldcover()
