"""Persist a real B07 assessment and provenance using disposable PostGIS."""
from datetime import timedelta
from pathlib import Path

from backend.main import app
from backend.tests.test_listing_postgres import database
from backend.tests.test_valuations import api, valuation_db, listing_document, seed, assess, QUERY
from backend.valuation_routes import service
from backend.valuation_service import ValuationService
from ml.tests.test_inference import world, package


def test_b07_real_package_persisted_in_postgres(api, valuation_db, listing_document, package, world, monkeypatch):
    from ml import inference
    from ml.tests.test_inference import NOW as package_now
    monkeypatch.setenv(inference.PACKAGE_ENV_VAR, str(world['pkg']))
    monkeypatch.setattr(inference, '_DEFAULT', dict(package=None, error=None, path=None))
    seed(valuation_db, listing_document, changes={'last_seen_at':package_now-timedelta(days=1)})
    app.dependency_overrides[service] = lambda: ValuationService(clock=lambda: package_now)
    result = assess(api, {**QUERY, 'area_sqm':65, 'floor':3, 'total_floors':9})
    assert result['valuation_assessment']['assessment_status'] == 'VALUATION_SUCCESS'
    with valuation_db() as connection:
        row = connection.execute('SELECT inference_provenance, response_document FROM api_valuation_estimates').fetchone()
        # The migration also upgrades already-existing audit tables and is repeatable.
        connection.execute((Path(__file__).resolve().parents[1] / 'sql' / '002_valuation_estimates.sql').read_text())
    assert row[1] == result
    assert row[0]['package_version'] == 'b07-test'
    assert row[0]['calibration_version'] == result['ml_prediction_interval']['calibration_version']
    assert row[0]['ontology']['rules_version'] == result['versions']['rule_engine_version']
    assert row[0]['snapshot_sha256'] and row[0]['observed_dataset_version']
