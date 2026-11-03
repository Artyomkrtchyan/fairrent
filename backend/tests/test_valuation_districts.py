"""District snapshot validation and real PostGIS point-in-polygon checks."""
import json
import os
from pathlib import Path

import pytest

from backend.valuation_coverage import CoverageUnavailable
from backend.valuation_districts import DISTRICT_IDS, DistrictRegistry

PATH = Path(__file__).resolve().parents[2] / 'infra/valuation-coverage/districts.geojson'


def test_registry_has_all_twelve_districts_and_traceable_provenance():
    registry = DistrictRegistry(PATH)
    data = json.loads(PATH.read_text(encoding='utf-8'))
    assert {f['properties']['district_id'] for f in registry.features} == DISTRICT_IDS
    assert len(registry.features) == 12
    assert data['properties']['source'].startswith('https://gis.yerevan.am/')
    assert 'Not specified' in data['properties']['license']
    assert len(data['properties']['source_export_sha256']) == 64
    assert registry.version.startswith(data['properties']['version'] + ':')


@pytest.mark.parametrize('problem', ['missing_district', 'duplicate', 'no_source', 'wrong_geometry'])
def test_invalid_district_registry_fails_closed(tmp_path, problem):
    data = json.loads(PATH.read_text(encoding='utf-8'))
    if problem == 'missing_district':
        data['features'].pop()
    elif problem == 'duplicate':
        data['features'][0] = data['features'][1]
    elif problem == 'no_source':
        data['properties']['source'] = ''
    else:
        data['features'][0]['geometry']['type'] = 'Point'
    path = tmp_path / 'invalid.geojson'
    path.write_text(json.dumps(data))
    with pytest.raises(CoverageUnavailable):
        DistrictRegistry(path)


def test_actual_district_resolution_with_postgis():
    dsn = os.environ.get('C03_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set C03_TEST_DATABASE_URL for district PostGIS checks')
    import psycopg
    registry = DistrictRegistry(PATH)
    points = [(40.17767,44.51562), (40.19696,44.49440), (40.2139,44.5714),
              (40.1408,44.538), (40.088,44.548), (40.14503,44.48551),
              (40.789,43.847), (40.19459995909475,44.51731204925373)]
    with psycopg.connect(dsn) as connection:
        resolved = registry.resolve_many(connection, points)
    assert resolved == [('kentron','Kentron'), ('arabkir','Arabkir'), ('avan','Avan'),
                        ('erebuni','Erebuni'), ('nubarashen','Nubarashen'),
                        ('shengavit','Shengavit'), None, None]
