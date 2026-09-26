"""Phase 2: versioned GIS migration, inventory audit, training and rooftop review."""
import hashlib
import json
import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score, brier_score_loss
from sklearn.model_selection import GroupKFold

from antenna_cell_placement.config import (
    CLEANED_PHYSICAL_SITES_CSV, CLEANED_RADIO_TOWERS_CSV, REPORTS_DIR,
    H3_GRID_GEOJSON_TEMPLATE, H3_FEATURE_TABLE_PARQUET_TEMPLATE,
    RAW_SQLITE_PATH, WORLDPOP_TIF_PATH, DEM_RASTER_PATH, ROADS_SHP_PATH,
    SUITABILITY_MODEL_PATH, MS_BUILDING_FOOTPRINTS_TILES, POP_PLACES_GEOJSON_PATH, ADMIN2_GEOJSON_PATH,
)
from antenna_cell_placement.gis_v2 import FeatureExtractorV2, FEATURE_VERSION
from antenna_cell_placement.inventory_audit_v2 import audit_inventory
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
from antenna_cell_placement.evaluation import LGB_PARAMS


def sha256(path):
    path=Path(path)
    digest=hashlib.sha256()
    if path.is_dir():
        # ESRI Arc/Info GRID is a directory dataset, not a single TIFF.
        for child in sorted(p for p in path.rglob('*') if p.is_file()):
            digest.update(child.relative_to(path).as_posix().encode('utf-8')+b'\0')
            digest.update(bytes.fromhex(sha256(child)))
        return digest.hexdigest()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


class VersionedSuitabilityModel:
    """Prediction requires the complete v2 feature table, including its version."""
    def __init__(self,pipeline):
        self.feature_version=FEATURE_VERSION
        self.features=list(SUITABILITY_FEATURE_COLS)
        self.pipeline=pipeline

    def predict_proba(self,data):
        if 'feature_version' not in data or not data.feature_version.eq(self.feature_version).all():
            raise ValueError(f'Model requires feature_version={self.feature_version}')
        values=data[self.features]
        if np.isinf(values.to_numpy()).any():
            raise ValueError('Infinite features are invalid; use NaN for missing evidence')
        return self.pipeline.predict_proba(values)


def metrics(labels,scores):
    return {'n':len(labels),'positives':int(np.sum(labels)),
            'roc_auc':float(roc_auc_score(labels,scores)),
            'average_precision':float(average_precision_score(labels,scores)),
            'accuracy_at_0_5':float(accuracy_score(labels,np.asarray(scores)>=0.5)),
            'brier_score':float(brier_score_loss(labels,scores))}


