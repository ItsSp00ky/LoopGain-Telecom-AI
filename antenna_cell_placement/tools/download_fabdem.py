"""Fetch selected official FABDEM V1-2 GeoTIFFs using verified ZIP byte ranges.

The Bristol release groups 1-degree TIFFs in multi-gigabyte ZIP archives. This
tool retrieves only the ZIP directory and requested members, and verifies each
member against the ZIP CRC before recording a local SHA-256 digest.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
from urllib.request import Request, urlopen
import zlib

import pandas as pd

from antenna_cell_placement.config import EXTERNAL_DATA_DIR, RECOMMENDATIONS_CSV


BASE_URL = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn"
DESTINATION = EXTERNAL_DATA_DIR / "fabdem_v1_2"
DATASET_URL = "https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn"


def tile_name(lat: int, lon: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}_FABDEM_V1-2.tif"


def bundle_name(lat: int, lon: int) -> str:
    south, west = lat // 10 * 10, lon // 10 * 10
    def corner(y: int, x: int) -> str:
        return f"{'N' if y >= 0 else 'S'}{abs(y):02d}{'E' if x >= 0 else 'W'}{abs(x):03d}"
    return f"{corner(south, west)}-{corner(south + 10, west + 10)}_FABDEM_V1-2.zip"


def _head(url: str) -> tuple[int, str]:
    with urlopen(Request(url, method="HEAD"), timeout=60) as response:
        if response.headers.get("Accept-Ranges", "").lower() != "bytes":
            raise ValueError(f"Range requests unavailable: {url}")
        return int(response.headers["Content-Length"]), response.headers.get("ETag", "")


def _range(url: str, start: int, length: int, size: int, etag: str) -> bytes:
    parts = []
    remaining = length
    position = start
    while remaining:
        chunk_length = min(remaining, 1024 * 1024)
        for attempt in range(4):
            headers = {"Range": f"bytes={position}-{position + chunk_length - 1}"}
            if etag:
                headers["If-Range"] = etag
            try:
                with urlopen(Request(url, headers=headers), timeout=120) as response:
                    expected = f"bytes {position}-{position + chunk_length - 1}/{size}"
                    if response.status != 206 or response.headers.get("Content-Range") != expected:
                        raise ValueError("Remote archive changed or returned the wrong byte range")
                    data = response.read(chunk_length)
                if len(data) == chunk_length:
                    break
            except (OSError, TimeoutError):
                if attempt == 3:
                    raise
        else:
            raise ValueError("Incomplete ZIP byte range after retries")
        parts.append(data)
        position += chunk_length
        remaining -= chunk_length
    return b"".join(parts)


def _entries(url: str, size: int, etag: str) -> dict[str, dict[str, int]]:
    tail_start = max(0, size - 65557)
    tail = _range(url, tail_start, size - tail_start, size, etag)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("ZIP end directory absent; ZIP64 archives are unsupported")
    _, disk, cd_disk, count_disk, count, cd_size, cd_start, comment = struct.unpack_from("<IHHHHIIH", tail, eocd)
    if disk or cd_disk or count_disk != count or cd_start == 0xFFFFFFFF:
        raise ValueError("Unsupported split or ZIP64 archive")
    directory = _range(url, cd_start, cd_size, size, etag)
    entries: dict[str, dict[str, int]] = {}
    offset = 0
    for _ in range(count):
        fields = struct.unpack_from("<IHHHHHHIIIHHHHHII", directory, offset)
        signature, _, _, flags, method, _, _, crc, packed, unpacked, name_len, extra_len, comment_len, _, _, _, local_offset = fields
        if signature != 0x02014B50 or flags & 1:
            raise ValueError("Invalid or encrypted ZIP directory member")
        name = directory[offset + 46:offset + 46 + name_len].decode("utf-8" if flags & 0x800 else "cp437")
        entries[Path(name).name] = {"method": method, "crc32": crc, "packed": packed,
                                    "unpacked": unpacked, "offset": local_offset}
        offset += 46 + name_len + extra_len + comment_len
    if offset != cd_size:
        raise ValueError("ZIP central directory length mismatch")
    return entries


def _fetch_member(url: str, entry: dict[str, int], size: int, etag: str) -> bytes:
    offset = entry["offset"]
    local = _range(url, offset, 30, size, etag)
    signature, _, flags, method, _, _, _, _, _, name_len, extra_len = struct.unpack("<IHHHHHIIIHH", local)
    if signature != 0x04034B50 or flags & 1 or method != entry["method"]:
        raise ValueError("ZIP local header differs from directory")
    packed = _range(url, offset + 30 + name_len + extra_len, entry["packed"], size, etag)
    if method == 8:
        content = zlib.decompress(packed, -15)
    elif method == 0:
        content = packed
    else:
        raise ValueError(f"Unsupported ZIP compression method {method}")
    if len(content) != entry["unpacked"] or zlib.crc32(content) != entry["crc32"]:
        raise ValueError("ZIP member CRC or length mismatch")
    return content


def download_selected(positions: list[tuple[int, int]], destination: Path = DESTINATION) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    bundles: dict[str, list[str]] = {}
    for lat, lon in sorted(set(positions)):
        bundles.setdefault(bundle_name(lat, lon), []).append(tile_name(lat, lon))
    def fetch_bundle(archive: str, names: list[str]) -> list[dict]:
        url = f"{BASE_URL}/{archive}"
        size, etag = _head(url)
        entries = _entries(url, size, etag)
        results = []
        for name in names:
            if name not in entries:
                raise ValueError(f"Official archive does not contain {name}")
            path = destination / name
            if not path.exists():
                data = _fetch_member(url, entries[name], size, etag)
                temporary = path.with_suffix(".part")
                temporary.write_bytes(data)
                temporary.replace(path)
            content = path.read_bytes()
            if len(content) != entries[name]["unpacked"] or zlib.crc32(content) != entries[name]["crc32"]:
                raise ValueError(f"Cached tile differs from official ZIP member: {name}")
            digest = sha256(content).hexdigest()
            results.append({"filename": name, "bytes": path.stat().st_size, "sha256": digest,
                            "source_archive_url": url, "source_archive_bytes": size,
                            "source_archive_etag": etag, "zip_crc32": f"{entries[name]['crc32']:08x}"})
            print(f"Verified {name}: {path.stat().st_size:,} bytes", flush=True)
        return results
    records = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(fetch_bundle, archive, names)
                 for archive, names in sorted(bundles.items())]
        for task in as_completed(tasks):
            records.extend(task.result())
    records.sort(key=lambda record: record["filename"])
    manifest = {"dataset": "FABDEM V1-2", "doi": DATASET_URL,
                "release": "V1-2 (2023-01-18)", "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "license": "CC BY-NC-SA 4.0 (dataset license.txt)",
                "license_url": f"{BASE_URL}/license.txt",
                "repository_license": "Non-Commercial Government Licence for public sector information",
                "horizontal_crs": "EPSG:4326", "vertical_crs": "EPSG:3855 (EGM2008)",
                "nominal_spacing": "1 arc-second", "elevation_unit": "metres",
                "attribution": "FABDEM is produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
                "source_role": "experimental terrain comparison only",
                "selection": "One-degree tiles containing frozen shortlisted candidates",
                "tiles": records}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def verify_cached_subset(destination: Path = DESTINATION) -> dict:
    """Build a manifest for already downloaded tiles, checked against official ZIP CRCs."""
    names = sorted(path.name for path in destination.glob("*_FABDEM_V1-2.tif"))
    if not names:
        raise ValueError("No cached FABDEM tiles to verify")
    positions = [(int(name[1:3]), int(name[4:7])) for name in names]
    bundles = {}
    for lat, lon in positions:
        bundles.setdefault(bundle_name(lat, lon), []).append(tile_name(lat, lon))
    records = []
    for archive, member_names in sorted(bundles.items()):
        url = f"{BASE_URL}/{archive}"
        size, etag = _head(url)
        entries = _entries(url, size, etag)
        for name in member_names:
            if name not in entries:
                raise ValueError(f"Official archive does not contain {name}")
            data = (destination / name).read_bytes()
            if len(data) != entries[name]["unpacked"] or zlib.crc32(data) != entries[name]["crc32"]:
                raise ValueError(f"Cached tile differs from official ZIP member: {name}")
            records.append({"filename": name, "bytes": len(data), "sha256": sha256(data).hexdigest(),
                            "source_archive_url": url, "source_archive_bytes": size,
                            "source_archive_etag": etag, "zip_crc32": f"{entries[name]['crc32']:08x}"})
    manifest = {"dataset": "FABDEM V1-2", "doi": DATASET_URL,
                "release": "V1-2 (2023-01-18)", "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "license": "CC BY-NC-SA 4.0 (dataset license.txt)",
                "license_url": f"{BASE_URL}/license.txt",
                "repository_license": "Non-Commercial Government Licence for public sector information",
                "horizontal_crs": "EPSG:4326", "vertical_crs": "EPSG:3855 (EGM2008)",
                "nominal_spacing": "1 arc-second", "elevation_unit": "metres",
                "attribution": "FABDEM is produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
                "source_role": "experimental terrain comparison only",
                "selection": "Verified cached subset of one-degree tiles containing frozen shortlisted candidates",
                "tiles": records}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Fetch only the first N ranked candidates' tiles")
    parser.add_argument("--cached-only", action="store_true", help="Verify downloaded tiles and record a partial manifest")
    parser.add_argument("--tile", action="append", metavar="N32E022",
                        help="Fetch an exact 1-degree tile; may be repeated")
    args = parser.parse_args()
    if args.cached_only:
        manifest = verify_cached_subset()
        print(f"Verified cached subset: {len(manifest['tiles'])} tiles")
        return
    if args.tile:
        positions = []
        for value in args.tile:
            match = re.fullmatch(r"([NS])(\d{2})([EW])(\d{3})", value.upper())
            if not match:
                parser.error(f"Invalid tile name: {value}")
            ns, lat, ew, lon = match.groups()
            positions.append((int(lat) * (1 if ns == "N" else -1),
                              int(lon) * (1 if ew == "E" else -1)))
        download_selected(positions)
        return
    recommendations = pd.read_csv(RECOMMENDATIONS_CSV).sort_values("recommendation_rank")
    if args.limit is not None:
        recommendations = recommendations.head(args.limit)
    import math
    positions = [(math.floor(row.canonical_latitude), math.floor(row.canonical_longitude))
                 for row in recommendations.itertuples()]
    download_selected(positions)


if __name__ == "__main__":
    main()
