"""Real B07 -> C04 exclusion/audit -> B06 signals -> protected C05 queue."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.generate_signals import generate, migrate
from backend.listing_models import ListingData
from backend.listing_repository import publish_listing
from backend.reviewer_auth import issue_session
from backend.tests.test_listing_postgres import database, validate_contract
from ml.tests.test_inference import world, package, NOW


@pytest.fixture
def market(database, listing_document, monkeypatch):
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('VALUATION_COVERAGE_FILE', str(root / 'infra/valuation-coverage/coverage.geojson'))
    monkeypatch.setenv('VALUATION_DISTRICTS_FILE', str(root / 'infra/valuation-coverage/districts.geojson'))
    records = []
    with database() as connection:
        connection.execute('CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public')
        migrate(connection, with_valuations=True)
        for i, price in enumerate([10000,10000,500,600,700],1):
            record = ListingData.model_validate({**listing_document, 'id':str(UUID(int=i)),
                'external_id':f'c05-price-{i}', 'latitude':40.18, 'longitude':44.51,
                'coordinate_confidence':'exact', 'area_sqm':65, 'rooms':2, 'floor':3, 'total_floors':9,
                'title':None, 'description':None, 'district_id':'kentron', 'price_monthly_normalized':price,
                'dedup_group_id':'subject-group' if i<3 else None, 'status':'active',
                'first_seen_at':NOW-timedelta(days=10), 'last_seen_at':NOW-timedelta(days=1)})
            publish_listing(connection, record)
            records.append(record)
    return records


def run(database, package):
    with database() as connection:
        return generate(connection, package=package, clock=lambda: NOW)


def target_audits(connection, subject):
    return connection.execute("SELECT response_document,inference_provenance FROM api_valuation_estimates "
        "WHERE inference_provenance->>'subject_listing_id'=%s ORDER BY generated_at,request_id", (str(subject.id),)).fetchall()


def test_calibrated_signal_excludes_subject_duplicates_and_is_idempotent(database, market, package):
    subject = market[0]
    summary = run(database, package)
    assert summary['price_checks'] == 'calibrated_B07' and summary['calibrated'] == 5
    with database() as connection:
        response, provenance = target_audits(connection, subject)[0]
        assert response['observed_market_statistics']['comparables_count'] == 3
        assert response['observed_market_statistics']['cluster_mean_price_usd'] == 600
        assert provenance['excluded_duplicate_group'] == 'subject-group'
        assert provenance['package_version'] == 'b07-test'
        signal, = connection.execute('SELECT document FROM api_listing_signals WHERE listing_id=%s AND active', (subject.id,)).fetchone()
        assert signal['category'] == 'price_anomaly'
        assert 'package_version=b07-test' in signal['evidence']
        assert any(e.startswith('model_version=') for e in signal['evidence'])
        review_id, = connection.execute('SELECT id FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()
    assert run(database, package)['queued'] == 0
    with database() as connection:
        assert connection.execute('SELECT document FROM api_listing_signals WHERE listing_id=%s AND active', (subject.id,)).fetchone()[0] == signal
        assert connection.execute('SELECT count(*) FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()[0] == 1
        actor = uuid4()
        _, token = issue_session(connection, actor)
        _, viewer = issue_session(connection, uuid4(), role='viewer')
    with TestClient(app) as client:
        assert client.get('/api/v1/reviews').status_code == 401
        assert client.get('/api/v1/reviews', headers={'Authorization':'Bearer '+viewer}).status_code == 403
        headers = {'Authorization':'Bearer '+token}
        queue = client.get('/api/v1/reviews?category=price_anomaly&rule_id=PRICE-OUTSIDE-INTERVAL', headers=headers)
        assert queue.status_code == 200, queue.text
        validate_contract(queue.json(), 'ReviewPage')
        assert any(row['listing_id'] == str(subject.id) for row in queue.json()['items'])
        response = client.patch('/api/v1/reviews/'+str(review_id), headers=headers,
            json=dict(status='resolved',decision='dismissed',reason='Calibrated price anomaly reviewed',version=1))
        assert response.status_code == 200, response.text
        assert response.json()['history'][-1]['actor_id'] == str(actor)
        assert response.json()['reviewed_at']
    run(database, package)
    with database() as connection:
        assert connection.execute('SELECT count(*) FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()[0] == 1


def test_self_and_duplicate_group_cannot_supply_minimum_support(database, market, package):
    with database() as connection:
        connection.execute('DELETE FROM api_listing_projection WHERE id=%s', (market[-1].id,))
    run(database, package)
    with database() as connection:
        result, _ = target_audits(connection, market[0])[0]
        assert result['observed_market_statistics']['comparables_count'] == 2
        assert result['valuation_assessment']['estimated_price_usd'] is None
        assert connection.execute("SELECT count(*) FROM api_listing_signals WHERE listing_id=%s AND active "
            "AND document->>'category'='price_anomaly'", (market[0].id,)).fetchone()[0] == 0


def test_runtime_failure_retires_price_but_preserves_independent_risk_and_review_history(database, market, package, monkeypatch):
    from ml import inference
    subject = market[0]
    subject.description = '3 rooms, 120 m2'
    with database() as connection:
        publish_listing(connection, subject)
    run(database, package)
    with database() as connection:
        original = connection.execute('SELECT signals FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()[0]
    monkeypatch.setattr(inference.tc, 'predict_usd', lambda *a,**k: (_ for _ in ()).throw(RuntimeError('model failed')))
    summary = run(database, package)
    assert summary['calibrated'] == 0
    with database() as connection:
        categories = connection.execute("SELECT document->>'category' FROM api_listing_signals WHERE listing_id=%s AND active", (subject.id,)).fetchall()
        assert categories and all(category == 'risk_evidence' for category, in categories)
        assert connection.execute('SELECT signals FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()[0] == original
        assert all(audit['fallback'] == 'inference_error: RuntimeError'
            for response,audit in target_audits(connection,subject) if response['valuation_assessment']['estimated_price_usd'] is None)


def test_signal_failure_rolls_back_valuation_audit_and_queue(database, market, package, monkeypatch):
    import backend.generate_signals as producer
    monkeypatch.setattr(producer, 'reconcile_signals', lambda *a: (_ for _ in ()).throw(ValueError('signal failed')))
    with pytest.raises(ValueError):
        with database() as connection:
            generate(connection, package=package, clock=lambda: NOW)
    with database() as connection:
        assert connection.execute('SELECT count(*) FROM api_valuation_estimates').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM api_listing_signals').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM api_review_queue').fetchone()[0] == 0


@pytest.mark.parametrize('field', ['building_type', 'dedup_group_id'])
def test_model_input_changes_invalidate_current_signals_immediately(database, market, package, field):
    subject = market[0]
    run(database, package)
    with database() as connection:
        assert connection.execute('SELECT count(*) FROM api_listing_signals WHERE listing_id=%s AND active', (subject.id,)).fetchone()[0] > 0
        setattr(subject,field, 'changed-group' if field == 'dedup_group_id' else
            ('panel' if subject.building_type != 'panel' else 'stone'))
        publish_listing(connection,subject)
    with database() as connection:
        assert connection.execute('SELECT count(*) FROM api_listing_signals WHERE listing_id=%s AND active', (subject.id,)).fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM api_review_queue WHERE listing_id=%s', (subject.id,)).fetchone()[0] == 1


@pytest.mark.parametrize('age_days', [61, -1])
def test_stale_or_future_asking_observation_has_no_price_alert(database, market, package, age_days):
    subject = market[0]
    subject.first_seen_at = NOW-timedelta(days=100)
    subject.last_seen_at = NOW-timedelta(days=age_days)
    subject.description = '3 rooms, 120 m2'
    with database() as connection:
        publish_listing(connection,subject)
    summary = run(database,package)
    assert summary['price_withheld'] >= 1
    with database() as connection:
        assert target_audits(connection,subject) == []
        categories = connection.execute("SELECT document->>'category' FROM api_listing_signals WHERE listing_id=%s AND active",(subject.id,)).fetchall()
        assert categories and all(category == 'risk_evidence' for category, in categories)
