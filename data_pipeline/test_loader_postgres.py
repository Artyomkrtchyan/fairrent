import json
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database.models import Base, IngestionRun, Listing, PriceObservation, Property
from . import ingestion
from .cli import ingest
from .ingestion import finish_run, start_run
from .scraper import ListingPipeline

TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set")

SEED = Path(__file__).with_name("seed_data.json")

@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(ingestion, "STALENESS_RUNS", 2)
    monkeypatch.setattr(ingestion, "MIN_SEEN_RATIO", 0.5)
    engine = create_engine(TEST_DB)
    assert "test" in (engine.url.database or ""), "refusing to run against a non-test database"
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


def rec(item_id, price=600, currency="USD", period="month", **extra):
    return {"id": item_id, "title": f"t{item_id}", "price": price, "currency": currency, "period": period,
            "lat": 40.18 + int(item_id) * 0.01 if str(item_id).isdigit() else 40.18, "lon": 44.51,
            "url": f"https://example.invalid/item/{item_id}", **extra}


def run(session, records, *, source="list.am", seen=None, complete=True):
    """One simulated crawl: ingest records, then close the run like the CLI does."""
    pipeline = ListingPipeline(delay=0)
    r = start_run(session, source, {})
    saved = ingest(records, pipeline, session, source, run_id=r.id)
    seen_ids = {str(x["id"]) for x in records} if seen is None else set(seen)
    finish_run(session, r, seen_ids=seen_ids, crawl_complete=complete,
               stats={"listings_seen": len(seen_ids), "listings_saved": saved,
                      "listings_quarantined": len(pipeline.quarantine_log)})
    pipeline.close()
    return r

def listing(session, ext, source="list.am"):
    session.expire_all()
    return session.query(Listing).filter_by(source=source, external_id=str(ext)).one()

def counts(session):
    return (session.query(Property).count(), session.query(Listing).count(),
            session.query(PriceObservation).count())

# ---- idempotency & price history -----------------------------------------------------

def test_repeated_ingestion_is_idempotent(session):
    for _ in range(3):
        run(session, [rec("1")])
    assert counts(session) == (1, 1, 1)

def test_amd_daily_stored_as_monthly_with_provenance(session):
    for _ in range(2):
        run(session, [rec("1", price=10_000, currency="AMD", period="day")])
    row = listing(session, 1)
    assert (row.price_amd, row.price_usd) == (300_000.0, 779.22)
    assert (row.original_price, row.original_currency, row.original_period) == (10_000.0, "AMD", "day")
    assert row.exchange_rate == 385.0 and row.exchange_rate_at is not None
    assert row.utilities_included is None                    # unknown stays NULL
    assert counts(session) == (1, 1, 1)

def test_price_change_is_traceable_without_duplicating_listing(session):
    r1 = run(session, [rec("1", price=600)])
    r2 = run(session, [rec("1", price=650)])
    run(session, [rec("1", price=650)])
    assert counts(session) == (1, 1, 2)
    obs = session.query(PriceObservation).order_by(PriceObservation.id).all()
    assert [o.original_price for o in obs] == [600.0, 650.0]
    assert [o.run_id for o in obs] == [r1.id, r2.id]
    assert listing(session, 1).price_usd == 650.0

def test_same_external_id_in_two_sources_is_two_listings(session):
    run(session, [rec("1")], source="list.am")
    run(session, [rec("1")], source="other-site")
    assert session.query(Listing).count() == 2

# ---- first/last seen, url, missing values ----------------------------------------------

def test_first_and_last_seen_and_url(session):
    r1 = run(session, [rec("1")])
    first = listing(session, 1)
    first_seen, last_seen = first.first_seen_at, first.last_seen_at
    r2 = run(session, [rec("1")])
    row = listing(session, 1)
    assert row.first_seen_at == first_seen and row.last_seen_at > last_seen
    assert row.last_seen_run_id == r2.id and row.url == "https://example.invalid/item/1"

