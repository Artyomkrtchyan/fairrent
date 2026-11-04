"""Internal C05 subject exclusion must not affect the public C04 request contract."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from backend.valuation_gateway import BaselineGateway
from backend.valuation_models import ValuationRequest
from backend.valuation_service import ValuationService


def test_subject_duplicate_group_is_excluded_and_shared_transaction_is_preserved(monkeypatch):
    monkeypatch.delenv('VALUATION_DISTRICTS_FILE', raising=False)
    now = datetime(2026,11,2,12,tzinfo=timezone.utc)
    records = [SimpleNamespace(id=UUID(int=i), latitude=40.18, longitude=44.51,
        area_sqm=65,rooms=2,price_monthly_normalized=price,district_id='kentron',
        dedup_group_id='subject' if i<3 else None,last_seen_at=now-timedelta(days=1))
        for i,price in enumerate([10000,10000,500,600,700],1)]
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
    assert result['valuation_assessment']['estimated_price_usd'] == 600
    assert not any('SET TRANSACTION' in statement for statement in connection.statements)
    assert repository.saved[1]['inference_provenance']['subject_listing_id'] == str(records[0].id)
