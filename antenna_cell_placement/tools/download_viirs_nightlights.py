"""Create bounded Libya windows from official monthly VIIRS composites."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

from antenna_cell_placement.config import (
    ADMIN0_GEOJSON_PATH,
    VIIRS_DIR,
    VIIRS_FLARES_CSV,
    VIIRS_MANIFEST,
)


BUCKET = "https://globalnightlight.s3.amazonaws.com/composites"
MONTHS = ("202401", "202404", "202407", "202410")
FLARE_URL = (
    "https://eogdata.mines.edu/global_flare_data/"
    "2024_flare_summary_v20250730_j01.kml"
)


def source_urls(month: str) -> tuple[str, str]:
    last_day = {"01": "31", "04": "30", "07": "31", "10": "31"}[month[-2:]]
    # The upstream archive renamed the same stray-light-corrected configuration
    # from ``ecm-slcorr`` to ``ecmslcfg`` in October 2024.
    configuration = "ecmslcfg" if month == "202410" else "ecm-slcorr"
    stem = f"DNB_npp_{month}01-{month}{last_day}_global_{configuration}_v10_ops"
    root = f"{BUCKET}/npp_{month}_ops/{stem}"
    return f"{root}.avg_rade9.tif", f"{root}.n_cf.tif"


def download_viirs_nightlights() -> dict[str, object]:
    VIIRS_DIR.mkdir(parents=True, exist_ok=True)
    with (VIIRS_DIR / ".download.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        return _download_locked()


def _download_locked() -> dict[str, object]:
    boundary = gpd.read_file(ADMIN0_GEOJSON_PATH).to_crs("EPSG:4326")
    bounds = tuple(float(value) for value in boundary.total_bounds)
    products = []
    for month in MONTHS:
        radiance_url, coverage_url = source_urls(month)
        radiance_path = VIIRS_DIR / f"viirs_{month}_radiance.tif"
        coverage_path = VIIRS_DIR / f"viirs_{month}_cloudfree_count.tif"
        _crop_remote_cog(radiance_url, radiance_path, bounds)
        _crop_remote_cog(coverage_url, coverage_path, bounds)
        products.append(
            {
                "month": month,
                "radiance_source_url": radiance_url,
                "coverage_source_url": coverage_url,
                "radiance": _file_record(radiance_path),
                "cloudfree_count": _file_record(coverage_path),
            }
        )

    flare_kml = VIIRS_DIR / "2024_global_gas_flares.kml"
    _download(FLARE_URL, flare_kml)
    flare_count = _subset_flares(flare_kml, VIIRS_FLARES_CSV, bounds)
    manifest = {
        "dataset": "VIIRS DNB monthly cloud-free composites",
        "periods": list(MONTHS),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source": "World Bank Light Every Night public AWS bucket",
        "documentation_url": "https://registry.opendata.aws/wb-light-every-night/",
        "license": "ODbL-1.0",
        "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "upstream_producer": "Earth Observation Group, Payne Institute for Public Policy",
        "radiance_units": "nW/cm^2/sr",
        "crs": "EPSG:4326",
        "nominal_resolution_arc_seconds": 15,
        "libya_bounds": list(bounds),
        "products": products,
        "gas_flare_catalog": {
            "source_url": FLARE_URL,
            "source_record": _file_record(flare_kml),
            "libya_subset": {**_file_record(VIIRS_FLARES_CSV), "rows": flare_count},
            "year": 2024,
            "producer": "Earth Observation Group",
            "documentation_url": "https://eogdata.mines.edu/products/vnf/global_gas_flare.html",
        },
        "processing": (
            "Remote COG range reads crop each source to the supplied Libya boundary "
            "bounding box. No radiance resampling or value substitution is performed."
        ),
    }
    VIIRS_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(products)} monthly Libya raster pairs and {flare_count} flare sites")
    return manifest


def _crop_remote_cog(url: str, destination: Path, bounds: tuple[float, ...]) -> None:
    if destination.exists():
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(url) as source:
            window = from_bounds(*bounds, transform=source.transform).round_offsets().round_lengths()
            data = source.read(1, window=window)
            profile = source.profile.copy()
            profile.update(
                width=data.shape[1],
                height=data.shape[0],
                transform=source.window_transform(window),
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate",
                predictor=3 if data.dtype.kind == "f" else 2,
            )
            with rasterio.open(temporary, "w", **profile) as target:
                target.write(data, 1)
    temporary.replace(destination)


def _download(url: str, destination: Path) -> None:
    if destination.exists():
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "antenna-placement/0.1"})
    with urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    temporary.replace(destination)


def _subset_flares(
    kml_path: Path, output_path: Path, bounds: tuple[float, ...]
) -> int:
    root = ElementTree.parse(kml_path).getroot()
    west, south, east, north = bounds
    rows = []
    for coordinates in root.iterfind(".//{*}Point/{*}coordinates"):
        if not coordinates.text:
            continue
        parts = coordinates.text.strip().split(",")
        if len(parts) < 2:
            continue
        longitude, latitude = map(float, parts[:2])
        if west <= longitude <= east and south <= latitude <= north:
            rows.append({"longitude": longitude, "latitude": latitude})
    pd.DataFrame(rows, columns=["longitude", "latitude"]).drop_duplicates().to_csv(
        output_path, index=False
    )
    return len(rows)


def _file_record(path: Path) -> dict[str, str | int]:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return {"filename": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


if __name__ == "__main__":
    download_viirs_nightlights()
