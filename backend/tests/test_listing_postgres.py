"""Real PostgreSQL tests. Use a disposable database via C03_TEST_DATABASE_URL.

Each test creates and removes only its own randomly named schema.
"""
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import sql

from backend.main import app
from backend.listing_models import ListingData
from backend.listing_repository import publish_listing


@pytest.fixture
def database(monkeypatch):
    dsn = os.environ.get("C03_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set C03_TEST_DATABASE_URL to run PostgreSQL integration tests")
    original_connect = psycopg.connect
    schema = "c03_test_" + uuid4().hex
    with original_connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    def connect(**kwargs):
        return original_connect(dsn, options=f"-csearch_path={schema}", **kwargs)
    try:
        with connect() as connection:
            migration = Path(__file__).resolve().parents[1] / "sql" / "001_listing_projection.sql"
            connection.execute(migration.read_text(encoding="utf-8"))
        monkeypatch.setattr(psycopg, "connect", connect)
        yield connect
    finally:
        with original_connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def populated(database, listing_document):
    records = []
    for i in range(1, 6):
        document = {**listing_document, "id": str(UUID(int=i)), "external_id": f"synthetic-{i}",
                    "first_seen_at": f"2026-09-0{i}T08:00:00Z", "published_at": None}
        if i == 2:
            document.update(area_sqm=60, latitude=None, longitude=None, coordinate_confidence="unknown")
        if i == 3:
            document.update(district_id="arabkir", rooms=3, price_monthly_normalized=800, area_sqm=None)
        if i == 4:
            document.update(status="inactive")
        if i == 5:
            document.update(price_monthly_normalized=None, conversion=None, area_sqm=80)
        record = ListingData.model_validate(document)
        with database() as connection:
            publish_listing(connection, record)
        records.append(record)
    return records


@pytest.fixture
def client(database):
    with TestClient(app) as client:
        yield client


def validate_contract(payload, name):
    path = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    schema = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def ids(response):
    assert response.status_code == 200, response.text
    validate_contract(response.json(), "ListingPage")
    return [UUID(item["id"]).int for item in response.json()["items"]]


def test_real_filters_and_boundaries(client, populated):
    response = client.get("/api/v1/listings", params={
        "district_id": "kentron", "price_min": 600, "price_max": 600,
        "area_min": 50, "area_max": 60, "rooms": 2, "sort": "area_asc",
    })
    assert ids(response) == [1, 2]
    assert response.json()["total"] == 2
    assert ids(client.get("/api/v1/listings?district_id=kentron%27%20OR%20TRUE--")) == []


@pytest.mark.parametrize("sort,expected", [
    ("newest", [5, 3, 2, 1]), ("price_asc", [1, 2, 3, 5]),
    ("price_desc", [3, 1, 2, 5]), ("area_asc", [1, 2, 5, 3]),
    ("area_desc", [5, 2, 1, 3]),
])
def test_real_ordering_nulls_and_ties(client, populated, sort, expected):
    assert ids(client.get("/api/v1/listings", params={"sort": sort})) == expected


def test_real_pagination_including_out_of_range(client, populated):
    first = client.get("/api/v1/listings?sort=price_asc&page_size=2")
    second = client.get("/api/v1/listings?sort=price_asc&page_size=2&page=2")
    assert ids(first) == [1, 2]
    assert ids(second) == [3, 5]
    assert first.json()["has_more"] is True
    assert second.json()["has_more"] is False
    beyond = client.get("/api/v1/listings?page=99")
    assert ids(beyond) == []
    assert beyond.json()["total"] == 4
    assert beyond.json()["has_more"] is False


def test_real_map_queries_exclude_unknown_coordinates(client, populated):
    response = client.get("/api/v1/listings?bbox=44.515,40.185,44.6,40.2&sort=price_asc&page_size=1")
    assert ids(response) == [1]
    assert response.json()["total"] == 3
    assert response.json()["has_more"] is True
    assert ids(client.get("/api/v1/listings?bbox=44,40,44.1,40.1")) == []


def test_real_details_include_inactive_and_missing(client, populated):
    response = client.get(f"/api/v1/listings/{populated[3].id}")
    assert response.status_code == 200
    validate_contract(response.json(), "ListingDetail")
    assert response.json()["listing"]["status"] == "inactive"
    missing = client.get(f"/api/v1/listings/{UUID(int=999)}")
    assert missing.status_code == 404
    validate_contract(missing.json(), "Error")


def test_publish_update_is_idempotent_and_atomic(database, client, populated):
    record = populated[0].model_copy(update={"status": "inactive"})
    with database() as connection:
        publish_listing(connection, record)
        publish_listing(connection, record)
    response = client.get("/api/v1/listings?status=inactive&sort=price_asc")
    assert ids(response) == [1, 4]
    with pytest.raises(RuntimeError):
        with database() as connection:
            publish_listing(connection, record.model_copy(update={"status": "active"}))
            raise RuntimeError("Roll back projection together with ingestion")
    assert client.get(f"/api/v1/listings/{record.id}").json()["listing"]["status"] == "inactive"


def test_empty_database_is_success(client):
    response = client.get("/api/v1/listings")
    assert ids(response) == []
    assert response.json()["total"] == 0
    assert response.json()["has_more"] is False
