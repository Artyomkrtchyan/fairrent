"""Validate the shipped municipal boundary independently of synthetic API fixtures."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from backend.valuation_coverage import Coverage, OutsideCoverage

BOUNDARY = Path(__file__).resolve().parents[2] / 'infra/valuation-coverage/coverage.geojson'


def test_boundary_identity_provenance_and_coordinate_order(monkeypatch):
    feature = json.loads(BOUNDARY.read_text(encoding='utf-8'))
    props = feature['properties']
    assert feature['type'] == 'Feature' and feature['id'] == 'AM01'
    assert props['name'] == 'Yerevan'
    assert props['source'].startswith('https://gis.yerevan.am/')
    assert 'Not specified' in props['license']
    assert len(props['source_export_sha256']) == 64
    district_bytes = BOUNDARY.with_name('districts.geojson').read_bytes()
    assert props['district_snapshot_sha256'] == hashlib.sha256(district_bytes).hexdigest()
    geometry = feature['geometry']
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    for polygon in polygons:
        for ring in polygon:
            assert len(ring) >= 4 and ring[0] == ring[-1]
            assert all(44 < lon < 45 and 39 < lat < 41 for lon, lat in ring)
    monkeypatch.setenv('VALUATION_COVERAGE_FILE', str(BOUNDARY))
    coverage = Coverage()
    expected = hashlib.sha256(json.dumps(feature, sort_keys=True).encode()).hexdigest()
    assert coverage.version == props['version'] + ':' + expected


def test_real_boundary_with_postgis(monkeypatch):
    dsn = os.environ.get('C03_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set C03_TEST_DATABASE_URL for real boundary PostGIS checks')
    import psycopg
    from types import SimpleNamespace
    monkeypatch.setenv('VALUATION_COVERAGE_FILE', str(BOUNDARY))
    coverage = Coverage()
    with psycopg.connect(dsn) as connection:
        # Republic Square and Barekamutyun are inside the city.
        for lat, lon in [(40.17767, 44.51562), (40.19696, 44.49440)]:
            coverage.check(connection, SimpleNamespace(latitude=lat, longitude=lon))
        # Gyumri and Abovyan are outside the city.
        for lat, lon in [(40.789, 43.847), (40.2739, 44.6256)]:
            with pytest.raises(OutsideCoverage):
                coverage.check(connection, SimpleNamespace(latitude=lat, longitude=lon))
        # ST_Covers includes the municipal boundary itself.
        geom = coverage.geometry
        point = geom['coordinates'][0][0] if geom['type'] == 'Polygon' else geom['coordinates'][0][0][0]
        coverage.check(connection, SimpleNamespace(latitude=point[1], longitude=point[0]))
