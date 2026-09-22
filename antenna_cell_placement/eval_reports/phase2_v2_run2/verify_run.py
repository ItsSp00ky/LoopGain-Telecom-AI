"""Integration verification of completed phase2 outputs (run from project root)."""
import json
from pathlib import Path
import joblib
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from antenna_cell_placement.phase2_pipeline import sha256
from antenna_cell_placement.gis_v2 import FEATURE_VERSION
from antenna_cell_placement.config import RAW_SQLITE_PATH, SUITABILITY_MODEL_PATH

out=Path('eval_reports/phase2_v2_run2')
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
assert 'completed_utc' in manifest
old=pd.read_parquet('eval_reports/experiment_20260922_v1/dataset.parquet')
new=pd.read_parquet(out/'dataset_v2.parquet')
for column in ('row_id','split','is_cell_site','sample_kind','municipality_name','canonical_longitude','canonical_latitude'):
    pd.testing.assert_series_equal(old[column],new[column])
assert new.feature_version.eq(FEATURE_VERSION).all()
assert manifest['raw_database_unchanged'] and manifest['serving_model_unchanged']
assert sha256(RAW_SQLITE_PATH)==manifest['sources_sha256'][str(RAW_SQLITE_PATH)]
assert sha256(SUITABILITY_MODEL_PATH)==manifest['serving_model_sha256_before']
dev=new.split.eq('development')
assert set(new.loc[dev,'municipality_name']).isdisjoint(set(new.loc[~dev,'municipality_name']))
model=joblib.load(out/'suitability_gis_v2.joblib')
pred=pd.read_csv(out/'comparison_predictions.csv')
np.testing.assert_allclose(model.predict_proba(new.loc[~dev])[:,1],pred.loc[~dev,'v2_features'],rtol=1e-12)
try:
    model.predict_proba(old)
except ValueError:
    pass
else:
    raise AssertionError('Model accepted legacy feature table')
hexes=pd.read_csv(out/'h3_scores_Tripoli_v2.csv')
assert hexes.h3_index.is_unique
assert hexes.combined_priority_score.is_monotonic_decreasing
assert np.isfinite(hexes.combined_priority_score).all()
roofs=gpd.read_file(out/'rooftop_candidates.geojson')
assert roofs.building_id.is_unique
assert roofs.footprint_area_m2.ge(150).all()
assert roofs.groupby('h3_index').size().le(5).all()
assert roofs.area_priority_rank.le(20).all()
assert roofs.building_height_m.isna().all()
assert not roofs.building_height_known.any()
assert roofs.structural_survey_required.all()
assert roofs.apply(lambda r:r.geometry.covers(Point(r.canonical_longitude,r.canonical_latitude)),axis=1).all()
checks={'frozen_rows_coordinates_labels_splits_preserved':True,'geographic_groups_disjoint':True,
        'reloaded_model_matches_saved_predictions':True,'legacy_features_rejected':True,
        'raw_and_serving_model_hashes_unchanged':True,'ranked_hexes':len(hexes),
        'rooftop_candidates':len(roofs),'shortlist_areas_with_buildings':int(roofs.h3_index.nunique()),
        'rooftop_points_inside_footprints':True,'building_heights_unknown':True,
        'missing_population_5km_by_kind':new.assign(missing=new.population_sum_5km.isna()).groupby('sample_kind').missing.agg(['sum','count','mean']).to_dict('index')}
(out/'integration_verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))
