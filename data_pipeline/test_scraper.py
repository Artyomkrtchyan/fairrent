import httpx
import pytest
from .normalizer import normalize_price
from .scraper import ListingPipeline

def good(**over):
    item = {"id": "1", "price": 600, "currency": "USD", "period": "month", "lat": 40.18, "lon": 44.51}
    item.update(over)
    return item


@pytest.fixture
def pipeline():
    p = ListingPipeline(delay=0)
    yield p
    p.close()


def test_valid_record_passes_and_is_typed(pipeline):
    out = pipeline.parse_and_validate_record(good())
    assert out["lat"] == 40.18 and out["lon"] == 44.51
    assert not pipeline.quarantine_log


def test_string_price_is_converted_and_normalizes(pipeline):
    out = pipeline.parse_and_validate_record(good(price="600"))
    assert out["price"] == 600.0 and isinstance(out["price"], float)
    normalize_price(out["price"], out["currency"], out["period"])  # no TypeError


def test_zero_coordinates_are_valid(pipeline):
    assert pipeline.parse_and_validate_record(good(lat=0, lon=0)) is not None


@pytest.mark.parametrize("override", [
    {"lon": None}, {"lat": None},
    {"lat": 91}, {"lat": -90.5}, {"lon": 180.1}, {"lon": -181},
    {"lat": "abc"}, {"lon": "x"}, {"lat": True}, {"lat": float("nan")}, {"lon": float("inf")},
    {"price": -5}, {"price": 0}, {"price": "abc"}, {"price": None},
    {"id": None}, {"id": ""},
    {"currency": "GBP"}, {"currency": None}, {"period": "fortnight"},
])
def test_invalid_records_are_quarantined(pipeline, override):
    item = good(**override)
    assert pipeline.parse_and_validate_record(item) is None
    assert len(pipeline.quarantine_log) == 1


def test_missing_longitude_key_is_quarantined(pipeline):
    item = good()
    del item["lon"]
    assert pipeline.parse_and_validate_record(item) is None


# ---- collection against a mocked, project-owned server (no external traffic) ----

BASE = "http://fairrent.test/category/56"


def _handler(requests_seen):
    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        path = request.url.path
        if path == "/category/56":
            page = request.url.params.get("pg", "1")
            links = {"1": [1, 2], "2": [2, 3]}.get(page, [])
            return httpx.Response(200, text="".join(f'<a href="/item/{i}">x</a>' for i in links))
        if path == "/item/2":
            return httpx.Response(404)
        n = path.rsplit("/", 1)[1]
        return httpx.Response(200, text=(
            f'<h1 class="pTitle">Flat {n}</h1><span class="pPrice">$600</span>'
            '<div class="pattr">55 sq. m.</div><div data-lat="40.18" data-lng="44.51"></div>'
        ))
    return handler


def _pipeline(seen):
    client = httpx.Client(transport=httpx.MockTransport(_handler(seen)))
    return ListingPipeline(client=client, delay=0)


def test_collect_respects_pages_and_dedupes():
    seen = []
    items = list(_pipeline(seen).collect(BASE, pages=2))
    assert [i["id"] for i in items] == ["1", "3"]          # item 2 -> 404 -> skipped
    assert any("pg=2" in u for u in seen)
    first = items[0]
    assert (first["lat"], first["lon"], first["currency"]) == (40.18, 44.51, "USD")


def test_collect_single_page_does_not_request_page_two():
    seen = []
    list(_pipeline(seen).collect(BASE, pages=1))
    assert not any("pg=2" in u for u in seen)


def test_failed_listing_fetch_is_quarantined():
    seen = []
    p = _pipeline(seen)
    list(p.collect(BASE, pages=1))
    assert len(p.quarantine_log) == 1
    assert "item/2" in p.quarantine_log[0]["raw_data"]["url"]


def test_max_listings():
    items = list(_pipeline([]).collect(BASE, pages=2, max_listings=1))
    assert len(items) == 1


# ---- optional fields: unknown stays None, real values survive -------------------

def test_optional_fields_unknown_is_none_not_zero(pipeline):
    out = pipeline.parse_and_validate_record(good(area_sqm=0, rooms_count=0, building_type="unknown", title=""))
    assert out["area_sqm"] is None and out["rooms_count"] is None
    assert out["building_type"] is None and out["title"] is None
    assert {"area_sqm", "rooms_count", "building_type", "title"} <= set(out["missing_fields"])


def test_known_optional_values_are_kept(pipeline):
    out = pipeline.parse_and_validate_record(good(area_sqm="55.5", rooms_count="2", floor=0, total_floors=9))
    assert (out["area_sqm"], out["rooms_count"], out["floor"], out["total_floors"]) == (55.5, 2, 0, 9)
    assert "floor" not in out["missing_fields"]            # ground floor 0 is a real value


def test_contradictory_floor_becomes_unknown(pipeline):
    out = pipeline.parse_and_validate_record(good(floor=12, total_floors=9))
    assert out["floor"] is None and out["total_floors"] is None


# ---- crawl completeness (drives the staleness policy) ---------------------------

def test_crawl_complete_only_when_pagination_ends():
    p = _pipeline([])
    list(p.collect(BASE, pages=3))                         # page 3 is empty -> end reached
    assert p.reached_end and p.crawl_complete
    assert p.seen_ids == {"1", "2", "3"}                   # item 2 was seen although its fetch 404s
    assert p.detail_failures == 1


def test_crawl_capped_by_pages_is_not_complete():
    p = _pipeline([])
    list(p.collect(BASE, pages=2))                         # cap hit before an empty page
    assert not p.reached_end and not p.crawl_complete


def test_crawl_capped_by_max_listings_is_not_complete():
    p = _pipeline([])
    list(p.collect(BASE, pages=3, max_listings=1))
    assert p.capped and not p.crawl_complete


def test_index_page_failure_makes_crawl_incomplete():
    def handler(request):
        if request.url.params.get("pg") == "2":
            return httpx.Response(404)
        if request.url.path == "/category/56":
            return httpx.Response(200, text='<a href="/item/1">x</a>' if request.url.params.get("pg") is None else "")
        return httpx.Response(200, text='<span class="pPrice">$1</span>')
    p = ListingPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)
    list(p.collect(BASE, pages=3))
    assert p.index_failures == 1 and not p.crawl_complete


def test_empty_first_page_is_not_a_complete_crawl():
    p = ListingPipeline(client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text="<html>blocked</html>"))), delay=0)
    list(p.collect(BASE, pages=3))
    assert not p.crawl_complete


def test_unfinished_generator_is_not_complete():
    p = _pipeline([])
    next(p.collect(BASE, pages=3))                         # consumer stops early
    assert not p.crawl_complete
