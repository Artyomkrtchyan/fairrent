"""Owned mock HTTP server -> accepted pipeline -> PostGIS -> publication -> API."""
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend import sync_listings
from backend.source_adapter import listing_uuid
from backend.tests.test_listing_postgres import database, client, validate_contract
from database.models import Base, Listing
from data_pipeline.cli import ingest
from data_pipeline.ingestion import finish_run, start_run
from data_pipeline.scraper import ListingPipeline


@pytest.fixture
def source_session(database):
    with database() as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    engine = create_engine("postgresql+psycopg://", creator=database)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def crawl(session, *, ids=(1, 2), price=10000):
    def respond(request):
        if request.url.path == "/category/56":
            links = "".join(f'<a href="/item/{i}">Apartment</a>' for i in ids) if "pg" not in request.url.params else ""
            return httpx.Response(200, text=f'<div id="listings">{links}</div>')
        if request.url.path == "/item/1":
            return httpx.Response(200, text=(
                f'<h1 class="pTitle">Synthetic daily apartment</h1><span class="pPrice">{price} AMD/day</span>'
                '<div data-lat="40.18" data-lng="44.51"></div>'
                '<div class="pattr">Area 50 sq</div><div class="pattr">Rooms 2</div>'))
        return httpx.Response(200, text='<h1 class="pTitle">Synthetic without coordinates</h1><span class="pPrice">$600</span>')
    transport = httpx.Client(transport=httpx.MockTransport(respond))
    pipeline = ListingPipeline(client=transport, delay=0)
    try:
        run = start_run(session, "list.am")
        saved = ingest(pipeline.collect("http://fairrent.test/category/56", 2), pipeline,
                       session, "list.am", run_id=run.id)
        finish_run(session, run, seen_ids=pipeline.seen_ids, crawl_complete=pipeline.crawl_complete,
                   stats={"listings_saved": saved})
        assert run.is_complete
    finally:
        transport.close()


def publish(database):
    with database() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return sync_listings.sync_projection(connection)


def test_pipeline_to_api_with_missing_coordinates_and_decimal_prices(database, source_session, client):
    crawl(source_session)
    # A05 district enrichment is represented explicitly, not inferred from coordinates.
    source_session.query(Listing).filter_by(external_id="1").one().property.district = "Kentron"
    source_session.commit()
    assert publish(database)["published"] == 2
    response = client.get("/api/v1/listings?district_id=kentron&rooms=2&price_min=779.22&price_max=779.22")
    assert response.status_code == 200
    validate_contract(response.json(), "ListingPage")
    assert response.json()["total"] == 1
    item = response.json()["items"][0]
    assert item["id"] == str(listing_uuid("list.am", "1"))
    assert item["price_original"] == 300000
    assert item["price_monthly_normalized"] == 779.22
    assert item["source_url"] == "http://fairrent.test/item/1"
    missing = client.get(f"/api/v1/listings/{listing_uuid('list.am', '2')}")
    assert missing.status_code == 200
    validate_contract(missing.json(), "ListingDetail")
    assert missing.json()["listing"]["latitude"] is None
    assert missing.json()["listing"]["rooms"] is None
    map_page = client.get("/api/v1/listings?bbox=44.5,40.17,44.52,40.19")
    assert map_page.json()["total"] == 1
    assert client.get("/api/v1/listings").json()["total"] == 2


def test_price_and_inactivity_updates_keep_public_ids(database, source_session, client):
    crawl(source_session)
    publish(database)
    for _ in range(2):
        crawl(source_session, ids=(1,), price=15000)
    result = publish(database)
    assert result["published"] == 2
    assert result["removed_from_projection"] == 0
    active = client.get("/api/v1/listings").json()
    assert active["total"] == 1
    assert active["items"][0]["id"] == str(listing_uuid("list.am", "1"))
    assert active["items"][0]["price_monthly_normalized"] == 1168.83
    inactive = client.get("/api/v1/listings?status=inactive").json()
    assert inactive["total"] == 1
    assert inactive["items"][0]["id"] == str(listing_uuid("list.am", "2"))
    assert client.get(f"/api/v1/listings/{listing_uuid('list.am', '2')}").status_code == 200
    assert publish(database)["published"] == 2  # no duplicates on repeated publication


def test_legacy_and_demo_records_are_not_published(database, source_session, client):
    crawl(source_session)
    source_session.add(Listing(source="list.am", external_id="legacy", title="Legacy without provenance"))
    source_session.add(Listing(source="demo", external_id="demo", title="Synthetic import"))
    source_session.commit()
    summary = publish(database)
    assert summary["published"] == 2
    assert summary["excluded_reasons"] == {"unobserved_legacy_record": 1}
    assert client.get("/api/v1/listings").json()["total"] == 2


def test_failed_publication_preserves_previous_snapshot(database, source_session, client, monkeypatch):
    crawl(source_session)
    publish(database)
    crawl(source_session, price=15000)
    original = sync_listings.publish_listing
    count = 0
    def fail_after_write(connection, record):
        nonlocal count
        original(connection, record)
        count += 1
        if count == 2:
            raise RuntimeError("simulated publisher failure")
    monkeypatch.setattr(sync_listings, "publish_listing", fail_after_write)
    with pytest.raises(RuntimeError):
        publish(database)
    detail = client.get(f"/api/v1/listings/{listing_uuid('list.am', '1')}").json()
    assert detail["listing"]["price_monthly_normalized"] == 779.22


def test_no_longer_publishable_record_is_removed_from_api_only(database, source_session, client):
    crawl(source_session)
    publish(database)
    source_session.query(Listing).filter_by(external_id="1").one().url = None
    source_session.commit()
    summary = publish(database)
    assert summary["published"] == 1
    assert summary["removed_from_projection"] == 1
    assert summary["excluded_reasons"] == {"invalid_contract_record": 1}
    assert client.get(f"/api/v1/listings/{listing_uuid('list.am', '1')}").status_code == 404
    assert source_session.query(Listing).count() == 2


def test_publication_waits_for_ingestion_completion(database, source_session, client):
    crawl(source_session)
    publish(database)
    start_run(source_session, "list.am")
    with pytest.raises(sync_listings.PublicationBusy):
        publish(database)
    assert client.get("/api/v1/listings").json()["total"] == 2
