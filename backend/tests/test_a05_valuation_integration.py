"""HTTP scrape -> A05/PostGIS -> publication -> C04/B03 -> saved estimate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from backend.main import app
from backend.tests.test_listing_postgres import database, client, validate_contract
from backend.tests.test_pipeline_integration import source_session, publish
from backend.valuation_gateway import BaselineGateway
from backend.valuation_routes import service
from backend.valuation_service import ValuationService
from data_pipeline.cli import ingest
from data_pipeline.geography import GEOGRAPHY_VERSION
from data_pipeline.ingestion import start_run, finish_run
from data_pipeline.scraper import ListingPipeline
from database.models import Listing


def test_a05_source_features_reach_valuation_and_audit(database, source_session, client, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('VALUATION_COVERAGE_FILE', str(root / 'infra/valuation-coverage/coverage.geojson'))
    monkeypatch.setenv('VALUATION_DISTRICTS_FILE', str(root / 'infra/valuation-coverage/districts.geojson'))
    def respond(request):
        if request.url.path == '/category/56':
            links = '' if 'pg' in request.url.params else ''.join(f'<a href="/item/{i}">Flat</a>' for i in (1,2,3))
            return httpx.Response(200, text=f'<div id="listings">{links}</div>')
        item_id = int(request.url.path.rsplit('/', 1)[1])
        return httpx.Response(200, text=(
            f'<h1 class="pTitle">Synthetic A05 flat {item_id}</h1><span class="pPrice">${400+100*item_id}</span>'
            '<div data-lat="40.18592" data-lng="44.51963" data-district="Կենտրոն"></div>'
            '<div class="pattr">Area 50 sq</div><div class="pattr">Rooms 2</div>'))
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        pipeline = ListingPipeline(client=transport, delay=0)
        run = start_run(source_session, 'list.am')
        count = ingest(pipeline.collect('http://fairrent.test/category/56', 2), pipeline,
                       source_session, 'list.am', run_id=run.id)
        finish_run(source_session, run, seen_ids=pipeline.seen_ids, crawl_complete=pipeline.crawl_complete,
                   stats={'listings_saved': count})
    assert count == 3 and run.is_complete
    prop = source_session.query(Listing).filter_by(external_id='1').one().property
    assert prop.district_id == 'kentron'
    assert prop.district_source == 'list.am:data-district'
    assert prop.coordinate_confidence == 'approximate'
    assert prop.coordinate_source == 'list.am:data-lat-data-lng'
    assert prop.distance_metro_m == 0 and prop.geography_version == GEOGRAPHY_VERSION
    assert publish(database)['published'] == 3
    catalogue = client.get('/api/v1/listings?district_id=kentron').json()
    assert catalogue['total'] == 3
    assert all(item['coordinate_confidence'] == 'approximate' for item in catalogue['items'])
    with database() as connection:
        connection.execute((root / 'backend/sql/002_valuation_estimates.sql').read_text(encoding='utf-8'))
    seen = {}
    class Provider(BaselineGateway):
        def assess(self, payload, **kwargs):
            seen.update(payload=payload, distances=self.snapshot['distance_metro_m'].tolist())
            return super().assess(payload, **kwargs)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    app.dependency_overrides[service] = lambda: ValuationService(provider=Provider, clock=lambda: now)
    try:
        response = client.post('/api/v1/valuations', json=dict(latitude=40.18592, longitude=44.51963,
            area_sqm=50, rooms=2, asking_price_usd_month=650))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    result = response.json()
    validate_contract(result, 'ValuationResponse')
    assert result['valuation_assessment']['estimated_price_usd'] == 600
    assert result['observed_market_statistics']['comparables_count'] == 3
    assert seen['payload']['district'] == 'Kentron'
    assert seen['payload']['distance_metro_m'] == 0
    assert seen['payload']['distance_center_m'] == prop.distance_center_m
    assert seen['payload']['distance_university_m'] == prop.distance_university_m
    assert 'asking_price_usd_month' not in seen['payload']
    assert seen['distances'] == [0, 0, 0]
    with database() as connection:
        saved = connection.execute('SELECT coverage_version, response_document FROM api_valuation_estimates').fetchone()
    assert ';a05=' + GEOGRAPHY_VERSION in saved[0] and ';districts=' in saved[0]
    assert saved[1] == result
