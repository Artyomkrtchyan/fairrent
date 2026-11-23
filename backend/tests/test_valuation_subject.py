"""Internal C05 subject exclusion must not affect the public C04 request contract."""
from datetime import datetime, timedelta, timezone
from statistics import stdev
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.valuation_gateway import BaselineGateway
from backend.valuation_models import ValuationRequest
from backend.valuation_service import ValuationService


def test_subject_duplicate_group_is_excluded_and_shared_transaction_is_preserved(monkeypatch):
    monkeypatch.delenv('VALUATION_DISTRICTS_FILE', raising=False)
    now = datetime(2026,11,2,12,tzinfo=timezone.utc)
    records = [SimpleNamespace(id=UUID(int=i), latitude=40.18, longitude=44.51,
        area_sqm=65,rooms=2,price_monthly_normalized=price,district_id='kentron',status='active',
        dedup_group_id='subject' if i<3 else 'comparable' if i==3 else None,
        last_seen_at=now-timedelta(days=1))
        for i,price in enumerate([10000,10000,500,600,700],1)]
    records.append(SimpleNamespace(**{**vars(records[2]), 'id': UUID(int=6), 'rooms': 3,
                                     'price_monthly_normalized': 2000, 'last_seen_at': now}))
    class Connection:
        statements = []
        def execute(self, statement):
            self.statements.append(statement)
    class Repository:
        def connection(self):
            raise AssertionError('Must use caller-owned transaction')
        def candidates(self, connection, query, now):
            return records, 'test-snapshot'
        def save(self, connection, query, result, dataset_version, geography_version, **metadata):
            self.saved = result, metadata
    class Coverage:
        version = 'test:checksum'
        def check(self, connection, query):
            pass
    seen = []
    class Provider(BaselineGateway):
        def assess(self, payload, **kwargs):
            seen.extend(self.snapshot.listing_id)
            return super().assess(payload, **kwargs)
    connection,repository = Connection(),Repository()
    result = ValuationService(repository=repository, provider=Provider, coverage=Coverage(),clock=lambda:now).assess(
        ValuationRequest(latitude=40.18,longitude=44.51,area_sqm=65,rooms=2),str(uuid4()),
        subject=records[0],connection=connection)
    assert seen == [str(UUID(int=i)) for i in (3,4,5)]
    assert result['observed_market_statistics']['comparables_count'] == 3
    assert result['observed_market_statistics']['cluster_mean_price_usd'] == 600
    assert result['observed_market_statistics']['observed_price_std_dev_usd'] == 100
    assert result['observed_market_statistics']['cluster_mean_price_per_sqm_usd'] == pytest.approx(600 / 65)
    assert result['observed_market_statistics']['observed_price_std_dev_per_sqm_usd'] == pytest.approx(
        stdev([500 / 65, 600 / 65, 700 / 65]))
    assert result['cohort']['selection_version'] == 'b09-cohort-v1'
    assert result['valuation_assessment']['estimated_price_usd'] == 600
    assert not any('SET TRANSACTION' in statement for statement in connection.statements)
    assert repository.saved[1]['inference_provenance']['subject_listing_id'] == str(records[0].id)
