"""Exercise district orchestration with the real B03 adapter, without a DB."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.valuation_gateway import BaselineGateway
from backend.valuation_models import ValuationRequest
from backend.valuation_service import ValuationService

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('subject', [('kentron', 'Kentron'), None])
def test_canonical_district_and_consistent_cohort_reach_model_and_audit(monkeypatch, subject):
    records = [SimpleNamespace(id=UUID(int=i), latitude=40.18, longitude=44.51,
        price_monthly_normalized=price, area_sqm=50, rooms=2, district_id='stale-label',
        last_seen_at=NOW-timedelta(days=1), dedup_group_id=None)
        for i, price in enumerate([500, 600, 700, 5000], 1)]
    class Registry:
        version = 'district-snapshot:checksum'
        def resolve_many(self, connection, points):
            assert len(points) == 5
            return [subject] + [('kentron', 'Kentron')] * 3 + [('arabkir', 'Arabkir')]
    monkeypatch.setenv('VALUATION_DISTRICTS_FILE', 'test-snapshot')
    monkeypatch.setattr('backend.valuation_service.DistrictRegistry', lambda path: Registry())
    class Connection:
        def execute(self, command):
            pass
    class Repository:
        def connection(self):
            return nullcontext(Connection())
        def candidates(self, connection, query, now):
            return records, 'observed-test-snapshot'
        def save(self, connection, query, result, dataset_version, geography_version):
            self.saved = result, geography_version
    class Coverage:
        version = 'city:checksum'
        def check(self, connection, query):
            pass
    seen = {}
    class Provider(BaselineGateway):
        def assess(self, payload, **kwargs):
            seen['payload'] = payload
            seen['labels'] = set(self.snapshot.district)
            return super().assess(payload, **kwargs)
    repository = Repository()
    service = ValuationService(repository=repository, provider=Provider,
        coverage=Coverage(), clock=lambda: NOW)
    query = ValuationRequest(latitude=40.18, longitude=44.51, area_sqm=50, rooms=2)
    result = service.assess(query, str(uuid4()))
    assert seen['payload']['district'] == (subject[1] if subject else None)
    assert 'asking_price_usd_month' not in seen['payload']
    assert seen['labels'] == ({'Kentron'} if subject else {'Kentron', 'Arabkir'})
    assert result['observed_market_statistics']['comparables_count'] == (3 if subject else 4)
    assert result['observed_market_statistics']['cluster_mean_price_usd'] == (600 if subject else 1700)
    assert ('District Kentron (kentron)' if subject else 'District unresolved') in result['explanation']
    assert repository.saved[1] == 'city:checksum;districts=district-snapshot:checksum'
