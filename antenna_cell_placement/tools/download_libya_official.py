"""Fetch the two pinned public Libya statistics CSVs from the official portal."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/external/libya_official_2022_2025'


def main():
    manifest = json.loads((DIRECTORY / 'manifest.json').read_text())
    for name, source in manifest['sources'].items():
        target = DIRECTORY / name
        if not target.exists():
            with urlopen(source['url'], timeout=60) as response:
                content = response.read()
            if len(content) != source['bytes'] or hashlib.sha256(content).hexdigest() != source['sha256']:
                raise ValueError(f'Official source changed: {name}; review before replacing the snapshot')
            target.write_bytes(content)
        content = target.read_bytes()
        if len(content) != source['bytes'] or hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError(f'Official source hash or size mismatch: {name}')
        print(f'{name}: verified {len(content)} bytes')


if __name__ == '__main__':
    main()
