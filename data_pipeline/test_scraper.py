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


def catalogue(ids):
    """A genuine catalogue page; with no ids it is the genuine (empty) page after the last one."""
    return ('<html><title>Rentals</title><body><div class="dl" id="listings">'
            + "".join(f'<a href="/item/{i}">x</a>' for i in ids) + "</div></body></html>")


CAPTCHA = "<html><title>Just a moment...</title><body><h1>Please complete the CAPTCHA</h1></body></html>"
DENIED = "<html><title>403</title><body><h1>Access denied</h1></body></html>"


def _handler(requests_seen):
    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        path = request.url.path
        if path == "/category/56":
            page = request.url.params.get("pg", "1")
            links = {"1": [1, 2], "2": [2, 3]}.get(page, [])
            return httpx.Response(200, text=catalogue(links))
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
            return httpx.Response(200, text=catalogue([1] if request.url.params.get("pg") is None else []))
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


# ---- review item 1: blocked / unrecognised pages must never look like "end of pagination" -------

def _site(page2, page3=None):
    """Page 1 is a genuine catalogue; `page2`/`page3` are what the server returns for them."""
    pages = {"1": catalogue([1, 2]), "2": page2, "3": page3 if page3 is not None else catalogue([])}

    def handler(request):
        if request.url.path == "/category/56":
            return httpx.Response(200, text=pages[request.url.params.get("pg", "1")])
        return httpx.Response(200, text='<span class="pPrice">$1</span>')
    return ListingPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)


@pytest.mark.parametrize("blocked", [CAPTCHA, DENIED, "", "<html><body>maintenance</body></html>"])
def test_blocked_or_unrecognised_page_is_not_the_end_of_pagination(blocked):
    p = _site(blocked)
    list(p.collect(BASE, pages=5))
    assert not p.reached_end and p.index_failures == 1 and not p.crawl_complete
    assert any("not a recognizable catalogue page" in q["error"] for q in p.quarantine_log)


def test_captcha_page_that_contains_the_catalogue_container_is_still_blocked():
    sneaky = '<html><body>Please complete the CAPTCHA<div class="dl" id="listings"></div></body></html>'
    p = _site(sneaky)
    list(p.collect(BASE, pages=5))
    assert not p.crawl_complete


def test_genuine_empty_catalogue_page_still_ends_the_crawl():
    p = _site(catalogue([]))
    list(p.collect(BASE, pages=5))
    assert p.reached_end and p.crawl_complete


def test_end_cannot_be_verified_without_a_distinctive_container_on_page_1():
    bare = '<a href="/item/1">x</a>'            # no id/class anywhere around the links
    pages = {"1": bare, "2": "<html><body></body></html>"}

    def handler(request):
        if request.url.path == "/category/56":
            return httpx.Response(200, text=pages[request.url.params.get("pg", "1")])
        return httpx.Response(200, text='<span class="pPrice">$1</span>')
    p = ListingPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), delay=0)
    list(p.collect(BASE, pages=5))
    assert not p.crawl_complete                  # unverifiable end => never trusted


# ---- review item 3: coordinates are optional (both or neither) ---------------------------------

def test_listing_without_coordinates_is_accepted(pipeline):
    out = pipeline.parse_and_validate_record(good(lat=None, lon=None))
    assert out is not None and out["lat"] is None and out["lon"] is None
    assert "coordinates" in out["missing_fields"]
    assert not pipeline.quarantine_log


def test_blank_coordinates_count_as_missing(pipeline):
    out = pipeline.parse_and_validate_record(good(lat="", lon="  "))
    assert out is not None and out["lat"] is None


def test_coordinates_keys_absent_entirely_is_accepted(pipeline):
    item = good()
    del item["lat"], item["lon"]
    assert pipeline.parse_and_validate_record(item) is not None


@pytest.mark.parametrize("override", [{"lat": 40.1, "lon": None}, {"lat": None, "lon": 44.5},
                                      {"lat": "", "lon": 44.5}])
def test_only_one_coordinate_is_rejected(pipeline, override):
    assert pipeline.parse_and_validate_record(good(**override)) is None
    assert "both" in pipeline.quarantine_log[0]["error"]


def test_present_but_invalid_coordinates_are_still_rejected(pipeline):
    assert pipeline.parse_and_validate_record(good(lat=95, lon=44.5)) is None
    assert pipeline.parse_and_validate_record(good(lat="x", lon="y")) is None


def test_coordinates_present_have_no_coordinates_marker(pipeline):
    assert "coordinates" not in pipeline.parse_and_validate_record(good())["missing_fields"]


# ---- review item 4: integer fields are never truncated -----------------------------------------

@pytest.mark.parametrize("field,value", [("rooms_count", 2.9), ("rooms_count", "2.5"), ("floor", 3.5),
                                         ("total_floors", "9.1")])
def test_non_integral_integer_fields_become_unknown_not_truncated(pipeline, field, value):
    out = pipeline.parse_and_validate_record(good(**{field: value}))
    assert out is not None and out[field] is None
    assert out["rejected_fields"][field] == value         # kept for traceability
    assert field in out["missing_fields"]


@pytest.mark.parametrize("value", [2, 2.0, "2", "2.0"])
def test_integral_values_are_accepted_as_ints(pipeline, value):
    out = pipeline.parse_and_validate_record(good(rooms_count=value))
    assert out["rooms_count"] == 2 and isinstance(out["rooms_count"], int)
    assert out["rejected_fields"] == {}


def test_area_stays_fractional(pipeline):
    assert pipeline.parse_and_validate_record(good(area_sqm="55.5"))["area_sqm"] == 55.5