"""Source-verified measured-service review, isolated from deployment ranking."""
from pathlib import Path
from html import escape
import json

import folium
import numpy as np
import pandas as pd
from pyproj import Geod

from antenna_cell_placement.config import MODULE_DIR, PLANNING_INVENTORY_DIR
from antenna_cell_placement.source_integrity import verify_sources, require_sources, sha256


def verify_collections():
    report = verify_sources(lock_path=MODULE_DIR/'sources/collected_sources.lock.json')
    require_sources(report)
    return report


def add_service_layers(map_object, summary):
    """Each operator/RAT has its own switchable layer; tooltips state support."""
    from antenna_cell_placement.pilot import _cell_geometry, _json_safe
    if summary.empty:
        return
    for (mnc,rat), group in summary.groupby(['mnc','net_type'],sort=True):
        operator = {0:'Libyana',1:'Al-Madar'}.get(int(mnc),f'MNC {int(mnc)}')
        layer = folium.FeatureGroup(name=f'Measured service: {operator} / {rat}',show=True)
        fields = ['median_dbm','median_lte_rsrp_dbm','sample_count','day_count','device_count','spatial_bins_r9']
        for row in group.to_dict('records'):
            values = _json_safe(row)
            content = '<b>'+escape(operator+' / '+str(rat))+'</b><br>Collected route evidence; generic dBm is not RSRP.<table>'
            labels = ['Block-weighted generic signal (dBm)','Explicit LTE RSRP (dBm)','Observations','Days','Device labels','Spatial blocks']
            for name,label in zip(fields,labels):
                value = values.get(name)
                content += f'<tr><td>{label}</td><td>{escape(str(value)) if value is not None else "Unavailable"}</td></tr>'
            content += '</table>No measurements outside these areas are implied.'
            feature={'type':'Feature','geometry':_cell_geometry(row['h3_r8']),'properties':{}}
            folium.GeoJson(feature,style_function=lambda _:dict(color='#187e91',weight=1,fillColor='#187e91',fillOpacity=.2),
                           tooltip=folium.Tooltip(content),popup=folium.Popup(content,max_width=450)).add_to(layer)
        layer.add_to(map_object)


def measurement_support(shortlist, measurements):
    valid=measurements.loc[measurements.review_eligible.fillna(False)]
    rows=[]
    geod=Geod(ellps='WGS84')
    for row in shortlist.itertuples():
        distance=geod.inv(np.full(len(valid),row.canonical_longitude),np.full(len(valid),row.canonical_latitude),valid.lon.to_numpy(),valid.lat.to_numpy())[2]
        rows.append({'candidate_id':row.candidate_id,'nearest_measurement_m':float(min(distance)) if len(distance) else None,
                     'observations_within_1km':int(np.sum(distance<=1000)),'observations_within_5km':int(np.sum(distance<=5000))})
    return {'shortlist_count':len(rows),'measurement_source_available':bool(len(measurements)),
            'with_observations_1km':sum(r['observations_within_1km']>0 for r in rows),
            'with_observations_5km':sum(r['observations_within_5km']>0 for r in rows),
            'interpretation':'Observed support only; proximity is not validation of the planning point or a coverage radius.','rows':rows}


