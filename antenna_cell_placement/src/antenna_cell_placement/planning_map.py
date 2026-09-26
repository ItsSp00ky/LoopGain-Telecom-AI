"""Portable offline maps for the integrated planning contract."""
from html import escape
import json
from pathlib import Path
import re
import shutil

import folium
import geopandas as gpd
import pandas as pd

from antenna_cell_placement.config import MODULE_DIR
from antenna_cell_placement.map_visualizer import add_local_basemap
from antenna_cell_placement.source_integrity import sha256


def localize_maps(output):
    """Reuse the already bundled, hash-checked release assets; no CDN required."""
    output = Path(output)
    source = MODULE_DIR / 'submission'
    manifest = json.loads((source / 'vendor_manifest.json').read_text(encoding='utf-8'))
    urls = {r['source_url']: r for r in manifest}
    vendor = output / 'vendor'
    vendor.mkdir(exist_ok=True)
    for record in manifest:
        path = source / 'vendor' / record['filename']
        if sha256(path) != record['sha256']:
            raise ValueError(f'Bundled map asset changed: {path.name}')
        shutil.copy2(path, vendor / path.name)
    for page in output.glob('*.html'):
        text = page.read_text(encoding='utf-8')
        def replace(match):
            record = urls.get(match[2])
            if record is None:
                raise ValueError(f'Unbundled map asset: {match[2]}')
            return match[1] + 'vendor/' + record['filename'] + match[3]
        text = re.sub(r'((?:src|href)=[\"\'])(https?://[^\"\']+)([\"\'])', replace, text)
        page.write_text(text, encoding='utf-8', newline='\n')
    shutil.copy2(source / 'vendor_manifest.json', output / 'vendor_manifest.json')


def generate_planning_map(shortlist, output, scope='Tripoli'):
    output = Path(output)
    center = [float(shortlist.canonical_latitude.mean()), float(shortlist.canonical_longitude.mean())] if len(shortlist) else [32.8, 13.25]
    m = folium.Map(location=center, zoom_start=10 if scope != 'national' else 6, tiles=None)
    add_local_basemap(m)
    fields = ['recommendation_rank', 'planning_priority_score', 'population_sum_5km',
              'dist_to_nearest_site_m', 'dist_to_nearest_road_m', 'operator_scope',
              'reason_codes', 'building_height_status']
    aliases = ['Review rank', 'Planning priority (0–100)', 'Population within 5 km',
               'Nearest known site (m)', 'Road distance (m)', 'Operator scope',
               'Reasons', 'Building height']
    layer = folium.FeatureGroup(name='Planning priorities for engineering review')
    for _, row in shortlist.iterrows():
        content = '<b>Planning priority for engineering review</b><table>'
        for key, label in zip(fields, aliases):
            value = row.get(key)
            display = 'Unavailable' if pd.isna(value) else str(round(value, 2) if isinstance(value, float) else value)
            content += f'<tr><td>{escape(label)}</td><td>{escape(display)}</td></tr>'
        content += '</table>'
        folium.CircleMarker([row.canonical_latitude, row.canonical_longitude], radius=8,
                            color='#c35419', fill=True, fill_opacity=.8,
                            tooltip=folium.Tooltip(content), popup=folium.Popup(content, max_width=430)).add_to(layer)
    layer.add_to(m)
    folium.LayerControl().add_to(m)
    notice = 'No candidates met all constraints.' if shortlist.empty else f'{len(shortlist)} locations for engineering review.'
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:35px;left:20px;z-index:9999;background:white;padding:12px;max-width:380px;font:14px Arial">'
        '<b>Explainable planning priorities</b><br>' + notice +
        '<br>Population within 5 km is not population served. Building heights are unavailable. RF improvement and rooftop feasibility are unverified.</div>'))
    path = output / 'planning_map.html'
    m.save(str(path))
    return path


def write_overview(output, report, inventory):
    output = Path(output)
    comparisons = ''.join(f'<tr><td>{escape(name.replace("_", " "))}</td><td>{value["overlap_with_explainable"]:.0%}</td></tr>'
                          for name, value in report['comparisons'].items() if value['overlap_with_explainable'] is not None)
    roofs = '<a href="rooftop_candidates_map.html">Building footprints for review</a>' if (output / 'rooftop_candidates_map.html').exists() else 'Footprint review unavailable for this run.'
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Integrated antenna planning</title><style>
body{{font:17px/1.6 system-ui,sans-serif;background:#f2f5f8;color:#183042;margin:0}}main{{max-width:1040px;margin:40px auto;padding:32px;background:white;border-radius:14px}}
h1{{font-size:36px;line-height:1.2}}h2{{font-size:24px}}a{{color:#075a93}}.cards{{display:flex;gap:20px;flex-wrap:wrap}}.card{{padding:18px;background:#e9f2f7;border-radius:8px;min-width:170px}}b.num{{display:block;font-size:32px}}td,th{{padding:8px 18px;text-align:left;border-bottom:1px solid #ddd}}.note{{padding:18px;border-left:4px solid #c35419;background:#fff6ed}}
</style><main><p>LOOP GAIN · INTEGRATED GIS + EXPLAINABLE SCORING</p>
<h1>Planning priorities for engineering review</h1>
<p>Your corrected GIS measurements and inventory provenance, combined with Ahmed’s explainable scoring and source checks.</p>
<div class="cards"><div class="card"><b class="num">{report['candidate_count']:,}</b>candidate locations</div><div class="card"><b class="num">{report['eligible_count']:,}</b>passed strict checks</div><div class="card"><b class="num">{report['selected_count']}</b>spatially separated priorities</div><div class="card"><b class="num">{inventory['owner_confirmed_almadar_records']}</b>owner-confirmed Al-Madar records</div></div>
<h2>Explore the combined result</h2><ul><li><a href="planning_map.html">Open the offline planning map</a></li><li>{roofs}</li><li><a href="shortlist.csv">Shortlist CSV</a> · <a href="candidates.csv">All candidates and rejection reasons</a></li><li><a href="comparison.json">Matched ranking comparison</a> · <a href="manifest.json">Source and run evidence</a></li></ul>
<h2>How the ranking works</h2><p>40% population, 30% known-site gap, 20% road access and 10% terrain. These are provisional planning assumptions. Every selected location must meet the same population, distance, terrain and land-cover checks. No machine-learning prediction changes this primary ranking.</p>
<h2>Same candidates, different ranking methods</h2><table><tr><th>Method</th><th>Shortlist overlap with explainable score</th></tr>{comparisons}</table>
<p>Overlap and weight sensitivity describe how the ranking changes. They do not establish which method improves coverage.</p>
<h2>What the ML experiment means</h2><p>The earlier controlled experiment improved hard-negative AUC from 0.876141 to 0.885208 after GIS corrections; its corrected population-only baseline was 0.571961. This measures recognition of existing-site patterns on synthetic diagnostic labels. It is separate from this planning shortlist. An explicit research command can compare ML on these exact candidates.</p>
<p class="note"><b>Limits:</b> “Population within 5 km” is not population served. Building heights, usable roof area and structural capacity are unavailable or unverified. Outputs require engineering review; no RF coverage improvement has been demonstrated.</p>
<p>Sources: WorldPop density, SRTM terrain, UN OCHA boundaries/roads/places, observed telecom inventory, ESA WorldCover 2021, OpenStreetMap contributors (ODbL) and Microsoft building footprints where present.</p></main></html>'''
    (output / 'index.html').write_text(html, encoding='utf-8', newline='\n')
