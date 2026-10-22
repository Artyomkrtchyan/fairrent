import json
import os
from pathlib import Path
import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from database.models import Base, IngestionRun, Listing, PriceObservation, Property
from database.alembic_filters import make_include_hooks
from . import ingestion, queries
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
    # 4 is listed on the index (seen) but its detail page failed, so no record is ingested.
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
        r = run(session, [rec(1)])                             # "complete" but saw 1 of 4 (25%)
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


# =====================================================================================
# Review round 2 regressions
# =====================================================================================

def xy(session, property_id):
    session.expire_all()
    return session.execute(select(func.ST_X(Property.geom), func.ST_Y(Property.geom))
                           .where(Property.id == property_id)).one()


def flat(item_id, **extra):
    """A flat with full attributes so that grouping can apply."""
    base = dict(area_sqm=55, rooms_count=2, floor=5, total_floors=9,
                lat=40.1792, lon=44.5151, district="Kentron")
    base.update(extra)
    return rec(item_id, **base)


# ---- item 1: blocked pages must not deactivate anything (full pipeline over a mock server) ----

SITE = "http://fairrent.test/category/56"


def _catalogue(ids):
    return ('<html><title>Rentals</title><body><div class="dl" id="listings">'
            + "".join(f'<a href="/item/{i}">x</a>' for i in ids) + "</div></body></html>")


def _handler(page1_ids, page2):
    def handler(request):
        path = request.url.path
        if path == "/category/56":
            return httpx.Response(200, text=_catalogue(page1_ids) if request.url.params.get("pg") is None else page2)
        n = path.rsplit("/", 1)[1]
        return httpx.Response(200, text=(
            f'<h1 class="pTitle">Flat {n}</h1><span class="pPrice">$600</span>'
            f'<div data-lat="40.1{n}" data-lng="44.51"></div>'))
    return handler


def crawl(session, handler):
    """The same sequence the CLI runs: collect -> ingest -> finish_run(crawl state)."""
    pipeline = ListingPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)
    r = start_run(session, "list.am", {})
    saved = ingest(pipeline.collect(SITE, 5), pipeline, session, "list.am", run_id=r.id)
    finish_run(session, r, seen_ids=pipeline.seen_ids, crawl_complete=pipeline.crawl_complete,
               stats={"listings_seen": len(pipeline.seen_ids), "listings_saved": saved,
                      "listings_quarantined": len(pipeline.quarantine_log)})
    return r


@pytest.mark.parametrize("blocked_page", [
    "<html><title>Just a moment...</title><body>Please complete the CAPTCHA</body></html>",
    "<html><title>403</title><body><h1>Access denied</h1></body></html>",
])
def test_blocked_page_two_never_deactivates_listings(session, blocked_page):
    first = crawl(session, _handler([1, 2, 3, 4], _catalogue([])))       # genuine, complete crawl
    assert first.status == "success" and first.is_complete
    assert session.query(Listing).filter_by(is_active=True).count() == 4

    for _ in range(3):                      # page 1 shows only 2 of 4 (passes the 50% guard), page 2 is blocked
        r = crawl(session, _handler([1, 2], blocked_page))
        assert r.status == "partial" and not r.is_complete and r.listings_deactivated == 0
    session.expire_all()
    assert session.query(Listing).filter_by(is_active=True).count() == 4
    assert {l.consecutive_misses for l in session.query(Listing)} == {0}


def test_genuine_end_of_catalogue_still_deactivates_after_two_complete_runs(session):
    crawl(session, _handler([1, 2, 3, 4], _catalogue([])))
    crawl(session, _handler([1, 2, 3], _catalogue([])))
    r = crawl(session, _handler([1, 2, 3], _catalogue([])))
    assert r.is_complete and r.listings_deactivated == 1
    assert listing(session, 4).is_active is False


# ---- item 2: coordinate corrections ------------------------------------------------------------

def test_corrected_coordinates_move_an_exclusive_property(session):
    run(session, [flat("A", lat=40.10, lon=44.50)])
    pid = listing(session, "A").property_id
    run(session, [flat("A", lat=40.20, lon=44.60)])
    assert listing(session, "A").property_id == pid and session.query(Property).count() == 1
    assert xy(session, pid) == pytest.approx((44.60, 40.20))
    assert session.query(PriceObservation).count() == 1               # not a price change


def test_tiny_coordinate_noise_does_not_touch_the_property(session):
    run(session, [flat("A", lat=40.10000, lon=44.50000)])
    pid = listing(session, "A").property_id
    run(session, [flat("A", lat=40.100001, lon=44.500001)])           # ~0.1 m
    assert xy(session, pid) == pytest.approx((44.50, 40.10), abs=1e-7)


def test_shared_property_is_not_moved_when_one_listing_is_corrected(session):
    run(session, [flat("A"), flat("B", lat=40.17924, lon=44.51512)])  # same flat, advertised twice
    shared = listing(session, "A").property_id
    assert listing(session, "B").property_id == shared
    before = xy(session, shared)

    run(session, [flat("B", lat=40.2500, lon=44.6000)])               # B's coordinates were wrong
    a, b = listing(session, "A"), listing(session, "B")
    assert a.property_id == shared and b.property_id != shared        # A stays, B gets its own place
    assert xy(session, shared) == pytest.approx(before)               # shared property did not move
    assert xy(session, b.property_id) == pytest.approx((44.6000, 40.2500))
    assert session.query(Property).count() == 2