def run_service_review(output_dir, planning_run=None, towers=None, shortlist=None):
    from antenna_cell_placement.collected_data import audit_collections, load_measurements
    from antenna_cell_placement.pilot import build_pilot_review, prepare_measurements, service_summary
    from antenna_cell_placement.planning_map import localize_maps
    from antenna_cell_placement.map_visualizer import add_local_basemap
    before=verify_collections()
    output=Path(output_dir)
    output.mkdir(parents=True,exist_ok=False)
    if towers is None:
        manifest=json.loads((PLANNING_INVENTORY_DIR/'inventory_manifest.json').read_text(encoding='utf-8'))
        for name,digest in manifest['artifacts'].items():
            if sha256(PLANNING_INVENTORY_DIR/name)!=digest:
                raise ValueError('Reconciled inventory artifact changed')
        towers=pd.read_csv(PLANNING_INVENTORY_DIR/'radio_references.csv',dtype={'mcc':str,'mnc':str,'region_id':str,'site_id':str})
    audit=audit_collections(output=output/'collections.json')
    pilot=build_pilot_review(output_dir=output,towers=towers)
    measurements,_=load_measurements()
    summary=service_summary(prepare_measurements(measurements))
    support=None
    if planning_run is not None:
        run=Path(planning_run)
        run_manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        if run_manifest.get('status')!='completed' or sha256(run/'shortlist.csv')!=run_manifest['artifacts']['shortlist.csv']:
            raise ValueError('Planning shortlist changed or run incomplete')
        shortlist=pd.read_csv(run/'shortlist.csv')
    if shortlist is not None:
        support=measurement_support(shortlist,measurements)
        (output/'planning_measurement_support.json').write_text(json.dumps(support,indent=2)+'\n',encoding='utf-8')
    map_object=folium.Map(location=[32.85,13.25],zoom_start=11,tiles=None)
    add_local_basemap(map_object)
    add_service_layers(map_object,summary)
    folium.LayerControl(collapsed=False).add_to(map_object)
    map_object.get_root().html.add_child(folium.Element('<div style="position:fixed;bottom:25px;left:20px;z-index:9999;background:white;padding:15px;max-width:430px;font:14px Arial"><b>Measured service review</b><br>Choose operator and technology layers. Signals describe collected routes, days and devices. Blank areas have no supplied observations. Planning ranks are unchanged by this review.</div>'))
    map_object.save(str(output/'measured_service_map.html'))
    validation=pilot['temporal_validation']
    support_text=f"{support['with_observations_5km']}/{support['shortlist_count']} selected points have observations within 5 km." if support else 'No planning shortlist supplied for proximity review.'
    mae_text=f"{validation['mae_db']:.3f}" if validation['mae_db'] is not None else 'Unavailable'
    html=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Measured service review</title>
<style>body{{font:17px/1.6 system-ui;background:#eff5f8;color:#173448;margin:0}}main{{max-width:950px;margin:35px auto;background:white;padding:32px}}a{{color:#066894}}.note{{background:#fff3dc;padding:16px}}</style><main>
<h1>Measured service review</h1><p>{pilot['eligible_measurements']:,} eligible observations across {pilot['service_area_operator_radio_groups']} operator, technology and area groups.</p>
<p><a href="measured_service_map.html">Open offline service map</a> · <a href="measured_service_summary.csv">Summary CSV</a> · <a href="pilot_review.md">Pilot report</a> · <a href="pilot_review.json">Pilot evidence</a> · <a href="pilot_data_request.json">Field data request</a></p>
<h2>Later-day baseline</h2><p>{validation['matched_blocks']}/{validation['holdout_blocks']} held-out blocks could be scored ({validation['coverage_pct']}%). Matched-block MAE: {mae_text} dB.</p>
<p>This measures repeatability of observed-area signal medians, not an RF simulation or antenna-placement improvement. The reviewed holdout dates are September 26 and 28, 2026.</p>
<h2>Support for planning priorities</h2><p>{support_text}</p><p class="note">Operator and technology samples are uneven. Generic dBm and explicit LTE RSRP stay separate. Zero complete engineering sectors are available; site heights and deployment feasibility remain unverified.</p>
</main></html>'''
    (output/'index.html').write_text(html,encoding='utf-8')
    localize_maps(output)
    after=verify_collections()
    if before['source_lock_sha256']!=after['source_lock_sha256']:
        raise ValueError('Collection source lock changed during review')
    manifest={'status':'completed','source_lock_sha256':before['source_lock_sha256'],
              'ahmed_commit':'2c48a27494545988561acc4782e6b23530d33af0',
              'primary_ranking_modified':False,'eligible_measurements':pilot['eligible_measurements'],
              'planning_support':support,'artifacts':{p.relative_to(output).as_posix():sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return manifest
