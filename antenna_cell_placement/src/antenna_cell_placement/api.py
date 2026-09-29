"""Read-only HTTP service over the existing planning pipeline.

This wraps `cli.py`'s public commands (`doctor`, `assess`, `map`) so the platform
shell can call GIS over HTTP the same way it already calls churn's API. It does not
reimplement scoring: every route calls the same functions the CLI calls
(`assess_coordinate`, `verify_sources`) or serves files an already-completed
`recommend`/`all` run wrote under `integrated_release_v3/` (the run that carries the
real collected-data/reconciled-inventory integration; the earlier `integrated_release/`
predates it and is not the default here). Running a brand-new planning pass is a
slow, data-heavy batch job (H3 grid + rooftops + maps), so it stays a CLI-only
operation; this API only ever reads a run's finished output.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from antenna_cell_placement.placement import assess_coordinate
from antenna_cell_placement.source_integrity import verify_sources, sha256

DEFAULT_RUN_DIR = Path(__file__).resolve().parents[2] / "integrated_release_v3"

app = FastAPI(title="GIS Antenna Planning API", description=__doc__)


def _completed_run(run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, f"No run at {run_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise HTTPException(409, "Run is not marked completed")
    return manifest


@app.get("/health")
def health():
    report = verify_sources()
    return {"status": "ok" if report["required_ready"] else "degraded", "sources": report}


@app.get("/shortlist")
def shortlist(run_dir: Path = DEFAULT_RUN_DIR):
    """Serve the shortlist from an existing completed run, hash-verified."""
    manifest = _completed_run(run_dir)
    path = run_dir / "shortlist.geojson"
    if not path.exists() or sha256(path) != manifest["artifacts"].get(path.name):
        raise HTTPException(409, "shortlist.geojson missing or changed since the run completed")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/rooftops")
def rooftops(run_dir: Path = DEFAULT_RUN_DIR):
    manifest = _completed_run(run_dir)
    path = run_dir / "rooftop_candidates.geojson"
    if not path.exists():
        raise HTTPException(404, "This run did not include rooftop review")
    if sha256(path) != manifest["artifacts"].get(path.name):
        raise HTTPException(409, "rooftop_candidates.geojson changed since the run completed")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/map")
def planning_map(run_dir: Path = DEFAULT_RUN_DIR):
    """Serve the verified offline map HTML for a completed run (same check as `cli.py map`)."""
    manifest = _completed_run(run_dir)
    path = run_dir / "planning_map.html"
    if not path.exists() or sha256(path) != manifest["artifacts"].get(path.name):
        raise HTTPException(409, "planning_map.html missing or changed since the run completed")
    return FileResponse(path)


@app.get("/assess")
def assess(
    lat: float = Query(...),
    lon: float = Query(...),
    operator: str = Query("all", pattern="^(all|almadar|libyana)$"),
):
    try:
        return assess_coordinate(lat, lon, operator)
    except ValueError as error:
        # Same failure `doctor`/the CLI would raise: required local source data is
        # missing or does not match the source lock in this checkout.
        raise HTTPException(503, str(error)) from error
