"""Fetch and verify the pinned Zenodo foreign RF benchmark files."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


DIRECTORY = Path(__file__).resolve().parents[1] / 'data/external/chongqing_5g_2026'


def main():
    manifest = json.loads((DIRECTORY / 'manifest.json').read_text())
    for name, metadata in manifest['files'].items():
        target = DIRECTORY / name
        if not target.exists():
            url = f"{manifest['record']}/files/{name}?download=1"
            with urlopen(url, timeout=180) as response:
                content = response.read()
            if (len(content) != metadata['bytes'] or hashlib.sha256(content).hexdigest() != metadata['sha256']
                    or hashlib.md5(content).hexdigest() != metadata['zenodo_md5']):
                raise ValueError(f'Zenodo release changed: {name}')
            target.write_bytes(content)
        content = target.read_bytes()
        if (len(content) != metadata['bytes'] or hashlib.sha256(content).hexdigest() != metadata['sha256']
                or hashlib.md5(content).hexdigest() != metadata['zenodo_md5']):
            raise ValueError(f'Foreign benchmark file integrity mismatch: {name}')
        print(f'{name}: verified {len(content):,} bytes')


if __name__ == '__main__':
    main()
