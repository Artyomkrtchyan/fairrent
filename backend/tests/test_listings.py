from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.listing_models import ListingData, ListingQuery, public_listing
from backend.listing_repository import search_sql
from backend.listing_routes import repository


@pytest.fixture
def client(listing_document):
    class Repo:
        query = None

        def search(self, query):
            self.query = query
            return [ListingData.model_validate(listing_document)], 21

        def get(self, listing_id):
            return ListingData.model_validate(listing_document) if str(listing_id) == listing_document["id"] else None

    repo = Repo()
    app.dependency_overrides[repository] = lambda: repo
    with TestClient(app) as client:
        client.repo = repo
        yield client
    app.dependency_overrides.clear()


def test_search_contract_and_defaults(client, listing_document):
    response = client.get("/api/v1/listings")
    assert response.status_code == 200
    result = response.json()
    assert (result["page"], result["page_size"], result["total"], result["has_more"]) == (1, 20, 21, True)
    listing = result["items"][0]
    assert listing["id"] == listing_document["id"]
    assert listing["first_seen_at"].endswith("Z")
    assert listing["price_status"] == "insufficient_data"
    assert listing["freshness"]["data_as_of"] == listing_document["last_seen_at"]
    assert client.repo.query.status == "active"


@pytest.mark.parametrize("query", [
    "page=0", "page_size=101", "price_min=-1", "area_min=0", "rooms=0",
    "price_min=700&price_max=600", "area_min=80&area_max=50",
    "price_min=NaN", "price_max=inf", "sort=unknown", "status=unknown",
    "typo=1", "page=1&page=2", "bbox=44,40,45,41", "bbox=45,40,44,40.1",
    "bbox=181,40,181.1,40.1", "bbox=44,91,44.1,91.1", "bbox=bad",
    "bbox=44,40,44,40.1", "rooms=2.5",
])
def test_invalid_queries_use_error_contract(client, query):
    response = client.get("/api/v1/listings?" + query)
    assert response.status_code == 422
    result = response.json()
    assert result["code"] == "validation_error"
    assert str(UUID(result["request_id"])) == response.headers["x-request-id"]
    assert isinstance(result["details"], list)


def test_all_filters_are_parsed(client):
    response = client.get("/api/v1/listings", params={
        "district_id": "kentron", "price_min": 500, "price_max": 700, "rooms": 2,
        "area_min": 40, "area_max": 60, "status": "inactive", "sort": "price_desc",
        "page": 2, "page_size": 10, "bbox": "44.5,40.1,44.6,40.2",
    })
    assert response.status_code == 200
    query = client.repo.query
    assert (query.district_id, query.rooms, query.status, query.sort) == ("kentron", 2, "inactive", "price_desc")
    assert query.bounds() == (44.5, 40.1, 44.6, 40.2)


def test_details_and_errors(client, listing_document):
    listing_document["status"] = "inactive"
    response = client.get("/api/v1/listings/" + listing_document["id"])
    assert response.status_code == 200
    assert response.json()["listing"]["status"] == "inactive"
    assert response.json()["signals"] == []
    assert response.json()["estimate"] is None
    assert client.get("/api/v1/listings/00000000-0000-0000-0000-000000000099").status_code == 404
    assert client.get("/api/v1/listings/not-a-uuid").status_code == 422
    assert client.get("/api/v1/listings/" + listing_document["id"] + "?typo=1").status_code == 422


def test_dependency_failure_hides_database_details(client):
    def failed(query):
        raise psycopg.OperationalError("secret database credentials")
    client.repo.search = failed
    response = client.get("/api/v1/listings")
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert "secret" not in response.text


def test_sql_uses_bound_values():
    malicious = "kentron' OR TRUE --"
    where, params = search_sql(ListingQuery(district_id=malicious, price_min=500, bbox="44.5,40.1,44.6,40.2"))
    assert malicious not in where
    assert params == ["active", malicious, 500, 44.5, 44.6, 40.1, 40.2]


def test_freshness_is_computed_from_source_observation(listing_document):
    record = ListingData.model_validate(listing_document)
    record.first_seen_at = datetime.now(timezone.utc) - timedelta(days=30)
    record.last_seen_at = datetime.now(timezone.utc) - timedelta(days=15)
    assert public_listing(record).freshness.is_stale
    record.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert not public_listing(record).freshness.is_stale


@pytest.mark.parametrize("changes", [
    {"latitude": None}, {"latitude": 100}, {"area_sqm": 0}, {"rooms": 0},
    {"floor": 5, "total_floors": 4}, {"conversion": None},
    {"first_seen_at": "2026-10-17T08:00:00"}, {"source_url": "javascript:bad"},
])
def test_projection_rejects_invalid_source_data(listing_document, changes):
    with pytest.raises(ValidationError):
        ListingData.model_validate({**listing_document, **changes})


def test_unknown_values_remain_null(listing_document):
    listing_document.update(latitude=None, longitude=None, coordinate_confidence="unknown",
                            conversion=None, price_monthly_normalized=None, rooms=None, area_sqm=None)
    listing = public_listing(ListingData.model_validate(listing_document))
    assert listing.latitude is listing.longitude is listing.rooms is listing.area_sqm is None
    assert listing.conversion is listing.price_monthly_normalized is None
