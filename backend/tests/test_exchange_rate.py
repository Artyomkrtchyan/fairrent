"""Contract and failure tests for live USD/AMD conversion."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import exchange_rate_routes as fx
from backend.tests.test_listing_postgres import validate_contract


@pytest.fixture(autouse=True)
def clear_cache():
    fx._cache = None
    yield
    fx._cache = None


def test_cba_soap_usd_amount_is_normalized(monkeypatch):
    body = b"""<Envelope xmlns:c="http://www.cba.am/"><Body>
    <c:ExchangeRatesLatestByISOResult>
      <c:CurrentDate>2026-11-03T00:00:00</c:CurrentDate>
      <c:Rates><c:ExchangeRate><c:ISO>USD</c:ISO><c:Amount>10</c:Amount>
      <c:Rate>3600.70</c:Rate></c:ExchangeRate></c:Rates>
    </c:ExchangeRatesLatestByISOResult></Body></Envelope>"""

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return body

    def fake_urlopen(request, timeout):
        assert request.full_url == fx.CBA_URL
        assert b"<ISO>USD</ISO>" in request.data
        assert timeout == 4
        return Response()

    monkeypatch.setattr(fx.urllib.request, "urlopen", fake_urlopen)
    quote, as_of = fx._fetch_rate()
    assert quote == pytest.approx(360.07)
    assert as_of.tzinfo is timezone.utc


def test_exchange_rate_matches_c01_and_caches(monkeypatch):
    calls = []
    when = datetime.now(timezone.utc) - timedelta(hours=12)

    def fetch():
        calls.append(1)
        return 360.07, when

    monkeypatch.setattr(fx, "_fetch_rate", fetch)
    with TestClient(app) as client:
        first = client.get("/api/v1/exchange-rate")
        second = client.get("/api/v1/exchange-rate")
    assert first.status_code == second.status_code == 200
    validate_contract(first.json(), "ExchangeRate")
    assert first.json()["amd_per_usd"] == 360.07
    assert first.json()["status"] == "available"
    assert first.json()["freshness"]["is_stale"] is False
    assert len(calls) == 1


def test_stale_rate_is_not_presented_as_available(monkeypatch):
    monkeypatch.setattr(
        fx, "_fetch_rate",
        lambda: (375.0, datetime.now(timezone.utc) - timedelta(days=9)),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/exchange-rate")
    assert response.status_code == 200
    validate_contract(response.json(), "ExchangeRate")
    assert response.json()["status"] == "stale"
    assert response.json()["freshness"]["is_stale"] is True


def test_provider_failure_returns_contract_error(monkeypatch):
    def down():
        raise OSError("upstream secret / network path")

    monkeypatch.setattr(fx, "_fetch_rate", down)
    with TestClient(app) as client:
        response = client.get("/api/v1/exchange-rate")
    assert response.status_code == 503
    validate_contract(response.json(), "Error")
    assert response.json()["code"] == "service_unavailable"
    assert "secret" not in response.text


def test_broken_provider_data_is_rejected(monkeypatch):
    monkeypatch.setattr(fx, "_fetch_rate", lambda: (_ for _ in ()).throw(ValueError("bad quote")))
    with TestClient(app) as client:
        response = client.get("/api/v1/exchange-rate")
    assert response.status_code == 503
