"""C04 contract and PostgreSQL integration using explicitly synthetic coverage."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.listing_models import ListingData
from backend.listing_repository import publish_listing
from backend.tests.test_listing_postgres import database, validate_contract
from backend.valuation_gateway import BaselineGateway
from backend.valuation_routes import service
from backend.valuation_service import ValuationService

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
QUERY = dict(latitude=40.18, longitude=44.51, area_sqm=50, rooms=2)


@pytest.fixture
def valuation_db(database, monkeypatch, tmp_path):
    with database() as connection:
        connection.execute('CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public')
        connection.execute((Path(__file__).resolve().parents[1] / 'sql' / '002_valuation_estimates.sql').read_text(encoding='utf-8-sig'))
    coverage = dict(type='Feature', properties=dict(version='synthetic-test-only', source='synthetic test rectangle'),
        geometry=dict(type='Polygon', coordinates=[[[44.4,40.1],[44.6,40.1],[44.6,40.3],[44.4,40.3],[44.4,40.1]]]))
    path = tmp_path / 'coverage.geojson'
    path.write_text(json.dumps(coverage))
    monkeypatch.setenv('VALUATION_COVERAGE_FILE', str(path))
    app.dependency_overrides[service] = lambda: ValuationService(clock=lambda: NOW)
    try:
        yield database
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def api(valuation_db):
    with TestClient(app) as client:
        yield client


def seed(database, document, *, changes=None):
    changes = changes or {}
    for i, price in enumerate([500, 600, 700], 1):
        record = ListingData.model_validate({**document, 'id':str(UUID(int=i)),
            'external_id':f'valuation-{i}', 'latitude':40.18, 'longitude':44.51,
            'coordinate_confidence':'exact', 'area_sqm':50, 'rooms':2,
            'price_monthly_normalized':price, 'first_seen_at':NOW-timedelta(days=100),
            'last_seen_at':NOW-timedelta(days=1), 'status':'active', 'dedup_group_id':None,
            **changes})
        with database() as connection:
            publish_listing(connection, record)


# Import the existing synthetic listing fixture without duplicating its contract.
from backend.tests.conftest import listing_document


def assess(api, query=QUERY):
    response = api.post('/api/v1/valuations', json=query)
    assert response.status_code == 200, response.text
    validate_contract(response.json(), 'ValuationResponse')
    assert response.headers['X-Request-ID'] == response.json()['request_id']
    return response.json()


def test_success_persisted_with_versions(api, valuation_db, listing_document):
    seed(valuation_db, listing_document)
    result = assess(api)
    assert result['kind'] == 'property_valuation'
    assert result['valuation_assessment']['estimated_price_usd'] == 600
    assert result['observed_market_statistics']['comparables_count'] == 3
    assert result['observed_market_statistics']['observed_price_std_dev_usd'] == 100
    assert result['observed_market_statistics']['observed_price_std_dev_per_sqm_usd'] == 2
    assert all(v is None for v in result['ml_prediction_interval'].values())
    with valuation_db() as connection:
        row = connection.execute('SELECT dataset_version, model_version, coverage_version, response_document FROM api_valuation_estimates').fetchone()
    assert len(row[0]) == 64
    assert row[1] == BaselineGateway.model_version
    assert row[2].startswith('synthetic-test-only:')
    assert row[3] == result


@pytest.mark.parametrize('query', [dict(latitude=40.18,longitude=44.51),
    dict(latitude=40.18,longitude=44.51,area_sqm=90)])
def test_incomplete_features_use_disclosed_reference(api, valuation_db, listing_document, query):
    seed(valuation_db, listing_document)
    result = assess(api, query)
    assert result['kind'] == 'area_reference'
    assert result['valuation_assessment']['assessment_status'] == 'COORDINATE_BASELINE_ONLY'
    assert result['valuation_assessment']['estimated_price_usd'] == 720
    assert result['area_reference']['reference_area_sqm'] == 60
    assert 'configured' in result['area_reference']['note']
    assert result['price_status'] == 'insufficient_data'


def test_empty_and_singleton_statistics(api, valuation_db, listing_document):
    result = assess(api)
    assert result['valuation_assessment']['assessment_status'] == 'INSUFFICIENT_DATA_ABSTAIN'
    assert result['freshness']['is_stale'] is True
    assert result['observed_market_statistics']['cluster_mean_price_usd'] is None
    seed(valuation_db, listing_document, changes={'dedup_group_id':'same-property'})
    result = assess(api)
    assert result['observed_market_statistics']['comparables_count'] == 1
    assert result['observed_market_statistics']['observed_price_std_dev_usd'] is None
    assert result['valuation_assessment']['estimated_price_usd'] is None


@pytest.mark.parametrize('changes', [
    {'status':'inactive'}, {'latitude':40.29}, {'rooms':3},
    {'last_seen_at':NOW+timedelta(days=1)}, {'last_seen_at':NOW-timedelta(days=61)},
])
def test_excluded_inventory_never_estimated(api, valuation_db, listing_document, changes):
    seed(valuation_db, listing_document, changes=changes)
    result = assess(api)
    assert result['observed_market_statistics']['comparables_count'] == 0
    assert result['valuation_assessment']['estimated_price_usd'] is None


def test_no_old_result_reused_after_source_update(api, valuation_db, listing_document):
    seed(valuation_db, listing_document)
    first = assess(api)
    seed(valuation_db, listing_document, changes={'price_monthly_normalized':900})
    second = assess(api)
    assert first['valuation_assessment']['estimated_price_usd'] == 600
    assert second['valuation_assessment']['estimated_price_usd'] == 900
    with valuation_db() as connection:
        assert connection.execute('SELECT count(DISTINCT dataset_version) FROM api_valuation_estimates').fetchone()[0] == 2


def test_missing_area_counts_only_monthly(api, valuation_db, listing_document):
    seed(valuation_db, listing_document, changes={'area_sqm':None})
    result = assess(api)
    assert result['observed_market_statistics']['comparables_count'] == 3
    assert result['observed_market_statistics']['area_comparables_count'] == 0
    assert result['valuation_assessment']['estimated_price_usd'] is None


def test_outside_and_unconfigured_coverage(api, monkeypatch):
    response = api.post('/api/v1/valuations', json={**QUERY,'latitude':0,'longitude':0})
    assert response.status_code == 400
    assert response.json()['code'] == 'outside_coverage'
    monkeypatch.delenv('VALUATION_COVERAGE_FILE')
    response = api.post('/api/v1/valuations', json=QUERY)
    assert response.status_code == 503
    assert response.json()['code'] == 'service_unavailable'


def test_model_exception_does_not_write_or_serve_success(api, valuation_db, listing_document):
    seed(valuation_db, listing_document)
    class Broken:
        def __init__(self, *args, **kwargs):
            raise RuntimeError('synthetic model failure')
    app.dependency_overrides[service] = lambda: ValuationService(provider=Broken, clock=lambda: NOW)
    response = api.post('/api/v1/valuations', json=QUERY)
    assert response.status_code == 503
    with valuation_db() as connection:
        assert connection.execute('SELECT count(*) FROM api_valuation_estimates').fetchone()[0] == 0


@pytest.mark.parametrize('changes', [dict(extra=1),dict(radius_m=99),dict(window_days=91),
    dict(rooms=2.5),dict(area_sqm=0),dict(latitude=91),dict(floor=10,total_floors=2),
    dict(asking_price_usd_month=None)])
def test_validation(api, changes):
    response = api.post('/api/v1/valuations', json={**QUERY,**changes})
    assert response.status_code == 422
    validate_contract(response.json(), 'Error')


def test_versioned_provider_interval_and_asking_price_isolation(api, valuation_db, listing_document):
    seed(valuation_db, listing_document)
    class PackagedProvider(BaselineGateway):
        model_version = 'synthetic-versioned-package-v1'
        def assess(self, payload, **kwargs):
            assert 'asking_price_usd_month' not in payload
            result = super().assess(payload, **kwargs)
            result['ml_prediction_interval'] = dict(lower_bound_usd=550, upper_bound_usd=650,
                confidence_level=0.95, interval_width_usd=100, calibration_version='synthetic-calibration-v1')
            result['feature_attributions'] = [dict(feature='area_sqm',impact_pct=5,direction='positive')]
            return result
    app.dependency_overrides[service] = lambda: ValuationService(provider=PackagedProvider, clock=lambda: NOW)
    result = assess(api, {**QUERY,'asking_price_usd_month':700})
    assert result['versions']['model_version'] == 'synthetic-versioned-package-v1'
    assert result['price_status'] == 'above_range'
    assert result['ml_prediction_interval']['calibration_version'] == 'synthetic-calibration-v1'
    assert result['feature_attributions'][0]['feature'] == 'area_sqm'


@pytest.mark.parametrize('invalid', ['nan', 'interval'])
def test_invalid_model_results_are_not_persisted(api, valuation_db, listing_document, invalid):
    seed(valuation_db, listing_document)
    class InvalidProvider(BaselineGateway):
        def assess(self, payload, **kwargs):
            result = super().assess(payload, **kwargs)
            if invalid == 'nan':
                result['valuation_assessment']['estimated_price_usd'] = float('nan')
            else:
                result['ml_prediction_interval'] = dict(lower_bound_usd=700,upper_bound_usd=800,
                    confidence_level=0.95,interval_width_usd=100,calibration_version='synthetic-invalid')
            return result
    app.dependency_overrides[service] = lambda: ValuationService(provider=InvalidProvider, clock=lambda: NOW)
    response = api.post('/api/v1/valuations',json=QUERY)
    assert response.status_code == 503
    with valuation_db() as connection:
        assert connection.execute('SELECT count(*) FROM api_valuation_estimates').fetchone()[0] == 0


def test_request_query_parameters_rejected(api):
    assert api.post('/api/v1/valuations?unknown=1',json=QUERY).status_code == 422


def test_requested_radius_above_b03_default_is_honored(api, valuation_db, listing_document):
    seed(valuation_db, listing_document, changes={'latitude':40.215})
    assert assess(api)['observed_market_statistics']['comparables_count'] == 0
    result = assess(api, {**QUERY,'radius_m':5000})
    assert result['observed_market_statistics']['comparables_count'] == 3
    assert result['valuation_assessment']['estimated_price_usd'] == 600