def train_comparison(old,new,output):
    """Controlled v1/v2 recipe comparison using identical rows, labels and splits."""
    for col in ('row_id','split','is_cell_site','sample_kind','municipality_name'):
        if not old[col].reset_index(drop=True).equals(new[col].reset_index(drop=True)):
            raise ValueError(f'Frozen {col} changed')
    dev=new.split.eq('development').to_numpy()
    test=~dev
    hard=(new.sample_kind.eq('synthetic_hard')|new.is_cell_site.eq(1)).to_numpy() & test
    report={}
    predictions=new[['row_id','split','sample_kind','is_cell_site']].copy()
    trained=None
    for name,data in [('legacy_features_same_recipe',old),('v2_features',new)]:
        X=data[SUITABILITY_FEATURE_COLS]
        y=data.is_cell_site
        def estimator():
            # Fitted on each training fold only: no test-set imputation leakage.
            return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
                                 LGBMClassifier(**{**LGB_PARAMS,'n_jobs':2}))
        oof=np.full(int(dev.sum()),np.nan)
        Xdev,ydev=X[dev].reset_index(drop=True),y[dev].reset_index(drop=True)
        groups=data.loc[dev,'municipality_name'].reset_index(drop=True)
        for tr,va in GroupKFold(5).split(Xdev,ydev,groups):
            fitted=estimator().fit(Xdev.iloc[tr],ydev.iloc[tr])
            oof[va]=fitted.predict_proba(Xdev.iloc[va])[:,1]
        model=estimator().fit(X[dev],y[dev])
        scores=model.predict_proba(X[test])[:,1]
        hardscores=model.predict_proba(X[hard])[:,1]
        # Fill missing baseline demand using DEVELOPMENT median only.
        population=data.population_sum_5km.fillna(data.loc[dev,'population_sum_5km'].median())
        report[name]={'development_grouped_cv':metrics(ydev,oof),'test':metrics(y[test],scores),
                      'test_hard':metrics(y[hard],hardscores),
                      'population_only_test_auc':float(roc_auc_score(y[test],population[test])),
                      'population_only_hard_auc':float(roc_auc_score(y[hard],population[hard]))}
        predictions[name]=np.nan
        predictions.loc[dev,name]=oof
        predictions.loc[test,name]=scores
        if name=='v2_features':
            trained=VersionedSuitabilityModel(model)
    predictions.to_csv(output/'comparison_predictions.csv',index=False)
    joblib.dump(trained,output/'suitability_gis_v2.joblib')
    report['interpretation']='Same frozen diagnostic examples and recipe; geographic test was previously inspected. Synthetic labels are not deployment outcomes. No automatic serving-model promotion.'
    report['parameters']={**LGB_PARAMS,'n_jobs':2}
    (output/'model_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return trained,report


def run_phase2(output_dir=None, frozen_dataset=None, rooftops=True):
    output=Path(output_dir or REPORTS_DIR/'phase2_v2')
    output.mkdir(parents=True,exist_ok=False)
    frozen=Path(frozen_dataset or REPORTS_DIR/'experiment_20260922_v1/dataset.parquet')
    old=pd.read_parquet(frozen)
    sites=pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
    towers=pd.read_csv(CLEANED_RADIO_TOWERS_CSV)
    from antenna_cell_placement.data_cleaning import load_raw_records_from_sqlite
    before=sha256(RAW_SQLITE_PATH)
    serving_before=sha256(SUITABILITY_MODEL_PATH)
    scoped,clusters,audit=audit_inventory(load_raw_records_from_sqlite(),towers,sites)
    scoped.to_csv(output/'radio_inventory_scoped_v2.csv',index=False)
    clusters.to_csv(output/'physical_site_cluster_audit.csv',index=False)
    (output/'inventory_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    extractor=FeatureExtractorV2(sites)
    metadata={'feature_version':FEATURE_VERSION,'created_utc':datetime.now(timezone.utc).isoformat(),
              'population':extractor.population.metadata,'dem':extractor.dem.metadata,
              'unit_evidence':'https://hub.worldpop.org/geodata/summary?id=47207',
              'unit_evidence_note':'Published Libya population-density family is people/km². Local TIFF has no unit tag; density interpretation is explicit. Exact UN-adjustment provenance not established by local filename.',
              'sources_sha256':{str(p):sha256(p) for p in (RAW_SQLITE_PATH,WORLDPOP_TIF_PATH,DEM_RASTER_PATH,ROADS_SHP_PATH,CLEANED_PHYSICAL_SITES_CSV,frozen)},
              'source_code_sha256':{p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')},
              'inventory_audit':audit}
    extra_sources=[*ROADS_SHP_PATH.parent.glob(ROADS_SHP_PATH.stem+'.*'),
                   *MS_BUILDING_FOOTPRINTS_TILES,POP_PLACES_GEOJSON_PATH,ADMIN2_GEOJSON_PATH,
                   Path(H3_GRID_GEOJSON_TEMPLATE.format(city='Tripoli')),
                   Path(H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city='Tripoli'))]
    metadata['sources_sha256'].update({str(p):sha256(p) for p in extra_sources if p.is_file()})
    metadata['packages']={name:importlib.metadata.version(name) for name in
                          ('numpy','pandas','geopandas','rasterio','shapely','pyproj','scikit-learn','lightgbm')}
    metadata['serving_model_sha256_before']=serving_before
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Extracting v2 physical-site features...',flush=True)
    sf=extractor.extract(sites.canonical_longitude,sites.canonical_latitude,sites.physical_site_id)
    sf.insert(0,'physical_site_id',sites.physical_site_id.to_numpy())
    sf.to_parquet(output/'physical_sites_features_v2.parquet',index=False)
    sf.to_csv(output/'physical_sites_features_v2.csv',index=False)
    print('Recomputing frozen experiment locations...',flush=True)
    lookup={(float(r.canonical_longitude),float(r.canonical_latitude)):int(r.physical_site_id) for r in sites.itertuples()}
    ids=[lookup[(float(r.canonical_longitude),float(r.canonical_latitude))] if r.is_cell_site==1 else None for r in old.itertuples()]
    nf=extractor.extract(old.canonical_longitude,old.canonical_latitude,ids)
    new=old.copy()
    for column in nf.columns:
        if column=='municipality_name':
            new['municipality_polygon_v2']=nf[column]
        else:
            new[column]=nf[column]
    new.to_parquet(output/'dataset_v2.parquet',index=False)
    metadata['v2_dataset_sha256']=sha256(output/'dataset_v2.parquet')
    metadata['missing_feature_counts']={c:int(new[c].isna().sum()) for c in SUITABILITY_FEATURE_COLS}
    metadata['historical_grouping_policy']='Frozen municipality labels kept for controlled comparison; actual polygon membership is municipality_polygon_v2. Offshore/outside polygons remain unknown in v2.'
    trained,comparison=train_comparison(old,new,output)
    print(json.dumps(comparison,indent=2),flush=True)
    print('Computing Tripoli v2 circle and hex population features...',flush=True)
    grid=gpd.read_file(H3_GRID_GEOJSON_TEMPLATE.format(city='Tripoli'))
    hf=extractor.extract(grid.centroid_lon,grid.centroid_lat)
    hf['h3_index']=grid.h3_index.to_numpy()
    hex_stats=[extractor.population.zonal_population(geom) for geom in grid.geometry]
    for column,key in [('population_hex','population'),('population_hex_observed','observed_population'),('population_hex_valid_fraction','valid_fraction')]:
        hf[column]=[s[key] for s in hex_stats]
    previous=pd.read_parquet(H3_FEATURE_TABLE_PARQUET_TEMPLATE.format(city='Tripoli'))
    from antenna_cell_placement.h3_grid import PHASE2_COLUMN_PREFIXES
    carried=[c for c in previous if c.startswith(PHASE2_COLUMN_PREFIXES) or c.startswith('existing_sites_')]
    hf=hf.merge(previous[['h3_index']+carried],on='h3_index',how='left',validate='one_to_one')
    hf.to_parquet(output/'h3_features_Tripoli_v2.parquet',index=False)
    from antenna_cell_placement.expansion_score import mask_unscorable_hexes,compute_expansion_need_score
    scorable,masked=mask_unscorable_hexes(hf)
    scored=compute_expansion_need_score(scorable)
    # Neutralize unknown component evidence; prediction uses v2 model contract.
    scored['placement_suitability_score']=trained.predict_proba(scored)[:,1]
    scored['combined_priority_score']=scored.expansion_need_score*(0.75+0.5*scored.placement_suitability_score)
    scored=scored.sort_values('combined_priority_score',ascending=False).reset_index(drop=True)
    scored['expansion_rank']=np.arange(1,len(scored)+1)
    scored.to_csv(output/'h3_scores_Tripoli_v2.csv',index=False)
    scored_map=grid[['h3_index','geometry']].merge(scored,on='h3_index',validate='one_to_one')
    scored_map.to_file(output/'h3_scores_Tripoli_v2.geojson',driver='GeoJSON')
    metadata['h3']={'hexes':len(hf),'scored':len(scored),'masked':masked,
                    'partial_population_hexes':int((hf.population_hex_valid_fraction<0.99).sum())}
    if rooftops:
        from antenna_cell_placement.rooftop_candidates import shortlist_buildings,export_rooftops
        selected=scored_map.sort_values('expansion_rank').head(20)
        roofs,roof_audit=shortlist_buildings(selected)
        if len(roofs):
            rf=extractor.extract(roofs.canonical_longitude,roofs.canonical_latitude)
            for col in ('elevation_m','dist_to_nearest_road_m','dist_to_nearest_site_m','population_sum_3km','feature_version'):
                roofs[col]=rf[col].to_numpy()
        export_rooftops(roofs,output)
        metadata['rooftop_audit']=roof_audit
    metadata['raw_database_unchanged']=sha256(RAW_SQLITE_PATH)==before
    metadata['serving_model_unchanged']=sha256(SUITABILITY_MODEL_PATH)==serving_before
    metadata['completed_utc']=datetime.now(timezone.utc).isoformat()
    metadata['outputs']=[p.name for p in output.iterdir() if p.is_file()]
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Phase 2 complete:',output,flush=True)
    return metadata


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=None)
    parser.add_argument('--frozen-dataset',type=Path,default=None)
    args=parser.parse_args()
    run_phase2(args.output_dir,args.frozen_dataset)
