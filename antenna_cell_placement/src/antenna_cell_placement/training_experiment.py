"""Reproducible diagnostic experiment; never overwrites the serving model."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

from antenna_cell_placement.config import CLEANED_SITES_PARQUET, REPORTS_DIR
from antenna_cell_placement.evaluation import binary_metrics, generate_hard_negatives, LGB_PARAMS
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS, generate_synthetic_negative_samples

# These regions were already inspected in the historical report: a development
# benchmark, NOT a new blind final test. A prospective test remains necessary.
TEST_MUNICIPALITIES = [
    'Wadi Ashshati', 'Almarj', 'Derna', 'Ejdabia', 'Sebha', 'Nalut',
    'Al Jabal Al Akhdar', 'Tobruk', 'Aljfara',
]


def assign_splits(data):
    """Keep a complete municipality in one split, with a stable membership list."""
    result = data.copy()
    if result['municipality_name'].isna().any():
        raise ValueError('Municipality is required for every training row')
    result['split'] = np.where(result.municipality_name.isin(TEST_MUNICIPALITIES), 'test', 'development')
    for split in ('development', 'test'):
        part = result[result.split == split]
        if set(part.is_cell_site.unique()) != {0, 1}:
            raise ValueError(f'{split} needs both classes')
    return result


def metric_block(data, scores):
    result = binary_metrics(data.is_cell_site, scores)
    result['brier_score'] = float(brier_score_loss(data.is_cell_site, scores))
    result['population_only_roc_auc'] = float(roc_auc_score(data.is_cell_site, data.population_sum_5km))
    for k in (20, 50):
        top = np.argsort(-np.asarray(scores), kind='stable')[:min(k, len(data))]
        result[f'precision_at_{k}'] = float(data.iloc[top].is_cell_site.mean())
    return result


def run_training_experiment(output_dir=None):
    """Freeze examples/splits, grouped CV on development only, then test once."""
    if output_dir is None:
        output_dir = REPORTS_DIR / ('experiment_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    sites = pd.read_parquet(CLEANED_SITES_PARQUET)
    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    extractor.set_existing_sites(sites)
    positives = sites.assign(is_cell_site=1, sample_kind='observed_site')
    standard = generate_synthetic_negative_samples(sites, extractor, n_negatives=1500)
    standard['sample_kind'] = 'synthetic_background_corridor'
    # Generate each partition separately and enforce destination membership.
    hard_parts = []
    for is_test, seed in ((False, 17), (True, 27)):
        subset = sites[sites.municipality_name.isin(TEST_MUNICIPALITIES) == is_test]
        part = generate_hard_negatives(subset, extractor, n=1500, seed=seed)
        part['sample_kind'] = 'synthetic_hard'
        hard_parts.append(part)
    cols = SUITABILITY_FEATURE_COLS + ['canonical_latitude', 'canonical_longitude',
                                       'municipality_name', 'is_cell_site', 'sample_kind']
    data = pd.concat([frame[cols] for frame in [positives, standard, *hard_parts]], ignore_index=True)
    data = data.drop_duplicates(['canonical_latitude', 'canonical_longitude'], keep='first').reset_index(drop=True)
    data = assign_splits(data)
    data.insert(0, 'row_id', np.arange(len(data)))
    if not np.isfinite(data[SUITABILITY_FEATURE_COLS].to_numpy()).all():
        raise ValueError('Non-finite model inputs: audit source features before training')
    dataset_path = output_dir / 'dataset.parquet'
    data.to_parquet(dataset_path, index=False)
    dev = data[data.split == 'development'].reset_index(drop=True)
    test = data[data.split == 'test'].reset_index(drop=True)
    params = {**LGB_PARAMS, 'n_jobs': 2}
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'input_parquet_sha256': hashlib.sha256(CLEANED_SITES_PARQUET.read_bytes()).hexdigest(),
        'dataset_sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        'test_municipalities': TEST_MUNICIPALITIES, 'parameters': params,
        'features': SUITABILITY_FEATURE_COLS,
        'counts': data.groupby(['split','sample_kind']).size().to_dict(),
        'python': platform.python_version(),
        'packages': {name: version(name) for name in ('numpy','pandas','scikit-learn','lightgbm','geopandas')},
        'limitations': [
            'Test municipalities already inspected in historical evaluation; not a blind prospective test.',
            'Synthetic non-sites are unlabeled locations, not confirmed unsuitable sites.',
            'Network features use the full observed inventory; conditional inventory task, not hidden-network recovery.',
            'Legacy population windows and nationwide UTM33 distances remain uncorrected.',
            'Scores are class probabilities for this sampled task, not probabilities that new deployment is needed.',
        ],
    }
    manifest['counts'] = {f'{split}/{kind}': int(count) for (split,kind),count in manifest['counts'].items()}
    (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    oof = np.full(len(dev), np.nan)
    folds = []
    splitter = GroupKFold(n_splits=5)
    for fold, (train_idx, val_idx) in enumerate(splitter.split(dev, dev.is_cell_site, dev.municipality_name)):
        train, val = dev.iloc[train_idx], dev.iloc[val_idx]
        model = LGBMClassifier(**params).fit(train[SUITABILITY_FEATURE_COLS], train.is_cell_site)
        scores = model.predict_proba(val[SUITABILITY_FEATURE_COLS])[:,1]
        oof[val_idx] = scores
        folds.append({'fold':fold, 'municipalities':sorted(val.municipality_name.unique().tolist()),
                      'metrics':metric_block(val, scores)})
    model = LGBMClassifier(**params).fit(dev[SUITABILITY_FEATURE_COLS], dev.is_cell_site)
    scores = model.predict_proba(test[SUITABILITY_FEATURE_COLS])[:,1]
    hard_mask = test.sample_kind.isin(['observed_site','synthetic_hard']).to_numpy()
    report = {
        'development_grouped_cv': metric_block(dev,oof), 'folds':folds,
        'test':metric_block(test,scores),
        'test_hard_negative':metric_block(test[hard_mask],scores[hard_mask]),
        'promotion_status':'experimental artifact; not promoted to serving model',
    }
    joblib.dump(model, output_dir/'suitability_experiment.joblib')
    predictions = pd.concat([dev.assign(score=oof,prediction_kind='grouped_out_of_fold'),
                             test.assign(score=scores,prediction_kind='held_out')],ignore_index=True)
    predictions[['row_id','split','sample_kind','is_cell_site','score','prediction_kind']].to_csv(output_dir/'predictions.csv',index=False)
    (output_dir/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'output_dir':str(output_dir), 'test':report['test'],
                      'test_hard_negative':report['test_hard_negative']},indent=2))
    return report
