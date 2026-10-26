import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.market_models import MarketAggregate, public_market_index
from backend.market_routes import repository
from backend.tests.test_listing_postgres import validate_contract


@pytest.fixture
def market_fixtures():
    path = Path(__file__).resolve().parents[2] / "contracts" / "fixtures.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def client(market_fixtures):
    class Repo:
        record = market_fixtures["market-index"]["value"]["items"][0]
        total = 1
        query = None

        def search(self, query):
            self.query = query
            values = {key: value for key, value in self.record.items() if key != "freshness"}
            return [MarketAggregate.model_validate(values)], self.total, date(2026, 10, 12), date(2026, 10, 12)

    repo = Repo()
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            client.repo = repo
            yield client
    finally:
        app.dependency_overrides.pop(repository, None)


def test_market_response_matches_chart_fixture(client, market_fixtures):
    response = client.get("/api/v1/market-index")
    assert response.status_code == 200
    result = response.json()
    validate_contract(result, "MarketIndexPage")
    expected = market_fixtures["market-index"]["value"]["items"][0]
    assert {k: v for k, v in result["items"][0].items() if k != "freshness"} == {
        k: v for k, v in expected.items() if k != "freshness"
    }
    assert (result["page"], result["page_size"], result["total"], result["has_more"]) == (1, 20, 1, False)
    # C01 semantics define coverage as bucket starts, not the last Sunday's date.
    assert result["available_from"] == result["available_to"] == "2026-10-12"


def test_sparse_fixture_preserves_nulls_and_counts(client, market_fixtures):
    client.repo.record = market_fixtures["market-sparse"]["value"]
    response = client.get("/api/v1/market-index")
    assert response.status_code == 200
    validate_contract(response.json(), "MarketIndexPage")
    item = response.json()["items"][0]
    assert (item["sample_count"], item["area_sample_count"]) == (1, 0)
    assert item["status"] == "insufficient_data"
    assert item["median_usd_month"] is item["median_usd_m2"] is None


def test_empty_fixture_is_returned_without_inventing_periods(client, market_fixtures):
    client.repo.search = lambda query: ([], 0, None, None)
    response = client.get("/api/v1/market-index")
    assert response.status_code == 200
    assert response.json() == market_fixtures["market-empty"]["value"]
    validate_contract(response.json(), "MarketIndexPage")


@pytest.mark.parametrize("query", [
    "page=0", "page_size=101", "page_size=0", "page=1.5", "district_id=",
    "period_start=bad", "period_end=2026-02-30", "period_start=2026-10-26&period_end=2026-10-19",
    "period_start=1792368000", "period_end=2026-10-19T00:00:00Z", "source=list.am",
    "typo=1", "page=1&page=2", "district_id=kentron&district_id=arabkir",
])
def test_invalid_market_queries_use_error_contract(client, query):
    response = client.get("/api/v1/market-index?" + query)
    assert response.status_code == 422
    validate_contract(response.json(), "Error")
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert client.repo.query is None


def test_market_filters_and_pagination(client):
    client.repo.total = 25
    response = client.get("/api/v1/market-index", params={
        "district_id": "kentron", "period_start": "2026-10-13", "period_end": "2026-10-26",
        "page": 2, "page_size": 10,
    })
    assert response.status_code == 200
    assert response.json()["has_more"] is True
    assert client.repo.query.period_start == date(2026, 10, 13)
    assert client.repo.query.period_end == date(2026, 10, 26)
    assert client.repo.query.district_id == "kentron"


def test_market_dependency_failure_is_not_an_empty_dataset(client):
    def failed(query):
        raise psycopg.OperationalError("secret credentials and server details")
    client.repo.search = failed
    response = client.get("/api/v1/market-index")
    assert response.status_code == 503
    validate_contract(response.json(), "Error")
    assert response.json()["code"] == "service_unavailable"
    assert "secret" not in response.text


def test_freshness_uses_observation_not_publication_time(client):
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    fields = {k: v for k, v in client.repo.record.items() if k != "freshness"}
    for as_of, stale in ((now - timedelta(days=14), False),
                         (now - timedelta(days=14, seconds=1), True), (None, True)):
        record = MarketAggregate.model_validate({**fields, "data_as_of": as_of})
        result = public_market_index(record, now)
        assert result.freshness.is_stale is stale
        assert result.freshness.data_as_of == result.data_as_of == as_of
        assert result.freshness.generated_at == now
        assert result.median_usd_month == 600  # Stale observations remain visible.
