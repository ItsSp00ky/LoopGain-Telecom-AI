"""Network-scoped radio audit without changing stable legacy mast IDs."""
import numpy as np
import pandas as pd
from antenna_cell_placement.gis_v2 import GEOD


def network_identity(row):
    if row.get('owner_confirmed_almadar',False):
        return '606:1'
    if pd.notna(row.get('mcc')) and pd.notna(row.get('mnc')):
        return f"{int(row['mcc'])}:{int(row['mnc'])}"
    if row.get('operator') in ('Libyana','Al-Madar'):
        return {'Libyana':'606:0','Al-Madar':'606:1'}[row['operator']]
    return 'unknown'


def scoped_radio_inventory(raw):
    """Never merge two known networks sharing RAT/region/site identifiers.

    Snapshot bandwidth is the latest observed list total; it is not summed across
    repeat observations. Missing carrier identity prevents a claim of exact RF capacity.
    """
    data=raw.copy()
    data['network_identity']=data.apply(network_identity,axis=1)
    keys=['rat','region_id','site_id','network_identity']
    rows=[]
    for identity,group in data.groupby(keys,dropna=False,sort=True):
        ordered=group.sort_values(['last_seen_ms','record_id'],kind='stable')
        valid=ordered[ordered.bandwidths.map(bool)]
        latest=valid.iloc[-1] if len(valid) else None
        snapshot=float(sum(latest.bandwidths)) if latest is not None else np.nan
        rows.append({**dict(zip(keys,identity)), 'observation_count':len(group),
            'latitude':float(group.latitude.median()),'longitude':float(group.longitude.median()),
            'bandwidth_latest_observed_mhz':snapshot,
            'bandwidth_naive_all_observations_mhz':float(sum(sum(v) for v in group.bandwidths)),
            'bandwidth_method':'latest_observed_list_total' if latest is not None else 'unknown',
            'bandwidth_capacity_verified':False,
            'source_record_ids':','.join(map(str,group.record_id)),
            'last_seen_ms':int(group.last_seen_ms.max())})
    return pd.DataFrame(rows)


def audit_inventory(raw, towers, sites):
    scoped=scoped_radio_inventory(raw)
    old_keys=['rat','region_id','site_id']
    collisions=scoped.groupby(old_keys).network_identity.nunique()
    collisions=collisions[collisions>1]
    cluster_rows=[]
    for site_id,group in towers.groupby('physical_site_id'):
        max_distance=0.0
        xs,ys=group.longitude.to_numpy(),group.latitude.to_numpy()
        for i in range(len(group)):
            ds=GEOD.inv(np.full(len(group),xs[i]),np.full(len(group),ys[i]),xs,ys)[2]
            max_distance=max(max_distance,float(np.max(ds)))
        cluster_rows.append({'physical_site_id':int(site_id),'radios':len(group),
                             'geodesic_diameter_m':max_distance,'chain_exceeds_50m':max_distance>50.0})
    clusters=pd.DataFrame(cluster_rows)
    report={'raw_observations':len(raw),'legacy_radio_groups':len(towers),
            'network_scoped_radio_groups':len(scoped),'cross_network_legacy_key_collisions':len(collisions),
            'physical_sites':len(sites),'clusters_with_diameter_over_50m':int(clusters.chain_exceeds_50m.sum()),
            'max_cluster_diameter_m':float(clusters.geodesic_diameter_m.max()),
            'groups_with_reported_bandwidth':int(scoped.bandwidth_latest_observed_mhz.notna().sum()),
            'groups_with_repeat_observation_bandwidth_inflation':int((scoped.bandwidth_naive_all_observations_mhz>scoped.bandwidth_latest_observed_mhz+1e-6).sum()),
            'policy':'Scoped audit table is authoritative for observed bandwidth provenance; legacy estimated site capacity fields are not v2 ML inputs. Stable mast IDs are retained pending review of flagged clusters.'}
    return scoped,clusters,report
