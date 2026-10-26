"""C06 integration against the actual A07 migration and stable database view.

Requires C03_TEST_DATABASE_URL and the A07 dependency (PR #71) in the checkout.
Each test uses an isolated schema, supplied by the existing backend fixture.
"""
from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine

from backend.tests.test_listing_postgres import database, client, validate_contract


@pytest.fixture
def market_database(database):
    root = Path(__file__).resolve().parents[2]
    path = root / "database/migrations/versions/a07_neighborhood_price_index_20261025.py"
    if not path.exists():
        pytest.skip("Requires A07 migration from prerequisite PR #71")
    spec = importlib.util.spec_from_file_location("a07_market_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("postgresql+psycopg://", creator=database)
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        yield database
    finally:
        engine.dispose()


def insert_aggregate(database, *, district="kentron", week=date(2026, 10, 19),
                     count=5, area_count=5, monthly=700, unit=14, source="list.am", as_of=None):
    as_of = as_of or datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    with database() as connection:
        connection.execute("""
            INSERT INTO weekly_neighborhood_price_indexes
                (source, district_id, period_start, period_end, sample_count,
                 per_sqm_sample_count, median_price_usd_month, median_price_usd_per_sqm,
                 minimum_sample_count, price_status, per_sqm_status, data_as_of)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 5, %s, %s, %s)
        """, (source, district, week, week + timedelta(days=6), count, area_count, monthly, unit,
              "available" if count >= 5 else "insufficient_data",
              "available" if area_count >= 5 else "insufficient_data", as_of))


@pytest.fixture
def populated(market_database):
    insert_aggregate(market_database, week=date(2026, 10, 5))
    insert_aggregate(market_database, district="arabkir")
    insert_aggregate(market_database)
    insert_aggregate(market_database, week=date(2026, 10, 26), area_count=2, unit=None)
    insert_aggregate(market_database, week=date(2026, 11, 2), count=2, area_count=0, monthly=None, unit=None)
    insert_aggregate(market_database, source="other", week=date(2026, 9, 7), monthly=9999)


def payload(response):
    assert response.status_code == 200, response.text
    result = response.json()
    validate_contract(result, "MarketIndexPage")
    return result


def test_filters_ordering_and_coverage_are_from_a07(client, populated):
    result = payload(client.get("/api/v1/market-index?period_start=2026-10-19&period_end=2026-10-19"))
    assert [(v["period_start"], v["district_id"]) for v in result["items"]] == [
        ("2026-10-19", "arabkir"), ("2026-10-19", "kentron")]
    assert result["total"] == 2
    assert result["available_from"] == "2026-10-05"
    assert result["available_to"] == "2026-11-02"
    selected = payload(client.get("/api/v1/market-index?district_id=arabkir&period_start=2026-11-01"))
    assert selected["items"] == [] and selected["total"] == 0
    assert selected["available_from"] == selected["available_to"] == "2026-10-19"
    assert payload(client.get("/api/v1/market-index?district_id=kentron%27%20OR%20TRUE--"))["total"] == 0


def test_pagination_preserves_total_and_no_missing_weeks_are_fabricated(client, populated):
    first = payload(client.get("/api/v1/market-index?page_size=2"))
    second = payload(client.get("/api/v1/market-index?page_size=2&page=2"))
    assert first["total"] == second["total"] == 5
    assert first["has_more"] and second["has_more"]
    pairs = [(v["period_start"], v["district_id"]) for v in first["items"] + second["items"]]
    assert pairs == [("2026-10-05", "kentron"), ("2026-10-19", "arabkir"),
                     ("2026-10-19", "kentron"), ("2026-10-26", "kentron")]
    beyond = payload(client.get("/api/v1/market-index?page=99"))
    assert beyond["items"] == [] and beyond["total"] == 5 and not beyond["has_more"]
    gap = payload(client.get("/api/v1/market-index?period_start=2026-10-12&period_end=2026-10-18"))
    assert gap["items"] == [] and gap["total"] == 0


def test_sparse_metrics_are_independent_and_values_match_view(client, populated, market_database):
    result = payload(client.get("/api/v1/market-index?district_id=kentron"))
    available, partial, sparse = result["items"][1:]
    assert available["median_usd_month"] == 700 and available["median_usd_m2"] == 14
    assert partial["status"] == "available" and partial["median_usd_month"] == 700
    assert partial["median_usd_m2"] is None and partial["area_sample_count"] == 2
    assert sparse["status"] == "insufficient_data" and sparse["sample_count"] == 2
    assert sparse["median_usd_month"] is sparse["median_usd_m2"] is None
    with market_database() as connection:
        stored = connection.execute("""
            SELECT median_asking_price_usd_month, median_asking_price_usd_per_sqm_month,
                   sample_count, per_sqm_sample_count, data_as_of
            FROM weekly_neighborhood_asking_price_index
            WHERE source='list.am' AND district_id='kentron' AND period_start='2026-10-19'
        """).fetchone()
    assert [available[k] for k in ("median_usd_month", "median_usd_m2", "sample_count", "area_sample_count")] == list(stored[:4])
    assert datetime.fromisoformat(available["data_as_of"].replace("Z", "+00:00")) == stored[4]
    generated = {v["freshness"]["generated_at"] for v in result["items"]}
    assert len(generated) == 1


def test_empty_view_and_absent_view_are_distinct(client, market_database):
    empty = payload(client.get("/api/v1/market-index"))
    assert empty["items"] == [] and empty["total"] == 0
    assert empty["available_from"] is empty["available_to"] is None
    with market_database() as connection:
        connection.execute("DROP VIEW weekly_neighborhood_asking_price_index")
    response = client.get("/api/v1/market-index")
    assert response.status_code == 503
    validate_contract(response.json(), "Error")


def test_stale_source_data_is_served_with_freshness(client, market_database):
    observed = datetime.now(timezone.utc) - timedelta(days=15)
    insert_aggregate(market_database, as_of=observed)
    item = payload(client.get("/api/v1/market-index"))["items"][0]
    assert item["freshness"]["is_stale"] is True
    assert item["median_usd_month"] == 700
    assert item["freshness"]["data_as_of"] == item["data_as_of"]


def test_pipeline_calculation_to_a07_view_to_api(client, market_database):
    from data_pipeline.aggregate_neighborhoods import build_weekly_aggregates
    from database.models import WeeklyNeighborhoodPriceIndex
    from sqlalchemy.orm import Session

    observed = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    rows = [dict(property_id=i, district_id="kentron", price_usd=price, area_sqm=50,
                 original_period="month", last_seen_at=observed, is_active=True,
                 source="list.am", listing_id=i) for i, price in enumerate((500, 600, 700, 800, 900), 1)]
    rows.append({**rows[0], "listing_id": 10, "price_usd": 1500, "last_seen_at": observed - timedelta(days=1)})
    aggregates = build_weekly_aggregates(rows, date(2026, 10, 19))
    engine = create_engine("postgresql+psycopg://", creator=market_database)
    try:
        with Session(engine) as session, session.begin():
            session.add_all(WeeklyNeighborhoodPriceIndex(**row) for row in aggregates)
        item = payload(client.get("/api/v1/market-index"))["items"][0]
        assert item["median_usd_month"] == 700
        assert item["median_usd_m2"] == 14
        assert item["sample_count"] == item["area_sample_count"] == 5
        assert item["measure"] == "asking_price"
    finally:
        engine.dispose()
