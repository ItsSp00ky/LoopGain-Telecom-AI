"""Compare frozen planning runs and rebuild network features without uncertain sites."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from antenna_cell_placement.gis_v2 import network_features
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints, select_spatially_separated
from antenna_cell_placement.source_integrity import sha256


def load_run(path):
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    if manifest['status']!='completed':
        raise ValueError('Comparison requires complete runs')
    for name in ('candidates.csv','shortlist.csv'):
        if sha256(path/name)!=manifest['artifacts'][name]:
            raise ValueError('Run artifact changed: '+name)
    return manifest,pd.read_csv(path/'candidates.csv'),pd.read_csv(path/'shortlist.csv')


def compare(before,after):
    old_manifest,old,old_selected=load_run(before)
    manifest,current,selected=load_run(after)
    if set(old.candidate_id)!=set(current.candidate_id):
        raise ValueError('Inventory comparison requires the same candidate IDs')
    a=old.set_index('candidate_id').sort_index()
    b=current.set_index('candidate_id').sort_index()
    nonnetwork=['canonical_latitude','canonical_longitude','population_sum_5km','terrain_slope_deg',
                'elevation_m','elevation_prominence_3km','dist_to_nearest_road_m']
    for name in nonnetwork:
        if not np.allclose(a[name],b[name],equal_nan=True):
            raise ValueError('Non-inventory feature changed: '+name)
    sites_path=after/'physical_sites.csv'
    if sha256(sites_path)!=manifest['artifacts'][sites_path.name]:
        raise ValueError('Inventory artifact changed')
    sites=pd.read_csv(sites_path)
    certain=sites.loc[~sites.location_conflict.fillna(True)].copy()
    sensitivity=current.copy()
    for index,row in sensitivity.iterrows():
        for name,value in network_features(row.canonical_longitude,row.canonical_latitude,certain).items():
            sensitivity.at[index,name]=value
    constraints=PlanningConstraints(**manifest['constraints'])
    sensitivity=CellSiteOptimizer.evaluate_features(sensitivity,constraints)
    chosen=select_spatially_separated(sensitivity,constraints)
    delta=b.dist_to_nearest_site_m-a.dist_to_nearest_site_m
    report={'before_commit':old_manifest['base_commit'],'before_manifest_sha256':sha256(before/'manifest.json'),
            'after_manifest_sha256':sha256(after/'manifest.json'),'same_candidate_count':len(current),
            'nonnetwork_features_unchanged':True,'eligible_before':int(a.eligible.sum()),'eligible_after':int(b.eligible.sum()),
            'newly_eligible':int((~a.eligible & b.eligible).sum()),'newly_ineligible':int((a.eligible & ~b.eligible).sum()),
            'nearest_distance_changed_candidates':int(delta.abs().gt(.01).sum()),
            'maximum_absolute_nearest_distance_change_m':float(delta.abs().max()),
            'selected_before':len(old_selected),'selected_after':len(selected),
            'selected_ids_retained':len(set(old_selected.candidate_id)&set(selected.candidate_id)),
            'removed_selected_ids':sorted(set(old_selected.candidate_id)-set(selected.candidate_id)),
            'added_selected_ids':sorted(set(selected.candidate_id)-set(old_selected.candidate_id)),
            'conflict_exclusion_sensitivity':{'excluded_physical_references':len(sites)-len(certain),
                'eligible_count':int(sensitivity.eligible.sum()),'selected_count':len(chosen),
                'overlap_with_default':len(set(chosen.candidate_id)&set(selected.candidate_id))/len(selected) if len(selected) else None,
                'selected_ids':chosen.candidate_id.tolist(),
                'policy':'Exclude every physical reference containing a conflicted radio; rebuild all network distances/densities.'},
            'interpretation':'Inventory and shortlist sensitivity only. Neither reference inclusion nor exclusion establishes actual RF service.',
            'tool_sha256':sha256(__file__)}
    out=after/'inventory_comparison'
    out.mkdir(exist_ok=False)
    pd.DataFrame({'before_distance_m':a.dist_to_nearest_site_m,'after_distance_m':b.dist_to_nearest_site_m,
                  'before_eligible':a.eligible,'after_eligible':b.eligible,'before_score':a.planning_priority_score,'after_score':b.planning_priority_score}).to_csv(out/'candidate_changes.csv',lineterminator='\n')
    chosen.to_csv(out/'excluding_conflicts_shortlist.csv',index=False,lineterminator='\n')
    (out/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path)
    parser.add_argument('after',type=Path)
    args=parser.parse_args()
    compare(args.before,args.after)
