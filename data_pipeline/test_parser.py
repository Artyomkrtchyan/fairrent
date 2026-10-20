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


def test_parser_leaves_unknown_fields_as_none():
    r = parse_listing_html("<html><h1 class='pTitle'>x</h1></html>", external_id="1")
    assert r["area_sqm"] is None and r["rooms_count"] is None and r["floor"] is None
    assert r["price"] is None and r["lat"] is None and r["building_type"] is None


def test_parser_reads_floor_rooms_and_daily_price():
    html = """
    <span class="pPrice">10,000 AMD / day</span>
    <div class="pattr">Floor: 5/9</div><div class="pattr">Rooms: 2</div><div class="pattr">Area: 55.5 sq.m.</div>
    """
    r = parse_listing_html(html, external_id="2")
    assert (r["floor"], r["total_floors"], r["rooms_count"], r["area_sqm"]) == (5, 9, 2, 55.5)
    assert (r["price"], r["currency"], r["period"]) == (10000.0, "AMD", "day")
