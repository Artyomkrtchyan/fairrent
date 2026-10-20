from parser import parse_listing_html

def test_parse_listing_html():
    sample_html = """
    <html>
        <body>
            <h1 class="pTitle">2-room apartment in Arabkir</h1>
            <span class="pPrice">$600</span>
            <div class="pattr">55 sq. m.</div>
            <div class="pDesc">Nice view, fully furnished.</div>
        </body>
    </html>
    """
    result = parse_listing_html(sample_html, external_id="test_123")

    assert result["external_id"] == "test_123"
    assert result["title"] == "2-room apartment in Arabkir"
    assert result["price_usd"] == 600.0
    assert result["area_sqm"] == 55.0