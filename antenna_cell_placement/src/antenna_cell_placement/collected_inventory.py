"""Source-traceable radio references and bounded geodesic physical-site groups."""
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial import cKDTree
from scipy.spatial.distance import squareform

from antenna_cell_placement.config import (
    RAW_SQLITE_PATH, CLEANED_RADIO_TOWERS_CSV, INVENTORY_VERSION, PLANNING_INVENTORY_DIR,
)

GEOD = Geod(ellps='WGS84')
AS_OF = '2026-09-29T19:00:00Z'


def canonical_number(value):
    if pd.isna(value) or str(value).strip() == '':
        return 'unknown'
    return str(int(float(value)))


def distances(frame):
    n = len(frame)
    matrix = np.zeros((n, n))
    lon, lat = frame.longitude.to_numpy(), frame.latitude.to_numpy()
    for i in range(n - 1):
        matrix[i, i+1:] = GEOD.inv(np.full(n-i-1, lon[i]), np.full(n-i-1, lat[i]), lon[i+1:], lat[i+1:])[2]
    return matrix + matrix.T


def bounded_groups(frame, threshold):
    """Complete linkage; every pair in a cluster is within the geodesic bound."""
    if len(frame) <= 1:
        return [frame]
    labels = fcluster(linkage(squareform(distances(frame), checks=False), method='complete'), threshold, criterion='distance')
    groups = [frame.iloc[np.flatnonzero(labels == label)] for label in set(labels)]
    return sorted(groups, key=lambda g: (float(g.latitude.min()), float(g.longitude.min()), str(g.record_id.iloc[0])))


def representative(frame):
    # Pick an actual source coordinate, never an invented midpoint between alternatives.
    matrix = distances(frame)
    return frame.iloc[int(np.argmin(matrix.sum(axis=1)))]


def group_radio_records(records):
    raw = records.copy()
    for name, default in [('owner_confirmed_almadar', False), ('source_verified', False), ('source_file', 'fixture')]:
        if name not in raw:
            raw[name] = default
    raw['owner_confirmed_almadar'] = raw.owner_confirmed_almadar.fillna(False).astype(bool)
    for name in ('mcc', 'mnc', 'region_id', 'site_id'):
        raw[name] = raw[name].map(canonical_number)
    # Derived attribution is scoped to the immutable owner-confirmed import.
    raw.loc[raw.owner_confirmed_almadar, ['mcc','mnc']] = ['606','1']
    raw['record_id'] = raw.record_id.astype(str)
    if raw.record_id.duplicated().any():
        raise ValueError('Source record IDs must be unique')
    raw = raw.sort_values(['latitude','longitude','record_id'], kind='stable')
    towers, crosswalk = [], []
    keys = ['mcc','mnc','rat','region_id','site_id']
    for identity, group in raw.groupby(keys, dropna=False, sort=True):
        alternatives = bounded_groups(group, 1000.)
        for number, alternative in enumerate(alternatives, 1):
            point = representative(alternative)
            record_ids = sorted(alternative.record_id)
            radio_id = 'radio-' + sha256('\n'.join(record_ids).encode()).hexdigest()[:16]
            operator = {('606','0'):'Libyana',('606','1'):'Al-Madar'}.get(identity[:2], 'Unknown')
            towers.append({**dict(zip(keys,identity)), 'radio_id':radio_id,
                'latitude':float(point.latitude), 'longitude':float(point.longitude),
                'location_group':number, 'location_conflict':len(alternatives)>1,
                'source_verified':bool(point.source_verified) if pd.notna(point.source_verified) else False,
                'any_source_verified_in_group':bool(alternative.source_verified.fillna(False).any()),
                'owner_confirmed_almadar':bool(alternative.owner_confirmed_almadar.any()),
                'owner_confirmed_records':int(alternative.owner_confirmed_almadar.sum()),
                'operator':operator, 'observation_count':len(alternative),
                'first_seen_ms':pd.to_numeric(alternative.first_seen_ms,errors='coerce').min(),
                'last_seen_ms':pd.to_numeric(alternative.last_seen_ms,errors='coerce').max(),
                'source_files':'|'.join(sorted(alternative.source_file.dropna().unique())),
                'source_record_ids':'|'.join(record_ids),
                'representative_record_id':point.record_id,
                'location_diameter_m':float(distances(alternative).max()),
                'coordinate_policy':'observed_coordinate_medoid; source reference, not survey truth'})
            crosswalk.extend({'record_id':r.record_id, 'radio_id':radio_id,
                'owner_confirmed_almadar':bool(r.owner_confirmed_almadar), 'source_file':r.source_file,
                'status':'retained', 'operator':operator} for r in alternative.itertuples())
    return pd.DataFrame(towers), pd.DataFrame(crosswalk)


