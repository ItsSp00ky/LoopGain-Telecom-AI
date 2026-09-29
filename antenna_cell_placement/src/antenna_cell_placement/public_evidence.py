"""Audit public official statistics against existing planning evidence."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

from antenna_cell_placement.config import ADMIN2_GEOJSON_PATH, EXTERNAL_DATA_DIR, REPORTS_DIR, WORLDPOP_TIF_PATH
from antenna_cell_placement.population import density_to_population_counts


SOURCE_DIR = EXTERNAL_DATA_DIR / 'libya_official_2022_2025'


def _name(value):
    value = unicodedata.normalize('NFKC', str(value)).strip()
    value = re.sub('[أإآ]', 'ا', value)
    value = value.replace('ى', 'ي').replace('ئ', 'ي').replace('ة', 'ه')
    return re.sub(r'\s+', ' ', value)


def _verify_sources(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, source in manifest['sources'].items():
        content = (directory / name).read_bytes()
        if len(content) != source['bytes'] or hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError(f'Official source size or SHA-256 mismatch: {name}')
    return manifest


def evaluate_public_evidence(directory=SOURCE_DIR, output_path=REPORTS_DIR / 'public_evidence_review.json',
                             boundary_path=ADMIN2_GEOJSON_PATH, raster_path=WORLDPOP_TIF_PATH):
    directory = Path(directory)
    manifest = _verify_sources(directory)
    population = pd.read_csv(directory / 'population_by_region_2022.csv', encoding='utf-8-sig')
    if set(population.columns) != {'Area', 'Year', 'Sex', 'population_number'}:
        raise ValueError('Official population CSV schema changed')
    if len(population) != 44 or set(population.Year) != {2022} or set(population.Sex) != {'Male', 'Female'}:
        raise ValueError('Official population rows or reporting year changed')
    if population.duplicated(['Area', 'Year', 'Sex']).any() or population.population_number.isna().any():
        raise ValueError('Official population has missing or duplicate region/sex values')
    population['population_number'] = pd.to_numeric(population.population_number, errors='raise')
    if (population.population_number < 0).any():
        raise ValueError('Official population has negative counts')
    official = population.groupby('Area').population_number.sum()
    boundaries = gpd.read_file(boundary_path)
    if len(boundaries) != 22 or boundaries.adm2_pcode.duplicated().any():
        raise ValueError('Expected 22 distinct supplied municipality boundaries')
    boundary_names = {_name(row.adm2_name1): row for row in boundaries.itertuples()}
    if len(boundary_names) != 22:
        raise ValueError('Normalized municipality names are not unique')
    comparisons, unmatched = [], []
    with rasterio.open(raster_path) as raster:
        if raster.crs.to_epsg() != 4326:
            raise ValueError('WorldPop comparison requires WGS84 geographic pixels')
        for arabic_name, count in official.items():
            boundary = boundary_names.get(_name(arabic_name))
            if boundary is None:
                unmatched.append(arabic_name)
                continue
            clipped, transform = mask(raster, [mapping(boundary.geometry)], crop=True, filled=False)
            density = clipped[0].filled(0).astype('float64')
            density[density < 0] = 0
            worldpop = float(density_to_population_counts(density, transform).sum())
            comparisons.append({'source_region_ar': arabic_name, 'municipality': boundary.adm2_name,
                                'adm2_pcode': boundary.adm2_pcode, 'official_2022': int(count),
                                'worldpop_2020': round(worldpop, 1),
                                'worldpop_to_official_ratio': round(worldpop / count, 4) if count else None})
    comparisons.sort(key=lambda row: row['adm2_pcode'])
    technology = pd.read_csv(directory / 'mobile_users_by_technology_2019_2025.csv',
                             encoding='utf-8-sig', skiprows=1, thousands=',')
    if list(technology.columns) != ['السنة', '3G/2G', 'LTE/4G', 'Total']:
        raise ValueError('Official mobile technology CSV schema changed')
    if technology['السنة'].tolist() != list(range(2019, 2026)):
        raise ValueError('Official mobile technology years changed')
    if not (technology['3G/2G'] + technology['LTE/4G']).eq(technology.Total).all():
        raise ValueError('Official technology totals do not sum')
    yearly = [{'year': int(row[0]), 'reported_2g_3g': int(row[1]),
               'reported_lte_4g': int(row[2]), 'reported_total': int(row[3]),
               'lte_4g_share_pct': round(100 * row[2] / row[3], 2)}
              for row in technology.itertuples(index=False, name=None)]
    matched_official = sum(row['official_2022'] for row in comparisons)
    matched_worldpop = sum(row['worldpop_2020'] for row in comparisons)
    report = {
        'status': 'review_only', 'source_manifest': manifest,
        'population_comparison': {
            'official_regions': len(official), 'matched_municipalities': len(comparisons),
            'unmatched_official_regions_ar': sorted(unmatched),
            'official_total_all_regions_2022': int(official.sum()),
            'official_total_matched_2022': matched_official,
            'worldpop_total_matched_2020': round(matched_worldpop, 1),
            'matched_worldpop_to_official_ratio': round(matched_worldpop / matched_official, 4),
            'raster_method': 'WorldPop people/km2 times ellipsoidal source-pixel area; pixel-center municipality mask',
            'rows': comparisons,
        },
        'mobile_technology': {'rows': yearly, 'interpretation':
                              'National provider-reported figures; not spatial coverage, unique subscribers, traffic, or RF measurements.'},
        'decision': 'Use for source-quality and national context review only. Leave placement scores unchanged.',
        'limitations': ['Official 2022 population and WorldPop 2020 refer to different years.',
                        'Unmatched official regions have no safe one-to-one crosswalk to supplied boundaries.',
                        'Population comparison uses center-of-pixel assignment at municipality edges.',
                        'National technology totals cannot identify local service gaps or sector settings.'],
    }
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
