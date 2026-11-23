"""Real B07 package through the C04 HTTP/service boundary; synthetic training data only."""
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.valuation_routes import service
from backend.valuation_service import ValuationService
from ml import inference
from ml.tests.test_inference import world, package, NOW  # Reuse the checksummed synthetic artifact fixtures.


@pytest.fixture
def api(package, world, monkeypatch):
    monkeypatch.setenv(inference.PACKAGE_ENV_VAR, str(world['pkg']))
    monkeypatch.delenv('VALUATION_DISTRICTS_FILE', raising=False)
    inference._DEFAULT.update(package=None, error=None, path=None)
    records = [SimpleNamespace(id=UUID(int=i), latitude=40.18, longitude=44.51,
        price_monthly_normalized=price, area_sqm=50, rooms=2, district_id='kentron',
        last_seen_at=NOW-timedelta(days=1), dedup_group_id=None, status='active')
        for i, price in enumerate([500, 600, 700], 1)]
    class Connection:
        def execute(self, command):
            pass
    class Repository:
        saved = []
        def connection(self):
            return nullcontext(Connection())
        def candidates(self, connection, query, now):
            return records, 'observed-test-snapshot'
        def save(self, connection, query, result, dataset_version, geography_version, **metadata):
            self.saved.append((result, metadata))
    class Coverage:
        version = 'synthetic-city:checksum'
        def check(self, connection, query):
            pass
    repository = Repository()
    app.dependency_overrides[service] = lambda: ValuationService(repository=repository,
        coverage=Coverage(), clock=lambda: NOW)
    with TestClient(app) as client:
        yield client, repository, records
    app.dependency_overrides.clear()
    inference._DEFAULT.update(package=None, error=None, path=None)


QUERY = dict(latitude=40.18, longitude=44.51, area_sqm=65, rooms=2, floor=3, total_floors=9)


def test_real_package_interval_factors_ontology_and_audit(api):
    client, repository, records = api
    response = client.post('/api/v1/valuations', json={**QUERY, 'asking_price_usd_month':10000})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['valuation_assessment']['assessment_status'] == 'VALUATION_SUCCESS'
    assert result['ml_prediction_interval']['calibration_version']
    assert result['feature_attributions']
    assert result['versions']['rule_engine_version'].startswith('b06-')
    assert result['price_status'] == 'above_range'
    audit = repository.saved[-1][1]['inference_provenance']
    assert audit['package_version'] == 'b07-test'
    assert audit['calibration_version'] and audit['snapshot_sha256']
    assert audit['ontology']['rules_version'] == result['versions']['rule_engine_version']
    assert audit['observed_dataset_version'] == 'observed-test-snapshot'
    # Asking price affects only interval comparison, never prediction or baseline deviation.
    second = client.post('/api/v1/valuations', json={**QUERY, 'asking_price_usd_month':1}).json()
    assert second['valuation_assessment'] == result['valuation_assessment']
    assert second['price_status'] == 'below_range'


def test_coordinate_request_uses_training_fitted_reference(api, package):
    client, repository, records = api
    response = client.post('/api/v1/valuations', json=dict(latitude=40.18, longitude=44.51))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['kind'] == 'area_reference'
    assert result['valuation_assessment']['assessment_status'] == 'COORDINATE_BASELINE_ONLY'
    assert result['valuation_assessment']['estimated_price_usd'] == 600
    assert 'Training-fitted' in result['area_reference']['note']
    assert all(value is None for value in result['ml_prediction_interval'].values())


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'runtime'])
def test_package_failure_abstains_and_persists_no_baseline_substitution(api, monkeypatch, tmp_path, failure):
    import shutil
    client, repository, records = api
    if failure in ('missing', 'corrupt'):
        target = tmp_path / 'package'
        if failure == 'corrupt':
            import os
            shutil.copytree(os.environ[inference.PACKAGE_ENV_VAR], target)
            (target / 'model.cbm').write_bytes(b'broken')
        monkeypatch.setenv(inference.PACKAGE_ENV_VAR, str(target))
    else:
        monkeypatch.setattr(inference.tc, 'predict_usd', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    response = client.post('/api/v1/valuations', json=QUERY)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['valuation_assessment']['assessment_status'] == 'INSUFFICIENT_DATA_ABSTAIN'
    assert result['valuation_assessment']['estimated_price_usd'] is None
    assert result['observed_market_statistics']['cluster_mean_price_usd'] == 600
    assert result['feature_attributions'] == []
    assert all(value is None for value in result['ml_prediction_interval'].values())
    assert repository.saved[-1][1]['inference_provenance']['fallback']


def test_gate_and_sparse_cohort_abstain(api):
    client, repository, records = api
    for query in ({**QUERY, 'area_sqm':900}, QUERY):
        if query == QUERY:
            del records[1:]
        response = client.post('/api/v1/valuations', json=query)
        assert response.status_code == 200, response.text
        assert response.json()['valuation_assessment']['estimated_price_usd'] is None


def test_source_cutoff_controls_freshness_and_outside_package_coverage(api):
    client, repository, records = api
    for record in records:
        record.last_seen_at = NOW-timedelta(days=61)
    response = client.post('/api/v1/valuations', json=QUERY)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['freshness']['is_stale'] is True
    assert result['observed_market_statistics']['data_freshness_days'] is None
    assert result['observed_market_statistics']['comparables_count'] == 0
    assert result['valuation_assessment']['estimated_price_usd'] is None
    assert repository.saved[-1][1]['inference_provenance']['abstention_reason'] == 'insufficient_observed_data'
    previous_saves = len(repository.saved)
    outside = client.post('/api/v1/valuations', json={**QUERY, 'latitude':41.7})
    assert outside.status_code == 400
    assert outside.json()['code'] == 'outside_coverage'
    assert len(repository.saved) == previous_saves