def physical_groups(towers):
    """Find nearby components by ECEF chord, then enforce a 50m geodesic diameter."""
    frame = towers.sort_values('radio_id', kind='stable').reset_index(drop=True)
    frame['record_id'] = frame.radio_id
    n = len(frame)
    if not n:
        raise ValueError('No valid radio references')
    xyz = Transformer.from_crs(4979,4978,always_xy=True).transform(frame.longitude,frame.latitude,np.zeros(n))
    parent = list(range(n))
    def find(i):
        while i != parent[i]:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i,j in sorted(cKDTree(np.column_stack(xyz)).query_pairs(50.001)):
        a,b = find(i),find(j)
        parent[max(a,b)] = min(a,b)
    components = {}
    for i in range(n):
        components.setdefault(find(i),[]).append(i)
    sites=[]
    for indices in components.values():
        for group in bounded_groups(frame.iloc[indices],50.):
            point=representative(group)
            identity='\n'.join(sorted(group.radio_id))
            site_id=int(sha256(identity.encode()).hexdigest()[:12],16)
            frame.loc[group.index,'physical_site_id']=site_id
            sites.append({'physical_site_id':site_id,'canonical_latitude':float(point.latitude),
                'canonical_longitude':float(point.longitude), 'radio_tower_count':len(group),
                'has_almadar':bool(group.operator.eq('Al-Madar').any()),
                'has_libyana':bool(group.operator.eq('Libyana').any()),
                'location_conflict':bool(group.location_conflict.any()),
                'geodesic_diameter_m':float(distances(group).max()),
                'inventory_version':INVENTORY_VERSION, 'representative_radio_id':point.radio_id})
    frame['physical_site_id']=frame.physical_site_id.astype('int64')
    return frame.drop(columns='record_id'), pd.DataFrame(sites).sort_values('physical_site_id').reset_index(drop=True)


