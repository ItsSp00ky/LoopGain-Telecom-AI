"""Evidence-based review of conflicting source locations; no inferred survey truth."""

import numpy as np
import pandas as pd
from pyproj import Geod

IDENTITY = ['mcc', 'mnc', 'rat', 'region_id', 'site_id']
GEOD = Geod(ellps='WGS84')


def reconcile_locations(towers, as_of=None):
    """Return one auditable decision per conflicted identity, preserving alternatives.

    A unique source-verified alternative can be preferred for review only when
    its timestamp is valid and at least as recent as every competing reference.
    Neither contributor verification nor recency is an independent survey.
    """
    now = pd.Timestamp.now(tz='UTC') if as_of is None else pd.Timestamp(as_of)
    if now.tzinfo is None:
        now = now.tz_localize('UTC')
    decisions = []
    for identity, group in towers.loc[towers.location_conflict].groupby(IDENTITY, dropna=False, sort=True):
        group = group.sort_values('location_group').copy()
        last = pd.to_datetime(pd.to_numeric(group.last_seen_ms, errors='coerce'), unit='ms', utc=True, errors='coerce')
        first = pd.to_datetime(pd.to_numeric(group.first_seen_ms, errors='coerce'), unit='ms', utc=True, errors='coerce')
        valid_time = last.notna() & first.notna() & first.le(last) & last.le(now)
        verified = group.get('source_verified', pd.Series(False, index=group.index)).fillna(False).astype(bool)
        preferred = None
        if valid_time.all() and int(verified.sum()) == 1:
            selected = verified.loc[verified].index[0]
            if last.loc[selected] >= last.max():
                preferred = int(group.loc[selected, 'location_group'])
        max_separation = 0.0
        for i, row in group.iterrows():
            _, _, distances = GEOD.inv(np.full(len(group), row.longitude), np.full(len(group), row.latitude), group.longitude.to_numpy(), group.latitude.to_numpy())
            max_separation = max(max_separation, float(np.max(distances)))
        alternatives = []
        for i, row in group.iterrows():
            alternatives.append({
                'location_group': int(row.location_group),
                'latitude': float(row.latitude), 'longitude': float(row.longitude),
                'source_verified': bool(verified.loc[i]),
                'last_seen_utc': last.loc[i].isoformat() if pd.notna(last.loc[i]) else None,
                'timestamp_valid': bool(valid_time.loc[i]), 'source_files': row.source_files,
            })
        decisions.append({
            **dict(zip(IDENTITY, [None if pd.isna(v) else str(v) for v in identity])),
            'status': 'preferred_for_review' if preferred is not None else 'unresolved',
            'preferred_location_group': preferred,
            'reason': 'unique_source_verified_and_not_older' if preferred is not None else 'insufficient_independent_location_evidence',
            'maximum_separation_m': round(max_separation, 1),
            'alternatives': alternatives,
            'required_action': 'Obtain independently surveyed coordinates or an operator asset record with location provenance.',
        })
    return {
        'conflicted_identities': len(decisions),
        'preferred_for_review': sum(d['status'] == 'preferred_for_review' for d in decisions),
        'survey_resolved_identities': 0,
        'runtime_policy': 'Retain all conflicting references for conservative screening; exclude them from reliable pilot anchors.',
        'decisions': decisions,
    }