def test_unknown_stays_null_and_known_value_is_not_erased(session):
    run(session, [rec("1", area_sqm=55, rooms_count=2, floor=0, total_floors=9)])
    run(session, [rec("2")])                                   # nothing known about it
    other = listing(session, 2)
    assert other.area_sqm is None and other.rooms_count is None and other.floor is None
    run(session, [rec("1")])                                   # later scrape lost the attributes
    row = listing(session, 1)
    assert (row.area_sqm, row.rooms_count, row.floor, row.total_floors) == (55.0, 2, 0, 9)  # 0 is real

# ---- staleness policy ------------------------------------------------------------------

def four(session):
    run(session, [rec(i) for i in (1, 2, 3, 4)])

def test_deactivated_only_after_two_complete_runs_and_reactivated_when_seen(session):
    four(session)
    r2 = run(session, [rec(i) for i in (1, 2, 3)])
    row = listing(session, 4)
    assert row.is_active and row.consecutive_misses == 1 and r2.listings_deactivated == 0
    r3 = run(session, [rec(i) for i in (1, 2, 3)])
    row = listing(session, 4)
    assert not row.is_active and row.deactivated_at is not None and r3.listings_deactivated == 1
    run(session, [rec(i) for i in (1, 2, 3, 4)])
    row = listing(session, 4)
    assert row.is_active and row.deactivated_at is None and row.consecutive_misses == 0
    assert session.query(Listing).count() == 4                 # inactive rows are kept, never deleted

def test_partial_runs_never_count_as_misses(session):
    four(session)
    run(session, [rec(i) for i in (1, 2, 3)])                  # complete: 4 -> 1 miss
    for _ in range(3):
        r = run(session, [rec(1)], complete=False)             # capped / page failed
        assert r.status == "partial" and not r.is_complete
    row = listing(session, 4)
    assert row.is_active and row.consecutive_misses == 1

def test_collection_failure_is_not_inactivity(session):
    four(session)
    for _ in range(3):
        run(session, [rec(i) for i in (1, 2, 3)], seen={"1", "2", "3", "4"})
    row = listing(session, 4)
    assert row.is_active and row.consecutive_misses == 0

def test_failed_run_deactivates_nothing(session):
    four(session)
    r = start_run(session, "list.am", {})
    finish_run(session, r, error="boom", crawl_complete=True)
    assert r.status == "failed" and r.listings_deactivated == 0
    assert session.query(Listing).filter_by(is_active=True).count() == 4


def test_suspicious_complete_run_is_blocked_by_the_guard(session):
    four(session)
    for _ in range(3):
        r = run(session, [rec(1)])                             
        assert r.status == "partial" and "suspicious" in (r.notes or "")
    assert session.query(Listing).filter_by(is_active=True).count() == 4


def test_staleness_is_scoped_to_the_source(session):
    four(session)
    run(session, [rec("1")], source="other-site")
    for _ in range(3):
        run(session, [rec("1")], source="other-site")
    assert session.query(Listing).filter_by(source="list.am", is_active=True).count() == 4


def test_run_summary_is_recorded(session):
    r = run(session, [rec("1"), rec("2", price=-5)])
    row = session.get(IngestionRun, r.id)
    assert (row.status, row.is_complete, row.listings_saved, row.listings_quarantined) == ("success", True, 1, 1)
    assert row.finished_at is not None


# ---- duplicate grouping + seed data ----------------------------------------------------

def load_seed():
    return json.loads(SEED.read_text(encoding="utf-8"))


def test_seed_grouping_merges_only_the_true_duplicate(session):
    run(session, load_seed(), source="synthetic", complete=None)
    pid = {l.external_id: l.property_id for l in session.query(Listing).all()}
    assert pid["S-1001"] == pid["S-1002"]                      # same flat advertised twice
    others = [pid[k] for k in ("S-1003", "S-1004", "S-1005", "S-1006")]
    assert len(set(others + [pid["S-1001"]])) == 5             # different floor / size / unknown stay apart
    assert session.query(Property).count() == 5 and session.query(Listing).count() == 6


def test_seed_import_is_repeatable(session):
    for _ in range(2):
        run(session, load_seed(), source="synthetic", complete=None)
    assert counts(session) == (5, 6, 6)
    row = listing(session, "S-1005", source="synthetic")
    assert row.price_amd == 300_000.0                          # 10,000 AMD/day -> monthly
    assert listing(session, "S-1006", source="synthetic").area_sqm is None