def build_inventory(output_dir=PLANNING_INVENTORY_DIR):
    from antenna_cell_placement.data_cleaning import load_raw_records_from_sqlite
    from antenna_cell_placement.collected_data import cellmapper_raw_records
    from antenna_cell_placement.collected_opencellid import _libya_boundary
    from antenna_cell_placement.reconciliation import reconcile_locations
    from antenna_cell_placement.source_integrity import sha256 as file_hash
    from shapely.geometry import Point
    from antenna_cell_placement.config import MODULE_DIR
    from antenna_cell_placement.service_review import verify_collections

    verify_collections()
    source_lock=json.loads((MODULE_DIR/'sources/planning_sources.lock.json').read_text(encoding='utf-8'))
    expected=next(r['sha256'] for r in source_lock['sources'] if r['path']=='data/cleaned/cleaned_radio_towers.csv')
    if file_hash(CLEANED_RADIO_TOWERS_CSV)!=expected:
        raise ValueError('Historical inventory changed before crosswalk construction')

    output = Path(output_dir)
    output.mkdir(parents=True,exist_ok=False)
    raw = load_raw_records_from_sqlite()
    with sqlite3.connect(RAW_SQLITE_PATH.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        verification = {str(rid):str(json.loads(body).get('verified','')).lower()=='true'
                        for rid,body in conn.execute('SELECT source_record_id,raw_json FROM source_records')}
    raw['source_verified']=raw.record_id.astype(str).map(verification).fillna(False)
    raw['record_id']='sqlite:'+raw.record_id.astype(str)
    raw['source_file']='Libyan_cells_dataset/cells.sqlite3'
    collected=cellmapper_raw_records()
    collected['owner_confirmed_almadar']=False
    collected['source_file']=collected.source_file.map(lambda p:Path(p).relative_to(MODULE_DIR).as_posix())
    combined=pd.concat([raw,collected],ignore_index=True)
    # Explicit missing timestamps remain missing, not a manufactured 1970 observation.
    for name in ('first_seen_ms','last_seen_ms'):
        combined[name]=pd.to_numeric(combined[name],errors='coerce').where(lambda s:s>0)
    boundary=_libya_boundary()
    valid=np.isfinite(combined[['latitude','longitude']].astype(float)).all(axis=1)
    valid &= np.array([boundary.covers(Point(lon,lat)) if ok else False for lon,lat,ok in zip(combined.longitude,combined.latitude,valid)])
    rejected=combined.loc[~valid,['record_id','source_file','owner_confirmed_almadar']].copy()
    rejected['status']='invalid_or_outside_boundary'
    rejected['operator']=np.where(rejected.owner_confirmed_almadar.fillna(False),'Al-Madar','Unknown')
    radios,crosswalk=group_radio_records(combined.loc[valid])
    radios,sites=physical_groups(radios)
    crosswalk=crosswalk.merge(radios[['radio_id','physical_site_id']],on='radio_id',validate='many_to_one')
    crosswalk=pd.concat([crosswalk,rejected],ignore_index=True)
    crosswalk['physical_site_id']=crosswalk.physical_site_id.astype('Int64')
    old=pd.read_csv(CLEANED_RADIO_TOWERS_CSV)
    old_lookup={(str(r.rat),canonical_number(r.region_id),canonical_number(r.site_id)):int(r.physical_site_id) for r in old.itertuples()}
    previous={r.record_id:old_lookup.get((r.rat,canonical_number(r.region_id),canonical_number(r.site_id))) for r in raw.itertuples()}
    crosswalk['previous_physical_site_id']=crosswalk.record_id.map(previous).astype('Int64')
    owner=crosswalk.loc[crosswalk.owner_confirmed_almadar.fillna(False)]
    if len(owner)!=645 or not owner.operator.eq('Al-Madar').all():
        raise ValueError('Historical 645-record owner attribution changed')
    reconciliation=reconcile_locations(radios,as_of=AS_OF)
    report={'inventory_version':INVENTORY_VERSION,'as_of_utc':AS_OF,
        'raw_observations':len(raw),'collected_records':len(collected),'retained_source_records':int(valid.sum()),
        'rejected_source_records':len(rejected),'network_scoped_radio_groups':len(radios),
        'physical_sites':len(sites),'owner_confirmed_almadar_records':len(owner),
        'owner_confirmed_almadar_retained_records':int(owner.status.eq('retained').sum()),
        'owner_attribution_correct':True,'conflicted_identities':reconciliation['conflicted_identities'],
        'conflicted_physical_sites':int(sites.location_conflict.sum()),
        'max_cluster_diameter_m':float(sites.geodesic_diameter_m.max()),
        'clusters_with_diameter_over_50m':int(sites.geodesic_diameter_m.gt(50.000001).sum()),
        'policy':'Retain conflicting references for conservative screening, exclude them from reliable pilot anchors; no conflict is survey-resolved. No engineering parameters inferred.'}
    for name,frame in [('radio_references',radios),('physical_sites',sites),('source_crosswalk',crosswalk),('rejected_records',rejected)]:
        frame.to_csv(output/(name+'.csv'),index=False,lineterminator='\n')
    (output/'reconciliation.json').write_text(json.dumps(reconciliation,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    report['inputs']={p.relative_to(MODULE_DIR).as_posix():file_hash(p) for p in [RAW_SQLITE_PATH,CLEANED_RADIO_TOWERS_CSV, MODULE_DIR/'data/new_data/libya_collected_antennas/cellmapper/cellmapper_libya_antennas.csv']}
    report['artifacts']={p.name:file_hash(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output/'inventory_manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report
