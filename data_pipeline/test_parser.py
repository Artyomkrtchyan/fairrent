from .parser import parse_listing_html

def test_parse_listing_html():
    sample_html = """
    <html>
        <body>
            <h1 class="pTitle">2-room apartment in Arabkir</h1>
            <span class="pPrice">$600</span>
            <div class="pattr">55 sq. m.</div>
            <div class="pDesc">Nice view, fully furnished.</div>
            <div id="map" data-lat="40.19" data-lng="44.53"></div>
        </body>
    </html>
    """
    result = parse_listing_html(sample_html, external_id="test_123")

    assert result["external_id"] == "test_123"
    assert result["title"] == "2-room apartment in Arabkir"
    assert result["price_usd"] == 600.0
    assert result["area_sqm"] == 55.0
    assert (result["price"], result["currency"], result["period"]) == (600.0, "USD", "month")
    assert (result["lat"], result["lon"]) == (40.19, 44.53)
    assert result["coordinate_source"] == "list.am:data-lat-data-lng"
    assert result["coordinate_confidence"] == "approximate"


def test_parser_leaves_unknown_fields_as_none():
    r = parse_listing_html("<html><h1 class='pTitle'>x</h1></html>", external_id="1")
    assert r["area_sqm"] is None and r["rooms_count"] is None and r["floor"] is None
    assert r["price"] is None and r["lat"] is None and r["building_type"] is None
    assert r["coordinate_source"] is None and r["coordinate_confidence"] == "unknown"


def test_parser_accepts_only_explicit_official_district_fields():
    explicit = parse_listing_html(
        '<meta itemprop="addressLocality" content="Արաբկիր">', external_id="district-1")
    assert explicit["district"] == "Arabkir"
    assert explicit["district_source"] == "list.am:structured-address"
    title_only = parse_listing_html('<h1>Apartment in Kentron</h1>', external_id="district-2")
    assert title_only["district"] is None
    assert title_only["district_source"] is None


def test_parser_keeps_explicit_address_and_page_image_but_does_not_guess_from_title():
    parsed = parse_listing_html(
        '<h1>Apartment on Example Street in Kentron</h1>'
        '<meta itemprop="streetAddress" content="Example Street 12">'
        '<meta property="og:image" content="https://images.example.invalid/listing-1.jpg">',
        external_id="metadata-1",
    )
    assert parsed["address_raw"] == "Example Street 12"
    assert parsed["images"] == ["https://images.example.invalid/listing-1.jpg"]
    assert parsed["district"] is None


def test_parser_leaves_address_and_images_unknown_without_explicit_metadata():
    parsed = parse_listing_html("<h1>Apartment on Example Street in Kentron</h1>", "metadata-2")
    assert parsed["address_raw"] is None
    assert parsed["images"] == []
    assert parsed["district"] is None


def test_parser_reads_floor_rooms_and_daily_price():
    html = """
    <span class="pPrice">10,000 AMD / day</span>
    <div class="pattr">Floor: 5/9</div><div class="pattr">Rooms: 2</div><div class="pattr">Area: 55.5 sq.m.</div>
    """
    r = parse_listing_html(html, external_id="2")
    assert (r["floor"], r["total_floors"], r["rooms_count"], r["area_sqm"]) == (5, 9, 2, 55.5)
    assert (r["price"], r["currency"], r["period"]) == (10000.0, "AMD", "day")


def test_parser_does_not_truncate_fractional_rooms():
    r = parse_listing_html('<div class="pattr">Rooms: 2.5</div><div class="pattr">Floor: 3.5</div>', "9")
    assert r["rooms_count"] == 2.5 and r["floor"] == 3.5     # validation then marks them unknown
    r = parse_listing_html('<div class="pattr">Rooms: 2</div>', "9")
    assert r["rooms_count"] == 2 and isinstance(r["rooms_count"], int)