def test_small_correction_inside_a_shared_property_keeps_the_association(session):
    run(session, [flat("A"), flat("B", lat=40.17924, lon=44.51512)])
    shared = listing(session, "A").property_id
    before = xy(session, shared)
    run(session, [flat("B", lat=40.17926, lon=44.51514)])             # a few metres
    assert listing(session, "B").property_id == shared and xy(session, shared) == pytest.approx(before)


def test_corrected_coordinates_that_match_another_flat_join_it_without_moving_it(session):
    run(session, [flat("A"), flat("B", lat=40.3000, lon=44.7000)])    # B was wrongly placed far away
    pa, pb = listing(session, "A").property_id, listing(session, "B").property_id
    assert pa != pb
    before_a = xy(session, pa)
    run(session, [flat("B", lat=40.17923, lon=44.51511)])             # corrected: it IS flat A
    assert listing(session, "B").property_id == pa
    assert listing(session, "A").property_id == pa and xy(session, pa) == pytest.approx(before_a)


def test_missing_coordinates_later_do_not_erase_a_known_position(session):
    run(session, [flat("A", lat=40.10, lon=44.50)])
    pid = listing(session, "A").property_id
    run(session, [flat("A", lat=None, lon=None)])
    assert listing(session, "A").property_id == pid and xy(session, pid) == pytest.approx((44.50, 40.10))


def test_geographic_provenance_is_persisted_with_the_property(session):
    record = flat("geo-1", lat=40.18592, lon=44.51963, district="Արաբկիր",
                  coordinate_source="list.am:data-lat-data-lng",
                  coordinate_confidence="approximate", district_source="list.am:structured-address")
    run(session, [record])
    prop = session.get(Property, listing(session, "geo-1").property_id)
    assert prop.district == "Արաբկիր"
    assert prop.district_source == "list.am:structured-address"
    assert prop.coordinate_source == "list.am:data-lat-data-lng"
    assert prop.coordinate_confidence == "approximate"


# ---- item 3: listings without coordinates --------------------------------------------------------

def test_listing_without_coordinates_is_stored_searchable_but_not_on_the_map(session):
    run(session, [rec("1", lat=None, lon=None, district="Kentron", area_sqm=40, rooms_count=1, floor=2),
                  rec("2")])
    nocoord = listing(session, 1)
    prop = session.get(Property, nocoord.property_id)
    assert prop.geom is None and prop.district == "Kentron"           # property kept, position unknown
    assert nocoord.raw_data["missing_fields"].count("coordinates") == 1

    everything = {l.external_id for l in session.query(Listing)}      # search / detail path
    on_map = {l.external_id for l in queries.map_listings(session)}   # map path
    assert everything == {"1", "2"} and on_map == {"2"}


def test_listings_without_coordinates_are_never_grouped(session):
    same = dict(lat=None, lon=None, area_sqm=55, rooms_count=2, floor=5)
    run(session, [rec("1", **same), rec("2", **same)])
    assert listing(session, 1).property_id != listing(session, 2).property_id
    assert session.query(Property).count() == 2


def test_coordinates_arriving_later_complete_the_same_property(session):
    run(session, [rec("1", lat=None, lon=None)])
    pid = listing(session, 1).property_id
    run(session, [rec("1", lat=40.11, lon=44.55)])
    assert listing(session, 1).property_id == pid and session.query(Property).count() == 1
    assert xy(session, pid) == pytest.approx((44.55, 40.11))
    assert {l.external_id for l in queries.map_listings(session)} == {"1"}


def test_repeated_ingestion_of_a_listing_without_coordinates_is_idempotent(session):
    for _ in range(3):
        run(session, [rec("1", lat=None, lon=None)])
    assert counts(session) == (1, 1, 1)


# ---- item 4 (storage side): non-integral values are stored as unknown, never truncated -----------

def test_fractional_rooms_are_stored_as_null_not_truncated(session):
    run(session, [rec("1", rooms_count=2.9, floor=3.5)])
    row = listing(session, 1)
    assert row.rooms_count is None and row.floor is None
    assert row.raw_data["rejected_fields"] == {"rooms_count": 2.9, "floor": 3.5}

def test_rate_source_and_date_are_stored_separately_from_conversion_time(session):
    run(session, [rec("1", price=10_000, currency="AMD", period="day")])
    row = listing(session, 1)
    obs = session.query(PriceObservation).one()
    for record in (row, obs):
        assert record.rate_source == "static-config" and record.rate_date is not None
        assert record.exchange_rate == 385.0 and record.exchange_rate_at is not None
    assert row.rate_date.isoformat() == "2026-10-21"                  # effective date (config)
    assert not hasattr(row.rate_date, "hour")                         # a DATE, not a timestamp


def test_autogenerate_ignores_extension_owned_tables_and_schemas(session):
    engine = session.get_bind()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE ext_owned_junk (id int PRIMARY KEY)"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS fake_tiger"))
        conn.execute(text("CREATE TABLE fake_tiger.county (id int)"))
    try:
        include_name, include_object = make_include_hooks(Base.metadata)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={
                "target_metadata": Base.metadata, "include_schemas": True,
                "include_name": include_name, "include_object": include_object})
            assert compare_metadata(ctx, Base.metadata) == []
        with engine.connect() as conn:                                # sanity: unfiltered, they show up
            ctx = MigrationContext.configure(conn, opts={"target_metadata": Base.metadata})
            assert any(d[0] == "remove_table" for d in compare_metadata(ctx, Base.metadata))
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS ext_owned_junk"))
            conn.execute(text("DROP SCHEMA IF EXISTS fake_tiger CASCADE"))
