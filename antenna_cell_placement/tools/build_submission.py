"""Package the existing phase-2 Tripoli experiment; no retraining or branch merge.

Run from antenna_cell_placement with its locked Python environment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import geopandas as gpd
import pandas as pd

from antenna_cell_placement.config import MODULE_DIR, CLEANED_RADIO_TOWERS_CSV, RAW_SQLITE_PATH
from antenna_cell_placement.data_cleaning import load_raw_records_from_sqlite
from antenna_cell_placement.gis_v2 import FEATURE_VERSION
from antenna_cell_placement.map_visualizer import generate_h3_expansion_map
from antenna_cell_placement.rooftop_candidates import export_rooftops


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def localize_assets(output):
    """Vendor generated map dependencies, including CSS-relative fonts/images."""
    vendor = output / 'vendor'
    vendor.mkdir(exist_ok=True)
    old_manifest = output / 'vendor_manifest.json'
    previous = {record['source_url']: record for record in json.loads(old_manifest.read_text())} if old_manifest.exists() else {}
    for record in previous.values():
        cached = vendor / record['filename']
        if not cached.exists() or sha256(cached) != record['sha256']:
            raise ValueError(f'Cached vendor asset changed: {cached.name}')
    records = {}
    def fetch(url):
        url = url.split('#', 1)[0]
        if url in records:
            return records[url]['filename']
        filename = hashlib.sha256(url.encode()).hexdigest()[:12] + '_' + Path(urlparse(url).path).name
        records[url] = {'filename': filename, 'source_url': url}
        destination = vendor / filename
        if destination.exists():
            content = destination.read_bytes()
        else:
            with urlopen(url, timeout=60) as response:
                content = response.read()
        if filename.endswith('.css'):
            css = content.decode('utf-8')
            def asset(match):
                original = match.group(1).strip(' \"\'')
                if original.startswith(('data:', '#')):
                    return match.group(0)
                absolute = urljoin(url, original)
                fragment = '#' + original.split('#', 1)[1] if '#' in original else ''
                return 'url("' + fetch(absolute) + fragment + '")'
            # Cached files have already-localized references.
            if not destination.exists():
                css = re.sub(r'url\(([^)]+)\)', asset, css)
            content = css.encode('utf-8')
        destination.write_bytes(content)
        records[url].update(sha256=sha256(destination), bytes=len(content))
        return filename
    for page in output.glob('*.html'):
        html = page.read_text(encoding='utf-8')
        def rewrite(match):
            return match.group(1) + 'vendor/' + fetch(match.group(2)) + match.group(3)
        html = re.sub(r'((?:src|href)=[\"\'])(https?://[^\"\']+)([\"\'])', rewrite, html)
        page.write_text(html, encoding='utf-8')
    (output/'vendor_manifest.json').write_text(json.dumps(list({**previous, **records}.values()), indent=2), encoding='utf-8')


def build(phase2, output):
    phase2, output = phase2.resolve(), output.resolve()
    if phase2 == output:
        raise ValueError('Submission output must be separate from the source experiment')
    output.mkdir(parents=True, exist_ok=True)
    # Runtime assets and artifact checksums must survive Git checkout unchanged.
    (output/'.gitattributes').write_text('# Generated/vendor files: preserve bytes and upstream spacing.\n* -text whitespace=-blank-at-eol,-blank-at-eof,cr-at-eol\n', encoding='utf-8')
    metrics = json.loads((phase2/'model_comparison.json').read_text())
    manifest = json.loads((phase2/'manifest.json').read_text())
    hexes = gpd.read_file(phase2/'h3_scores_Tripoli_v2.geojson')
    if set(hexes.feature_version.dropna()) != {FEATURE_VERSION}:
        raise ValueError('Submission requires the verified v2 feature version')
    roofs = gpd.read_file(phase2/'rooftop_candidates.geojson')
    if roofs.building_height_known.any():
        raise ValueError('This submission narrative expects unavailable building heights; review new evidence before rebuilding')
    ranked = hexes.loc[hexes.combined_priority_score.notna()].sort_values('expansion_rank')
    top = ranked.head(20).copy()
    if len(top) != 20 or len(roofs) != 100:
        raise ValueError('Unexpected shortlist size; review the input experiment')
    if not set(roofs.h3_index).issubset(set(top.h3_index)):
        raise ValueError('Footprints do not belong to the top-20 planning areas')
    if not all(geometry.covers(__import__('shapely').geometry.Point(lon, lat)) for geometry, lon, lat in zip(roofs.geometry, roofs.canonical_longitude, roofs.canonical_latitude)):
        raise ValueError('A footprint review coordinate is outside its footprint')
    selected_columns = ['expansion_rank','h3_index','canonical_latitude','canonical_longitude','combined_priority_score',
                        'expansion_need_score','placement_suitability_score','population_sum_5km',
                        'population_valid_fraction_5km','population_hex','feature_version']
    shortlist = top[selected_columns].rename(columns={
        'combined_priority_score':'planning_priority_score',
        'placement_suitability_score':'experimental_site_pattern_score',
        'population_sum_5km':'population_within_5km',
    })
    shortlist['building_height_status'] = 'Unavailable'
    shortlist['review_status'] = 'Engineering review required; RF benefit unverified'
    shortlist.to_csv(output/'tripoli_shortlist.csv', index=False)
    generate_h3_expansion_map('Tripoli', source_geojson=phase2/'h3_scores_Tripoli_v2.geojson', output_html=output/'tripoli_planning_map.html')
    export_rooftops(roofs, output)

    raw = load_raw_records_from_sqlite()
    radios = pd.read_csv(CLEANED_RADIO_TOWERS_CSV)
    confirmed_raw = int(raw.owner_confirmed_almadar.sum())
    confirmed_radios = radios.loc[radios.owner_confirmed_almadar.eq(True)]
    if confirmed_raw != 645 or len(confirmed_radios) == 0 or not confirmed_radios.operator.eq('Al-Madar').all():
        raise ValueError('Al-Madar owner-confirmation provenance failed')
    operator_counts = radios.groupby(['operator','rat'], dropna=False).size().rename('radio_groups').reset_index()
    operator_counts.to_csv(output/'operator_inventory_counts.csv', index=False)
    evidence = {
        'owner_confirmed_almadar_raw_records': confirmed_raw,
        'owner_confirmed_almadar_radio_groups': len(confirmed_radios),
        'attribution_methods': sorted(confirmed_radios.operator_attribution_method.unique().tolist()),
        'radio_groups_total': len(radios), 'scored_tripoli_hexes': len(ranked),
        'shortlisted_areas': len(top), 'footprint_candidates': len(roofs),
        'usable_footprint_heights': int(roofs.building_height_known.sum()),
        'footprint_coordinates_inside_geometry': True,
        'raw_database_sha256': sha256(RAW_SQLITE_PATH),
    }
    (output/'verification.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    for name in ('model_comparison.json','inventory_audit.json'):
        shutil.copy2(phase2/name, output/name)
    shutil.copy2(phase2/'manifest.json', output/'phase2_source_manifest.json')
    old, new = metrics['legacy_features_same_recipe'], metrics['v2_features']
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tripoli | Planning priorities for engineering review</title>
<style>body{font:16px/1.5 system-ui,sans-serif;margin:0;color:#172a3b;background:#eef3f6}main{max-width:1100px;margin:auto;padding:36px 28px}h1{font-size:36px;line-height:1.15;max-width:850px}h2{font-size:23px}small,.muted{color:#526475}.tag{letter-spacing:.12em;font-size:12px;text-transform:uppercase;color:#126b60;font-weight:700}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card,section{background:white;border:1px solid #d9e2e8;border-radius:12px;padding:20px;margin:18px 0}.card{margin:0}.card strong{display:block;font-size:30px;color:#126b60}a{color:#095f91}nav{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}nav a{background:#126b60;color:white;text-decoration:none;padding:12px 18px;border-radius:7px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:9px;border-bottom:1px solid #d9e2e8}.note{border-left:4px solid #cd8a21;padding-left:14px}.links{display:flex;gap:20px;flex-wrap:wrap}footer{font-size:13px;color:#526475;margin-top:24px}@media(max-width:720px){.cards{grid-template-columns:1fr 1fr}h1{font-size:28px}main{padding:20px}}</style>
<main><div class="tag">Loop Gain / Samsung Innovation Campus / Submission demo</div>
<h1>Planning priorities for engineering review</h1>
<p>Tripoli pilot: inspect candidate areas and mapped building footprints, understand the evidence, and identify what engineers must verify.</p>
<div class="cards"><div class="card"><strong>20</strong>priority areas</div><div class="card"><strong>100</strong>footprints for review</div><div class="card"><strong>Unavailable</strong>building heights</div><div class="card"><strong>645</strong>owner-confirmed Al-Madar records</div></div>
<nav><a href="tripoli_planning_map.html">Open Tripoli planning map</a><a href="rooftop_candidates_map.html">Open footprint review map</a></nav>
<section><h2>What this demo establishes</h2><p>GIS evidence supports a provisional shortlist. The current area ranking includes an experimental ML multiplier. Distances to known sites are inventory gaps; population within 5 km is a catchment estimate. Neither establishes service coverage.</p>
<p class="note"><b>Engineering review required.</b> No equipment, frequency-band or bandwidth recommendation is issued. Roof height, structural condition, ownership, power and backhaul remain unverified. The tallest building has not been identified.</p></section>
<section><h2>ML experiment: existing-site pattern recognition</h2><table><thead><tr><th>Same frozen hard-negative examples</th><th>Legacy features</th><th>Corrected GIS features</th></tr></thead><tbody>
<tr><td>Model ROC-AUC</td><td>OLD_AUC</td><td>NEW_AUC</td></tr>
<tr><td>Population-only ROC-AUC</td><td>OLD_POP</td><td>NEW_POP</td></tr></tbody></table>
<p><b>0.876 → 0.885 is diagnostic model evidence, not coverage improvement.</b> Same 2,033 test examples: 533 observed sites and 1,500 synthetic hard negatives. The geographic test was previously inspected. Synthetic negatives are unlabelled locations in reality; network features use the known inventory. AUC is not percentage accuracy or deployment probability.</p>
<p class="muted">The separate historical-site recovery test also matters: the Tripoli planning score scored 0.716 AUC versus 0.767 for population alone. It has not demonstrated superiority for future network expansion.</p></section>
<section><h2>Presentation backups and evidence</h2><div class="links"><a href="tripoli_shortlist.csv">20-area shortlist CSV</a><a href="rooftop_candidates.csv">100-footprint CSV</a><a href="rooftop_candidates.geojson">Footprints GeoJSON</a><a href="operator_inventory_counts.csv">Operator counts CSV</a><a href="verification.json">Verification</a><a href="model_comparison.json">Model metrics</a></div><p>Static screenshots are in the <code>screenshots</code> folder. Maps embed geographic context and use bundled JavaScript/CSS; no internet map tiles are needed.</p></section>
<footer>Submission prepared from the versioned phase-2 experiment. Population and site inventories are imperfect proxies. All output is for engineering review.</footer></main></html>'''
    for token, value in {'OLD_AUC':old['test_hard']['roc_auc'],'NEW_AUC':new['test_hard']['roc_auc'],
                         'OLD_POP':old['population_only_hard_auc'],'NEW_POP':new['population_only_hard_auc']}.items():
        html = html.replace(token, f'{value:.6f}')
    (output/'index.html').write_text(html, encoding='utf-8')
    localize_assets(output)
    source_files = ['h3_scores_Tripoli_v2.geojson','rooftop_candidates.geojson','model_comparison.json','manifest.json']
    run = {'built_utc':datetime.now(timezone.utc).isoformat(),'feature_version':FEATURE_VERSION,
           'phase2_source_directory':str(phase2), 'phase2_sources':{name:sha256(phase2/name) for name in source_files},
           'code_sha256':{path.name:sha256(path) for path in (MODULE_DIR/'src/antenna_cell_placement').glob('*.py')},
           'files_sha256':{str(path.relative_to(output)):sha256(path) for path in output.rglob('*') if path.is_file() and path.name != 'submission_manifest.json'}}
    (output/'submission_manifest.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase2-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=MODULE_DIR/'submission')
    args = parser.parse_args()
    build(args.phase2_dir, args.output_dir)
