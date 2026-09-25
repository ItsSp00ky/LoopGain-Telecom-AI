"""Content-addressed input checks and portable, exclusive download locking."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256 as _sha256
import json
import os
from pathlib import Path

from antenna_cell_placement.config import MODULE_DIR, SOURCE_LOCK_PATH


def sha256(path):
    path = Path(path)
    digest = _sha256()
    if path.is_dir():
        for child in sorted(p for p in path.rglob('*') if p.is_file()):
            digest.update(child.relative_to(path).as_posix().encode() + b'\0')
            digest.update(bytes.fromhex(sha256(child)))
    else:
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
    return digest.hexdigest()


@contextmanager
def download_lock(path):
    """Fail explicitly if another download owns the lock; Windows and POSIX."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f'Download lock exists: {path}. Check for a running download before removing a stale lock.') from exc
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def verify_sources(root=MODULE_DIR, lock_path=SOURCE_LOCK_PATH):
    """Never bless changed input automatically. Optional failures disable context."""
    root = Path(root).resolve()
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    records = lock.get('sources', [])
    if not records or len({r['path'] for r in records}) != len(records):
        raise ValueError('Source lock must contain unique, explicit input records')
    results = []
    for record in records:
        path = (root / record['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Source path escapes the project')
        status = 'missing'
        actual = None
        if path.exists():
            actual = sha256(path)
            status = 'verified' if actual == record['sha256'] else 'changed'
        results.append({**record, 'status': status, 'actual_sha256': actual})
    required = [r for r in results if r['required']]
    if not required:
        raise ValueError('Source lock has no required sources')
    report = {
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'source_lock_sha256': sha256(lock_path),
        'required_ready': all(r['status'] == 'verified' for r in required),
        'sources': results,
        'interpretation': 'Integrity relative to the reviewed inputs, not RF or source completeness validation.',
    }
    metadata = {}
    groups = {r['group'] for r in results}
    for group, folder, module in (
        ('worldcover', 'worldcover_2021', 'worldcover'),
        ('osm', 'osm_libya_2026_09_19', 'buildings'),
    ):
        if group not in groups:
            continue
        from importlib import import_module
        try:
            check = import_module('antenna_cell_placement.' + module).verify_manifest(root / 'data/external' / folder)
            metadata[group] = check
        except (OSError, ValueError, KeyError, TypeError) as exc:
            metadata[group] = {'verified': False, 'failures': [str(exc)]}
        if any(r['required'] for r in results if r['group'] == group) and not metadata[group]['verified']:
            report['required_ready'] = False
    report['metadata_checks'] = metadata
    report['usage_gates'] = {
        'worldcover': 'Water screening and review context; no RF clutter model',
        'osm': 'Mapped footprints and selected POIs are review context only; no score multiplier',
        'height_ookla_viirs_ports': 'Excluded from runtime scoring',
        'independent_rf_validation': 'Unavailable',
    }
    return report


def group_ready(report, group):
    rows = [r for r in report['sources'] if r['group'] == group]
    metadata_ok = report.get('metadata_checks', {}).get(group, {}).get('verified', True)
    return bool(rows) and metadata_ok and all(r['status'] == 'verified' for r in rows)


def require_sources(report):
    failures = [r['path'] + ':' + r['status'] for r in report['sources']
                if r['required'] and r['status'] != 'verified']
    for group, check in report.get('metadata_checks', {}).items():
        if not check['verified'] and any(r['required'] for r in report['sources'] if r['group'] == group):
            failures.append(group + ':manifest_metadata_invalid')
    if failures:
        raise ValueError('Required source verification failed: ' + ', '.join(failures))


def verify_downloaded_file(path, expected_path=None):
    """Downloaded bytes must match the reviewed lock, including same-size files."""
    path = Path(path).resolve()
    target = Path(expected_path).resolve() if expected_path is not None else path
    relative = target.relative_to(MODULE_DIR.resolve()).as_posix()
    lock = json.loads(SOURCE_LOCK_PATH.read_text(encoding='utf-8'))
    expected = next((r for r in lock['sources'] if r['path'] == relative), None)
    if expected is None or sha256(path) != expected['sha256']:
        raise ValueError(f'Unreviewed or changed download: {relative}')
